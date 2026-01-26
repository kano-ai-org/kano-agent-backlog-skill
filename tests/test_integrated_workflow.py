"""Test integrated SQLite index + vector search workflow."""

import pytest
from pathlib import Path
import tempfile
import sqlite3

from kano_backlog_ops.backlog_index import build_index, get_index_status
from kano_backlog_ops.backlog_vector_index import build_vector_index
from kano_backlog_ops.backlog_vector_query import search_similar
from kano_backlog_core.config import ConfigLoader


def test_integrated_index_and_search_workflow(tmp_path):
    """Test the complete workflow: build SQLite index, build vector index, search."""
    # Setup test backlog structure
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    items_root = product_root / "items" / "task" / "0000"
    config_root = product_root / "_config"
    items_root.mkdir(parents=True)
    config_root.mkdir(parents=True)
    
    # Create config file with noop embedding settings
    config_content = """
[product]
name = "test-product"
prefix = "TEST"

[embedding]
provider = "noop"
model = "noop-embedding"
dimension = 1536

[vector]
backend = "sqlite"
path = ".cache/vector"
collection = "backlog"
metric = "cosine"

[tokenizer]
adapter = "heuristic"
model = "text-embedding-3-small"
max_tokens = 8192

[chunking]
version = "chunk-v1"
target_tokens = 512
max_tokens = 1024
overlap_tokens = 50
"""
    config_path = config_root / "config.toml"
    config_path.write_text(config_content, encoding='utf-8')
    
    # Create test items with different content
    items = [
        {
            "id": "TEST-TSK-001",
            "title": "Implement embedding pipeline",
            "context": "We need to build an embedding pipeline for semantic search.",
            "goal": "Create a working embedding system with vector storage.",
        },
        {
            "id": "TEST-TSK-002", 
            "title": "Add SQLite indexing",
            "context": "The backlog needs a SQLite index for fast queries.",
            "goal": "Build and maintain a SQLite index of backlog items.",
        },
        {
            "id": "TEST-TSK-003",
            "title": "Create search interface",
            "context": "Users need to search through backlog items efficiently.",
            "goal": "Provide both text and semantic search capabilities.",
        }
    ]
    
    for i, item in enumerate(items):
        item_path = items_root / f"{item['id']}_task-{i+1}.md"
        item_content = f"""---
id: {item['id']}
uid: 01234567-89ab-cdef-0123-45678900000{i}
type: Task
state: Proposed
title: {item['title']}
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
{item['context']}

# Goal
{item['goal']}

# Approach
Standard implementation approach.

# Acceptance Criteria
- Feature should work correctly
- Tests should pass

# Risks / Dependencies
None.

# Worklog
2026-01-23 10:00 [agent=test] Created test item.
"""
        item_path.write_text(item_content, encoding='utf-8')
    
    # Phase A: Build SQLite index
    index_result = build_index(product="test-product", backlog_root=backlog_root)
    assert index_result.items_indexed == 3
    
    # Verify index status
    status = get_index_status(product="test-product", backlog_root=backlog_root)
    assert len(status.indexes) == 1
    assert status.indexes[0].exists
    assert status.indexes[0].item_count == 3
    
    # Phase B: Build vector index (with noop embeddings)
    vector_result = build_vector_index(
        product="test-product", 
        backlog_root=backlog_root,
        force=True
    )
    assert vector_result.items_processed == 3
    assert vector_result.chunks_indexed >= 3  # At least one chunk per item
    assert vector_result.backend_type == "sqlite"
    
    # Phase C: Test search functionality
    # Search for embedding-related content
    search_results = search_similar(
        query_text="embedding pipeline semantic search",
        product="test-product",
        k=5,
        backlog_root=backlog_root
    )
    
    # Should return results (even with noop embeddings, similarity should work)
    assert len(search_results) > 0
    
    # Search for SQLite-related content
    sqlite_results = search_similar(
        query_text="SQLite index database",
        product="test-product", 
        k=5,
        backlog_root=backlog_root
    )
    
    assert len(sqlite_results) > 0
    
    # Verify search results have expected structure
    for result in search_results:
        assert hasattr(result, 'chunk_id')
        assert hasattr(result, 'text')
        assert hasattr(result, 'score')
        assert hasattr(result, 'source_id')
        assert hasattr(result, 'duration_ms')
        assert isinstance(result.text, str)
        assert len(result.text) > 0


def test_index_build_deterministic(tmp_path):
    """Test that index builds are deterministic."""
    # Setup minimal test structure
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    items_root = product_root / "items" / "task" / "0000"
    items_root.mkdir(parents=True)
    
    # Create a single test item
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
This is a test task for deterministic indexing.

# Goal
Verify that index builds are consistent.
"""
    item_path.write_text(item_content, encoding='utf-8')
    
    # Build index twice
    result1 = build_index(product="test-product", backlog_root=backlog_root)
    result2 = build_index(product="test-product", backlog_root=backlog_root, force=True)
    
    # Results should be identical
    assert result1.items_indexed == result2.items_indexed == 1
    
    # Status should be consistent
    status1 = get_index_status(product="test-product", backlog_root=backlog_root)
    status2 = get_index_status(product="test-product", backlog_root=backlog_root)
    
    assert status1.indexes[0].item_count == status2.indexes[0].item_count == 1
