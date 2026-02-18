"""Test index status functionality."""

import pytest
from pathlib import Path
import tempfile
import sqlite3

from kano_backlog_ops.backlog_index import get_index_status, build_index
from kano_backlog_core.canonical import CanonicalStore
from kano_backlog_core.models import BacklogItem, ItemType, ItemState


def test_index_status_no_indexes(tmp_path):
    """Test status when no indexes exist."""
    backlog_root = tmp_path / "_kano" / "backlog"
    products_root = backlog_root / "products"
    products_root.mkdir(parents=True)
    
    result = get_index_status(backlog_root=backlog_root)
    assert result.indexes == []


def test_index_status_missing_index(tmp_path):
    """Test status when product exists but no index."""
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    product_root.mkdir(parents=True)
    
    result = get_index_status(product="test-product", backlog_root=backlog_root)
    assert len(result.indexes) == 1
    assert result.indexes[0].product == "test-product"
    assert not result.indexes[0].exists
    assert result.indexes[0].item_count == 0


def test_index_status_existing_index(tmp_path):
    """Test status when index exists."""
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    product_root.mkdir(parents=True)
    
    # Create a simple SQLite index
    index_path = tmp_path / ".kano" / "cache" / "backlog" / "index.backlog.test-product.v1.db"
    index_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(index_path))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE items (
            id TEXT PRIMARY KEY,
            title TEXT
        )
    """)
    cur.execute("INSERT INTO items (id, title) VALUES ('TEST-001', 'Test Item')")
    conn.commit()
    conn.close()
    
    result = get_index_status(product="test-product", backlog_root=backlog_root)
    assert len(result.indexes) == 1
    assert result.indexes[0].product == "test-product"
    assert result.indexes[0].exists
    assert result.indexes[0].item_count == 1
    assert result.indexes[0].size_bytes > 0


def test_build_and_status_integration(tmp_path):
    """Test building an index and checking its status."""
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    items_root = product_root / "items" / "task" / "0000"
    items_root.mkdir(parents=True)
    
    # Create a test item
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
Test the indexing functionality.

# Approach
Create a simple test case.

# Acceptance Criteria
- Index should be built successfully
- Status should show correct item count

# Risks / Dependencies
None.

# Worklog
2026-01-23 10:00 [agent=test] Created test item.
"""
    item_path.write_text(item_content, encoding='utf-8')
    
    # Build the index
    result = build_index(product="test-product", backlog_root=backlog_root)
    assert result.items_indexed == 1
    
    # Check status
    status = get_index_status(product="test-product", backlog_root=backlog_root)
    assert len(status.indexes) == 1
    assert status.indexes[0].exists
    assert status.indexes[0].item_count == 1
