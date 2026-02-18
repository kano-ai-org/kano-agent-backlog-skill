"""Tests for atomic ID generation."""

import concurrent.futures
import sqlite3
import pytest
from pathlib import Path
from kano_backlog_ops.item_utils import get_next_id_from_db
from conftest import write_project_backlog_config

def test_atomic_id_generation_concurrent(tmp_path: Path):
    """Test that concurrent ID generation produces unique, sequential IDs."""
    db_path = tmp_path / "chunks.sqlite3"
    
    # Init DB
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE id_sequences (
            prefix TEXT NOT NULL,
            type_code TEXT NOT NULL,
            next_number INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (prefix, type_code)
        )
    """)
    conn.close()
    
    prefix = "TEST"
    type_code = "TSK"
    worker_count = 10
    ids_per_worker = 50
    total_ids = worker_count * ids_per_worker
    
    def generate_ids():
        my_ids = []
        for _ in range(ids_per_worker):
            # Simulate some work
            new_id = get_next_id_from_db(db_path, prefix, type_code)
            my_ids.append(new_id)
        return my_ids
        
    # Run concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(generate_ids) for _ in range(worker_count)]
        results = []
        for future in concurrent.futures.as_completed(futures):
            results.extend(future.result())
            
    # Verification
    assert len(results) == total_ids
    assert len(set(results)) == total_ids  # All unique
    
    # Check range
    results.sort()
    assert results[0] == 1
    assert results[-1] == total_ids
    
    # Check DB state
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "SELECT next_number FROM id_sequences WHERE prefix = ? AND type_code = ?",
        (prefix, type_code)
    )
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == total_ids

def test_sync_sequences_dry_run(tmp_path: Path):
    """Test synchronization dry run."""
    write_project_backlog_config(tmp_path)

    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    items_root = product_root / "items" / "task" / "0000"
    items_root.mkdir(parents=True)
    
    (items_root / "TEST-TSK-0001_a.md").touch()
    (items_root / "TEST-TSK-0002_b.md").touch()
    (items_root / "TEST-TSK-0005_c.md").touch()
    
    from kano_backlog_ops.item_utils import sync_id_sequences

    cache_dir = tmp_path / ".kano" / "cache" / "backlog"
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / "backlog.test-product.chunks.v1.db"
    
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE id_sequences (
            prefix TEXT NOT NULL,
            type_code TEXT NOT NULL,
            next_number INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (prefix, type_code)
        )
    """)
    conn.commit()
    conn.close()
    
    result = sync_id_sequences(product="test-product", backlog_root=backlog_root, dry_run=True)
    
    assert result["TSK"] == 6
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT next_number FROM id_sequences WHERE prefix = 'TEST'")
    assert cursor.fetchone() is None
    conn.close()
    
    sync_id_sequences(product="test-product", backlog_root=backlog_root, dry_run=False)
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT next_number FROM id_sequences WHERE prefix = 'TEST' AND type_code = 'TSK'")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == 6
    conn.close()
