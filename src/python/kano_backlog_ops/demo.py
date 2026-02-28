"""Demo data seeding operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from kano_backlog_core.models import ItemType
from .workitem import create_item, CreateItemResult
from .init import _resolve_backlog_root


@dataclass
class DemoSeedResult:
    """Result of seeding demo data."""
    product_root: Path
    items_created: List[CreateItemResult]
    skipped: int


def seed_demo(
    *,
    product: str,
    agent: str,
    backlog_root: Optional[Path] = None,
    count: int = 5,
    force: bool = False,
) -> DemoSeedResult:
    """
    Seed a product with reproducible demo items.

    Creates a small set of sample items (epic → feature → task/bug) for testing/demos.

    Args:
        product: Product name
        agent: Agent identifier for audit logging
        backlog_root: Backlog root path (auto-detected if None)
        count: Number of demo items to create (default: 5, creates 1 epic → 1 feature → 3 tasks)
        force: Recreate items even if they exist (deletes existing demo items first)

    Returns:
        DemoSeedResult with created items

    Raises:
        FileNotFoundError: If product not initialized
        FileExistsError: If demo items exist and force=False
    """
    backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)
    product_root = backlog_root_path / "products" / product
    if not product_root.exists():
        raise FileNotFoundError(f"Product not initialized: {product_root}")

    # Check for existing demo items
    existing_demo = _find_demo_items(product_root)
    if existing_demo and not force:
        raise FileExistsError(
            f"Demo items already exist in {product} (found {len(existing_demo)} items). "
            "Use --force to recreate."
        )

    # Clean up existing demo items if force=True
    if existing_demo and force:
        for item_path in existing_demo:
            item_path.unlink()

    # Create demo hierarchy
    created: List[CreateItemResult] = []

    # 1. Epic
    epic_result = create_item(
        item_type=ItemType.EPIC,
        title="Demo Epic: Multi-Agent Backlog System",
        product=product,
        agent=agent,
        priority="P1",
        area="demo",
        tags=["demo", "sample"],
    )
    created.append(epic_result)

    # 2. Feature
    feature_result = create_item(
        item_type=ItemType.FEATURE,
        title="Demo Feature: Local-First Backlog Ops",
        product=product,
        agent=agent,
        parent=epic_result.id,
        priority="P1",
        area="demo",
        tags=["demo", "sample"],
    )
    created.append(feature_result)

    # 3. Tasks (limit based on count parameter)
    task_count = min(count - 2, 3)  # Reserve 2 for epic+feature
    task_titles = [
        "Implement file-based canonical storage",
        "Add SQLite index builder",
        "Create CLI facade with Typer",
    ]

    for i, title in enumerate(task_titles[:task_count]):
        task_result = create_item(
            item_type=ItemType.TASK,
            title=f"Demo Task: {title}",
            product=product,
            agent=agent,
            parent=feature_result.id,
            priority="P2",
            area="demo",
            tags=["demo", "sample"],
        )
        created.append(task_result)

    return DemoSeedResult(
        product_root=product_root,
        items_created=created,
        skipped=len(existing_demo),
    )


def _find_demo_items(product_root: Path) -> List[Path]:
    """Find all demo items (tagged with 'demo' or containing 'Demo' in title)."""
    items_root = product_root / "items"
    if not items_root.exists():
        return []

    demo_items: List[Path] = []
    for md_file in items_root.glob("**/*.md"):
        if "demo" in md_file.name.lower():
            demo_items.append(md_file)
    return demo_items
