"""
Schema loader for SQLite index and canonical schemas.

This module provides utilities to load SQL schema files from the core schema directory.
Per ADR-0012, all schemas should be loaded from these canonical definitions rather than
hardcoded in application code.
"""

from pathlib import Path
from typing import Optional


_SCHEMA_DIR = Path(__file__).parent


def load_indexing_schema() -> str:
    """Load the indexing schema SQL.
    
    This schema is used for the rebuildable SQLite index at .cache/index.sqlite3.
    It is aligned with canonical_schema.sql per ADR-0012.
    
    Returns:
        SQL string for creating the index schema
    """
    schema_path = _SCHEMA_DIR / "indexing_schema.sql"
    return schema_path.read_text(encoding="utf-8")


def load_canonical_schema() -> str:
    """Load the canonical schema SQL.
    
    This schema defines the complete data model used by:
    - Repo-level derived index
    - Workset DBs (per-agent/per-task materialized cache bundles)
    
    Per ADR-0012, workset DBs MUST reuse this schema.
    
    Returns:
        SQL string for creating the canonical schema
    """
    schema_path = _SCHEMA_DIR / "canonical_schema.sql"
    return schema_path.read_text(encoding="utf-8")


def get_schema_path(schema_name: str) -> Path:
    """Get the path to a schema file.
    
    Args:
        schema_name: Name of the schema file (e.g., 'indexing_schema.sql')
        
    Returns:
        Path to the schema file
        
    Raises:
        FileNotFoundError: If schema file does not exist
    """
    schema_path = _SCHEMA_DIR / schema_name
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    return schema_path
