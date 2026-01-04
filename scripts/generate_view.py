#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

backlog_entry = Path(__file__).resolve().parent / "backlog" / "generate_view.py"
if __name__ == "__main__" and backlog_entry.exists():
    runpy.run_path(str(backlog_entry), run_name="__main__")
    raise SystemExit(0)

import argparse
import datetime
import os
from typing import Dict, List, Tuple


STATE_GROUPS = {
    "Proposed": "New",
    "Planned": "New",
    "Ready": "New",
    "New": "New",
    "InProgress": "InProgress",
    "Review": "InProgress",
    "Blocked": "InProgress",
    "Done": "Done",
    "Dropped": "Done",
}

TYPE_ORDER = ["Epic", "Feature", "UserStory", "Task", "Bug"]
TYPE_LABELS = {
    "Epic": "Epics",
    "Feature": "Features",
    "UserStory": "UserStories",
    "Task": "Tasks",
    "Bug": "Bugs",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Markdown view for backlog items.")
    parser.add_argument(
        "--items-root",
        default="_kano/backlog/items",
        help="Backlog items root (default: _kano/backlog/items).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output markdown file path.",
    )
    parser.add_argument(
        "--groups",
        default="New,InProgress",
        help="Comma-separated groups to include (default: New,InProgress).",
    )
    parser.add_argument(
        "--title",
        default="Active Work",
        help="Document title (default: Active Work).",
    )
    parser.add_argument(
        "--source-label",
        help="Optional label shown in output (default: --items-root).",
    )
    return parser.parse_args()


def strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
        return value[1:-1]
    return value


def parse_frontmatter(path: Path) -> Dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        value = strip_quotes(raw)
        data[key] = value
    return data


def collect_items(
    root: Path,
    allowed_groups: List[str],
) -> Dict[str, Dict[str, List[Tuple[str, str, Path]]]]:
    groups: Dict[str, Dict[str, List[Tuple[str, str, Path]]]] = {}
    for path in root.rglob("*.md"):
        if path.name == "README.md" or path.name.endswith(".index.md"):
            continue
        data = parse_frontmatter(path)
        item_id = data.get("id", "").strip()
        item_type = data.get("type", "").strip()
        state = data.get("state", "").strip()
        title = data.get("title", "").strip()
        if not item_id or not item_type or not state:
            continue
        group = STATE_GROUPS.get(state)
        if group not in allowed_groups:
            continue
        groups.setdefault(group, {}).setdefault(item_type, []).append((item_id, title, path))
    return groups


def format_items(
    groups: Dict[str, Dict[str, List[Tuple[str, str, Path]]]],
    output_path: Path,
    title: str,
    allowed_groups: List[str],
    source_label: str,
) -> List[str]:
    out_dir = output_path.parent
    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"Generated: {timestamp}")
    lines.append(f"Source: {source_label}")
    lines.append("")

    for group in allowed_groups:
        lines.append(f"## {group}")
        lines.append("")
        group_items = groups.get(group, {})
        has_any = any(group_items.get(item_type) for item_type in TYPE_ORDER)
        if not has_any:
            lines.append("_No items._")
            lines.append("")
            continue
        for item_type in TYPE_ORDER:
            items = group_items.get(item_type, [])
            if not items:
                continue
            label = TYPE_LABELS.get(item_type, item_type)
            lines.append(f"### {label}")
            lines.append("")
            for item_id, title, path in sorted(items, key=lambda item: item[0]):
                text = f"{item_id} {title}".strip()
                rel = os.path.relpath(path, out_dir).replace("\\", "/")
                lines.append(f"- [{text}]({rel})")
            lines.append("")
    return lines


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    allowed_groups = [group.strip() for group in args.groups.split(",") if group.strip()]
    items_root = Path(args.items_root)
    if not items_root.is_absolute():
        items_root = (repo_root / items_root).resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()

    source_label = args.source_label or args.items_root
    groups = collect_items(items_root, allowed_groups)
    output_lines = format_items(groups, output_path, args.title, allowed_groups, source_label)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
