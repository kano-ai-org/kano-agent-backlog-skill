"""
Schema definitions for the Kano backlog system.

This package contains SQL schema files and utilities for loading them.
Per ADR-0012, all schemas should be loaded from these canonical definitions.

Available schemas:
- indexing_schema.sql: Schema for rebuildable SQLite index
- canonical_schema.sql: Complete canonical schema for worksets and indexes
"""

from .loader import (
    load_indexing_schema,
    load_canonical_schema,
    get_schema_path,
)

__all__ = [
    "load_indexing_schema",
    "load_canonical_schema",
    "get_schema_path",
]
