"""
adr.py - ADR (Architecture Decision Record) operations.

This module provides use-case functions for creating and managing ADRs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from datetime import date
import re

from kano_backlog_core.audit import AuditLog
from kano_backlog_core.config import ConfigLoader

from .item_utils import slugify


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

    if not title or not title.strip():
        raise ValueError("ADR title cannot be empty")

    if backlog_root is not None:
        backlog_root = backlog_root.resolve()
        products_root = backlog_root / "products"
        product_root = (products_root / product) if products_root.exists() else backlog_root
        if not product_root.exists():
            raise FileNotFoundError(f"Product root does not exist: {product_root}")
    else:
        context = ConfigLoader.from_path(Path.cwd(), product=product)
        product_root = context.product_root

    decisions_dir = product_root / "decisions"
    if not decisions_dir.exists() or not decisions_dir.is_dir():
        raise FileNotFoundError(f"Decisions directory not found: {decisions_dir}")

    next_number = _find_next_adr_number(decisions_dir)
    adr_id = f"ADR-{next_number:04d}"
    adr_slug = slugify(title)
    adr_path = decisions_dir / f"{adr_id}_{adr_slug}.md"

    if adr_path.exists():
        raise FileExistsError(f"ADR already exists: {adr_path}")

    related_items = list(related_items or [])
    today = date.today().isoformat()

    related_items_yaml = _yaml_list_inline(related_items)
    content = (
        "---\n"
        f"id: {adr_id}\n"
        f"title: \"{_escape_yaml_string(title.strip())}\"\n"
        f"status: {status}\n"
        f"date: {today}\n"
        f"related_items: {related_items_yaml}\n"
        "supersedes: null\n"
        "superseded_by: null\n"
        "---\n\n"
        "# Decision\n\n"
        "# Context\n\n"
        "# Options Considered\n\n"
        "# Pros / Cons\n\n"
        "# Consequences\n\n"
        "# Follow-ups\n"
    )

    decisions_dir.mkdir(parents=True, exist_ok=True)
    adr_path.write_text(content, encoding="utf-8")

    AuditLog.log_file_operation(
        operation="create",
        path=str(adr_path).replace("\\\\", "/"),
        tool="kano backlog adr create",
        agent=agent,
        metadata={
            "adr_id": adr_id,
            "title": title.strip(),
            "product": product,
            "status": status,
            "related_items": related_items,
        },
    )

    return CreateADRResult(id=adr_id, title=title.strip(), path=adr_path)


def _find_next_adr_number(decisions_dir: Path) -> int:
    """Find next ADR number by parsing frontmatter IDs (not filenames)."""
    pattern = re.compile(r"^id:\s*ADR-(\d{4})", re.MULTILINE)
    max_num = 0
    
    for path in decisions_dir.glob("*.md"):
        if path.name == "README.md":
            continue
        try:
            content = path.read_text(encoding="utf-8")
            match = pattern.search(content)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)
        except (OSError, ValueError):
            continue
    
    return max_num + 1


def _yaml_list_inline(values: List[str]) -> str:
    if not values:
        return "[]"
    escaped = [f"\"{_escape_yaml_string(v)}\"" for v in values]
    return f"[{', '.join(escaped)}]"


def _escape_yaml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', "\\\"")


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
