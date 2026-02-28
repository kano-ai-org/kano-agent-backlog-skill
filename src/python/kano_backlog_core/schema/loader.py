"""
Schema loader for SQLite index and canonical schemas.

This module provides utilities to load SQL schema files from the core schema directory.
Per ADR-0012, all schemas should be loaded from these canonical definitions rather than
hardcoded in application code.
"""

from pathlib import Path
from typing import Iterable, Optional


_SCHEMA_DIR = Path(__file__).parent


def load_schema(schema_name: str) -> str:
    """Load a schema file by name.

    Args:
        schema_name: Filename under this directory.

    Returns:
        SQL string.
    """
    return get_schema_path(schema_name).read_text(encoding="utf-8")


def load_schema_bundle(schema_names: Iterable[str]) -> str:
    """Load and concatenate multiple schema files.

    This is useful when a DB needs the canonical schema plus optional additive
    extensions (e.g., workset_ tables) while keeping each schema in its own file.

    Args:
        schema_names: Sequence of filenames under this directory.

    Returns:
        Combined SQL string.
    """
    parts = []
    for name in schema_names:
        text = load_schema(name)
        parts.append(f"\n\n-- === {name} ===\n\n")
        parts.append(text)
    return "".join(parts).lstrip()


def load_indexing_schema() -> str:
    """Load the indexing schema SQL.
    
    This schema is used for the rebuildable SQLite index at .cache/index.sqlite3.
    It is aligned with canonical_schema.sql per ADR-0012.
    
    Returns:
        SQL string for creating the index schema
    """
    return load_schema("indexing_schema.sql")


def load_canonical_schema() -> str:
    """Load the canonical schema SQL.
    
    This schema defines the complete data model used by:
    - Repo-level derived index
    - Workset DBs (per-agent/per-task materialized cache bundles)
    
    Per ADR-0012, workset DBs MUST reuse this schema.
    
    Returns:
        SQL string for creating the canonical schema
    """
    return load_schema("canonical_schema.sql")


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
