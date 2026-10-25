"""Zotero process and SQLite lock diagnostics.

Zotero keeps an exclusive lock on its database while running, so write
operations from Annota must wait until the desktop application is closed.
These helpers make failures explicit instead of letting SQLite time out with a
generic "database is locked" error.
"""

from __future__ import annotations

import csv
import io
import platform
import sqlite3
import subprocess
import time
from pathlib import Path

from .config import ZOTERO_DB_PATH

_PROCESS_CACHE_TTL = 2.0
_process_cache: tuple[float, list[dict]] = (0.0, [])


class ZoteroBusyError(sqlite3.OperationalError):
    """Raised when a write is attempted while Zotero holds the database lock."""


def find_zotero_processes(refresh: bool = False) -> list[dict]:
    """Return running Zotero processes as ``{pid, name}`` dictionaries."""
    global _process_cache
    now = time.monotonic()
    cached_at, cached = _process_cache
    if not refresh and cached_at and now - cached_at < _PROCESS_CACHE_TTL:
        return list(cached)

    system = platform.system()
    processes: list[dict] = []
    try:
        if system == "Windows":
            completed = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for row in csv.reader(io.StringIO(completed.stdout)):
                if len(row) >= 2 and "zotero" in row[0].casefold():
                    processes.append({"pid": row[1], "name": row[0]})
        else:
            completed = subprocess.run(
                ["ps", "-A", "-o", "pid=,comm="],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for line in completed.stdout.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and "zotero" in parts[1].casefold():
                    processes.append({"pid": parts[0], "name": parts[1]})
    except (OSError, subprocess.SubprocessError):
        pass

    _process_cache = (now, processes)
    return list(processes)


def probe_database(timeout: float = 1.0) -> dict:
    """Probe the Zotero database for existence and write availability."""
    path = Path(ZOTERO_DB_PATH)
    result = {
        "path": str(path),
        "exists": path.exists(),
        "writable": False,
        "error": None,
    }
    if not result["exists"]:
        return result

    conn = None
    try:
        conn = sqlite3.connect(f"file:{path}", uri=True, timeout=timeout)
        conn.execute(f"PRAGMA busy_timeout={max(1, int(timeout * 1000))}")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        result["writable"] = True
    except sqlite3.OperationalError as exc:
        result["error"] = str(exc)
    finally:
        if conn is not None:
            conn.close()
    return result


def get_status(refresh: bool = False) -> dict:
    """Return a structured Zotero availability report with a user hint."""
    processes = find_zotero_processes(refresh=refresh)
    database = probe_database()
    running = bool(processes)

    if not database["exists"]:
        hint = (
            "Zotero database not found. Set ZOTERO_DATA_DIR to the folder that "
            "contains zotero.sqlite."
        )
    elif database["writable"]:
        hint = "Zotero database is writable. Read and write tools are available."
        if running:
            hint = (
                "Zotero is running but the database is currently writable. "
                "Writes may still conflict; close Zotero if a write fails."
            )
    elif running:
        pids = ", ".join(str(process["pid"]) for process in processes)
        hint = (
            f"Zotero is running (pid {pids}) and holds the database lock. "
            "Close Zotero before create/delete/merge operations. Read-only "
            "tools still work through a database snapshot."
        )
    else:
        hint = (
            "The database is locked by another process. Close any program using "
            f"zotero.sqlite and retry. Detail: {database['error']}"
        )

    return {
        "platform": platform.system(),
        "zotero_running": running,
        "processes": processes,
        "database": database,
        "write_ready": database["writable"],
        "hint": hint,
    }


def ensure_write_ready() -> None:
    """Raise a clear error when a write cannot succeed because Zotero is open."""
    processes = find_zotero_processes()
    if not processes:
        return
    database = probe_database(timeout=0.5)
    if database["writable"]:
        return

    pids = ", ".join(str(process["pid"]) for process in processes)
    raise ZoteroBusyError(
        f"Zotero is running (pid {pids}) and the database is locked. "
        "Close Zotero, then retry this write. Read-only tools still work."
    )
