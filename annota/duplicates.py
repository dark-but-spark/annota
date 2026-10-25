"""Detect and merge duplicate PDFs stored under the same paper title.

Two attachments are treated as duplicates only when:

* their parent items share the same normalized title, and
* the PDF files are byte-identical (SHA-256), and
* the detected/metadata languages do not conflict.

Merging is conservative: unique annotations and notes are moved to the kept
attachment, collection/tag membership is merged, and the duplicate items are
moved to the Zotero trash so the operation can be undone.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

from . import zotero_db
from .config import ZOTERO_STORAGE_DIR

logger = logging.getLogger(__name__)

_TEXT_SAMPLE_PAGES = 2
_TEXT_SAMPLE_CHARS = 8000
_MIN_SCRIPT_CHARS = 20

_LANGUAGE_ALIASES = {
    "eng": "en",
    "english": "en",
    "zho": "zh",
    "chi": "zh",
    "chinese": "zh",
    "cmn": "zh",
    "jpn": "ja",
    "japanese": "ja",
    "kor": "ko",
    "korean": "ko",
    "fra": "fr",
    "fre": "fr",
    "french": "fr",
    "deu": "de",
    "ger": "de",
    "german": "de",
    "spa": "es",
    "spanish": "es",
    "rus": "ru",
    "russian": "ru",
    "por": "pt",
    "portuguese": "pt",
    "ita": "it",
    "italian": "it",
}

_NON_LATIN_LANGUAGES = {"zh", "ja", "ko", "ru", "ar", "el", "he"}


def normalize_title(title: str) -> str:
    """Normalize a title for conservative comparison."""
    text = unicodedata.normalize("NFKC", title or "")
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text.rstrip(" .")


def normalize_language(value: str | None) -> str | None:
    """Map common language names/codes to a short language code."""
    if not value:
        return None
    code = str(value).strip().casefold().replace("_", "-")
    if not code:
        return None
    base = code.split("-")[0]
    return _LANGUAGE_ALIASES.get(base, base)


def detect_language(text: str) -> str | None:
    """Detect a coarse language/script from a text sample.

    Latin-script languages cannot be told apart reliably without a language
    model, so they are reported as ``latin``.  That is sufficient here because
    duplicate candidates must also have byte-identical PDFs.
    """
    sample = (text or "")[:_TEXT_SAMPLE_CHARS]
    counts = {
        "cjk": 0,
        "kana": 0,
        "hangul": 0,
        "cyrillic": 0,
        "arabic": 0,
        "latin": 0,
    }
    for char in sample:
        code = ord(char)
        if 0x3040 <= code <= 0x30FF:
            counts["kana"] += 1
        elif 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            counts["cjk"] += 1
        elif 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
            counts["hangul"] += 1
        elif 0x0400 <= code <= 0x04FF:
            counts["cyrillic"] += 1
        elif 0x0600 <= code <= 0x06FF:
            counts["arabic"] += 1
        elif char.isascii() and char.isalpha():
            counts["latin"] += 1

    if counts["kana"] >= _MIN_SCRIPT_CHARS and (
        counts["kana"] + counts["cjk"] >= _MIN_SCRIPT_CHARS
    ):
        return "ja"
    if counts["hangul"] >= _MIN_SCRIPT_CHARS:
        return "ko"
    if counts["cjk"] >= _MIN_SCRIPT_CHARS:
        return "zh"
    if counts["cyrillic"] >= _MIN_SCRIPT_CHARS:
        return "ru"
    if counts["arabic"] >= _MIN_SCRIPT_CHARS:
        return "ar"
    if counts["latin"] >= _MIN_SCRIPT_CHARS:
        return "latin"
    return None


def _languages_compatible(metadata_language: str, detected_language: str) -> bool:
    if not detected_language:
        return True
    if detected_language == "latin":
        return metadata_language not in _NON_LATIN_LANGUAGES
    # CJK script detection cannot always separate Japanese kanji-only text from
    # Chinese, so accept the pair when metadata says either language.
    if detected_language in {"zh", "ja"} and metadata_language in {"zh", "ja"}:
        return True
    return metadata_language == detected_language


def _language_conflict(members: list[dict]) -> tuple[bool, list[str]]:
    metadata = {
        lang for lang in (m.get("metadata_language") for m in members) if lang
    }
    detected = {
        lang for lang in (m.get("detected_language") for m in members) if lang
    }
    languages = sorted(metadata | detected)

    if len(metadata) > 1 or len(detected) > 1:
        return True, languages
    if metadata and detected:
        meta = next(iter(metadata))
        det = next(iter(detected))
        if not _languages_compatible(meta, det):
            return True, languages
    return False, languages


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text_sample(path: Path) -> str:
    doc = fitz.open(str(path))
    try:
        parts = []
        for page_index in range(min(_TEXT_SAMPLE_PAGES, len(doc))):
            parts.append(doc[page_index].get_text("text"))
        return "\n".join(parts)
    finally:
        doc.close()


def _resolve_pdf_path(record: dict) -> Path | None:
    raw = (record.get("path") or "").strip()
    if not raw:
        return None
    if raw.startswith("storage:"):
        key = record.get("attachment_key")
        if not key:
            return None
        return ZOTERO_STORAGE_DIR / key / raw[len("storage:"):]
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else None


def _record_for_output(record: dict) -> dict:
    return {
        "item_id": record["item_id"],
        "attachment_id": record["attachment_id"],
        "annotation_count": record["annotation_count"],
        "note_count": record["note_count"],
        "language": record.get("metadata_language")
        or record.get("detected_language")
        or "unknown",
        "date_added": record.get("parent_date_added"),
    }


def _build_group(title_key: str, content_hash: str, members: list[dict]) -> dict:
    conflict, languages = _language_conflict(members)
    target = sorted(
        members,
        key=lambda m: (
            -m["annotation_count"],
            m.get("parent_date_added") or "",
            m["attachment_id"],
        ),
    )[0]
    duplicates = [m for m in members if m["attachment_id"] != target["attachment_id"]]
    return {
        "title": members[0].get("title"),
        "title_key": title_key,
        "content_hash": content_hash,
        "mergeable": not conflict,
        "reason": "different_language" if conflict else None,
        "languages": languages,
        "target": _record_for_output(target),
        "duplicates": [_record_for_output(m) for m in duplicates],
        "annotation_count": sum(m["annotation_count"] for m in members),
    }


def find_duplicate_pdfs() -> list[dict]:
    """Return groups of byte-identical PDFs stored under the same title."""
    records = zotero_db.list_pdf_attachments()

    by_title: dict[str, list[dict]] = {}
    for record in records:
        title = record.get("title")
        if not title:
            continue
        by_title.setdefault(normalize_title(title), []).append(record)

    groups: list[dict] = []
    for title_key, candidates in by_title.items():
        if len(candidates) < 2:
            continue

        hashed: list[dict] = []
        for record in candidates:
            path = _resolve_pdf_path(record)
            if path is None or not path.is_file():
                logger.debug("Skipping missing PDF for item %s", record["item_id"])
                continue
            item = dict(record)
            try:
                item["content_hash"] = _sha256(path)
                item["detected_language"] = detect_language(_read_text_sample(path))
            except Exception as exc:  # damaged/encrypted PDF
                logger.warning(
                    "Cannot fingerprint PDF for item %s: %s", record["item_id"], exc
                )
                continue
            item["metadata_language"] = normalize_language(record.get("language"))
            hashed.append(item)

        by_hash: dict[str, list[dict]] = {}
        for item in hashed:
            by_hash.setdefault(item["content_hash"], []).append(item)

        for content_hash, members in by_hash.items():
            if len(members) < 2:
                continue
            groups.append(_build_group(title_key, content_hash, members))

    groups.sort(key=lambda group: (not group["mergeable"], group["title_key"]))
    return groups


def _matches_title(group: dict, title: str | None) -> bool:
    if not title:
        return True
    return normalize_title(title) in group["title_key"]


def merge_duplicate_pdfs(
    dry_run: bool = True,
    title: str | None = None,
) -> dict:
    """Merge all mergeable duplicate groups, optionally filtered by title."""
    groups = [group for group in find_duplicate_pdfs() if _matches_title(group, title)]
    results: list[dict] = []

    for group in groups:
        base = {
            "title": group["title"],
            "content_hash": group["content_hash"],
            "target": group["target"],
            "duplicates": group["duplicates"],
        }
        if not group["mergeable"]:
            results.append(
                {
                    **base,
                    "status": "skipped",
                    "reason": group["reason"],
                    "languages": group["languages"],
                }
            )
            continue

        if dry_run:
            results.append(
                {
                    **base,
                    "status": "would_merge",
                    "annotation_count": group["annotation_count"],
                    "note_count": sum(d["note_count"] for d in group["duplicates"]),
                }
            )
            continue

        try:
            detail = zotero_db.merge_duplicate_group(
                target_parent_item_id=group["target"]["item_id"],
                target_attachment_id=group["target"]["attachment_id"],
                duplicates=[
                    {
                        "item_id": duplicate["item_id"],
                        "attachment_id": duplicate["attachment_id"],
                    }
                    for duplicate in group["duplicates"]
                ],
            )
            results.append({**base, "status": "merged", **detail})
        except Exception as exc:
            logger.exception("Failed to merge duplicate group %s", group["title"])
            results.append({**base, "status": "error", "error": str(exc)})

    merged = sum(1 for result in results if result["status"] == "merged")
    return {
        "dry_run": dry_run,
        "groups_found": len(groups),
        "groups_merged": merged,
        "results": results,
    }
