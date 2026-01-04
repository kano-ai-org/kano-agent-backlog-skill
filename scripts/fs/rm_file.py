#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete a file within the repo.")
    parser.add_argument("--path", required=True, help="File path to delete.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore missing files.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions only.")
    return parser.parse_args()


def resolve_path(value: str, repo_root: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def ensure_inside_repo(path: Path, repo_root: Path) -> None:
    try:
        path.relative_to(repo_root)
    except ValueError as exc:
        raise SystemExit(f"Path must be inside the repo root: {path}") from exc


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()

    target = resolve_path(args.path, repo_root)
    ensure_inside_repo(target, repo_root)

    if not target.exists():
        if args.force:
            print(f"Missing (ignored): {target}")
            return 0
        raise SystemExit(f"Path not found: {target}")
    if not target.is_file():
        raise SystemExit(f"Only files are supported: {target}")

    if args.dry_run:
        print(f"[DRY] delete {target}")
        return 0

    target.unlink()
    print(f"Deleted: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
