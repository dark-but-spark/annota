#!/usr/bin/env python3
"""Translate a formula-heavy PDF with BabelDOC (external tool).

BabelDOC preserves formulas, tables, and layout while translating prose.  It is
an optional companion to Annota's native note translator: Annota is better for
prose notes, BabelDOC is better for pages containing equations.

Install once:
    uv tool install --python 3.12 BabelDOC

If BabelDOC fails with ``cannot import name 'BitStream'``:
    uv pip install --python <babeldoc-python> "bitstring==4.1.4"

Examples:
    python babeldoc_translate.py --pdf paper.pdf --pages 1-5
    python babeldoc_translate.py --pdf paper.pdf --pages 3-4 --dual
    python babeldoc_translate.py --pdf paper.pdf --provider deepseek \
        --glossary terms.csv --output out/
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from annota import ollama_client
from annota.config import (
    ANNOTA_USER_CONFIG_PATH,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_LLM_MODEL,
    TRANSLATION_TARGET_LANGUAGE,
)


def _load_user_config() -> dict:
    try:
        data = json.loads(Path(ANNOTA_USER_CONFIG_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _deepseek_settings() -> dict:
    import os

    section = _load_user_config().get("deepseek")
    if not isinstance(section, dict):
        section = {}
    return {
        "api_key": (
            os.environ.get("DEEPSEEK_API_KEY")
            or section.get("api_key")
            or ""
        ),
        "base_url": (
            os.environ.get("DEEPSEEK_BASE_URL")
            or section.get("base_url")
            or DEEPSEEK_BASE_URL
        ).rstrip("/"),
        "model": (
            os.environ.get("DEEPSEEK_MODEL")
            or section.get("model")
            or DEEPSEEK_MODEL
        ),
    }


def _choose_provider(requested: str) -> tuple[str, dict]:
    settings = _deepseek_settings()
    if requested == "deepseek":
        if not settings["api_key"]:
            raise SystemExit(
                "DEEPSEEK_API_KEY is not configured. Set it in the environment "
                "or ~/.annota/config.json."
            )
        return "deepseek", settings

    local = ollama_client.status()
    if local.get("available") and local.get("models"):
        return "ollama", {
            "base_url": OLLAMA_BASE_URL,
            "model": OLLAMA_LLM_MODEL or local["models"][0],
        }

    if requested == "ollama":
        raise SystemExit(
            "Ollama is not available. Start it with `ollama serve` or use "
            "--provider deepseek."
        )
    if settings["api_key"]:
        return "deepseek", settings
    raise SystemExit(
        "No provider available: start Ollama or configure DEEPSEEK_API_KEY."
    )


def _openai_base_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    return base_url if base_url.endswith("/v1") else f"{base_url}/v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, help="input PDF path")
    parser.add_argument(
        "--pages",
        default=None,
        help="1-based pages for BabelDOC, e.g. 1-5 or 1,3,5",
    )
    parser.add_argument("--output", default=None, help="output directory")
    parser.add_argument(
        "--target", default=TRANSLATION_TARGET_LANGUAGE, help="target language"
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "deepseek", "ollama"],
        default="auto",
        help="translation provider",
    )
    parser.add_argument(
        "--glossary",
        help="BabelDOC glossary CSV (source,target[,tgt_lng])",
    )
    parser.add_argument("--dual", action="store_true", help="also output dual PDF")
    parser.add_argument(
        "--extra",
        nargs=argparse.REMAINDER,
        help="extra BabelDOC arguments (after --)",
    )
    args = parser.parse_args()

    pdf = Path(args.pdf).expanduser()
    if not pdf.is_file():
        raise SystemExit(f"PDF not found: {pdf}")

    executable = shutil.which("babeldoc")
    if not executable:
        raise SystemExit(
            "babeldoc is not installed. Run:\n"
            "  uv tool install --python 3.12 BabelDOC\n"
            "If it reports a bitstring error, run:\n"
            '  uv pip install --python <babeldoc-python> "bitstring==4.1.4"'
        )

    provider, settings = _choose_provider(args.provider)
    output = Path(args.output).expanduser() if args.output else pdf.parent
    output.mkdir(parents=True, exist_ok=True)

    command = [
        executable,
        "--files",
        str(pdf),
        "--output",
        str(output),
        "--lang-in",
        "en",
        "--lang-out",
        args.target,
        "--openai",
        "--openai-model",
        settings["model"],
        "--openai-base-url",
        _openai_base_url(settings["base_url"]),
        "--skip-scanned-detection",
        "--watermark-output-mode",
        "no_watermark",
    ]
    if provider == "deepseek":
        command += ["--openai-api-key", settings["api_key"]]
    else:
        command += ["--openai-api-key", "ollama"]
    if args.pages:
        command += ["--pages", args.pages]
    if not args.dual:
        command.append("--no-dual")
    if args.glossary:
        glossary = Path(args.glossary).expanduser()
        if not glossary.is_file():
            raise SystemExit(f"Glossary not found: {glossary}")
        command += ["--glossary-files", str(glossary)]
    if args.extra:
        command += args.extra

    print(f"provider: {provider} / {settings['model']}")
    print(f"output:   {output}")
    completed = subprocess.run(command)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
