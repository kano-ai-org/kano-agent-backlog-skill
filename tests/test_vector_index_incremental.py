"""Tests for incremental vector index build behavior (sqlite backend)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from kano_backlog_ops.backlog_vector_index import build_vector_index
from conftest import write_project_backlog_config


def _read_vector_chunk_count(db_path: Path, collection: str) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM {collection}_chunks")
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def _find_vector_db(cache_dir: Path, product: str) -> Path:
    dbs = sorted(cache_dir.glob(f"backlog.{product}.vectors.*.db"))
    if not dbs:
        raise FileNotFoundError(f"Vector DB not found under {cache_dir}")
    return dbs[0]


def test_vector_index_incremental_and_prune(tmp_path: Path) -> None:
    write_project_backlog_config(tmp_path)

    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    items_root = product_root / "items" / "task" / "0000"
    items_root.mkdir(parents=True)

    item_path = items_root / "TEST-TSK-001_test-task.md"
    item_path.write_text(
        """---
id: TEST-TSK-001
uid: 01234567-89ab-cdef-0123-456789abcdef
type: Task
state: Proposed
title: Test Task
priority: P3
parent: null
owner: test-agent
area: general
iteration: backlog
tags: []
created: '2026-01-23'
updated: '2026-01-23'
---

# Context
This is a test task about schema alignment.
""",
        encoding="utf-8",
    )

    # First build (force -> fresh DB)
    build_vector_index(product="test-product", backlog_root=backlog_root, force=True)
    cache_dir = tmp_path / ".kano" / "cache" / "backlog"
    db_path = _find_vector_db(cache_dir, product="test-product")
    count1 = _read_vector_chunk_count(db_path, "backlog")
    assert count1 > 0

    # Second build (incremental -> should not explode in size)
    build_vector_index(product="test-product", backlog_root=backlog_root, force=False)
    db_path2 = _find_vector_db(cache_dir, product="test-product")
    count2 = _read_vector_chunk_count(db_path2, "backlog")
    assert count2 == count1

    # Modify the item so canonical chunk IDs change (prune should remove stale rows).
    item_path.write_text(
        """---
id: TEST-TSK-001
uid: 01234567-89ab-cdef-0123-456789abcdef
type: Task
state: Proposed
title: Test Task
priority: P3
parent: null
owner: test-agent
area: general
iteration: backlog
tags: []
created: '2026-01-23'
updated: '2026-01-23'
---

# Context
This is a test task about schema alignment.

# Goal
New content should change chunk ids.
""",
        encoding="utf-8",
    )

    build_vector_index(product="test-product", backlog_root=backlog_root, force=False)
    db_path3 = _find_vector_db(cache_dir, product="test-product")
    count3 = _read_vector_chunk_count(db_path3, "backlog")
    assert count3 > 0
    # Should not grow unbounded (stale chunk IDs must be pruned).
    assert count3 < count1 + 100
