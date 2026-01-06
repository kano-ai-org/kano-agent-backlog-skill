#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from config_loader import (  # noqa: E402
    allowed_roots_for_repo,
    get_config_value,
    load_config_with_defaults,
    resolve_allowed_root,
    validate_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a rebuildable SQLite index for file-first backlog items."
    )
    parser.add_argument(
        "--backlog-root",
        default="_kano/backlog",
        help="Backlog root path (default: _kano/backlog).",
    )
    parser.add_argument(
        "--config",
        help=(
            "Optional config path override (must be under allowed roots). "
            "When omitted, uses KANO_BACKLOG_CONFIG_PATH if set, otherwise `<backlog-root>/_config/config.json` when present."
        ),
    )
    parser.add_argument(
        "--db-path",
        help=(
            "SQLite DB path override. If omitted, uses config index.path or defaults to "
            "`<sandbox.root>/_index/backlog.sqlite3`."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["rebuild", "incremental"],
        help="Index mode override (default: config index.mode).",
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Agent identity running the script (required, used for auditability).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without writing the database.",
    )
    return parser.parse_args()


def ensure_under_allowed(path: Path, allowed_roots: List[Path], label: str) -> Path:
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(root) for root in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
        return value[1:-1]
    return value


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in ("null", "Null", "NULL", "~"):
        return None
    if value in ("true", "True", "TRUE"):
        return True
    if value in ("false", "False", "FALSE"):
        return False
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except Exception:
            return strip_quotes(value)
    return strip_quotes(value)


def find_frontmatter_block(lines: List[str]) -> Optional[Tuple[int, int]]:
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return 0, i
    return None


def parse_frontmatter_yaml(lines: List[str]) -> Dict[str, Any]:
    block = find_frontmatter_block(lines)
    if block is None:
        return {}
    start, end = block
    raw = lines[start + 1 : end]
    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Any]] = [(0, root)]

    def current_container(indent: int) -> Any:
        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()
        return stack[-1][1]

    for raw_line in raw:
        if not raw_line.strip():
            continue
        line = raw_line.rstrip("\n")
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        container = current_container(indent)

        if stripped.startswith("- "):
            item = parse_scalar(stripped[2:].strip())
            if not isinstance(container, list):
                continue
            container.append(item)
            continue

        if ":" not in stripped:
            continue
        key, rest = stripped.split(":", 1)
        key = key.strip()
        value_raw = rest.strip()

        if value_raw == "":
            new_obj: Dict[str, Any] = {}
            if isinstance(container, dict):
                container[key] = new_obj
                stack.append((indent + 2, new_obj))
            continue

        value = parse_scalar(value_raw)
        if isinstance(container, dict):
            container[key] = value
            if isinstance(value, list):
                stack.append((indent + 2, value))
        # Lists of dicts are not required for current frontmatter patterns.
    return root


def parse_worklog_entries(lines: List[str]) -> List[Dict[str, Optional[str]]]:
    entries: List[Dict[str, Optional[str]]] = []
    in_worklog = False
    for line in lines:
        if line.startswith("# "):
            in_worklog = line.strip() == "# Worklog"
            continue
        if not in_worklog:
            continue
        if not line.strip():
            continue

        raw_line = line.rstrip("\n")
        agent: Optional[str] = None
        occurred_at: Optional[str] = None
        message = raw_line

        # Best-effort: "YYYY-MM-DD HH:MM [agent=NAME] message"
        parts = raw_line.split(" ", 2)
        if len(parts) >= 2 and len(parts[0]) == 10 and parts[0][4] == "-" and parts[0][7] == "-":
            # date only or date+time
            if len(parts) >= 3 and len(parts[1]) >= 4 and ":" in parts[1]:
                occurred_at = f"{parts[0]} {parts[1][:5]}"
                message = parts[2]
            else:
                occurred_at = parts[0]
                message = raw_line[len(parts[0]) :].lstrip()

        if "[agent=" in message:
            prefix, rest = message.split("[agent=", 1)
            if "]" in rest:
                agent = rest.split("]", 1)[0].strip()
                message = (prefix + rest.split("]", 1)[1]).strip()

        entries.append(
            {
                "occurred_at": occurred_at,
                "agent": agent,
                "message": message.strip(),
                "raw_line": raw_line,
            }
        )
    return entries


@dataclass(frozen=True)
class IndexedItem:
    item_id: str
    item_type: str
    title: str
    state: Optional[str]
    priority: Optional[str]
    parent_id: Optional[str]
    area: Optional[str]
    iteration: Optional[str]
    owner: Optional[str]
    created: Optional[str]
    updated: Optional[str]
    source_path: str
    product: str
    content_sha256: str
    frontmatter_json: str
    tags: List[str]
    links: List[Tuple[str, str]]
    decisions: List[str]
    worklog_entries: List[Dict[str, Optional[str]]]


def normalize_path(repo_root: Path, path: Path) -> str:
    rel = path.resolve().relative_to(repo_root.resolve())
    return str(rel).replace("\\", "/")


def extract_product_from_path(source_path: str, platform_root: Optional[Path] = None) -> str:
    """Extract product name from a normalized source path.
    
    Path patterns:
    - "products/kano-agent-backlog-skill/items/..." -> "kano-agent-backlog-skill"
    - "_kano/backlog/products/kano-agent-backlog-skill/items/..." -> "kano-agent-backlog-skill"
    - "sandboxes/test-skill/items/..." -> "test-skill"
    - "_kano/backlog/sandboxes/test-skill/items/..." -> "test-skill"
    - "items/..." (legacy) -> "kano-agent-backlog-skill" (default)
    - "_kano/backlog/items/..." (legacy) -> "kano-agent-backlog-skill" (default)
    
    Args:
        source_path: Normalized path (forward slashes, relative).
        platform_root: Not used, kept for compatibility.
        
    Returns:
        Product name extracted from path.
    """
    parts = source_path.split("/")
    for i, part in enumerate(parts):
        if part == "products" and i + 1 < len(parts):
            return parts[i + 1]
        elif part == "sandboxes" and i + 1 < len(parts):
            return parts[i + 1]
    # Legacy: items/ without products/ or sandboxes/ parent
    return "kano-agent-backlog-skill"


def extract_item(
    repo_root: Path,
    path: Path,
) -> Optional[IndexedItem]:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    fm = parse_frontmatter_yaml(lines)
    item_id = str(fm.get("id") or "").strip()
    item_type = str(fm.get("type") or "").strip()
    title = str(fm.get("title") or "").strip().strip("\"")
    if not item_id or not item_type or not title:
        return None

    state = fm.get("state")
    priority = fm.get("priority")
    parent_id = fm.get("parent")
    area = fm.get("area")
    iteration = fm.get("iteration")
    owner = fm.get("owner")
    created = fm.get("created")
    updated = fm.get("updated")

    tags_raw = fm.get("tags") or []
    tags: List[str] = []
    if isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    elif isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    links: List[Tuple[str, str]] = []
    if isinstance(parent_id, str) and parent_id.strip():
        links.append(("parent", parent_id.strip()))
    links_obj = fm.get("links")
    if isinstance(links_obj, dict):
        for relation in ("relates", "blocks", "blocked_by"):
            targets = links_obj.get(relation)
            if isinstance(targets, list):
                for t in targets:
                    target = str(t).strip()
                    if target:
                        links.append((relation, target))

    external = fm.get("external")
    if isinstance(external, dict):
        azure_id = external.get("azure_id")
        jira_key = external.get("jira_key")
        if azure_id not in (None, "", "null"):
            links.append(("external", f"azure:{azure_id}"))
        if jira_key not in (None, "", "null"):
            links.append(("external", f"jira:{jira_key}"))

    decisions_raw = fm.get("decisions") or []
    decisions: List[str] = []
    if isinstance(decisions_raw, list):
        decisions = [str(d).strip() for d in decisions_raw if str(d).strip()]
    elif isinstance(decisions_raw, str):
        decisions = [decisions_raw.strip()] if decisions_raw.strip() else []

    worklog_entries = parse_worklog_entries(lines)
    source_path = normalize_path(repo_root, path)
    product = extract_product_from_path(source_path)
    frontmatter_json = json.dumps(fm, ensure_ascii=False, sort_keys=True)

    return IndexedItem(
        item_id=item_id,
        item_type=item_type,
        title=title,
        state=str(state).strip() if state is not None else None,
        priority=str(priority).strip() if priority is not None else None,
        parent_id=str(parent_id).strip() if parent_id is not None else None,
        area=str(area).strip() if area is not None else None,
        iteration=str(iteration).strip() if iteration is not None else None,
        owner=str(owner).strip() if owner is not None else None,
        created=str(created).strip() if created is not None else None,
        updated=str(updated).strip() if updated is not None else None,
        source_path=source_path,
        product=product,
        content_sha256=sha256_text(content),
        frontmatter_json=frontmatter_json,
        tags=tags,
        links=links,
        decisions=decisions,
        worklog_entries=worklog_entries,
    )


def load_schema_sql() -> str:
    skill_root = Path(__file__).resolve().parents[2]
    schema_path = skill_root / "references" / "indexing_schema.sql"
    return schema_path.read_text(encoding="utf-8")


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(load_schema_sql())
    conn.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("schema_version", "1"))


def clear_all(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM worklog_entries")
    conn.execute("DELETE FROM item_decisions")
    conn.execute("DELETE FROM item_links")
    conn.execute("DELETE FROM item_tags")
    conn.execute("DELETE FROM items")


def upsert_item(conn: sqlite3.Connection, item: IndexedItem, known_ids: Optional[set[str]] = None) -> None:
    parent_id = item.parent_id
    if known_ids is not None and parent_id and parent_id not in known_ids:
        parent_id = None
    conn.execute(
        """
        INSERT INTO items(
          id, product, type, title, state, priority, parent_id, area, iteration, owner,
          created, updated, source_path, content_sha256, frontmatter_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(product, id) DO UPDATE SET
          type=excluded.type,
          title=excluded.title,
          state=excluded.state,
          priority=excluded.priority,
          parent_id=excluded.parent_id,
          area=excluded.area,
          iteration=excluded.iteration,
          owner=excluded.owner,
          created=excluded.created,
          updated=excluded.updated,
          source_path=excluded.source_path,
          content_sha256=excluded.content_sha256,
          frontmatter_json=excluded.frontmatter_json
        """,
        (
            item.item_id,
            item.product,
            item.item_type,
            item.title,
            item.state,
            item.priority,
            parent_id,
            item.area,
            item.iteration,
            item.owner,
            item.created,
            item.updated,
            item.source_path,
            item.content_sha256,
            item.frontmatter_json,
        ),
    )

    conn.execute("DELETE FROM item_tags WHERE item_id = ?", (item.item_id,))
    conn.execute("DELETE FROM item_links WHERE item_id = ?", (item.item_id,))
    conn.execute("DELETE FROM item_decisions WHERE item_id = ?", (item.item_id,))
    conn.execute("DELETE FROM worklog_entries WHERE item_id = ?", (item.item_id,))

    conn.executemany(
        "INSERT OR IGNORE INTO item_tags(item_id, tag) VALUES(?, ?)",
        [(item.item_id, tag) for tag in item.tags],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO item_links(item_id, relation, target) VALUES(?, ?, ?)",
        [(item.item_id, rel, tgt) for rel, tgt in item.links],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO item_decisions(item_id, decision_ref) VALUES(?, ?)",
        [(item.item_id, ref) for ref in item.decisions],
    )
    conn.executemany(
        "INSERT INTO worklog_entries(item_id, occurred_at, agent, message, raw_line) VALUES(?, ?, ?, ?, ?)",
        [
            (
                item.item_id,
                e.get("occurred_at"),
                e.get("agent"),
                e.get("message") or "",
                e.get("raw_line") or "",
            )
            for e in item.worklog_entries
        ],
    )


def collect_indexable_items(repo_root: Path, md_files: Sequence[Path]) -> List[IndexedItem]:
    items: List[IndexedItem] = []
    for path in md_files:
        item = extract_item(repo_root, path)
        if item is None:
            continue
        items.append(item)
    return items


def order_items_for_fk(items: Sequence[IndexedItem]) -> List[IndexedItem]:
    items_by_id = {item.item_id: item for item in items}
    memo: Dict[str, int] = {}
    visiting: set[str] = set()

    def depth(item_id: str) -> int:
        if item_id in memo:
            return memo[item_id]
        if item_id in visiting:
            memo[item_id] = 0
            return 0
        visiting.add(item_id)
        item = items_by_id.get(item_id)
        if not item or not item.parent_id or item.parent_id not in items_by_id:
            memo[item_id] = 0
        else:
            memo[item_id] = 1 + depth(item.parent_id)
        visiting.remove(item_id)
        return memo[item_id]

    def type_rank(item_type: str) -> int:
        order = {"Epic": 0, "Feature": 1, "UserStory": 2, "Story": 2, "Task": 3, "SubTask": 4, "Bug": 4}
        return order.get(item_type, 99)

    return sorted(items, key=lambda it: (depth(it.item_id), type_rank(it.item_type), it.item_id))


def warn_missing_parents(items: Sequence[IndexedItem]) -> None:
    ids = {item.item_id for item in items}
    missing = sorted({item.parent_id for item in items if item.parent_id and item.parent_id not in ids})
    if missing:
        print(f"Warning: {len(missing)} parent IDs not found in items; parent_id will be stored as NULL for those rows.")


def read_existing_hashes(conn: sqlite3.Connection) -> Dict[str, str]:
    rows = conn.execute("SELECT source_path, content_sha256 FROM items").fetchall()
    return {str(row[0]): str(row[1] or "") for row in rows}


def delete_missing(conn: sqlite3.Connection, current_paths: Iterable[str]) -> int:
    current = set(current_paths)
    rows = conn.execute("SELECT id, source_path FROM items").fetchall()
    removed = 0
    for item_id, source_path in rows:
        if str(source_path) not in current:
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
            removed += 1
    return removed


def main() -> int:
    args = parse_args()
    _ = args.agent  # required; recorded via command args in audit logs

    repo_root = Path.cwd().resolve()
    allowed_roots = allowed_roots_for_repo(repo_root)

    backlog_root = Path(args.backlog_root)
    if not backlog_root.is_absolute():
        backlog_root = (repo_root / backlog_root).resolve()
    root = ensure_under_allowed(backlog_root, allowed_roots, "backlog-root")

    config_path: Optional[str] = args.config
    if config_path is None and os.getenv("KANO_BACKLOG_CONFIG_PATH"):
        config_path = None
    elif config_path is None:
        default_for_root = backlog_root / "_config" / "config.json"
        if default_for_root.exists():
            config_path = str(default_for_root)

    config = load_config_with_defaults(repo_root=repo_root, config_path=config_path)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    items_root = (backlog_root / "items").resolve()
    if ensure_under_allowed(items_root, allowed_roots, "items-root") != root:
        raise SystemExit("items-root must share the same root as backlog-root.")

    db_path_raw = args.db_path or get_config_value(config, "index.path")
    if not db_path_raw:
        db_path_raw = str((backlog_root / "_index" / "backlog.sqlite3").resolve())
    db_path = Path(db_path_raw)
    if not db_path.is_absolute():
        db_path = (repo_root / db_path).resolve()
    ensure_under_allowed(db_path, allowed_roots, "db-path")

    mode = args.mode or str(get_config_value(config, "index.mode") or "rebuild")
    if mode not in ("rebuild", "incremental"):
        raise SystemExit("index.mode must be rebuild or incremental.")

    process_profile = str(get_config_value(config, "process.profile") or get_config_value(config, "process.path") or "")

    md_files = sorted(
        p for p in items_root.rglob("*.md") if p.name != "README.md" and not p.name.endswith(".index.md")
    )

    print(f"Backlog root: {backlog_root}")
    print(f"Items: {items_root} ({len(md_files)} files)")
    print(f"DB path: {db_path}")
    print(f"Mode: {mode}")
    if not bool(get_config_value(config, "index.enabled", False)) and args.db_path is None:
        print("Note: config index.enabled is false; running explicitly anyway.")

    if args.dry_run:
        return 0

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        # This DB is a rebuildable index. Some environments fail SQLite journaling
        # modes with "disk I/O error". Use journal_mode=OFF for compatibility.
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(conn)
        conn.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("generated_at_utc", now_utc_iso()))
        conn.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("repo_root", str(repo_root)))
        conn.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("backlog_root", normalize_path(repo_root, backlog_root)))
        conn.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("process_profile", process_profile))

        if mode == "rebuild":
            items = collect_indexable_items(repo_root, md_files)
            warn_missing_parents(items)
            ordered = order_items_for_fk(items)
            known_ids = {item.item_id for item in ordered}
            with conn:
                clear_all(conn)
                for item in ordered:
                    upsert_item(conn, item, known_ids=known_ids)
            print(f"Indexed items: {conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]}")
            return 0

        existing_hashes = read_existing_hashes(conn)
        items = collect_indexable_items(repo_root, md_files)
        warn_missing_parents(items)
        ordered = order_items_for_fk(items)
        known_ids = {item.item_id for item in ordered}
        current_paths = [item.source_path for item in ordered]
        changed = 0
        with conn:
            for item in ordered:
                if existing_hashes.get(item.source_path) == item.content_sha256:
                    continue
                upsert_item(conn, item, known_ids=known_ids)
                changed += 1
            removed = delete_missing(conn, current_paths)
        print(f"Updated items: {changed}, removed: {removed}")
        print(f"Indexed items: {conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
