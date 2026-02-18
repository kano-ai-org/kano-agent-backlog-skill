"""chunks_db.py - Canonical chunks SQLite DB (FTS5) operations.

This module builds a rebuildable per-product SQLite database that uses the
canonical schema (ADR-0012) and populates:
- items (metadata)
- chunks (content chunks)
- chunks_fts (FTS5 keyword search over chunks)

Source of truth remains canonical Markdown files under
_kano/backlog/products/<product>/items/**, plus ADRs and Topics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Any
import json
import os
import sqlite3
import sys
import time

import frontmatter

from kano_backlog_core.canonical import CanonicalStore
from kano_backlog_core.chunking import chunk_text_with_tokenizer
from kano_backlog_core.chunking import ChunkingOptions
from kano_backlog_core.config import ConfigLoader
from kano_backlog_core.errors import ConfigError
from kano_backlog_core.schema import load_canonical_schema
from kano_backlog_core.tokenizer import resolve_tokenizer

from .init import _resolve_backlog_root

# Conditional import for UUIDv7
if sys.version_info >= (3, 12):
    from uuid import uuid7  # type: ignore
else:
    from uuid6 import uuid7  # type: ignore


@dataclass
class ChunksDbBuildResult:
    db_path: Path
    items_indexed: int
    chunks_indexed: int
    build_time_ms: float


@dataclass
class ChunkSearchRow:
    item_id: str
    item_title: str
    item_path: str
    chunk_id: str
    parent_uid: str
    section: Optional[str]
    content: str
    score: float


@dataclass
class ChunkFtsCandidate:
    item_id: str
    item_title: str
    item_path: str
    chunk_id: str
    parent_uid: str
    section: Optional[str]
    bm25_score: float
    snippet: str


def _scan_adrs(product_root: Path, backlog_root_path: Path) -> list[tuple[Path, Any, float]]:
    """Scan ADRs from decisions/ directory and map to canonical schema."""
    decisions_dir = product_root / "decisions"
    if not decisions_dir.exists():
        return []
    
    results = []
    for adr_path in decisions_dir.glob("ADR-*.md"):
        try:
            post = frontmatter.load(adr_path)
            adr_id = post.get("id", "")
            adr_uid = post.get("uid", "")
            
            if not adr_uid:
                adr_uid = str(uuid7())
            
            adr_title = post.get("title", adr_path.stem)
            adr_status = post.get("status", "Proposed")
            adr_date = post.get("date", "")
            
            class ADRItem:
                def __init__(self):
                    self.uid = adr_uid
                    self.id = adr_id
                    self.type = type("ItemType", (), {"value": "ADR"})()
                    self.state = type("ItemState", (), {"value": adr_status})()
                    self.title = adr_title
                    self.priority = "P3"
                    self.parent = None
                    self.owner = "system"
                    self.area = "decisions"
                    self.iteration = "backlog"
                    self.tags = []
                    self.created = str(adr_date)
                    self.updated = str(adr_date)
                    self.content = post.content
                    self.decision = post.content
            
            mtime = os.stat(adr_path).st_mtime
            results.append((adr_path, ADRItem(), mtime))
        except Exception:
            continue
    
    return results


def _scan_topics(backlog_root_path: Path) -> list[tuple[Path, Any, float]]:
    """Scan Topics from topics/ directory and map to canonical schema."""
    topics_dir = backlog_root_path / "topics"
    if not topics_dir.exists():
        return []
    
    results = []
    for topic_dir in topics_dir.iterdir():
        if not topic_dir.is_dir():
            continue
        
        manifest_path = topic_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            topic_name = manifest.get("topic", topic_dir.name)
            topic_uid = str(uuid7())
            topic_id = f"TOPIC-{topic_name}"
            topic_status = manifest.get("status", "open")
            topic_created = manifest.get("created_at", "")
            topic_updated = manifest.get("updated_at", "")
            
            brief_path = topic_dir / "brief.generated.md"
            brief_content = ""
            if brief_path.exists():
                brief_content = brief_path.read_text(encoding="utf-8")
            
            class TopicItem:
                def __init__(self):
                    self.uid = topic_uid
                    self.id = topic_id
                    self.type = type("ItemType", (), {"value": "Topic"})()
                    self.state = type("ItemState", (), {"value": topic_status})()
                    self.title = topic_name
                    self.priority = "P3"
                    self.parent = None
                    self.owner = manifest.get("agent", "system")
                    self.area = "topics"
                    self.iteration = "backlog"
                    self.tags = []
                    self.created = topic_created
                    self.updated = topic_updated
                    self.content = brief_content
                    self.context = brief_content
            
            mtime = os.stat(manifest_path).st_mtime
            results.append((manifest_path, TopicItem(), mtime))
        except Exception:
            continue
    
    return results


def build_chunks_db(
    *,
    product: str,
    backlog_root: Optional[Path] = None,
    force: bool = False,
    cache_root: Optional[Path] = None,
    custom_config_file: Optional[Path] = None,
) -> ChunksDbBuildResult:
    """Build the canonical chunks DB for a product.
    
    Args:
        product: Product name
        backlog_root: Backlog root path
        force: Force rebuild even if exists
        cache_root: Override cache root directory (for shared cache on NAS, etc.)
    """

    t0 = time.perf_counter()

    backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)
    product_root = backlog_root_path / "products" / product
    if not product_root.exists():
        raise FileNotFoundError(f"Product backlog not found: {product_root}")

    if cache_root:
        cache_dir = Path(cache_root)
    else:
        _, effective = ConfigLoader.load_effective_config(
            backlog_root_path,
            product=product,
            custom_config_file=custom_config_file,
        )
        cache_dir = ConfigLoader.get_chunks_cache_root(backlog_root_path, effective)
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / f"backlog.{product}.chunks.v1.db"
    if db_path.exists() and not force:
        raise FileExistsError(f"Chunks DB already exists: {db_path} (use force to rebuild)")

    if db_path.exists():
        db_path.unlink()

    # Resolve pipeline config so chunking/tokenizer matches embedding pipeline.
    # Fall back to deterministic defaults when config is absent (e.g., in tests).
    try:
        _, effective = ConfigLoader.load_effective_config(
            backlog_root_path,
            product=product,
            custom_config_file=custom_config_file,
        )
        pc = ConfigLoader.validate_pipeline_config(effective)
        chunking_options = pc.chunking
        tokenizer_model = pc.tokenizer.model
        tokenizer_adapter = pc.tokenizer.adapter
        tokenizer = resolve_tokenizer(pc.tokenizer.adapter, pc.tokenizer.model)
    except ConfigError:
        chunking_options = ChunkingOptions(tokenizer_adapter="heuristic")
        tokenizer_model = "default-model"
        tokenizer_adapter = "heuristic"
        tokenizer = resolve_tokenizer("heuristic", tokenizer_model)

    store = CanonicalStore(product_root)

    paths = store.list_items()
    loaded: list[tuple[Path, object, float]] = []
    id_to_uid: dict[str, str] = {}
    for path in paths:
        try:
            item = store.read(path)
        except Exception:
            continue
        mtime = os.stat(path).st_mtime
        loaded.append((path, item, mtime))
        if getattr(item, "id", None) and getattr(item, "uid", None):
            id_to_uid[str(item.id)] = str(item.uid)
    
    adr_items = _scan_adrs(product_root, backlog_root_path)
    loaded.extend(adr_items)
    for _, item, _ in adr_items:
        if getattr(item, "id", None) and getattr(item, "uid", None):
            id_to_uid[str(item.id)] = str(item.uid)
    
    topic_items = _scan_topics(backlog_root_path)
    loaded.extend(topic_items)
    for _, item, _ in topic_items:
        if getattr(item, "id", None) and getattr(item, "uid", None):
            id_to_uid[str(item.id)] = str(item.uid)

    conn = sqlite3.connect(str(db_path))
    try:
        # Use in-memory journaling for derived DBs to avoid environments where
        # rollback journal file operations (rename/lock) are blocked.
        try:
            conn.execute("PRAGMA journal_mode=MEMORY")
            conn.execute("PRAGMA synchronous=OFF")
            conn.execute("PRAGMA temp_store=MEMORY")
        except sqlite3.OperationalError:
            pass
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        cur.executescript(load_canonical_schema())

        # Record chunking/tokenizer metadata for traceability (derived DB).
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("chunking_version", str(chunking_options.version)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("chunking_target_tokens", str(chunking_options.target_tokens)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("chunking_max_tokens", str(chunking_options.max_tokens)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("chunking_overlap_tokens", str(chunking_options.overlap_tokens)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("tokenizer_adapter", str(tokenizer_adapter)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("tokenizer_model", str(tokenizer_model)),
        )

        # Insert items.
        item_rows = []
        for path, item, mtime in loaded:
            parent_display = getattr(item, "parent", None)
            parent_uid = id_to_uid.get(str(parent_display)) if parent_display else None

            try:
                rel_path = Path(path).relative_to(backlog_root_path).as_posix()
            except ValueError:
                rel_path = str(path)

            frontmatter_dict = {
                "uid": item.uid,
                "id": item.id,
                "type": item.type.value,
                "state": item.state.value,
                "title": item.title,
                "priority": item.priority,
                "parent": parent_display,
                "parent_uid": parent_uid,
                "owner": item.owner,
                "area": item.area,
                "iteration": item.iteration,
                "tags": item.tags or [],
                "created": item.created,
                "updated": item.updated,
            }

            item_rows.append(
                {
                    "uid": item.uid,
                    "id": item.id,
                    "type": item.type.value,
                    "state": item.state.value,
                    "title": item.title,
                    "path": rel_path,
                    "mtime": mtime,
                    "content_hash": None,
                    "frontmatter": json.dumps(frontmatter_dict, ensure_ascii=False),
                    "created": item.created,
                    "updated": item.updated,
                    "priority": item.priority,
                    "parent_uid": parent_uid,
                    "owner": item.owner,
                    "area": item.area,
                    "iteration": item.iteration,
                    "tags": json.dumps(item.tags or [], ensure_ascii=False),
                }
            )

        if item_rows:
            cur.executemany(
                """
                INSERT INTO items (
                    uid, id, type, state, title, path, mtime, content_hash, frontmatter,
                    created, updated, priority, parent_uid, owner, area, iteration, tags
                ) VALUES (
                    :uid, :id, :type, :state, :title, :path, :mtime, :content_hash, :frontmatter,
                    :created, :updated, :priority, :parent_uid, :owner, :area, :iteration, :tags
                )
                """,
                item_rows,
            )

        chunk_rows = []
        for _, item, _ in loaded:
            sections: list[tuple[str, str]] = [("title", str(getattr(item, "title", "") or ""))]

            item_type = getattr(item.type, "value", "") if hasattr(item, "type") else ""
            
            if item_type == "ADR":
                decision_content = getattr(item, "decision", None)
                if isinstance(decision_content, str) and decision_content.strip():
                    sections.append(("decision", decision_content.strip()))
                
                content = getattr(item, "content", None)
                if isinstance(content, str) and content.strip():
                    sections.append(("content", content.strip()))
            
            elif item_type == "Topic":
                context_content = getattr(item, "context", None)
                if isinstance(context_content, str) and context_content.strip():
                    sections.append(("context", context_content.strip()))
                
                content = getattr(item, "content", None)
                if isinstance(content, str) and content.strip():
                    sections.append(("content", content.strip()))
            
            else:
                for key in [
                    "context",
                    "goal",
                    "non_goals",
                    "approach",
                    "alternatives",
                    "acceptance_criteria",
                    "risks",
                ]:
                    value = getattr(item, key, None)
                    if isinstance(value, str) and value.strip():
                        sections.append((key, value.strip()))

                worklog = getattr(item, "worklog", None)
                if isinstance(worklog, list) and worklog:
                    wl_text = "\n".join(str(x) for x in worklog if str(x).strip()).strip()
                    if wl_text:
                        sections.append(("worklog", wl_text))

            chunk_index = 0
            for section_key, section_text in sections:
                if not section_text.strip():
                    continue

                # Chunk per section so the canonical `section` column is meaningful.
                # Use the item UID as the source namespace to keep deterministic boundaries.
                # Include section in the chunk namespace to avoid collisions across
                # repeated short texts (e.g., "None.") in different sections.
                section_source_id = f"{item.uid}#{section_key}"
                raw_chunks = chunk_text_with_tokenizer(
                    source_id=section_source_id,
                    text=section_text,
                    options=chunking_options,
                    tokenizer=tokenizer,
                    model_name=tokenizer_model,
                )

                for rc in raw_chunks:
                    content = rc.text.strip()
                    if not content:
                        continue

                    chunk_rows.append(
                        {
                            "chunk_id": rc.chunk_id,
                            "parent_uid": item.uid,
                            "chunk_index": chunk_index,
                            "content": content,
                            "section": section_key,
                            "embedding": None,
                        }
                    )
                    chunk_index += 1

        if chunk_rows:
            cur.executemany(
                """
                INSERT INTO chunks (
                    chunk_id, parent_uid, chunk_index, content, section, embedding
                ) VALUES (
                    :chunk_id, :parent_uid, :chunk_index, :content, :section, :embedding
                )
                """,
                chunk_rows,
            )

        conn.commit()

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return ChunksDbBuildResult(
            db_path=db_path,
            items_indexed=len(item_rows),
            chunks_indexed=len(chunk_rows),
            build_time_ms=elapsed_ms,
        )
    finally:
        conn.close()


def query_chunks_fts(
    *,
    product: str,
    query: str,
    k: int = 10,
    backlog_root: Optional[Path] = None,
    cache_root: Optional[Path] = None,
    custom_config_file: Optional[Path] = None,
) -> list[ChunkSearchRow]:
    """Keyword search over canonical chunks_fts."""

    backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)

    if cache_root:
        cache_dir = Path(cache_root)
    else:
        try:
            _, effective = ConfigLoader.load_effective_config(
                backlog_root_path,
                product=product,
                custom_config_file=custom_config_file,
            )
            cache_dir = ConfigLoader.get_chunks_cache_root(backlog_root_path, effective)
        except ConfigError:
            cache_dir = backlog_root_path / "products" / product / ".cache"

    db_path = cache_dir / f"backlog.{product}.chunks.v1.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Chunks DB not found: {db_path} (run chunks build first)")

    if not query.strip():
        return []

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()

        # FTS5 bm25(): lower is better. Convert to higher-is-better score.
        rows = cur.execute(
            """
            SELECT
                i.id,
                i.title,
                i.path,
                c.chunk_id,
                c.parent_uid,
                c.section,
                c.content,
                bm25(chunks_fts) AS bm25_score
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            JOIN items i ON i.uid = c.parent_uid
            WHERE chunks_fts MATCH ?
            ORDER BY bm25_score ASC
            LIMIT ?
            """,
            (query, int(k)),
        ).fetchall()

        out: list[ChunkSearchRow] = []
        for (
            item_id,
            item_title,
            item_path,
            chunk_id,
            parent_uid,
            section,
            content,
            bm25_score,
        ) in rows:
            score = -float(bm25_score) if bm25_score is not None else 0.0
            out.append(
                ChunkSearchRow(
                    item_id=item_id,
                    item_title=item_title,
                    item_path=item_path,
                    chunk_id=chunk_id,
                    parent_uid=parent_uid,
                    section=section,
                    content=content,
                    score=score,
                )
            )

        return out
    finally:
        conn.close()


def query_chunks_fts_candidates(
    *,
    product: str,
    query: str,
    k: int = 200,
    backlog_root: Optional[Path] = None,
    cache_root: Optional[Path] = None,
    custom_config_file: Optional[Path] = None,
    snippet_tokens: int = 20,
    snippet_prefix: str = "<mark>",
    snippet_suffix: str = "</mark>",
    snippet_ellipsis: str = "...",
) -> list[ChunkFtsCandidate]:
    """Return top-N FTS candidates with snippets for hybrid rerank."""

    backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)

    if cache_root:
        cache_dir = Path(cache_root)
    else:
        try:
            _, effective = ConfigLoader.load_effective_config(
                backlog_root_path,
                product=product,
                custom_config_file=custom_config_file,
            )
            cache_dir = ConfigLoader.get_chunks_cache_root(backlog_root_path, effective)
        except ConfigError:
            cache_dir = backlog_root_path / "products" / product / ".cache"

    db_path = cache_dir / f"backlog.{product}.chunks.v1.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Chunks DB not found: {db_path} (run chunks build first)")

    if not query.strip():
        return []

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()

        rows = cur.execute(
            """
            SELECT
                i.id,
                i.title,
                i.path,
                c.chunk_id,
                c.parent_uid,
                c.section,
                bm25(chunks_fts) AS bm25_score,
                snippet(chunks_fts, 2, ?, ?, ?, ?) AS snippet
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            JOIN items i ON i.uid = c.parent_uid
            WHERE chunks_fts MATCH ?
            ORDER BY bm25_score ASC
            LIMIT ?
            """,
            (
                snippet_prefix,
                snippet_suffix,
                snippet_ellipsis,
                int(snippet_tokens),
                query,
                int(k),
            ),
        ).fetchall()

        out: list[ChunkFtsCandidate] = []
        for (
            item_id,
            item_title,
            item_path,
            chunk_id,
            parent_uid,
            section,
            bm25_score,
            snippet,
        ) in rows:
            out.append(
                ChunkFtsCandidate(
                    item_id=item_id,
                    item_title=item_title,
                    item_path=item_path,
                    chunk_id=chunk_id,
                    parent_uid=parent_uid,
                    section=section,
                    bm25_score=float(bm25_score) if bm25_score is not None else 0.0,
                    snippet=str(snippet or ""),
                )
            )

        return out
    finally:
        conn.close()
