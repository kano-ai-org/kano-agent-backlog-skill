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

from .init import _resolve_backlog_root  # reuse existing resolver
from kano_backlog_core.canonical import CanonicalStore


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
        idx_dir = prod_root / "_index"
        idx_dir.mkdir(parents=True, exist_ok=True)
        return idx_dir / "backlog.sqlite3"

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
        index_path=last_index_path if last_index_path else backlog_root_path / "_index" / "backlog.sqlite3",
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


def _scan_items(product_root: Path) -> Iterable[dict]:
    store = CanonicalStore(product_root)
    for path in store.list_items():
        try:
            item = store.read(path)
        except Exception:
            continue  # skip unreadable files
        stat = os.stat(path)
        mtime = stat.st_mtime
        yield {
            "id": item.id,
            "uid": item.uid,
            "type": item.type.value,
            "state": item.state.value,
            "title": item.title,
            "priority": item.priority,
            "parent": item.parent,
            "owner": item.owner,
            "area": item.area,
            "iteration": item.iteration,
            "tags": json.dumps(item.tags or [], ensure_ascii=False),
            "created": item.created,
            "updated": item.updated,
            "product": product_root.name,
            "path": str(path),
            "mtime": mtime,
        }


def _rebuild_sqlite_index(index_path: Path, product_root: Path) -> int:
    if index_path.exists():
        index_path.unlink()
    index_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(index_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                uid TEXT,
                type TEXT,
                state TEXT,
                title TEXT,
                priority TEXT,
                parent TEXT,
                owner TEXT,
                area TEXT,
                iteration TEXT,
                tags TEXT,
                created TEXT,
                updated TEXT,
                product TEXT,
                path TEXT,
                mtime REAL
            )
            """
        )
        rows = list(_scan_items(product_root))
        if rows:
            cur.executemany(
                """
                INSERT INTO items (
                    id, uid, type, state, title, priority, parent, owner, area,
                    iteration, tags, created, updated, product, path, mtime
                ) VALUES (
                    :id, :uid, :type, :state, :title, :priority, :parent, :owner, :area,
                    :iteration, :tags, :created, :updated, :product, :path, :mtime
                )
                """,
                rows,
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()
