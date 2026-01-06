#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

sys.dont_write_bytecode = True

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from config_loader import load_config_with_defaults  # noqa: E402
from context import (  # noqa: E402
    find_repo_root,
    find_platform_root,
    get_product_root,
    get_sandbox_root_or_none,
    resolve_product_name,
)
from product_args import add_product_arguments, get_product_and_sandbox_flags  # noqa: E402

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate backlog item folders against the active process profile."
    )
    parser.add_argument(
        "--backlog-root",
        help="Backlog root path (defaults to product root).",
    )
    parser.add_argument(
        "--config",
        help="Optional config path override.",
    )
    parser.add_argument(
        "--process-profile",
        help="Process profile ID (e.g. builtin/azure-boards-agile). Overrides config for this run.",
    )
    parser.add_argument(
        "--process-path",
        help="Process profile JSON path (relative to repo root or absolute). Overrides config for this run.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create missing item folders derived from the process profile.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions only.")
    add_product_arguments(parser)
    return parser.parse_args()


def normalize_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "", value.lower())
    return cleaned


def pluralize_slug(slug: str) -> str:
    if slug.endswith("y") and len(slug) > 1 and slug[-2] not in "aeiou":
        return slug[:-1] + "ies"
    if slug.endswith("s"):
        return slug + "es"
    return slug + "s"


def resolve_process_definition(
    process_cfg: dict,
    repo_root: Path,
    skill_root: Path,
) -> Optional[dict]:
    path_value = process_cfg.get("path")
    profile = process_cfg.get("profile")
    if path_value:
        path = Path(path_value)
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                return None
        return None
    if isinstance(profile, str) and profile.startswith("builtin/"):
        name = profile.split("/", 1)[1]
        path = skill_root / "references" / "processes" / f"{name}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                return None
    return None


def derive_item_folders(process_def: Optional[dict]) -> list[str]:
    fallback = ["epics", "features", "userstories", "tasks", "bugs"]
    if not process_def:
        return fallback
    work_item_types = process_def.get("work_item_types")
    if not isinstance(work_item_types, list):
        return fallback
    folders: list[str] = []
    seen = set()
    for entry in work_item_types:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("slug") or entry.get("type") or ""
        if not isinstance(raw, str):
            continue
        slug = normalize_slug(raw)
        if not slug:
            continue
        folder = pluralize_slug(slug)
        if folder in seen:
            continue
        seen.add(folder)
        folders.append(folder)
    return folders or fallback


def format_item_folders(folders: list[str]) -> list[str]:
    return [f"- `items/{folder}/`" for folder in folders]


def resolve_backlog_root(
    repo_root: Path,
    product_name: str,
    use_sandbox: bool,
    backlog_root_arg: Optional[str],
) -> Path:
    if backlog_root_arg:
        path = Path(backlog_root_arg)
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        return path
    platform_root = find_platform_root(repo_root)
    if use_sandbox:
        return get_sandbox_root_or_none(product_name, platform_root) or (
            platform_root / "sandboxes" / product_name
        )
    return get_product_root(product_name, platform_root)


def main() -> int:
    args = parse_args()
    repo_root = find_repo_root()
    product_name, use_sandbox = get_product_and_sandbox_flags(args)
    product_name = resolve_product_name(product_name)

    backlog_root = resolve_backlog_root(repo_root, product_name, use_sandbox, args.backlog_root)
    items_root = backlog_root / "items"

    config = load_config_with_defaults(
        repo_root=repo_root,
        config_path=args.config,
        product_name=product_name,
    )
    if args.process_profile or args.process_path:
        config.setdefault("process", {})
        if args.process_profile:
            config["process"]["profile"] = args.process_profile
            config["process"]["path"] = None
        if args.process_path:
            config["process"]["path"] = args.process_path
            config["process"]["profile"] = None

    skill_root = Path(__file__).resolve().parents[2]
    process_def = resolve_process_definition(config.get("process", {}), repo_root, skill_root)
    expected = derive_item_folders(process_def)

    if not items_root.exists() and not args.apply:
        raise SystemExit(f"Items root not found: {items_root}. Use --apply to create.")

    if args.apply and not items_root.exists() and not args.dry_run:
        items_root.mkdir(parents=True, exist_ok=True)

    existing = []
    if items_root.exists():
        existing = sorted([p.name for p in items_root.iterdir() if p.is_dir()])

    missing = [folder for folder in expected if folder not in existing]
    extra = [folder for folder in existing if folder not in expected]

    print(f"Process profile: {config.get('process', {})}")
    print(f"Items root: {items_root}")
    if missing:
        print("Missing folders:")
        for folder in missing:
            print(f"- {folder}")
    else:
        print("Missing folders: none")
    if extra:
        print("Extra folders (not in profile):")
        for folder in extra:
            print(f"- {folder}")
    else:
        print("Extra folders: none")

    if args.apply and missing:
        for folder in missing:
            target = items_root / folder
            if args.dry_run:
                print(f"[DRY] mkdir {target}")
            else:
                target.mkdir(parents=True, exist_ok=True)
        print("Applied missing folder creation.")

    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
