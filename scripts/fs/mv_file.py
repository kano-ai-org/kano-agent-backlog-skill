#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402


def backlog_root_for_repo(repo_root: Path) -> Path:
    return (repo_root / "_kano" / "backlog").resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Move a file within the repo.")
    parser.add_argument("--src", required=True, help="Source file path.")
    parser.add_argument("--dest", required=True, help="Destination file path.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting an existing destination file.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions only.")
    return parser.parse_args()


def resolve_path(value: str, repo_root: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def ensure_inside_backlog(path: Path, backlog_root: Path) -> None:
    try:
        path.relative_to(backlog_root)
    except ValueError as exc:
        raise SystemExit(f"Path must be inside {backlog_root}: {path}") from exc


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    backlog_root = backlog_root_for_repo(repo_root)

    src = resolve_path(args.src, repo_root)
    dest = resolve_path(args.dest, repo_root)
    ensure_inside_backlog(src, backlog_root)
    ensure_inside_backlog(dest, backlog_root)

    if not src.exists():
        raise SystemExit(f"Source not found: {src}")
    if not src.is_file():
        raise SystemExit(f"Source must be a file: {src}")
    if dest.exists() and not args.overwrite:
        raise SystemExit(f"Destination exists: {dest}")

    if args.dry_run:
        print(f"[DRY] move {src} -> {dest}")
        return 0

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    print(f"Moved: {src} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
