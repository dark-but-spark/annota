"""Annota configuration.

Values are resolved in this order:

1. environment variables
2. ``~/.annota/config.json`` (override with ``ANNOTA_CONFIG_PATH``)
3. built-in defaults

The JSON file may use nested sections (preferred) or legacy flat keys such as
``deepseek_api_key``.  See ``config.example.json`` and ``docs/configuration.md``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _default_zotero_dir() -> str:
    return str(Path.home() / "Zotero")


def _as_bool(value, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


ANNOTA_USER_CONFIG_PATH = Path(
    os.environ.get("ANNOTA_CONFIG_PATH", str(Path.home() / ".annota" / "config.json"))
)


def _load_config_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


_USER_CONFIG = _load_config_file(ANNOTA_USER_CONFIG_PATH)


def _config_value(section: str, key: str):
    section_data = _USER_CONFIG.get(section)
    if isinstance(section_data, dict) and key in section_data:
        return section_data[key]
    return _USER_CONFIG.get(f"{section}_{key}")


def _setting(env_name: str, section: str, key: str, default):
    env_value = os.environ.get(env_name)
    if env_value not in (None, ""):
        return env_value
    file_value = _config_value(section, key)
    if file_value is None or file_value == "":
        return default
    return file_value


def _path_setting(env_name: str, section: str, key: str, default: Path) -> Path:
    value = _setting(env_name, section, key, str(default))
    return Path(os.path.expandvars(os.path.expanduser(str(value))))


# ── Zotero data paths ───────────────────────────────────────────
_zotero_default = Path(_default_zotero_dir())
ZOTERO_DATA_DIR = _path_setting(
    "ZOTERO_DATA_DIR", "zotero", "data_dir", _zotero_default
)
ZOTERO_DB_PATH = _path_setting(
    "ZOTERO_DB_PATH", "zotero", "db_path", ZOTERO_DATA_DIR / "zotero.sqlite"
)
ZOTERO_STORAGE_DIR = _path_setting(
    "ZOTERO_STORAGE_DIR", "zotero", "storage_dir", ZOTERO_DATA_DIR / "storage"
)

# ── Zotero database constants ───────────────────────────────────
LIBRARY_ID = _as_int(
    _setting("ZOTERO_LIBRARY_ID", "zotero", "library_id", 1), 1
)

ITEM_TYPE_ANNOTATION = 1
ITEM_TYPE_ATTACHMENT = 3
ITEM_TYPE_NOTE = 28

ANN_HIGHLIGHT = 1
ANN_NOTE = 2
ANN_IMAGE = 3
ANN_INK = 4
ANN_UNDERLINE = 5
ANN_TEXT = 6

ANN_TYPE_MAP = {
    "highlight": ANN_HIGHLIGHT,
    "note": ANN_NOTE,
    "image": ANN_IMAGE,
    "ink": ANN_INK,
    "underline": ANN_UNDERLINE,
    "text": ANN_TEXT,
}

KEY_CHARSET = "23456789ABCDEFGHIJKLMNPQRSTUVWXYZ"
KEY_LENGTH = 8

DEFAULT_COLOR = "#ffd400"

# ── SQLite connection and retry ─────────────────────────────────
DB_TIMEOUT = _as_float(
    _setting("ANNOTA_DB_TIMEOUT", "database", "timeout", 30), 30
)
DB_RETRY_COUNT = _as_int(
    _setting("ANNOTA_DB_RETRY_COUNT", "database", "retry_count", 3), 3
)
DB_RETRY_BASE_DELAY = _as_float(
    _setting("ANNOTA_DB_RETRY_DELAY", "database", "retry_base_delay", 1), 1
)


# ── Ollama ──────────────────────────────────────────────────────
OLLAMA_BASE_URL = str(
    _setting(
        "OLLAMA_BASE_URL", "ollama", "base_url", "http://127.0.0.1:11434"
    )
).rstrip("/")
OLLAMA_LLM_MODEL = str(
    _setting("OLLAMA_LLM_MODEL", "ollama", "llm_model", "qwen2.5:7b")
)
OLLAMA_LLM_FALLBACK_MODEL = str(
    _setting(
        "OLLAMA_LLM_FALLBACK_MODEL",
        "ollama",
        "fallback_model",
        "deepseek-r1:1.5b",
    )
)
OLLAMA_EMBED_MODEL = str(
    _setting("OLLAMA_EMBED_MODEL", "ollama", "embed_model", "")
)
OLLAMA_TIMEOUT = _as_float(
    _setting("OLLAMA_TIMEOUT", "ollama", "timeout", 90), 90
)
OLLAMA_AUTO_START = _as_bool(
    _setting("OLLAMA_AUTO_START", "ollama", "auto_start", True), True
)


# ── Paper translation ───────────────────────────────────────────
TRANSLATION_TARGET_LANGUAGE = str(
    _setting(
        "ANNOTA_TRANSLATION_TARGET",
        "translation",
        "target_language",
        "zh-CN",
    )
)
TRANSLATION_CHUNK_CHARS = _as_int(
    _setting(
        "ANNOTA_TRANSLATION_CHUNK_CHARS",
        "translation",
        "chunk_chars",
        3000,
    ),
    3000,
)
TRANSLATION_PROVIDER = str(
    _setting(
        "ANNOTA_TRANSLATION_PROVIDER", "translation", "provider", "auto"
    )
).lower()

DEEPSEEK_API_KEY = str(
    _setting("DEEPSEEK_API_KEY", "deepseek", "api_key", "")
)
DEEPSEEK_BASE_URL = str(
    _setting(
        "DEEPSEEK_BASE_URL",
        "deepseek",
        "base_url",
        "https://api.deepseek.com",
    )
).rstrip("/")
DEEPSEEK_MODEL = str(
    _setting("DEEPSEEK_MODEL", "deepseek", "model", "deepseek-chat")
)
DEEPSEEK_TIMEOUT = _as_float(
    _setting("DEEPSEEK_TIMEOUT", "deepseek", "timeout", 120), 120
)
