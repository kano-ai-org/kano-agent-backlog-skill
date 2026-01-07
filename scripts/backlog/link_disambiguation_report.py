#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Local imports
COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from product_args import add_product_arguments  # noqa: E402

BACKLOG_LIB_PARENT = Path(__file__).resolve().parent
if str(BACKLOG_LIB_PARENT) not in sys.path:
    sys.path.insert(0, str(BACKLOG_LIB_PARENT))
from lib.index import BacklogIndex  # noqa: E402


def is_full_uid(ref: str) -> bool:
    return len(ref) == 36 and "-" in ref


def is_id_uidshort(ref: str) -> bool:
    return "@" in ref


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report ambiguous link targets and suggest id@uidshort disambiguations."
    )
    parser.add_argument(
        "--backlog-root",
        default="_kano/backlog",
        help="Backlog root path (default: _kano/backlog).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--relations",
        default="parent,relates,blocks,blocked_by",
        help="Comma-separated relations to check (default: parent,relates,blocks,blocked_by).",
    )
    parser.add_argument(
        "--collisions-only",
        action="store_true",
        help="Only output when ambiguous references are found.",
    )
    add_product_arguments(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    backlog_root = (repo_root / args.backlog_root).resolve()
    if not backlog_root.exists():
        print(f"Error: Backlog root not found: {backlog_root}")
        return 1

    index = BacklogIndex(backlog_root)
    relations = [r.strip() for r in args.relations.split(",") if r.strip()]

    ambiguous: List[Dict[str, str]] = []

    # Iterate items; for each relation, check targets
    for did, items in index.items_by_id.items():
        for item in items:
            fm = item.frontmatter or {}
            parent_ref = str(fm.get("parent") or "").strip()
            links = fm.get("links") or {}

            def check_ref(rel: str, ref: str, product: str) -> None:
                if not ref:
                    return
                # Skip already collision-safe refs
                if is_full_uid(ref) or is_id_uidshort(ref):
                    return
                # Display ID resolution scope
                if rel == "parent":
                    matches = index.get_by_id(ref, product=product)
                else:
                    matches = index.get_by_id(ref, product=product)
                    if not matches:
                        # Try cross-product to suggest options
                        matches = index.get_by_id(ref)

                if len(matches) == 1:
                    return
                if len(matches) == 0:
                    ambiguous.append(
                        {
                            "item": item.id,
                            "product": item.product,
                            "relation": rel,
                            "target": ref,
                            "issue": "not found",
                            "suggest": "use id@uidshort or full uid",
                        }
                    )
                    return

                # Multiple matches: suggest id@uidshort candidates
                suggestions = [f"{m.id}@{m.uidshort}" for m in matches if m.uidshort]
                ambiguous.append(
                    {
                        "item": item.id,
                        "product": item.product,
                        "relation": rel,
                        "target": ref,
                        "issue": "ambiguous",
                        "suggest": ", ".join(suggestions) or "use full uid",
                    }
                )

            if "parent" in relations:
                check_ref("parent", parent_ref, item.product)

            for rel in ("relates", "blocks", "blocked_by"):
                if rel not in relations:
                    continue
                targets = links.get(rel)
                if isinstance(targets, list):
                    for ref in targets:
                        check_ref(rel, str(ref).strip(), item.product)

    if args.collisions_only and not ambiguous:
        return 0

    if args.format == "json":
        import json
        print(json.dumps({"count": len(ambiguous), "items": ambiguous}, indent=2, ensure_ascii=False))
        return 0

    # Text output
    print("Link Disambiguation Report")
    print("==========================")
    print(f"Ambiguous/invalid references: {len(ambiguous)}")
    print()
    for row in ambiguous:
        print(f"- {row['item']} ({row['product']}) {row['relation']} -> {row['target']} [{row['issue']}]")
        print(f"  Suggest: {row['suggest']}")
    if not ambiguous:
        print("No ambiguous references found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
