"""Tests for canonical chunks DB (FTS5) operations."""

import json
from pathlib import Path

import pytest

from kano_backlog_ops.backlog_chunks_db import build_chunks_db, query_chunks_fts


def test_build_chunks_db_and_query(tmp_path: Path) -> None:
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
This is a test task.

# Goal
Test the chunks DB build and query.
"""
    item_path.write_text(item_content, encoding="utf-8")

    result = build_chunks_db(product="test-product", backlog_root=backlog_root, force=True)
    assert result.items_indexed == 1
    assert result.chunks_indexed > 0
    assert result.db_path.exists()

    hits = query_chunks_fts(product="test-product", backlog_root=backlog_root, query="chunks", k=10)
    assert hits
    assert hits[0].item_id == "TEST-TSK-001"
    assert "products/test-product/items" in hits[0].item_path


def test_build_chunks_db_with_adr(tmp_path: Path) -> None:
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    decisions_dir = product_root / "decisions"
    decisions_dir.mkdir(parents=True)
    
    items_root = product_root / "items"
    items_root.mkdir(parents=True)

    adr_path = decisions_dir / "ADR-0001_test-decision.md"
    adr_content = """---
id: ADR-0001
uid: 01234567-89ab-cdef-0123-456789abcdef
title: Test Decision
status: Accepted
date: '2026-01-23'
related_items: []
supersedes: null
superseded_by: null
---

# Decision
Use SQLite for local indexing.

# Context
Need fast keyword search over backlog items.

# Options Considered
1. SQLite FTS5
2. External search engine

# Consequences
Simple deployment, no external dependencies.
"""
    adr_path.write_text(adr_content, encoding="utf-8")

    result = build_chunks_db(product="test-product", backlog_root=backlog_root, force=True)
    assert result.items_indexed == 1
    assert result.chunks_indexed > 0
    assert result.db_path.exists()

    hits = query_chunks_fts(product="test-product", backlog_root=backlog_root, query="SQLite", k=10)
    assert hits
    assert hits[0].item_id == "ADR-0001"


def test_build_chunks_db_with_topic(tmp_path: Path) -> None:
    backlog_root = tmp_path / "_kano" / "backlog"
    topics_dir = backlog_root / "topics" / "test-topic"
    topics_dir.mkdir(parents=True)

    manifest_path = topics_dir / "manifest.json"
    manifest_content = {
        "topic": "test-topic",
        "agent": "test-agent",
        "seed_items": [],
        "pinned_docs": [],
        "snippet_refs": [],
        "status": "open",
        "created_at": "2026-01-23T00:00:00Z",
        "updated_at": "2026-01-23T00:00:00Z",
        "has_spec": False
    }
    manifest_path.write_text(json.dumps(manifest_content, indent=2), encoding="utf-8")

    brief_path = topics_dir / "brief.generated.md"
    brief_content = """# Topic Brief: test-topic

## Facts
- This is a test topic for indexing
- Topics enable context switching

## Unknowns / Risks
- Performance with large topics
"""
    brief_path.write_text(brief_content, encoding="utf-8")

    product_root = backlog_root / "products" / "test-product"
    items_root = product_root / "items"
    items_root.mkdir(parents=True)

    result = build_chunks_db(product="test-product", backlog_root=backlog_root, force=True)
    assert result.items_indexed == 1
    assert result.chunks_indexed > 0
    assert result.db_path.exists()

    hits = query_chunks_fts(product="test-product", backlog_root=backlog_root, query="context switching", k=10)
    assert hits
    assert "TOPIC-test-topic" in hits[0].item_id
