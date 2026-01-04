#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402


def allowed_roots_for_repo(repo_root: Path) -> List[Path]:
    return [
        (repo_root / "_kano" / "backlog").resolve(),
        (repo_root / "_kano" / "backlog_sandbox").resolve(),
    ]


def resolve_allowed_root(path: Path, allowed_roots: List[Path]) -> Optional[Path]:
    resolved = path.resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def ensure_under_allowed(path: Path, allowed_roots: List[Path]) -> None:
    if resolve_allowed_root(path, allowed_roots) is None:
        allowed = " or ".join(str(root) for root in allowed_roots)
        raise SystemExit(f"Item must be under {allowed}: {path}")


READY_SECTIONS = [
    "Context",
    "Goal",
    "Approach",
    "Acceptance Criteria",
    "Risks / Dependencies",
]

STATE_ORDER = [
    "Proposed",
    "Planned",
    "Ready",
    "InProgress",
    "Review",
    "Done",
    "Dropped",
]
STATE_RANK = {state: idx for idx, state in enumerate(STATE_ORDER)}
ACTIVE_STATES = {"InProgress", "Review", "Blocked"}
READY_STATES = {"Ready"}
PLANNED_STATES = {"Planned"}
PROPOSED_STATES = {"Proposed"}
DONE_STATES = {"Done"}
DROPPED_STATES = {"Dropped"}

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
    parser.add_argument("--agent", required=True, help="Worklog agent name (required).")
    parser.add_argument("--force", action="store_true", help="Skip Ready gate validation.")
    parser.add_argument(
        "--no-sync-parent",
        action="store_true",
        help="Disable forward-only parent state sync (default: sync enabled).",
    )
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


def strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
        return value[1:-1]
    return value


def parse_frontmatter(lines: List[str]) -> Dict[str, str]:
    start, end = find_frontmatter(lines)
    if start == -1:
        return {}
    data: Dict[str, str] = {}
    for line in lines[start + 1 : end]:
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        data[key.strip()] = strip_quotes(raw)
    return data


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


@dataclass
class ItemInfo:
    item_id: str
    item_type: str
    title: str
    state: str
    parent: str
    path: Path


def find_items_root(path: Path) -> Optional[Path]:
    for parent in path.parents:
        if parent.name == "items":
            return parent
    return None


def collect_items(root: Path) -> List[ItemInfo]:
    items: List[ItemInfo] = []
    for path in root.rglob("*.md"):
        if path.name == "README.md" or path.name.endswith(".index.md"):
            continue
        data = parse_frontmatter(load_lines(path))
        item_id = data.get("id", "").strip()
        if not item_id:
            continue
        items.append(
            ItemInfo(
                item_id=item_id,
                item_type=data.get("type", "").strip(),
                title=data.get("title", "").strip(),
                state=data.get("state", "").strip(),
                parent=data.get("parent", "").strip(),
                path=path,
            )
        )
    return items


def build_child_map(items: List[ItemInfo]) -> Dict[str, List[ItemInfo]]:
    children: Dict[str, List[ItemInfo]] = {}
    for item in items:
        if not item.parent or item.parent.lower() == "null":
            continue
        children.setdefault(item.parent, []).append(item)
    return children


def recommend_parent_state(children: List[ItemInfo]) -> Optional[str]:
    if not children:
        return None
    states = [child.state for child in children if child.state]
    if not states:
        return None
    if all(state in DONE_STATES for state in states):
        return "Done"
    if all(state in DROPPED_STATES for state in states):
        return "Dropped"
    if all(state in DONE_STATES.union(DROPPED_STATES) for state in states):
        return "Done"
    if any(state in ACTIVE_STATES for state in states):
        return "InProgress"
    if any(state in READY_STATES for state in states):
        return "Planned"
    if any(state in PLANNED_STATES for state in states):
        return "Planned"
    if any(state in PROPOSED_STATES for state in states):
        return "Proposed"
    return None


def advance_parent_state(
    parent: ItemInfo,
    target_state: str,
    agent: str,
    source_id: str,
) -> bool:
    current_state = parent.state or "Proposed"
    if current_state not in STATE_RANK or target_state not in STATE_RANK:
        return False
    if STATE_RANK[current_state] >= STATE_RANK[target_state]:
        return False
    lines = load_lines(parent.path)
    updated_date = datetime.now().strftime("%Y-%m-%d")
    lines = update_frontmatter(lines, target_state, updated_date)
    message = f"Auto-sync from child {source_id} -> {target_state}."
    lines = append_worklog(lines, message, agent)
    write_lines(parent.path, lines)
    parent.state = target_state
    return True


def get_unique_item(items_by_id: Dict[str, List[ItemInfo]], item_id: str) -> Optional[ItemInfo]:
    matches = items_by_id.get(item_id, [])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Warning: duplicate id {item_id}; skipping parent sync.")
    return None


def sync_parent_chain(
    children_map: Dict[str, List[ItemInfo]],
    items_by_id: Dict[str, List[ItemInfo]],
    child: ItemInfo,
    agent: str,
) -> None:
    parent_id = child.parent
    while parent_id and parent_id.lower() != "null":
        parent = get_unique_item(items_by_id, parent_id)
        if not parent:
            return
        desired = recommend_parent_state(children_map.get(parent_id, []))
        if desired:
            advance_parent_state(parent, desired, agent, child.item_id)
        parent_id = parent.parent


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    allowed_roots = allowed_roots_for_repo(repo_root)
    item_path = Path(args.item)
    if not item_path.is_absolute():
        item_path = (repo_root / item_path).resolve()
    ensure_under_allowed(item_path, allowed_roots)
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

    if not args.no_sync_parent:
        items_root = find_items_root(item_path)
        if items_root:
            items = collect_items(items_root)
            items_by_id: Dict[str, List[ItemInfo]] = {}
            for item in items:
                items_by_id.setdefault(item.item_id, []).append(item)
            child = next(
                (item for item in items if item.path.resolve() == item_path),
                None,
            )
            if child:
                children_map = build_child_map(items)
                sync_parent_chain(children_map, items_by_id, child, args.agent)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
