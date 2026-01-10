"""
index.py - SQLite index operations.

This module provides use-case functions for building and maintaining
the SQLite index that accelerates backlog queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class IndexBuildResult:
    """Result of building the index."""
    index_path: Path
    items_indexed: int
    links_indexed: int
    build_time_ms: float


@dataclass
class IndexRefreshResult:
    """Result of refreshing the index."""
    index_path: Path
    items_added: int
    items_updated: int
    items_removed: int
    refresh_time_ms: float


def build_index(
    *,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
    force: bool = False,
) -> IndexBuildResult:
    """
    Build the SQLite index from scratch.

    Scans all backlog items and creates the index database.

    Args:
        product: Product name (builds index for all if not specified)
        backlog_root: Root path for backlog
        force: Force rebuild even if index exists

    Returns:
        IndexBuildResult with build details

    Raises:
        FileNotFoundError: If backlog not initialized
        FileExistsError: If index exists and force=False
    """
    # TODO: Implement - currently delegates to build_sqlite_index.py
    raise NotImplementedError("build_index not yet implemented - use build_sqlite_index.py")


def refresh_index(
    *,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> IndexRefreshResult:
    """
    Incrementally refresh the index.

    Updates the index with changes since last refresh (based on mtime).

    Args:
        product: Product name
        backlog_root: Root path for backlog

    Returns:
        IndexRefreshResult with refresh details

    Raises:
        FileNotFoundError: If index not built yet
    """
    # TODO: Implement - currently delegates to build_sqlite_index.py with incremental mode
    raise NotImplementedError("refresh_index not yet implemented - use build_sqlite_index.py")
