#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

backlog_entry = Path(__file__).resolve().parent / "backlog" / "validate_ready.py"
if __name__ == "__main__" and backlog_entry.exists():
    runpy.run_path(str(backlog_entry), run_name="__main__")
    raise SystemExit(0)

import argparse
from typing import Dict, List


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
    item_path = Path(args.item)
    if not item_path.exists():
        raise SystemExit(f"Item not found: {item_path}")

    lines = load_lines(item_path)
    missing = validate_ready(lines)
    if missing:
        raise SystemExit(f"Ready gate incomplete: {', '.join(missing)}")

    print("Ready gate OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
