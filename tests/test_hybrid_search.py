"""Tests for hybrid search (FTS candidates -> vector rerank)."""

from __future__ import annotations

import json
from pathlib import Path

from kano_backlog_ops.backlog_vector_index import build_vector_index
from kano_backlog_ops.backlog_vector_query import search_hybrid


def test_hybrid_search_end_to_end(tmp_path: Path) -> None:
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    items_root = product_root / "items" / "task" / "0000"
    config_root = product_root / "_config"
    items_root.mkdir(parents=True)
    config_root.mkdir(parents=True)

    # Minimal pipeline config: sqlite vector backend + noop embedder.
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
    item_content = """---
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
Validate hybrid search.
"""
    item_path.write_text(item_content, encoding="utf-8")

    # Build embedding index for product (this will also build chunks DB on demand).
    build_vector_index(product="test-product", backlog_root=backlog_root, force=True)

    results = search_hybrid(
        query_text="schema",
        product="test-product",
        k=5,
        fts_k=50,
        backlog_root=backlog_root,
    )

    assert results
    assert results[0].item_id == "TEST-TSK-001"
    assert "products/test-product/items" in results[0].item_path
    assert "schema" in results[0].snippet.lower()
