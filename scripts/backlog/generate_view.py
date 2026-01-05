#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from config_loader import get_config_value, load_config_with_defaults, validate_config  # noqa: E402


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


def ensure_under_allowed(path: Path, allowed_roots: List[Path], label: str) -> Path:
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(root) for root in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


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
        "--source",
        choices=["auto", "files", "sqlite"],
        default="auto",
        help="Data source (default: auto; prefer sqlite when index.enabled=true and DB exists).",
    )
    parser.add_argument(
        "--items-root",
        default="_kano/backlog/items",
        help="Backlog items root (default: _kano/backlog/items).",
    )
    parser.add_argument(
        "--backlog-root",
        help="Backlog root path override (default: parent of --items-root).",
    )
    parser.add_argument(
        "--config",
        help="Optional config path override (default: KANO_BACKLOG_CONFIG_PATH or <backlog-root>/_config/config.json).",
    )
    parser.add_argument(
        "--db-path",
        help="SQLite DB path override (default: config index.path or <backlog-root>/_index/backlog.sqlite3).",
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
        default="InProgress Work",
        help="Document title (default: InProgress Work).",
    )
    parser.add_argument(
        "--source-label",
        help="Optional label shown in output (default: --items-root).",
    )
    return parser.parse_args()


def resolve_config_for_backlog_root(repo_root: Path, backlog_root: Path, cli_config: Optional[str]) -> Optional[str]:
    if cli_config is not None:
        return cli_config
    if os.getenv("KANO_BACKLOG_CONFIG_PATH"):
        return None
    candidate = backlog_root / "_config" / "config.json"
    if candidate.exists():
        return str(candidate)
    return None


def resolve_db_path(repo_root: Path, backlog_root: Path, config: Dict[str, object], cli_db_path: Optional[str]) -> Path:
    db_path_raw = cli_db_path or get_config_value(config, "index.path")
    if not db_path_raw:
        db_path_raw = str((backlog_root / "_index" / "backlog.sqlite3").resolve())
    db_path = Path(str(db_path_raw))
    if not db_path.is_absolute():
        db_path = (repo_root / db_path).resolve()
    return db_path


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


def open_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA query_only = ON")
    return conn


def collect_items_from_sqlite(
    repo_root: Path,
    db_path: Path,
    allowed_groups: List[str],
) -> Dict[str, Dict[str, List[Tuple[str, str, Path]]]]:
    groups: Dict[str, Dict[str, List[Tuple[str, str, Path]]]] = {}
    with open_readonly(db_path) as conn:
        rows = conn.execute("SELECT id, type, state, title, source_path FROM items").fetchall()
    for item_id, item_type, state, title, source_path in rows:
        item_id = str(item_id or "").strip()
        item_type = str(item_type or "").strip()
        state = str(state or "").strip()
        title = str(title or "").strip()
        if not item_id or not item_type or not state:
            continue
        group = STATE_GROUPS.get(state)
        if group not in allowed_groups:
            continue
        source = Path(str(source_path or "").replace("\\", "/"))
        path = (repo_root / source).resolve()
        groups.setdefault(group, {}).setdefault(item_type, []).append((item_id, title, path))
    return groups


def pluralize_label(item_type: str) -> str:
    if item_type in TYPE_LABELS:
        return TYPE_LABELS[item_type]
    if item_type.endswith("s"):
        return item_type
    return f"{item_type}s"


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
        all_types = list(group_items.keys())
        type_order = TYPE_ORDER + sorted([t for t in all_types if t not in TYPE_ORDER])
        has_any = any(group_items.get(item_type) for item_type in type_order)
        if not has_any:
            lines.append("_No items._")
            lines.append("")
            continue
        for item_type in type_order:
            items = group_items.get(item_type, [])
            if not items:
                continue
            label = pluralize_label(item_type)
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
    repo_root = Path.cwd().resolve()
    allowed_roots = allowed_roots_for_repo(repo_root)
    allowed_groups = [group.strip() for group in args.groups.split(",") if group.strip()]
    items_root = Path(args.items_root)
    if not items_root.is_absolute():
        items_root = (repo_root / items_root).resolve()
    items_root_root = ensure_under_allowed(items_root, allowed_roots, "items-root")

    backlog_root = Path(args.backlog_root) if args.backlog_root else items_root.parent
    if not backlog_root.is_absolute():
        backlog_root = (repo_root / backlog_root).resolve()
    backlog_root_root = ensure_under_allowed(backlog_root, allowed_roots, "backlog-root")
    if backlog_root_root != items_root_root:
        raise SystemExit("items-root and backlog-root must share the same root.")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()
    output_root = ensure_under_allowed(output_path, allowed_roots, "output")
    if output_root != items_root_root:
        raise SystemExit("items-root and output must share the same root.")

    config_path = resolve_config_for_backlog_root(repo_root, backlog_root, args.config)
    config = load_config_with_defaults(repo_root=repo_root, config_path=config_path)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    db_path = resolve_db_path(repo_root, backlog_root, config, args.db_path)
    ensure_under_allowed(db_path, allowed_roots, "db-path")

    index_enabled = bool(get_config_value(config, "index.enabled", False))
    use_sqlite = False
    if args.source == "sqlite":
        use_sqlite = True
    elif args.source == "files":
        use_sqlite = False
    else:
        use_sqlite = index_enabled and db_path.exists()

    source_label = args.source_label or args.items_root
    if use_sqlite:
        if not db_path.exists():
            raise SystemExit(f"DB does not exist: {db_path}\nRun scripts/indexing/build_sqlite_index.py first.")
        source_label = args.source_label or f"sqlite:{db_path.as_posix()}"
        groups = collect_items_from_sqlite(repo_root, db_path, allowed_groups)
    else:
        if args.source == "auto" and index_enabled and not db_path.exists():
            source_label = args.source_label or f"files:{args.items_root} (sqlite missing, fallback)"
        groups = collect_items(items_root, allowed_groups)
    output_lines = format_items(groups, output_path, args.title, allowed_groups, source_label)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
