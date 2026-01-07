#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from product_args import add_product_arguments  # noqa: E402

BACKLOG_LIB_PARENT = Path(__file__).resolve().parent
if str(BACKLOG_LIB_PARENT) not in sys.path:
    sys.path.insert(0, str(BACKLOG_LIB_PARENT))
from lib.index import BacklogIndex  # noqa: E402
from lib.utils import parse_frontmatter, update_frontmatter  # noqa: E402


def is_full_uid(ref: str) -> bool:
    return len(ref) == 36 and "-" in ref


def is_id_uidshort(ref: str) -> bool:
    return "@" in ref


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-fix ambiguous link refs by converting display IDs to id@uidshort when uniquely resolvable."
    )
    parser.add_argument(
        "--backlog-root",
        default="_kano/backlog",
        help="Backlog root path (default: _kano/backlog).",
    )
    parser.add_argument(
        "--relations",
        default="relates,blocks,blocked_by",
        help="Comma-separated relations to fix (default: relates,blocks,blocked_by). Parent is not modified.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files.",
    )
    add_product_arguments(parser)
    return parser.parse_args()


def fix_ref(ref: str, index: BacklogIndex, product: str) -> Tuple[str, Optional[str]]:
    """Return (new_ref, reason) if changed; else (ref, None)."""
    if not ref:
        return ref, None
    if is_full_uid(ref) or is_id_uidshort(ref):
        return ref, None
    # Prefer same-product resolution
    in_product = index.get_by_id(ref, product=product)
    if len(in_product) == 1:
        m = in_product[0]
        if m.uidshort:
            return f"{m.id}@{m.uidshort}", "same-product unique"
        return ref, None
    # If no match in product, try global unique
    global_matches = index.get_by_id(ref)
    if len(global_matches) == 1:
        m = global_matches[0]
        if m.uidshort:
            return f"{m.id}@{m.uidshort}", "global unique"
    # Ambiguous or not found
    return ref, None


def process_item(path: Path, index: BacklogIndex, dry_run: bool) -> Tuple[int, int]:
    content = path.read_text(encoding="utf-8")
    fm, body, _ = parse_frontmatter(content)
    if not isinstance(fm, dict):
        return 0, 0
    product = ""
    # Derive product via index (items are indexed already), fallback to path parsing
    # We will scan index for item id
    item_id = str(fm.get("id") or "").strip()
    items = index.get_by_id(item_id)
    if items:
        product = items[0].product

    links = fm.get("links") or {}
    if not isinstance(links, dict):
        return 0, 0

    relations = []
    for r in ("relates", "blocks", "blocked_by"):
        targets = links.get(r)
        if isinstance(targets, list) and targets:
            relations.append(r)

    changed = 0
    scanned = 0
    new_links: Dict[str, List[str]] = dict(links)
    for rel in relations:
        targets = links.get(rel) or []
        fixed_targets: List[str] = []
        for ref in targets:
            scanned += 1
            new_ref, reason = fix_ref(str(ref).strip(), index, product)
            fixed_targets.append(new_ref)
            if reason:
                changed += 1
                print(f"Fix: {path.name} [{rel}] {ref} -> {new_ref} ({reason})")
        new_links[rel] = fixed_targets

    if changed:
        if dry_run:
            print(f"[Dry Run] Would update {path}")
        else:
            update_frontmatter(path, {"links": new_links}, dry_run=False)
    return scanned, changed


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    backlog_root = (repo_root / args.backlog_root).resolve()
    if not backlog_root.exists():
        print(f"Error: Backlog root not found: {backlog_root}")
        return 1

    index = BacklogIndex(backlog_root)

    items_dir = backlog_root / "items"
    if items_dir.exists():
        candidates = list(items_dir.rglob("*.md"))
    else:
        # Platform layout: scan products/*/items
        products_dir = backlog_root / "products"
        candidates = []
        if products_dir.exists():
            for prod_dir in products_dir.iterdir():
                if not prod_dir.is_dir():
                    continue
                item_dir = prod_dir / "items"
                if item_dir.exists():
                    candidates.extend(p for p in item_dir.rglob("*.md") if p.name != "README.md" and not p.name.endswith(".index.md"))

    total_scanned = 0
    total_changed = 0
    for path in candidates:
        scanned, changed = process_item(path, index, args.dry_run)
        total_scanned += scanned
        total_changed += changed

    print(f"Scanned refs: {total_scanned}, Changed: {total_changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
