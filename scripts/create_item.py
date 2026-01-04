#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

backlog_entry = Path(__file__).resolve().parent / "backlog" / "create_item.py"
if __name__ == "__main__" and backlog_entry.exists():
    runpy.run_path(str(backlog_entry), run_name="__main__")
    raise SystemExit(0)

import argparse
import datetime
import re
import unicodedata
from typing import List, Optional


TYPE_MAP = {
    "epic": ("Epic", "EPIC", "epics"),
    "feature": ("Feature", "FTR", "features"),
    "userstory": ("UserStory", "USR", "userstories"),
    "task": ("Task", "TSK", "tasks"),
    "bug": ("Bug", "BUG", "bugs"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a backlog item from a template.")
    parser.add_argument(
        "--items-root",
        default="_kano/backlog/items",
        help="Backlog items root (default: _kano/backlog/items).",
    )
    parser.add_argument(
        "--backlog-root",
        help="Backlog root for index registry (default: parent of items root).",
    )
    parser.add_argument("--type", required=True, help="Epic|Feature|UserStory|Task|Bug")
    parser.add_argument("--title", required=True, help="Item title.")
    parser.add_argument("--parent", help="Parent item ID.")
    parser.add_argument("--priority", default="P2", help="Priority (default: P2).")
    parser.add_argument("--area", default="general", help="Area (default: general).")
    parser.add_argument("--iteration", default="null", help="Iteration value or null.")
    parser.add_argument("--tags", default="", help="Comma-separated tags.")
    parser.add_argument("--owner", default="null", help="Owner value or null.")
    parser.add_argument("--agent", required=True, help="Worklog agent name (required).")
    parser.add_argument("--project-name", help="Project name override.")
    parser.add_argument("--prefix", help="ID prefix override.")
    parser.add_argument(
        "--create-index",
        action="store_true",
        help="Create Epic index file (default for Epic).",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Skip Epic index file creation.",
    )
    parser.add_argument(
        "--index-registry",
        help="Path to indexes.md (default: <backlog-root>/_meta/indexes.md). Use 'none' to disable.",
    )
    parser.add_argument(
        "--worklog-message",
        default="Created from template.",
        help="Initial Worklog message.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print target path and exit.")
    return parser.parse_args()


def normalize_nullable(value: Optional[str]) -> str:
    if value is None:
        return "null"
    trimmed = value.strip()
    if trimmed.lower() in ("", "null", "none"):
        return "null"
    return trimmed


def yaml_list(values: List[str]) -> str:
    if not values:
        return "[]"
    escaped = [v.replace('"', '\\"') for v in values]
    inner = ", ".join(f"\"{v}\"" for v in escaped)
    return f"[{inner}]"


def read_project_name(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("PROJECT_NAME="):
            value = line.split("=", 1)[1].strip()
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            return value
    return None


def split_segments(name: str) -> List[str]:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    segments: List[str] = []
    for part in parts:
        if not part:
            continue
        segments.extend(re.findall(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+", part))
    return segments


def derive_prefix(name: str) -> str:
    segments = split_segments(name)
    letters = []
    for seg in segments:
        for ch in seg:
            if ch.isalpha():
                letters.append(ch)
                break
    prefix = "".join(letters)

    if len(prefix) == 1:
        seed = segments[0] if segments else name
        consonant = ""
        for ch in seed[1:]:
            if ch.isalpha() and ch.upper() not in "AEIOU":
                consonant = ch
                break
        if consonant:
            prefix += consonant
        else:
            for ch in seed[1:]:
                if ch.isalpha():
                    prefix += ch
                    break

    if len(prefix) < 2:
        letters = [ch for ch in name if ch.isalpha()]
        if len(letters) >= 2:
            prefix = letters[0] + letters[1]

    if not prefix:
        raise ValueError("Unable to derive prefix. Provide --prefix or --project-name.")

    return prefix.upper()


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "untitled"


def read_frontmatter_id(path: Path) -> Optional[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("id:"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def find_next_number(root: Path, prefix: str, type_code: str) -> int:
    pattern = re.compile(rf"{re.escape(prefix)}-{type_code}-(\d{{4}})")
    max_num = 0
    if not root.exists():
        return 1
    for path in root.rglob("*.md"):
        if path.name == "README.md" or path.name.endswith(".index.md"):
            continue
        item_id = read_frontmatter_id(path)
        match = pattern.search(item_id or path.name)
        if not match:
            continue
        number = int(match.group(1))
        if number > max_num:
            max_num = number
    return max_num + 1


def build_index_registry_path(backlog_root: Optional[Path], override: Optional[str]) -> Optional[Path]:
    if override:
        if override.lower() == "none":
            return None
        return Path(override)
    if backlog_root:
        return backlog_root / "_meta" / "indexes.md"
    return None


def update_index_registry(path: Path, item_id: str, index_file: str, updated: str, notes: str) -> None:
    if not path.exists():
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    if any(item_id in line for line in lines):
        return

    header_idx = None
    for idx, line in enumerate(lines):
        if line.strip().startswith("| type |"):
            header_idx = idx
            break

    if header_idx is None:
        lines.extend(["", "| type | item_id | index_file | updated | notes |", "| ---- | ------- | ---------- | ------- | ----- |"])
    elif header_idx + 1 >= len(lines) or "|" not in lines[header_idx + 1]:
        lines.insert(header_idx + 1, "| ---- | ------- | ---------- | ------- | ----- |")

    lines.append(f"| Epic | {item_id} | {index_file} | {updated} | {notes} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_item(
    item_id: str,
    item_type: str,
    title: str,
    priority: str,
    parent: str,
    area: str,
    iteration: str,
    tags: str,
    created: str,
    updated: str,
    owner: str,
    agent: str,
    message: str,
) -> str:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "---",
        f"id: {item_id}",
        f"type: {item_type}",
        f"title: \"{title}\"",
        "state: Proposed",
        f"priority: {priority}",
        f"parent: {parent}",
        f"area: {area}",
        f"iteration: {iteration}",
        f"tags: {tags}",
        f"created: {created}",
        f"updated: {updated}",
        f"owner: {owner}",
        "external:",
        "  azure_id: null",
        "  jira_key: null",
        "links:",
        "  relates: []",
        "  blocks: []",
        "  blocked_by: []",
        "decisions: []",
        "---",
        "",
        "# Context",
        "",
        "# Goal",
        "",
        "# Non-Goals",
        "",
        "# Approach",
        "",
        "# Alternatives",
        "",
        "# Acceptance Criteria",
        "",
        "# Risks / Dependencies",
        "",
        "# Worklog",
        "",
        f"{timestamp} [agent={agent}] {message}",
    ]
    return "\n".join(lines) + "\n"


def render_index(item_id: str, title: str, updated: str, backlog_root_label: str) -> str:
    lines = [
        "---",
        "type: Index",
        f"for: {item_id}",
        f"title: \"{title} Index\"",
        f"updated: {updated}",
        "---",
        "",
        "# MOC",
        "",
        "## Auto list (Dataview)",
        "",
        "```dataview",
        "table id, state, priority",
        f"from \"{backlog_root_label}/items/features\"",
        f"where parent = \"{item_id}\"",
        "sort priority asc",
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    type_key = args.type.strip().lower()
    if type_key not in TYPE_MAP:
        raise SystemExit(f"Unknown type: {args.type}. Use Epic, Feature, UserStory, Task, or Bug.")

    type_label, type_code, type_folder = TYPE_MAP[type_key]

    items_root = Path(args.items_root)
    if not items_root.is_absolute():
        items_root = (Path.cwd() / items_root).resolve()

    backlog_root = None
    if args.backlog_root:
        backlog_root = Path(args.backlog_root)
        if not backlog_root.is_absolute():
            backlog_root = (Path.cwd() / backlog_root).resolve()
    elif items_root.name == "items":
        backlog_root = items_root.parent

    prefix = args.prefix
    if not prefix:
        project_name = args.project_name or read_project_name(Path("config/profile.env"))
        if not project_name:
            raise SystemExit("PROJECT_NAME not found. Provide --project-name or --prefix.")
        prefix = derive_prefix(project_name)

    parent = normalize_nullable(args.parent)
    if type_label != "Epic" and parent == "null":
        print("Warning: non-Epic item without --parent.")

    next_number = find_next_number(items_root / type_folder, prefix, type_code)
    bucket = (next_number // 100) * 100
    bucket_str = f"{bucket:04d}"

    slug = slugify(args.title)
    item_id = f"{prefix}-{type_code}-{next_number:04d}"
    file_name = f"{item_id}_{slug}.md"
    item_path = items_root / type_folder / bucket_str / file_name

    if item_path.exists():
        raise SystemExit(f"Item already exists: {item_path}")

    if args.dry_run:
        print(f"ID: {item_id}")
        print(f"Path: {item_path}")
        return 0

    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    date = datetime.datetime.now().strftime("%Y-%m-%d")

    item_body = render_item(
        item_id=item_id,
        item_type=type_label,
        title=args.title,
        priority=args.priority,
        parent=parent,
        area=normalize_nullable(args.area),
        iteration=normalize_nullable(args.iteration),
        tags=yaml_list(tags),
        created=date,
        updated=date,
        owner=normalize_nullable(args.owner),
        agent=args.agent,
        message=args.worklog_message,
    )

    item_path.parent.mkdir(parents=True, exist_ok=True)
    item_path.write_text(item_body, encoding="utf-8")
    print(f"Created item: {item_path}")

    create_index = args.create_index or (type_label == "Epic" and not args.no_index)
    if type_label == "Epic" and create_index:
        index_path = item_path.with_suffix(".index.md")
        backlog_label = "_kano/backlog"
        if backlog_root:
            try:
                backlog_label = backlog_root.relative_to(Path.cwd()).as_posix()
            except ValueError:
                backlog_label = backlog_root.as_posix()
        index_body = render_index(item_id, args.title, date, backlog_label)
        index_path.write_text(index_body, encoding="utf-8")
        print(f"Created index: {index_path}")

        registry_path = build_index_registry_path(backlog_root, args.index_registry)
        if registry_path:
            registry_path = registry_path.resolve()
            index_rel = index_path
            try:
                index_rel = index_path.relative_to(Path.cwd())
            except ValueError:
                pass
            update_index_registry(
                registry_path,
                item_id=item_id,
                index_file=index_rel.as_posix(),
                updated=date,
                notes=args.title,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
