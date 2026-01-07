#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from lib.index import BacklogIndex
from lib.resolver import resolve_ref

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from config_loader import get_config_value, load_config_with_defaults, validate_config  # noqa: E402
from product_args import add_product_arguments, get_product_and_sandbox_flags  # noqa: E402
from context import get_context  # noqa: E402
from lib.utils import parse_frontmatter as parse_fm_yaml  # noqa: E402


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
    parser = argparse.ArgumentParser(description="Update backlog work item state and append Worklog.")
    parser.add_argument("--item", required=True, help="Path/reference to backlog work item markdown file.")
    parser.add_argument("--state", help="Target state (e.g., Ready, InProgress).")
    parser.add_argument("--action", choices=sorted(STATE_ACTIONS.keys()), help="Action shortcut.")
    parser.add_argument("--message", help="Worklog message override.")
    parser.add_argument("--agent", required=True, help="Worklog agent name (required).")
    parser.add_argument(
        "--config",
        help=(
            "Optional config path override (default: KANO_BACKLOG_CONFIG_PATH or _kano/backlog/_config/config.json). "
            "Controls auto-refresh behavior."
        ),
    )
    parser.add_argument("--force", action="store_true", help="Skip Ready gate validation.")
    parser.add_argument(
        "--no-sync-parent",
        action="store_true",
        help="Disable forward-only parent state sync (default: sync enabled).",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Disable automatic dashboard refresh for this invocation.",
    )
    add_product_arguments(parser)
    return parser.parse_args()


def should_auto_refresh(config: dict) -> bool:
    return bool(get_config_value(config, "views.auto_refresh", True))


def refresh_dashboards(backlog_root: Path, agent: str, config_path: Optional[str], product: Optional[str] = None) -> None:
    refresh_script = Path(__file__).resolve().parent / "view_refresh_dashboards.py"
    cmd = [sys.executable, str(refresh_script), "--backlog-root", str(backlog_root), "--agent", agent]
    if config_path:
        cmd.extend(["--config", config_path])
    if product:
        cmd.extend(["--product", product])
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "Failed to refresh dashboards.")


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


def update_frontmatter(lines: List[str], state: str, updated_date: str, owner: Optional[str] = None) -> List[str]:
    start, end = find_frontmatter(lines)
    if start == -1:
        raise ValueError("Frontmatter not found.")

    updated = False
    state_updated = False
    owner_updated = False
    owner_exists = False
    for idx in range(start + 1, end):
        if lines[idx].startswith("state:"):
            lines[idx] = f"state: {state}"
            state_updated = True
        if lines[idx].startswith("updated:"):
            lines[idx] = f"updated: {updated_date}"
            updated = True
        if lines[idx].startswith("owner:"):
            owner_exists = True
            if owner is not None:
                lines[idx] = f"owner: {owner}"
                owner_updated = True

    if not state_updated:
        raise ValueError("Frontmatter missing state field.")
    if not updated:
        raise ValueError("Frontmatter missing updated field.")
    
    # If owner should be set but field doesn't exist, add it before the closing ---
    if owner is not None and not owner_exists:
        # Insert owner field before the closing ---
        lines.insert(end, f"owner: {owner}")
        owner_updated = True
    
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
    data = parse_frontmatter(lines)
    missing = []

    # Check parent (required for non-Epic items)
    parent = data.get("parent", "").strip()
    item_type = data.get("type", "").strip()
    if item_type != "Epic" and (not parent or parent.lower() == "null"):
        missing.append("parent field (must not be null for non-Epic items)")

    for name in READY_SECTIONS:
        if name not in sections or not section_has_content(sections[name]):
            missing.append(f"Section: {name}")
    return missing


def check_blocked_by(item_path: Path, backlog_root: Path, product_name: Optional[str] = None) -> List[str]:
    content = item_path.read_text(encoding="utf-8")
    fm, _, _ = parse_fm_yaml(content)

    links = fm.get("links", {})
    if not isinstance(links, dict):
        return []

    blocked_by = links.get("blocked_by", [])
    if not blocked_by:
        return []

    if isinstance(blocked_by, str):
        blocked_by = [blocked_by]

    index = BacklogIndex(backlog_root)
    blocking_items = []

    # We consider Done/Closed/Dropped/Completed as resolved
    resolved_states = {"Done", "Closed", "Dropped", "Completed"}

    for ref in blocked_by:
        # Decide resolution strategy based on ref format
        is_full_uid = len(ref) == 36 and "-" in ref
        is_id_uidshort = "@" in ref

        # For collision-safe refs (uid/id@uidshort), allow cross-product resolution
        if is_full_uid or is_id_uidshort:
            matches = resolve_ref(ref, index, product=None)
        else:
            # Display IDs resolve within current product by default
            matches = resolve_ref(ref, index, product=product_name)
        if not matches:
            hint = (
                "use id@uidshort or full uid for cross-product references"
                if (product_name is not None)
                else "ensure the display ID exists"
            )
            blocking_items.append(f"{ref} (not found; {hint})")
            continue

        # Ambiguous reference: suggest id@uidshort options
        if len(matches) > 1:
            suggestions = ", ".join(f"{m.id}@{m.uidshort}" for m in matches if m.uidshort)
            blocking_items.append(f"{ref} (ambiguous; try {suggestions})")
            # Skip checking states for ambiguous refs; require disambiguation first
            continue

        for match in matches:
            if match.state not in resolved_states:
                blocking_items.append(f"{match.id} ({match.state})")

    return blocking_items


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
    # Don't change owner when auto-syncing parent state
    lines = update_frontmatter(lines, target_state, updated_date, owner=None)
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
    config = load_config_with_defaults(repo_root=repo_root, config_path=args.config)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    allowed_roots = allowed_roots_for_repo(repo_root)
    item_path = Path(args.item)
    if not item_path.is_absolute():
        item_path = (repo_root / item_path).resolve()
    # Try resolving if path not recognized
    if resolve_allowed_root(item_path, allowed_roots) is None or not item_path.exists():
        backlog_root = repo_root / "_kano" / "backlog"
        if backlog_root.exists():
            try:
                index = BacklogIndex(backlog_root)
                matches = resolve_ref(args.item, index)
                if len(matches) == 1:
                    item_path = matches[0].path
                    print(f"Resolved '{args.item}' to {item_path.name}")
                elif len(matches) > 1:
                    raise SystemExit(f"Ambiguous reference: '{args.item}' matches {len(matches)} items.")
            except ImportError:
                 pass

    ensure_under_allowed(item_path, allowed_roots)
    if not item_path.exists():
        raise SystemExit(f"Item not found: {item_path}")

    if not args.state and not args.action:
        raise SystemExit("Provide --state or --action.")

    if args.state and args.action:
        raise SystemExit("Use only one of --state or --action.")

    target_state = args.state or STATE_ACTIONS[args.action]
    lines = load_lines(item_path)
    
    # Parse current frontmatter to check owner and state
    frontmatter = parse_frontmatter(lines)
    current_state = frontmatter.get("state", "").strip()
    current_owner = frontmatter.get("owner", "").strip()
    # Validate parent resolution within current product to avoid ID collisions
    item_type = frontmatter.get("type", "").strip()
    parent_ref = frontmatter.get("parent", "").strip()
    if not args.force and item_type and item_type != "Epic" and parent_ref and parent_ref.lower() != "null":
        ctx = get_context(product_arg=args.product, repo_root=repo_root)
        platform_root = ctx["platform_root"]
        product_name = ctx["product_name"]
        index = BacklogIndex(platform_root)
        matches = resolve_ref(parent_ref, index, product=product_name)
        if not matches:
            raise SystemExit(
                (
                    "Parent not found in current product. Parent is intended to be intra-product. "
                    "If you need a cross-product relationship, use links.relates/blocks/blocked_by "
                    "with a collision-safe ref (id@uidshort or full uid)."
                )
            )
        if len(matches) > 1:
            raise SystemExit(
                (
                    "Ambiguous parent reference (multiple items share this display ID in the current product). "
                    "Keep parent intra-product and use a unique parent id; for cross-product relationships, use links.* "
                    "with id@uidshort or full uid."
                )
            )
    
    # Conflict guard: if item is InProgress and owned by someone else, reject
    if current_state == "InProgress" and current_owner and current_owner.lower() != "null":
        if current_owner != args.agent:
            raise SystemExit(
                f"Item is already InProgress and owned by '{current_owner}'. "
                f"Only the owner can update this item. Current agent: '{args.agent}'."
            )
    
    # Auto-assign owner when moving to InProgress
    owner_to_set = None
    if target_state == "InProgress":
        # If no owner or owner is null, set to current agent
        if not current_owner or current_owner.lower() == "null":
            owner_to_set = args.agent
        # If already owned by current agent, keep it
        elif current_owner == args.agent:
            owner_to_set = args.agent
        # If owned by someone else but state is not InProgress yet, this shouldn't happen
        # (we already checked above), but handle gracefully
        else:
            owner_to_set = current_owner

    if target_state == "InProgress" and not args.force:
        # Resolve backlog_root for index
        ctx = get_context(product_arg=args.product, repo_root=repo_root)
        platform_root = ctx["platform_root"]
        product_name = ctx["product_name"]

        blocking = check_blocked_by(item_path, platform_root, product_name)
        if blocking:
            print("Error: Work item is blocked by the following incomplete items:")
            for b in blocking:
                print(f"  - {b}")
            raise SystemExit("Aborting state transition due to unresolved dependencies. Use --force to override.")

    if target_state == "Ready" and not args.force:
        missing = validate_ready(lines)
        if missing:
            raise SystemExit(f"Ready gate incomplete: {', '.join(missing)}")

    updated_date = datetime.now().strftime("%Y-%m-%d")
    lines = update_frontmatter(lines, target_state, updated_date, owner=owner_to_set)

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

    if not args.no_refresh and should_auto_refresh(config):
        ctx = get_context(product_arg=args.product, repo_root=repo_root)
        platform_root = ctx["platform_root"]
        product_name = ctx["product_name"]
        refresh_dashboards(
            backlog_root=platform_root,
            agent=args.agent,
            config_path=args.config,
            product=product_name,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
