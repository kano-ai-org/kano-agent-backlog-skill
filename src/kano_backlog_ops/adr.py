"""
adr.py - ADR (Architecture Decision Record) operations.

This module provides use-case functions for creating and managing ADRs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from datetime import date


@dataclass
class ADRInfo:
    """ADR metadata."""
    id: str
    title: str
    status: str
    date: date
    path: Path
    related_items: List[str]


@dataclass
class CreateADRResult:
    """Result of creating an ADR."""
    id: str
    title: str
    path: Path


def create_adr(
    title: str,
    *,
    product: str,
    agent: str,
    related_items: Optional[List[str]] = None,
    status: str = "Proposed",
    backlog_root: Optional[Path] = None,
) -> CreateADRResult:
    """
    Create a new ADR.

    Args:
        title: ADR title
        product: Product name
        agent: Agent identity for audit logging
        related_items: List of related item IDs
        status: Initial status (default: Proposed)
        backlog_root: Root path for backlog

    Returns:
        CreateADRResult with created ADR details

    Raises:
        ValueError: If title is empty
        FileNotFoundError: If backlog not initialized
    """
    # TODO: Implement - currently delegates to adr_init.py
    raise NotImplementedError("create_adr not yet implemented - use adr_init.py")


def list_adrs(
    *,
    product: Optional[str] = None,
    status: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> List[ADRInfo]:
    """
    List ADRs with optional filters.

    Args:
        product: Filter by product
        status: Filter by status
        backlog_root: Root path for backlog

    Returns:
        List of ADRInfo objects
    """
    # TODO: Implement
    raise NotImplementedError("list_adrs not yet implemented")
