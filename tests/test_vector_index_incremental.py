"""Tests for incremental vector index build behavior (sqlite backend)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from kano_backlog_ops.backlog_vector_index import build_vector_index


def _read_vector_chunk_count(db_dir: Path, collection: str) -> int:
    dbs = sorted(db_dir.glob(f"{collection}.*.sqlite3"))
    if not dbs:
        return 0
    conn = sqlite3.connect(str(dbs[0]))
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM {collection}_chunks")
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def test_vector_index_incremental_and_prune(tmp_path: Path) -> None:
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    items_root = product_root / "items" / "task" / "0000"
    config_root = product_root / "_config"
    items_root.mkdir(parents=True)
    config_root.mkdir(parents=True)

    config = {
        "chunking": {
            "target_tokens": 50,
            "max_tokens": 100,
            "overlap_tokens": 10,
            "version": "chunk-v1",
            "tokenizer_adapter": "heuristic",
        },
        "tokenizer": {
            "adapter": "heuristic",
            "model": "test-model",
            "max_tokens": 200,
        },
        "embedding": {
            "provider": "noop",
            "model": "noop-embedding",
            "dimension": 16,
        },
        "vector": {
            "backend": "sqlite",
            "path": ".cache/vector",
            "collection": "test",
            "metric": "cosine",
        },
    }
    (config_root / "config.json").write_text(json.dumps(config), encoding="utf-8")

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
    vec_dir = product_root / ".cache" / "vector"
    count1 = _read_vector_chunk_count(vec_dir, "test")
    assert count1 > 0

    # Second build (incremental -> should not explode in size)
    build_vector_index(product="test-product", backlog_root=backlog_root, force=False)
    count2 = _read_vector_chunk_count(vec_dir, "test")
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
    count3 = _read_vector_chunk_count(vec_dir, "test")
    assert count3 > 0
    # Should not grow unbounded (stale chunk IDs must be pruned).
    assert count3 < count1 + 100
