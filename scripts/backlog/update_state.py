#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

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

STATE_ACTIONS = {
    "propose": "Proposed",
    "plan": "Planned",
    "ready": "Ready",
    "start": "InProgress",
    "review": "Review",
    "done": "Done",
    "block": "Blocked",
    "drop": "Dropped",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update backlog item state and append Worklog.")
    parser.add_argument("--item", required=True, help="Path to backlog item markdown file.")
    parser.add_argument("--state", help="Target state (e.g., Ready, InProgress).")
    parser.add_argument("--action", choices=sorted(STATE_ACTIONS.keys()), help="Action shortcut.")
    parser.add_argument("--message", help="Worklog message override.")
    parser.add_argument("--agent", default="codex", help="Worklog agent name.")
    parser.add_argument("--force", action="store_true", help="Skip Ready gate validation.")
    return parser.parse_args()


def load_lines(path: Path) -> List[str]:
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines: List[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_frontmatter(lines: List[str]) -> Tuple[int, int]:
    if not lines or lines[0].strip() != "---":
        return -1, -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return 0, idx
    return -1, -1


def update_frontmatter(lines: List[str], state: str, updated_date: str) -> List[str]:
    start, end = find_frontmatter(lines)
    if start == -1:
        raise ValueError("Frontmatter not found.")

    updated = False
    state_updated = False
    for idx in range(start + 1, end):
        if lines[idx].startswith("state:"):
            lines[idx] = f"state: {state}"
            state_updated = True
        if lines[idx].startswith("updated:"):
            lines[idx] = f"updated: {updated_date}"
            updated = True

    if not state_updated:
        raise ValueError("Frontmatter missing state field.")
    if not updated:
        raise ValueError("Frontmatter missing updated field.")
    return lines


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


def ensure_worklog(lines: List[str]) -> List[str]:
    for line in lines:
        if line.strip() == "# Worklog":
            return lines
    return lines + ["", "# Worklog", ""]


def append_worklog(lines: List[str], message: str, agent: str) -> List[str]:
    lines = ensure_worklog(lines)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"{timestamp} [agent={agent}] {message}"
    lines.append(entry)
    return lines


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

    if not args.state and not args.action:
        raise SystemExit("Provide --state or --action.")

    if args.state and args.action:
        raise SystemExit("Use only one of --state or --action.")

    target_state = args.state or STATE_ACTIONS[args.action]
    lines = load_lines(item_path)

    if target_state == "Ready" and not args.force:
        missing = validate_ready(lines)
        if missing:
            raise SystemExit(f"Ready gate incomplete: {', '.join(missing)}")

    updated_date = datetime.now().strftime("%Y-%m-%d")
    lines = update_frontmatter(lines, target_state, updated_date)

    message = args.message or f"State -> {target_state}."
    lines = append_worklog(lines, message, args.agent)

    write_lines(item_path, lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
