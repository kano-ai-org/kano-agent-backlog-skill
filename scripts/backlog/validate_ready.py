#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402


def backlog_root_for_repo(repo_root: Path) -> Path:
    return (repo_root / "_kano" / "backlog").resolve()


def ensure_under_backlog(path: Path, backlog_root: Path) -> None:
    try:
        path.resolve().relative_to(backlog_root)
    except ValueError as exc:
        raise SystemExit(f"Item must be under {backlog_root}: {path}") from exc


READY_SECTIONS = [
    "Context",
    "Goal",
    "Approach",
    "Acceptance Criteria",
    "Risks / Dependencies",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Ready gate sections for a backlog item.")
    parser.add_argument("--item", required=True, help="Path to backlog item markdown file.")
    return parser.parse_args()


def load_lines(path: Path) -> List[str]:
    return path.read_text(encoding="utf-8").splitlines()


def section_map(lines: List[str]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {}
    current = None
    for line in lines:
        if line.startswith("# "):
            current = line[2:].strip()
            sections[current] = []
            continue
        if current:
            sections[current].append(line)
    return sections


def section_has_content(lines: List[str]) -> bool:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        return True
    return False


def validate_ready(lines: List[str]) -> List[str]:
    sections = section_map(lines)
    missing = []
    for name in READY_SECTIONS:
        if name not in sections or not section_has_content(sections[name]):
            missing.append(name)
    return missing


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    backlog_root = backlog_root_for_repo(repo_root)
    item_path = Path(args.item)
    if not item_path.is_absolute():
        item_path = (repo_root / item_path).resolve()
    ensure_under_backlog(item_path, backlog_root)
    if not item_path.exists():
        raise SystemExit(f"Item not found: {item_path}")

    lines = load_lines(item_path)
    missing = validate_ready(lines)
    if missing:
        raise SystemExit(f"Ready gate incomplete: {', '.join(missing)}")

    print("Ready gate OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
