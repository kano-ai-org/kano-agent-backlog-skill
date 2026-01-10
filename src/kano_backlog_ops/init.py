"""
init.py - Backlog initialization operations.

This module provides use-case functions for initializing backlog structures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from kano_backlog_core.config import BacklogContext


def init_backlog(
    product: str,
    backlog_root: Optional[Path] = None,
    *,
    agent: str,
    create_guides: bool = False,
) -> Path:
    """
    Initialize backlog structure for a product.

    Creates:
    - items/ folder structure (by type)
    - decisions/ folder
    - views/ folder
    - _config/config.json
    - _index/ folder
    - _meta/ folder

    Args:
        product: Product name (used as folder name and ID prefix)
        backlog_root: Root path for backlog (defaults to _kano/backlog/products/<product>)
        agent: Agent identity for audit logging
        create_guides: Whether to create/update AGENTS.md, CLAUDE.md

    Returns:
        Path to the initialized product backlog root

    Raises:
        FileExistsError: If backlog already initialized
        ValueError: If product name is invalid
    """
    # TODO: Implement - currently delegates to bootstrap_init_backlog.py
    raise NotImplementedError("init_backlog not yet implemented - use bootstrap_init_backlog.py")


def check_initialized(
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> bool:
    """
    Check if backlog is initialized for a product.

    Args:
        product: Product name to check
        backlog_root: Root path for backlog

    Returns:
        True if config.json exists and is valid
    """
    # TODO: Implement
    raise NotImplementedError("check_initialized not yet implemented")
