"""Tests for hybrid search (FTS candidates -> vector rerank)."""

from __future__ import annotations

from pathlib import Path

from kano_backlog_ops.backlog_vector_index import build_vector_index
from kano_backlog_ops.backlog_vector_query import search_hybrid
from conftest import write_project_backlog_config


def test_hybrid_search_end_to_end(tmp_path: Path) -> None:
    write_project_backlog_config(tmp_path)

    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    items_root = product_root / "items" / "task" / "0000"
    items_root.mkdir(parents=True)

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
