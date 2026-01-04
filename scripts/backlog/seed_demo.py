#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from config_loader import allowed_roots_for_repo, resolve_allowed_root  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed demo backlog items and views under a permitted root."
    )
    parser.add_argument(
        "--backlog-root",
        default="_kano/backlog",
        help="Backlog root path (default: _kano/backlog).",
    )
    parser.add_argument(
        "--prefix",
        help="ID prefix override (default: derived from repo name).",
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Worklog agent name for seeded items (required).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow seeding even if demo items already exist.",
    )
    parser.add_argument(
        "--skip-views",
        action="store_true",
        help="Skip generating demo views.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without creating files.",
    )
    return parser.parse_args()


def ensure_under_allowed(path: Path, allowed_roots: List[Path], label: str) -> Path:
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(root) for root in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def read_frontmatter_id(path: Path) -> Optional[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("id:"):
            return line.split(":", 1)[1].strip().strip("\"")
    return None


def has_demo_seed(items_root: Path) -> bool:
    for path in items_root.rglob("*.md"):
        if path.name.endswith(".index.md"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0].strip() != "---":
            continue
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if line.startswith("tags:") and "demo-seed" in line:
                return True
    return False


def run_create_item(
    python: str,
    script: Path,
    args: List[str],
    dry_run: bool,
) -> Optional[Path]:
    cmd = [python, str(script)] + args
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "create_item failed")
    if dry_run:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("Created item:"):
            path = line.split("Created item:", 1)[1].strip()
            return Path(path)
    raise SystemExit("Could not determine created item path.")


def run_generate_view(
    python: str,
    script: Path,
    args: List[str],
    dry_run: bool,
) -> None:
    cmd = [python, str(script)] + args
    if dry_run:
        print("[DRY] " + " ".join(cmd))
        return
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "generate_view failed")


def derive_prefix(repo_root: Path, override: Optional[str]) -> str:
    if override:
        return override
    name = repo_root.name
    letters = [ch for ch in name if ch.isalnum()]
    if not letters:
        raise SystemExit("Unable to derive prefix. Provide --prefix.")
    prefix = "".join([ch for ch in name if ch.isalpha()][:4]) or letters[0]
    return prefix.upper()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    allowed_roots = allowed_roots_for_repo(repo_root)

    backlog_root = Path(args.backlog_root)
    if not backlog_root.is_absolute():
        backlog_root = (repo_root / backlog_root).resolve()
    root = ensure_under_allowed(backlog_root, allowed_roots, "backlog-root")

    items_root = backlog_root / "items"
    views_root = backlog_root / "views"
    if ensure_under_allowed(items_root, allowed_roots, "items-root") != root:
        raise SystemExit("items-root must share the same root as backlog-root.")
    if ensure_under_allowed(views_root, allowed_roots, "views-root") != root:
        raise SystemExit("views-root must share the same root as backlog-root.")

    items_root.mkdir(parents=True, exist_ok=True)
    views_root.mkdir(parents=True, exist_ok=True)

    if has_demo_seed(items_root) and not args.force:
        raise SystemExit("Demo seed items already exist. Use --force to add more.")

    python = sys.executable
    create_item = SCRIPT_DIR / "create_item.py"
    generate_view = SCRIPT_DIR / "generate_view.py"
    prefix = derive_prefix(repo_root, args.prefix)
    tags = "demo-seed"
    agent = args.agent

    epic_path = run_create_item(
        python,
        create_item,
        [
            "--items-root",
            str(items_root),
            "--backlog-root",
            str(backlog_root),
            "--type",
            "Epic",
            "--title",
            "Demo Backlog Flow",
            "--area",
            "demo",
            "--tags",
            tags,
            "--agent",
            agent,
            "--prefix",
            prefix,
        ],
        args.dry_run,
    )
    epic_id = read_frontmatter_id(epic_path) if epic_path else None
    if epic_path and not epic_id:
        raise SystemExit("Failed to read Epic id.")

    feature_path = run_create_item(
        python,
        create_item,
        [
            "--items-root",
            str(items_root),
            "--backlog-root",
            str(backlog_root),
            "--type",
            "Feature",
            "--title",
            "Local-first backlog system",
            "--area",
            "demo",
            "--tags",
            tags,
            "--parent",
            epic_id or "",
            "--agent",
            agent,
            "--prefix",
            prefix,
        ],
        args.dry_run,
    )
    feature_id = read_frontmatter_id(feature_path) if feature_path else None
    if feature_path and not feature_id:
        raise SystemExit("Failed to read Feature id.")

    story_path = run_create_item(
        python,
        create_item,
        [
            "--items-root",
            str(items_root),
            "--backlog-root",
            str(backlog_root),
            "--type",
            "UserStory",
            "--title",
            "Plan before code changes",
            "--area",
            "demo",
            "--tags",
            tags,
            "--parent",
            feature_id or "",
            "--agent",
            agent,
            "--prefix",
            prefix,
        ],
        args.dry_run,
    )
    story_id = read_frontmatter_id(story_path) if story_path else None
    if story_path and not story_id:
        raise SystemExit("Failed to read UserStory id.")

    run_create_item(
        python,
        create_item,
        [
            "--items-root",
            str(items_root),
            "--backlog-root",
            str(backlog_root),
            "--type",
            "Task",
            "--title",
            "Run sample workflow",
            "--area",
            "demo",
            "--tags",
            tags,
            "--parent",
            story_id or "",
            "--agent",
            agent,
            "--prefix",
            prefix,
        ],
        args.dry_run,
    )

    run_create_item(
        python,
        create_item,
        [
            "--items-root",
            str(items_root),
            "--backlog-root",
            str(backlog_root),
            "--type",
            "Bug",
            "--title",
            "Demo bug for workflow",
            "--area",
            "demo",
            "--tags",
            tags,
            "--parent",
            story_id or "",
            "--agent",
            agent,
            "--prefix",
            prefix,
        ],
        args.dry_run,
    )

    if not args.skip_views:
        run_generate_view(
            python,
            generate_view,
            [
                "--items-root",
                str(items_root),
                "--groups",
                "New,InProgress",
                "--title",
                "InProgress Work",
                "--output",
                str(views_root / "Dashboard_PlainMarkdown_Active.md"),
                "--source-label",
                str(backlog_root / "items"),
            ],
            args.dry_run,
        )
        run_generate_view(
            python,
            generate_view,
            [
                "--items-root",
                str(items_root),
                "--groups",
                "New",
                "--title",
                "New Work",
                "--output",
                str(views_root / "Dashboard_PlainMarkdown_New.md"),
                "--source-label",
                str(backlog_root / "items"),
            ],
            args.dry_run,
        )
        run_generate_view(
            python,
            generate_view,
            [
                "--items-root",
                str(items_root),
                "--groups",
                "Done",
                "--title",
                "Done Work",
                "--output",
                str(views_root / "Dashboard_PlainMarkdown_Done.md"),
                "--source-label",
                str(backlog_root / "items"),
            ],
            args.dry_run,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
