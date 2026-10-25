#!/usr/bin/env python3
"""Find PDFs with identical content under the same title and merge them.

By default this only prints a preview.  Pass --apply to perform the merge.
Zotero must be closed before applying changes because the SQLite database is
locked while Zotero is running.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from annota.duplicates import merge_duplicate_pdfs


def _print_human(result: dict) -> None:
    mode = "DRY RUN" if result["dry_run"] else "APPLIED"
    print(f"[{mode}] duplicate groups: {result['groups_found']}, merged: {result['groups_merged']}")
    for item in result["results"]:
        print(f"\n- {item.get('title')}")
        print(f"  status: {item['status']}")
        target = item.get("target") or {}
        print(
            "  keep: item {item_id} / attachment {attachment_id} "
            "({annotation_count} annotations)".format(**target)
        )
        for duplicate in item.get("duplicates", []):
            print(
                "  duplicate: item {item_id} / attachment {attachment_id} "
                "({annotation_count} annotations)".format(**duplicate)
            )
        if item.get("reason"):
            print(f"  reason: {item['reason']} ({', '.join(item.get('languages') or [])})")
        if item.get("error"):
            print(f"  error: {item['error']}")
        for merged in item.get("merged", []):
            if merged.get("skipped"):
                print(f"  skipped source {merged['source_item_id']}: {merged['skipped']}")
            else:
                print(
                    "  moved from item {source_item_id}: "
                    "{annotations_moved} annotations, {attachment_notes_moved} attachment notes, "
                    "{parent_notes_moved} parent notes, {child_attachments_moved} attachments".format(
                        **merged
                    )
                )
    if any(item["status"] == "error" for item in result["results"]):
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the merge (Zotero must be closed)",
    )
    parser.add_argument(
        "--title",
        help="only process groups whose normalized title contains this text",
    )
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    args = parser.parse_args()

    result = merge_duplicate_pdfs(dry_run=not args.apply, title=args.title)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)


if __name__ == "__main__":
    main()
