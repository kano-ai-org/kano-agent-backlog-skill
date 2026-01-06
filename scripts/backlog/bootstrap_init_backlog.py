#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import json
import re
from pathlib import Path
from typing import Optional

sys.dont_write_bytecode = True

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from config_loader import default_config, merge_defaults  # noqa: E402
from context import (  # noqa: E402
    find_repo_root,
    find_platform_root,
    resolve_product_name,
    get_product_root,
    get_sandbox_root_or_none,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize backlog scaffold under a product in the multi-product platform.",
        epilog="Example: python bootstrap_init_backlog.py --product test-skill --agent copilot"
    )
    parser.add_argument(
        "--product",
        help="Product name to initialize (e.g. kano-agent-backlog-skill). Defaults to BACKLOG_PRODUCT env or defaults.json.",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Target the sandbox environment for the product (creates under _kano/backlog/sandboxes/<product>).",
    )
    parser.add_argument(
        "--agent",
        help="Agent identifier for audit logging (e.g. copilot, cursor).",
    )
    parser.add_argument(
        "--process-profile",
        help="Process profile ID (e.g. builtin/azure-boards-agile). Overrides defaults.",
    )
    parser.add_argument(
        "--process-path",
        help="Process profile JSON path (relative to repo root or absolute). Overrides defaults.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite baseline files when they already exist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing files.",
    )
    return parser.parse_args()


def write_file(path: Path, content: str, force: bool, dry_run: bool) -> None:
    if path.exists() and not force:
        print(f"Skip existing: {path}")
        return
    if dry_run:
        print(f"[DRY] write {path}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"Wrote: {path}")


def make_dir(path: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"[DRY] mkdir {path}")
        return
    path.mkdir(parents=True, exist_ok=True)


def load_existing_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


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


def main() -> int:
    args = parse_args()
    
    try:
        # Discover platform root and resolve product name
        repo_root = find_repo_root()
        platform_root = find_platform_root(repo_root)
        product_name = resolve_product_name(args.product)
        
        print(f"Repository root: {repo_root}")
        print(f"Platform root: {platform_root}")
        print(f"Target product: {product_name}")
        print(f"Target sandbox: {args.sandbox}")
        
        # Resolve backlog root (product or sandbox)
        if args.sandbox:
            try:
                backlog_root = get_sandbox_root_or_none(product_name, platform_root) or (platform_root / "sandboxes" / product_name)
            except FileNotFoundError:
                backlog_root = platform_root / "sandboxes" / product_name
        else:
            try:
                backlog_root = get_product_root(product_name, platform_root)
            except FileNotFoundError:
                backlog_root = platform_root / "products" / product_name
        
        print(f"Initializing backlog at: {backlog_root}")
        
        # Ensure path is under platform root (safety check)
        if not str(backlog_root).startswith(str(platform_root)):
            raise SystemExit(f"backlog_root must be under {platform_root}: {backlog_root}")
        
        # Check if already initialized
        if backlog_root.exists() and not args.force:
            config_file = backlog_root / "_config" / "config.json"
            if config_file.exists():
                print(f"Backlog already initialized at {backlog_root}. Use --force to overwrite.")
                return 1
    
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    config_path = backlog_root / "_config" / "config.json"
    baseline = merge_defaults(default_config(), load_existing_config(config_path))
    if args.process_profile:
        baseline.setdefault("process", {})
        baseline["process"]["profile"] = args.process_profile
        baseline["process"]["path"] = None
    if args.process_path:
        baseline.setdefault("process", {})
        baseline["process"]["path"] = args.process_path
        baseline["process"]["profile"] = None

    skill_root = Path(__file__).resolve().parents[2]
    process_def = resolve_process_definition(baseline.get("process", {}), repo_root, skill_root)
    item_folders = derive_item_folders(process_def)

    dirs = [
        backlog_root / "_config",
        backlog_root / "_meta",
        backlog_root / "decisions",
        backlog_root / "views",
    ]
    for folder in item_folders:
        dirs.append(backlog_root / "items" / folder)
    for path in dirs:
        make_dir(path, args.dry_run)

    readme_path = backlog_root / "README.md"
    readme_lines = [
        f"# {backlog_root.name} Backlog",
        "",
        "Local-first project backlog (file-based).",
        "",
        "## Structure",
        "",
        "- `_meta/`: schema and conventions",
        *format_item_folders(item_folders),
        "- `decisions/`: ADRs",
        "- `views/`: dashboards",
        "",
    ]
    readme_content = "\n".join(readme_lines)
    write_file(readme_path, readme_content, args.force, args.dry_run)

    index_path = backlog_root / "_meta" / "indexes.md"
    index_content = "\n".join(
        [
            "# Index Registry",
            "",
            "| type | item_id | index_file | updated | notes |",
            "| ---- | ------- | ---------- | ------- | ----- |",
            "",
        ]
    )
    write_file(index_path, index_content, args.force, args.dry_run)

    # Load baseline defaults and customize for this product
    baseline["project"]["name"] = product_name
    
    # Optionally derive prefix from product name (simple heuristic)
    # e.g., "kano-agent-backlog-skill" -> "KABSD"
    if "prefix" not in baseline.get("project", {}):
        prefix = _derive_prefix(product_name)
        baseline["project"]["prefix"] = prefix
    
    config_content = json.dumps(baseline, indent=2, ensure_ascii=True) + "\n"
    write_file(config_path, config_content, args.force, args.dry_run)

    dashboard_index_path = backlog_root / "views" / "Dashboard.md"
    dashboard_index_content = "\n".join(
        [
            "# Dashboard",
            "",
            "This folder can host multiple view styles over the same file-first backlog items.",
            "",
            "## Plain Markdown (no plugins)",
            "",
            "- `Dashboard_PlainMarkdown.md` (embeds the generated lists)",
            "- Generated outputs: `Dashboard_PlainMarkdown_{Active,New,Done}.md`",
            "",
            "Refresh generated dashboards:",
            f"- `python skills/kano-agent-backlog-skill/scripts/backlog/view_refresh_dashboards.py --product {product_name} --agent <agent-name>`",
            "",
            "## Optional: SQLite index",
            "",
            "If `index.enabled=true` in `_config/config.json`, scripts can prefer SQLite for faster reads,",
            "while Markdown files remain the source of truth.",
            "",
        ]
    )
    write_file(dashboard_index_path, dashboard_index_content, args.force, args.dry_run)

    plain_dashboard_path = backlog_root / "views" / "Dashboard_PlainMarkdown.md"
    plain_dashboard_content = "\n".join(
        [
            "# Dashboard (Plain Markdown)",
            "",
            "Embeds the generated Markdown lists (no Obsidian plugins required).",
            "",
            "![[Dashboard_PlainMarkdown_Active.md]]",
            "",
            "![[Dashboard_PlainMarkdown_New.md]]",
            "",
            "![[Dashboard_PlainMarkdown_Done.md]]",
            "",
        ]
    )
    write_file(plain_dashboard_path, plain_dashboard_content, args.force, args.dry_run)
    
    print(f"\n✓ Backlog initialized successfully at {backlog_root}")
    if args.agent:
        print(f"  Run this to refresh dashboards: python ... view_refresh_dashboards.py --product {product_name} --agent {args.agent}")
    
    return 0


def _derive_prefix(product_name: str) -> str:
    """
    Simple heuristic to derive a prefix from product name.
    E.g., "kano-agent-backlog-skill" -> "KABSD"
    """
    parts = product_name.split("-")
    prefix = "".join(p[0].upper() for p in parts if p)
    return prefix or "PRJ"


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
