#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from product_args import add_product_arguments  # noqa: E402
from config_loader import (
    allowed_roots_for_repo,
    load_config_with_defaults,
    validate_config,
)

BACKLOG_DIR = Path(__file__).resolve().parents[1] / "backlog"
if str(BACKLOG_DIR) not in sys.path:
    sys.path.insert(0, str(BACKLOG_DIR))
from lib.index import BacklogIndex  # noqa: E402
from lib.resolver import resolve_ref  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show next checklist items from workset plan.")
    parser.add_argument("--item", required=True, help="Backlog item ref (id/uid/id@uidshort)")
    parser.add_argument(
        "--cache-root",
        default="_kano/backlog/sandboxes/.cache",
        help="Cache root (default: _kano/backlog/sandboxes/.cache)",
    )
    parser.add_argument("--config", help="Optional config path override")
    add_product_arguments(parser)
    return parser.parse_args()


def ensure_under_allowed(path: Path, allowed_roots: list[Path], label: str) -> Path:
    from config_loader import resolve_allowed_root
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(r) for r in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()

    config = load_config_with_defaults(repo_root=repo_root, config_path=args.config)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    backlog_root = repo_root / "_kano" / "backlog"
    allowed_roots = allowed_roots_for_repo(repo_root)

    # Resolve item
    index = BacklogIndex(backlog_root)
    matches = resolve_ref(args.item, index)
    if len(matches) != 1:
        print("Item not found or ambiguous.")
        return 1
    item = matches[0]

    cache_root = Path(args.cache_root)
    if not cache_root.is_absolute():
        cache_root = (repo_root / cache_root).resolve()
    ensure_under_allowed(cache_root, allowed_roots, "cache-root")

    ws_dir = cache_root / item.uid
    plan_path = ws_dir / "plan.md"
    if not plan_path.exists():
        print(f"Workset plan not found: {plan_path}")
        return 1

    checklist = []
    for line in plan_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("- "):
            checklist.append(line.strip()[2:])
    if not checklist:
        print("No checklist items.")
        return 0

    print("Next checklist:")
    for i, item in enumerate(checklist, 1):
        print(f"{i}. {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
