"""
index.py - SQLite index operations.

This module provides use-case functions for building and maintaining
the SQLite index that accelerates backlog queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterable
import json
import sqlite3
import time
from datetime import datetime
import os

from .init import _resolve_backlog_root
from kano_backlog_core.canonical import CanonicalStore
from kano_backlog_core.schema import load_indexing_schema


@dataclass
class IndexBuildResult:
    """Result of building the index."""
    index_path: Path
    items_indexed: int
    links_indexed: int
    build_time_ms: float


@dataclass
class IndexRefreshResult:
    """Result of refreshing the index."""
    index_path: Path
    items_added: int
    items_updated: int
    items_removed: int
    refresh_time_ms: float


@dataclass
class IndexInfo:
    """Information about a single index."""
    product: str
    index_path: Path
    exists: bool
    item_count: int = 0
    size_bytes: int = 0
    last_modified: str = ""


@dataclass
class IndexStatusResult:
    """Result of checking index status."""
    indexes: list[IndexInfo]


def build_index(
    *,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
    force: bool = False,
) -> IndexBuildResult:
    """
    Build the SQLite index from scratch.

    Scans all backlog items and creates the index database.

    Args:
        product: Product name (builds index for all if not specified)
        backlog_root: Root path for backlog
        force: Force rebuild even if index exists

    Returns:
        IndexBuildResult with build details

    Raises:
        FileNotFoundError: If backlog not initialized
        FileExistsError: If index exists and force=False
    """
    t0 = time.perf_counter()
    backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)

    def _product_index_path(prod_root: Path) -> Path:
        cache_dir = prod_root / ".cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "index.sqlite3"

    items_indexed_total = 0
    links_indexed_total = 0  # links not indexed in MVP
    last_index_path: Path | None = None

    if product:
        prod_root = (backlog_root_path / "products" / product)
        if not prod_root.exists():
            raise FileNotFoundError(f"Product backlog not found: {prod_root}")
        index_path = _product_index_path(prod_root)
        if index_path.exists() and not force:
            raise FileExistsError(f"Index already exists: {index_path} (use force to rebuild)")
        items_indexed = _rebuild_sqlite_index(index_path, prod_root)
        items_indexed_total += items_indexed
        last_index_path = index_path
    else:
        # Build all products under backlog_root
        products_root = backlog_root_path / "products"
        if not products_root.exists():
            raise FileNotFoundError(f"No products directory at {products_root}")
        built_any = False
        for prod_dir in sorted(p for p in products_root.iterdir() if p.is_dir()):
            index_path = _product_index_path(prod_dir)
            if index_path.exists() and not force:
                # Skip existing unless forced
                continue
            items_indexed = _rebuild_sqlite_index(index_path, prod_dir)
            items_indexed_total += items_indexed
            last_index_path = index_path
            built_any = True
        if not built_any and last_index_path is None:
            raise FileExistsError("All product indexes already exist; use force to rebuild")

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return IndexBuildResult(
        index_path=last_index_path if last_index_path else backlog_root_path / ".cache" / "index.sqlite3",
        items_indexed=items_indexed_total,
        links_indexed=links_indexed_total,
        build_time_ms=elapsed_ms,
    )


def refresh_index(
    *,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> IndexRefreshResult:
    """
    Incrementally refresh the index.

    Updates the index with changes since last refresh (based on mtime).

    Args:
        product: Product name
        backlog_root: Root path for backlog

    Returns:
        IndexRefreshResult with refresh details

    Raises:
        FileNotFoundError: If index not built yet
    """
    # MVP: perform a full rebuild for the requested scope and report as "added".
    t0 = time.perf_counter()
    result = build_index(product=product, backlog_root=backlog_root, force=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return IndexRefreshResult(
        index_path=result.index_path,
        items_added=result.items_indexed,
        items_updated=0,
        items_removed=0,
        refresh_time_ms=elapsed_ms,
    )


def get_index_status(
    *,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> IndexStatusResult:
    """
    Get status information for SQLite indexes.

    Args:
        product: Product name (check all if not specified)
        backlog_root: Root path for backlog

    Returns:
        IndexStatusResult with status details

    Raises:
        FileNotFoundError: If backlog not initialized
    """
    backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)

    def _product_index_path(prod_root: Path) -> Path:
        cache_dir = prod_root / ".cache"
        return cache_dir / "index.sqlite3"

    def _get_index_info(prod_name: str, prod_root: Path) -> IndexInfo:
        index_path = _product_index_path(prod_root)
        exists = index_path.exists()
        
        info = IndexInfo(
            product=prod_name,
            index_path=index_path,
            exists=exists
        )
        
        if exists:
            # Get file stats
            stat = index_path.stat()
            info.size_bytes = stat.st_size
            info.last_modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            # Get item count from database
            try:
                conn = sqlite3.connect(index_path)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM items")
                info.item_count = cur.fetchone()[0]
                conn.close()
            except Exception:
                info.item_count = 0
        
        return info

    indexes = []
    
    if product:
        prod_root = (backlog_root_path / "products" / product)
        if not prod_root.exists():
            raise FileNotFoundError(f"Product backlog not found: {prod_root}")
        indexes.append(_get_index_info(product, prod_root))
    else:
        # Check all products
        products_root = backlog_root_path / "products"
        if not products_root.exists():
            raise FileNotFoundError(f"No products directory at {products_root}")
        for prod_dir in sorted(p for p in products_root.iterdir() if p.is_dir()):
            indexes.append(_get_index_info(prod_dir.name, prod_dir))

    return IndexStatusResult(indexes=indexes)


def _scan_items(product_root: Path) -> Iterable[dict]:
    store = CanonicalStore(product_root)

    # Build a map from display ID -> UID so we can resolve parent_uid.
    # Canonical frontmatter stores `parent` as the display ID today.
    paths = store.list_items()
    loaded: list[tuple[Path, object, float]] = []
    id_to_uid: dict[str, str] = {}

    for path in paths:
        try:
            item = store.read(path)
        except Exception:
            continue
        stat = os.stat(path)
        mtime = stat.st_mtime
        loaded.append((path, item, mtime))
        if getattr(item, "id", None) and getattr(item, "uid", None):
            id_to_uid[str(item.id)] = str(item.uid)

    backlog_root = product_root.parent.parent

    for path, item, mtime in loaded:
        parent_display = getattr(item, "parent", None)
        parent_uid = id_to_uid.get(str(parent_display)) if parent_display else None

        rel_path = path
        try:
            rel_path = path.relative_to(backlog_root)
        except ValueError:
            # Fallback: keep absolute if path is outside backlog_root.
            rel_path = path

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

        yield {
            "uid": item.uid,
            "id": item.id,
            "type": item.type.value,
            "state": item.state.value,
            "title": item.title,
            "path": str(rel_path).replace("\\", "/"),
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


def _rebuild_sqlite_index(index_path: Path, product_root: Path) -> int:
    if index_path.exists():
        index_path.unlink()
    index_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(index_path)
    try:
        cur = conn.cursor()
        
        schema_sql = load_indexing_schema()
        cur.executescript(schema_sql)
        
        rows = list(_scan_items(product_root))
        if rows:
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
                rows,
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()
