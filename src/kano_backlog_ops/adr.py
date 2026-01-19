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
import sys

import frontmatter

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


@dataclass
class AdrUidFixAction:
    path: Path
    old_uid: str
    new_uid: Optional[str]
    status: str


@dataclass
class AdrUidFixResult:
    product: str
    checked: int
    updated: int
    actions: List[AdrUidFixAction]


# Conditional import for UUIDv7
if sys.version_info >= (3, 12):
    from uuid import uuid7  # type: ignore
else:
    from uuid6 import uuid7  # type: ignore


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
    adr_uid = str(uuid7())
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
        f"uid: {adr_uid}\n"
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
            "uid": adr_uid,
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


def _is_uuidv7(value: str) -> bool:
    pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    return bool(pattern.match(value.lower()))


def backfill_adr_uids(
    *,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
    agent: str,
    model: Optional[str] = None,
    apply: bool = False,
) -> List[AdrUidFixResult]:
    """Add missing/invalid ADR UIDs (UUIDv7) across product decisions."""
    results: List[AdrUidFixResult] = []

    product_roots: List[Path] = []
    if backlog_root:
        backlog_root = Path(backlog_root).resolve()
        if product:
            product_roots.append(backlog_root / "products" / product)
        else:
            products_dir = backlog_root / "products"
            if products_dir.exists():
                product_roots.extend([p for p in products_dir.iterdir() if p.is_dir()])
    else:
        if product:
            ctx = ConfigLoader.from_path(Path.cwd(), product=product)
            product_roots.append(ctx.product_root)
        else:
            ctx = ConfigLoader.from_path(Path.cwd())
            products_dir = ctx.backlog_root / "products"
            if products_dir.exists():
                product_roots.extend([p for p in products_dir.iterdir() if p.is_dir()])

    for root in product_roots:
        decisions_dir = root / "decisions"
        actions: List[AdrUidFixAction] = []
        checked = 0
        updated = 0

        if not decisions_dir.exists():
            results.append(AdrUidFixResult(product=root.name, checked=0, updated=0, actions=[]))
            continue

        for path in decisions_dir.glob("*.md"):
            if path.name.lower() == "readme.md":
                continue
            try:
                post = frontmatter.load(path)
            except Exception:
                continue
            checked += 1
            current_uid = str(post.get("uid", "") or "")
            if current_uid and _is_uuidv7(current_uid):
                actions.append(AdrUidFixAction(path=path, old_uid=current_uid, new_uid=None, status="ok"))
                continue

            new_uid = str(uuid7())
            actions.append(AdrUidFixAction(path=path, old_uid=current_uid or "<missing>", new_uid=new_uid, status="added"))
            if apply:
                post["uid"] = new_uid
                path.write_text(frontmatter.dumps(post), encoding="utf-8")
                updated += 1
                AuditLog.log_file_operation(
                    operation="update",
                    path=str(path).replace("\\", "/"),
                    tool="kano backlog adr fix-uids",
                    agent=agent,
                    metadata={
                        "adr_id": post.get("id"),
                        "uid": new_uid,
                        "product": root.name,
                        "model": model,
                    },
                )

        results.append(AdrUidFixResult(product=root.name, checked=checked, updated=updated, actions=actions))

    return results
