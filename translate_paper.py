#!/usr/bin/env python3
"""Translate a Zotero paper with local Ollama or the DeepSeek API.

Local Ollama is preferred.  When it is unavailable and no DeepSeek API key is
configured, this CLI asks for the API settings interactively.  MCP tool calls
never prompt; they return translation_unavailable instead.

Examples:
    python translate_paper.py --item 123
    python translate_paper.py --item 123 --pages 0,1 --target zh-CN
    python translate_paper.py --pdf paper.pdf --no-note
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from annota import translation, zotero_db
from annota.zotero_status import ZoteroBusyError, ensure_write_ready


def _parse_pages(value: str | None) -> list[int] | None:
    if not value:
        return None
    pages = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages)) or None


def _resolve_item(item: str | None, pdf: str | None) -> tuple[Path, dict | None]:
    if pdf:
        path = Path(pdf).expanduser()
        if not path.is_file():
            raise SystemExit(f"PDF not found: {path}")
        return path, None

    if not item:
        raise SystemExit("Pass --item or --pdf")

    direct = Path(item).expanduser()
    if direct.is_file():
        return direct, None

    if item.isdigit():
        metadata = zotero_db.get_item_metadata(int(item))
        attachment_id = int(item) if zotero_db.get_pdf_path(int(item)) else None
    else:
        attachment_id = zotero_db.get_attachment_id_by_key(item)
        if attachment_id is None:
            raise SystemExit(f"Zotero item not found: {item}")
        metadata = zotero_db.get_item_metadata(attachment_id)

    if "error" in metadata:
        raise SystemExit(metadata["error"])

    if attachment_id is None:
        attachment_id = metadata.get("pdf_attachment_id")
    if not attachment_id:
        raise SystemExit("No PDF attachment found for this Zotero item")

    pdf_path = zotero_db.get_pdf_path(attachment_id)
    if not pdf_path or not pdf_path.is_file():
        raise SystemExit(f"PDF file not found for attachment {attachment_id}")
    return pdf_path, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item", help="Zotero itemID, attachment ID, or key")
    parser.add_argument("--pdf", help="PDF path (when not using a Zotero item)")
    parser.add_argument(
        "--pages",
        help="0-indexed pages, e.g. 0,1,2 or 3-5 (default: whole paper)",
    )
    parser.add_argument("--target", default="zh-CN", help="target language")
    parser.add_argument(
        "--no-note",
        action="store_true",
        help="print translations instead of saving a child note",
    )
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=3000,
        help="maximum characters per model request",
    )
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    args = parser.parse_args()

    pdf_path, metadata = _resolve_item(args.item, args.pdf)
    save_note = not args.no_note
    if save_note:
        if metadata is None:
            raise SystemExit("--no-note is required when translating a plain PDF path")
        try:
            ensure_write_ready()
        except ZoteroBusyError as exc:
            raise SystemExit(str(exc))

    def progress(index: int, total: int, chunk: dict) -> None:
        print(
            f"Translating {index}/{total} (page {chunk['page'] + 1})...",
            file=sys.stderr,
            flush=True,
        )

    result = translation.translate_pdf(
        pdf_path,
        pages=_parse_pages(args.pages),
        target_language=args.target,
        max_chars_per_chunk=args.chunk_chars,
        allow_prompt=True,
        progress=progress,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.no_note:
        print(
            f"# Translation ({result['provider']} / {result['model']}, "
            f"{result['target_language']})"
        )
        for item in result["pages"]:
            print(f"\n## Page {item['page'] + 1}\n")
            print(item["translation"])
        return

    note = translation.save_translation_note(
        metadata["itemID"], metadata.get("title", ""), result
    )
    print(
        f"Translated {result['page_count']} pages with "
        f"{result['provider']} / {result['model']}."
    )
    print(f"Saved child note itemID={note['itemID']} key={note['key']}.")
    print("Restart Zotero or press Ctrl+Shift+R to see the note.")


if __name__ == "__main__":
    main()
