#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Ensure shared libs are importable
LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from context import (  # noqa: E402
    find_repo_root,
    get_product_root,
    get_sandbox_root,
    resolve_product_name,
)

BACKLOG_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(BACKLOG_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(BACKLOG_LIB_DIR))
from utils import parse_frontmatter  # noqa: E402


@dataclass
class WorklogEntry:
    uid: str
    timestamp: str
    agent: Optional[str]
    content: str


@dataclass
class Chunk:
    chunk_id: str
    chunk_index: int
    section: str
    content: str


@dataclass
class ParsedItem:
    uid: str
    item_id: str
    item_type: str
    title: str
    state: Optional[str]
    priority: Optional[str]
    parent_ref: Optional[str]
    parent_uid: Optional[str]
    area: Optional[str]
    iteration: Optional[str]
    owner: Optional[str]
    tags: List[str]
    created: Optional[str]
    updated: Optional[str]
    rel_path: str
    abs_path: Path
    mtime: float
    content_hash: str
    frontmatter_json: str
    link_refs: Dict[str, List[str]] = field(default_factory=dict)
    resolved_links: List[Tuple[str, str]] = field(default_factory=list)
    worklog_entries: List[WorklogEntry] = field(default_factory=list)
    chunks: List[Chunk] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or refresh the canonical SQLite backlog index (per ADR-0012)."
    )
    parser.add_argument(
        "--backlog-root",
        default="_kano/backlog",
        help="Relative or absolute path to the backlog root (default: _kano/backlog).",
    )
    parser.add_argument(
        "--product",
        help="Product name override (default resolved from env/defaults).",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Target the sandbox directory instead of the product directory.",
    )
    parser.add_argument(
        "--mode",
        choices=["rebuild", "incremental"],
        default="rebuild",
        help="Rebuild deletes the DB first; incremental updates changed items only.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force removal of the existing DB before running (alias for rebuild).",
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Agent or user executing the script (stored in schema_meta).",
    )
    return parser.parse_args()


def load_schema_sql(product_root: Path) -> str:
    schema_path = product_root / "_meta" / "canonical_schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(
            f"Canonical schema not found for product at {schema_path}. "
            "Ensure ADR-0012 assets are present."
        )
    return schema_path.read_text(encoding="utf-8")


def normalize_backlog_root(repo_root: Path, backlog_root_raw: str) -> Path:
    path = Path(backlog_root_raw)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def discover_markdown_files(base_dir: Path) -> List[Path]:
    if not base_dir.exists():
        return []
    files: List[Path] = []
    for path in base_dir.rglob("*.md"):
        if path.name == "README.md" or path.name.endswith(".index.md"):
            continue
        files.append(path)
    return files


def ensure_uid(value: Optional[str], rel_path: str) -> str:
    if value and value.strip():
        return value.strip()
    deterministic = uuid.uuid5(uuid.NAMESPACE_URL, rel_path)
    return str(deterministic)


def ensure_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


HEADING_RE = re.compile(r"^(#+)\s+(.*)$")
WORKLOG_HEADER_RE = re.compile(r"^#+\s*Worklog\s*$", re.IGNORECASE)
WORKLOG_META_RE = re.compile(r"\[([^=\]]+)=([^\]]+)\]")
DEFAULT_WORKLOG_AGENT = "unknown"
DEFAULT_STATE = "Unknown"


def extract_chunks(body: str, item_uid: str) -> List[Chunk]:
    sections: List[Chunk] = []
    current_title = "Body"
    buffer: List[str] = []

    def flush(title: str) -> None:
        text = "\n".join(buffer).strip()
        if not text:
            return
        if title.lower() == "worklog":
            buffer.clear()
            return
        chunk_index = len(sections)
        chunk_id = f"{item_uid}-chunk-{chunk_index}"
        sections.append(Chunk(chunk_id=chunk_id, chunk_index=chunk_index, section=title, content=text))
        buffer.clear()

    for line in body.splitlines():
        heading = HEADING_RE.match(line.strip())
        if heading:
            flush(current_title)
            current_title = heading.group(2).strip() or "Section"
            continue
        buffer.append(line)

    flush(current_title)

    if not sections and body.strip():
        sections.append(Chunk(chunk_id=f"{item_uid}-chunk-0", chunk_index=0, section="Body", content=body.strip()))

    return sections


def parse_worklog_entries(lines: Sequence[str], item_uid: str) -> List[WorklogEntry]:
    entries: List[WorklogEntry] = []
    in_section = False
    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith("#"):
            in_section = bool(WORKLOG_HEADER_RE.match(stripped))
            continue
        if not in_section or not stripped:
            continue

        timestamp, remainder = split_timestamp(stripped)
        meta_pairs = WORKLOG_META_RE.findall(remainder)
        agent: Optional[str] = None
        for key, value in meta_pairs:
            if key.lower() == "agent":
                agent = value.strip()
        message = WORKLOG_META_RE.sub("", remainder).strip()
        entry_uid = uuid.uuid5(uuid.NAMESPACE_URL, f"{item_uid}:{timestamp}:{agent}:{message}")
        entries.append(WorklogEntry(uid=str(entry_uid), timestamp=timestamp, agent=agent, content=message))
    return entries


TIMESTAMP_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})(?:[ T](?P<time>\d{2}:\d{2}))?\s*(?P<rest>.*)$")


def split_timestamp(line: str) -> Tuple[str, str]:
    match = TIMESTAMP_RE.match(line)
    if not match:
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return now_iso, line
    date_part = match.group("date")
    time_part = match.group("time")
    rest = match.group("rest") or ""
    if time_part:
        timestamp = f"{date_part}T{time_part}:00Z"
    else:
        timestamp = f"{date_part}T00:00:00Z"
    return timestamp, rest.strip()


def parse_markdown_file(path: Path, repo_root: Path, fallback_type: Optional[str]) -> Optional[ParsedItem]:
    content = path.read_text(encoding="utf-8")
    fm, body, _ = parse_frontmatter(content)
    if not fm:
        print(f"Skipping {path}: missing frontmatter")
        return None

    item_id_raw = fm.get("id") or fm.get("uid")
    if not item_id_raw:
        print(f"Skipping {path}: missing id field")
        return None
    item_id = str(item_id_raw).strip()
    rel_path = path.relative_to(repo_root).as_posix()
    uid = ensure_uid(str(fm.get("uid", "")), rel_path)
    item_type = str(fm.get("type") or fallback_type or "Task").strip()
    title = str(fm.get("title") or item_id).strip()
    state_val = fm.get("state") or fm.get("status")
    state = str(state_val).strip() if state_val is not None else None
    priority = str(fm.get("priority") or "").strip() or None
    area = str(fm.get("area") or "").strip() or None
    iteration = str(fm.get("iteration") or "").strip() or None
    owner = str(fm.get("owner") or "").strip() or None
    created = str(fm.get("created") or fm.get("date") or "").strip() or None
    updated = str(fm.get("updated") or fm.get("decision_date") or "").strip() or None
    parent_ref_val = fm.get("parent") or fm.get("parent_id")
    parent_ref = str(parent_ref_val).strip() if parent_ref_val else None
    tags = ensure_list(fm.get("tags"))
    link_refs: Dict[str, List[str]] = {}
    links_field = fm.get("links")
    if isinstance(links_field, dict):
        for relation, raw_targets in links_field.items():
            targets = ensure_list(raw_targets)
            if targets:
                link_refs[str(relation)] = targets

    worklog_entries = parse_worklog_entries(body.splitlines(), uid)
    chunks = extract_chunks(body, uid)

    parsed = ParsedItem(
        uid=uid,
        item_id=item_id,
        item_type=item_type,
        title=title,
        state=state,
        priority=priority,
        parent_ref=parent_ref,
        parent_uid=None,
        area=area,
        iteration=iteration,
        owner=owner,
        tags=tags,
        created=created,
        updated=updated,
        rel_path=rel_path,
        abs_path=path,
        mtime=path.stat().st_mtime,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        frontmatter_json=json.dumps(fm, ensure_ascii=False, sort_keys=True, default=str),
        link_refs=link_refs,
        worklog_entries=worklog_entries,
        chunks=chunks,
    )
    return parsed


def resolve_reference(value: str, id_to_uid: Dict[str, str], known_uids: Dict[str, str]) -> Optional[str]:
    target = id_to_uid.get(value)
    if target:
        return target
    if value in known_uids:
        return value
    return None


def deduplicate_links(resolved: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen = set()
    unique: List[Tuple[str, str]] = []
    for relation, target in resolved:
        key = (relation, target)
        if key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique


def collect_items(product_root: Path, repo_root: Path) -> List[ParsedItem]:
    sources: List[Tuple[List[Path], Optional[str]]] = []
    sources.append((discover_markdown_files(product_root / "items"), None))
    sources.append((discover_markdown_files(product_root / "decisions"), "Decision"))

    items: List[ParsedItem] = []
    for files, fallback_type in sources:
        for path in files:
            parsed = parse_markdown_file(path, repo_root, fallback_type)
            if parsed:
                items.append(parsed)

    id_to_uid: Dict[str, str] = {}
    uid_lookup: Dict[str, str] = {}
    for item in items:
        id_to_uid[item.item_id] = item.uid
        uid_lookup[item.uid] = item.uid

    for item in items:
        if item.parent_ref:
            item.parent_uid = resolve_reference(item.parent_ref, id_to_uid, uid_lookup)
        resolved: List[Tuple[str, str]] = []
        for relation, targets in item.link_refs.items():
            for target in targets:
                target_uid = resolve_reference(target, id_to_uid, uid_lookup)
                if target_uid:
                    resolved.append((relation, target_uid))
        if item.parent_uid:
            resolved.append(("parent", item.parent_uid))
        item.resolved_links = deduplicate_links(resolved)
    return items


def clear_all_tables(conn: sqlite3.Connection) -> None:
    for table in ("links", "worklog", "chunks", "items", "workset_manifest", "workset_provenance"):
        try:
            conn.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            continue


def insert_item(
    conn: sqlite3.Connection,
    item: ParsedItem,
    link_buffer: List[Tuple[str, str, str]],
) -> None:
    fallback_ts = datetime.fromtimestamp(item.mtime, timezone.utc).isoformat(timespec="seconds")
    created = item.created or fallback_ts
    updated = item.updated or item.created or fallback_ts
    state = item.state or DEFAULT_STATE
    tags_json = json.dumps(item.tags, ensure_ascii=False)
    conn.execute(
        """
        INSERT OR REPLACE INTO items (
            uid, id, type, state, title, path, mtime, content_hash, frontmatter,
            created, updated, priority, parent_uid, owner, area, iteration, tags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item.uid,
            item.item_id,
            item.item_type,
            state,
            item.title,
            item.rel_path,
            item.mtime,
            item.content_hash,
            item.frontmatter_json,
            created,
            updated,
            item.priority,
            item.parent_uid,
            item.owner,
            item.area,
            item.iteration,
            tags_json,
        ),
    )

    if item.resolved_links:
        for relation, target_uid in item.resolved_links:
            link_buffer.append((item.uid, target_uid, relation))

    if item.worklog_entries:
        conn.executemany(
            "INSERT OR REPLACE INTO worklog (uid, item_uid, timestamp, agent, content) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    entry.uid,
                    item.uid,
                    entry.timestamp,
                    entry.agent or DEFAULT_WORKLOG_AGENT,
                    entry.content,
                )
                for entry in item.worklog_entries
            ],
        )

    if item.chunks:
        conn.executemany(
            """
            INSERT OR REPLACE INTO chunks (chunk_id, parent_uid, chunk_index, content, section, embedding)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            [
                (chunk.chunk_id, item.uid, chunk.chunk_index, chunk.content, chunk.section)
                for chunk in item.chunks
            ],
        )


def flush_link_buffer(conn: sqlite3.Connection, link_buffer: List[Tuple[str, str, str]]) -> None:
    if not link_buffer:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO links (source_uid, target_uid, type)
        VALUES (?, ?, ?)
        """,
        link_buffer,
    )
    link_buffer.clear()


def delete_item(conn: sqlite3.Connection, uid: str) -> None:
    conn.execute("DELETE FROM links WHERE source_uid = ?", (uid,))
    conn.execute("DELETE FROM worklog WHERE item_uid = ?", (uid,))
    conn.execute("DELETE FROM chunks WHERE parent_uid = ?", (uid,))
    conn.execute("DELETE FROM items WHERE uid = ?", (uid,))


def load_existing_hashes(conn: sqlite3.Connection) -> Dict[str, str]:
    rows = conn.execute("SELECT uid, content_hash FROM items").fetchall()
    return {str(uid): str(content_hash or "") for uid, content_hash in rows}


def remove_missing_items(conn: sqlite3.Connection, existing: Iterable[str], seen: Iterable[str]) -> int:
    existing_set = set(existing)
    seen_set = set(seen)
    missing = existing_set - seen_set
    for uid in missing:
        delete_item(conn, uid)
    return len(missing)


def record_metadata(
    conn: sqlite3.Connection,
    product_name: str,
    product_root: Path,
    mode: str,
    agent: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata = {
        "generated_at_utc": now,
        "generator": "scripts/backlog/index_db.py",
        "product_name": product_name,
        "product_root": str(product_root),
        "mode": mode,
        "agent": agent,
    }
    for key, value in metadata.items():
        conn.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", (key, value))


def main() -> int:
    args = parse_args()
    repo_root = find_repo_root()
    backlog_root = normalize_backlog_root(repo_root, args.backlog_root)
    platform_root = backlog_root
    if not platform_root.exists():
        raise FileNotFoundError(f"Backlog root not found at {platform_root}")
    product_name = resolve_product_name(args.product, platform_root=platform_root)
    product_root = (
        get_sandbox_root(product_name, platform_root)
        if args.sandbox
        else get_product_root(product_name, platform_root)
    )

    schema_sql = load_schema_sql(product_root)
    db_path = product_root / "_index" / "backlog.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "rebuild" or args.force:
        if db_path.exists():
            db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)

    items = collect_items(product_root, repo_root)
    print(f"Product: {product_name} ({'sandbox' if args.sandbox else 'product'})")
    print(f"Backlog root: {backlog_root}")
    print(f"DB path: {db_path}")
    print(f"Mode: {args.mode}")
    print(f"Items discovered: {len(items)}")

    link_buffer: List[Tuple[str, str, str]] = []

    with conn:
        if args.mode == "rebuild":
            clear_all_tables(conn)
            for item in items:
                insert_item(conn, item, link_buffer)
            flush_link_buffer(conn, link_buffer)
            updated = len(items)
            skipped = 0
            removed = 0
        else:
            existing_hashes = load_existing_hashes(conn)
            seen: List[str] = []
            updated = 0
            skipped = 0
            for item in items:
                seen.append(item.uid)
                if existing_hashes.get(item.uid) == item.content_hash:
                    skipped += 1
                    continue
                delete_item(conn, item.uid)
                insert_item(conn, item, link_buffer)
                updated += 1
            flush_link_buffer(conn, link_buffer)
            removed = remove_missing_items(conn, existing_hashes.keys(), seen)

        record_metadata(conn, product_name, product_root, args.mode, args.agent)

    conn.close()
    print(f"Updated items: {updated}, skipped: {skipped}, removed: {removed}")
    return 0


if __name__ == "__main__":
    sys.exit(run_with_audit(main))
