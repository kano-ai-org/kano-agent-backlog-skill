"""
workitem.py - Work item CRUD operations (direct implementation, no subprocess).

Per ADR-0013: This module provides use-case functions for creating, reading, updating,
and listing backlog work items (Epic, Feature, UserStory, Task, Bug).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from datetime import datetime
import sys
import uuid

from kano_backlog_core.models import BacklogItem, ItemType, ItemState
if sys.version_info >= (3, 12):
    from uuid import uuid7  # type: ignore
else:
    from uuid6 import uuid7  # type: ignore
from kano_backlog_core.config import BacklogContext, ConfigLoader

from . import item_utils
from . import item_templates
from . import frontmatter
from . import worklog


@dataclass
class CreateItemResult:
    """Result of creating a work item."""
    id: str
    uid: str
    path: Path
    type: ItemType


@dataclass
class UpdateStateResult:
    """Result of updating item state."""
    id: str
    old_state: ItemState
    new_state: ItemState
    worklog_appended: bool
    parent_synced: bool
    dashboards_refreshed: bool


@dataclass
class ValidationResult:
    """Result of Ready gate validation."""
    id: str
    is_valid: bool
    missing_sections: List[str]
    warnings: List[str]


def create_item(
    item_type: ItemType,
    title: str,
    *,
    product: Optional[str] = None,
    agent: str,
    parent: Optional[str] = None,
    priority: str = "P2",
    tags: Optional[List[str]] = None,
    area: Optional[str] = None,
    iteration: Optional[str] = None,
    backlog_root: Optional[Path] = None,
    worklog_message: str = "Created item",
) -> CreateItemResult:
    """
    Create a new work item (direct implementation).

    Args:
        item_type: Type of item (epic, feature, userstory, task, bug)
        title: Item title
        product: Product name (default: "demo" for testing/local development)
        agent: Agent identity for audit logging
        parent: Parent item ID (optional)
        priority: Priority level (P0-P3, default P2)
        tags: List of tags
        area: Area/component
        iteration: Sprint/iteration
        backlog_root: Root path for backlog
        worklog_message: Initial worklog message

    Returns:
        CreateItemResult with created item details

    Raises:
        ValueError: If title is empty or type is invalid
        FileNotFoundError: If backlog not initialized
        OSError: If unable to write item file
    """
    if not title or not title.strip():
        raise ValueError("Title cannot be empty")
    
    # Setup
    title = title.strip()
    tags = tags or []
    area = area or "general"
    iteration = iteration or "backlog"
    product = product or "demo"  # Default for testing
    
    # Resolve context (backlog root + product root + prefix)
    if backlog_root is None:
        try:
            ctx = ConfigLoader.from_path(Path.cwd(), product=product)
            backlog_root = ctx.product_root  # Use product root, not platform root
            # Read prefix from product config
            config_path = backlog_root / "_config" / "config.json"
            if config_path.exists():
                import json
                config_data = json.loads(config_path.read_text(encoding="utf-8"))
                prefix = config_data.get("project", {}).get("prefix") or item_utils.derive_prefix(product)
            else:
                prefix = item_utils.derive_prefix(product)
        except Exception as e:
            raise ValueError(
                f"Cannot resolve backlog context for product '{product}'. "
                f"Ensure the product is initialized via 'kano backlog init --product {product}'. "
                f"Error: {e}"
            )
    else:
        # Explicit backlog_root provided; use it directly and derive prefix
        prefix = item_utils.derive_prefix(product)
    
    # Generate IDs
    type_code_map = {
        ItemType.EPIC: "EPIC",
        ItemType.FEATURE: "FTR",
        ItemType.USER_STORY: "USR",
        ItemType.TASK: "TSK",
        ItemType.BUG: "BUG",
    }
    type_code = type_code_map[item_type]
    items_root = backlog_root / "items"
    next_id = item_utils.find_next_number(items_root, prefix, type_code)
    item_id = f"{prefix}-{type_code}-{next_id:04d}"
    uid = str(uuid7())
    
    # Calculate storage path
    bucket = item_utils.calculate_bucket(next_id)
    
    # Determine subdirectory based on item type
    type_subdir_map = {
        ItemType.EPIC: "epic",
        ItemType.FEATURE: "feature",
        ItemType.USER_STORY: "userstory",
        ItemType.TASK: "task",
        ItemType.BUG: "bug",
    }
    subdir = type_subdir_map[item_type]
    
    item_dir = backlog_root / "items" / subdir / bucket
    
    # Construct item filename: <ID>_<slugified_title>.md
    slug = item_utils.slugify(title)
    item_path = item_dir / f"{item_id}_{slug}.md"
    
    # Create directory if needed
    item_dir.mkdir(parents=True, exist_ok=True)
    
    # Create parent reference
    parent_ref = parent or "null"
    
    # Create timestamps
    today = item_utils.get_today()
    
    # Generate content
    content = item_templates.render_item_body(
        item_id=item_id,
        uid=uid,
        item_type=item_type.value,
        title=title,
        priority=priority,
        parent=parent_ref,
        area=area,
        iteration=iteration,
        tags=tags,
        created=today,
        updated=today,
        owner=None,
        agent=agent,
        worklog_message=worklog_message,
    )
    
    # Write item file
    try:
        item_path.write_text(content, encoding="utf-8")
    except OSError as e:
        raise OSError(f"Failed to write item file {item_path}: {e}") from e
    
    # If Epic, create index MOC
    if item_type == ItemType.EPIC:
        index_path = item_path.parent / f"{item_id}_{item_utils.slugify(title)}.index.md"
        index_content = item_templates.render_epic_index(
            item_id=item_id,
            title=title,
            updated=today,
            backlog_root_label="../../..",  # Relative path from index to backlog root
        )
        try:
            index_path.write_text(index_content, encoding="utf-8")
        except OSError as e:
            raise OSError(f"Failed to write index file {index_path}: {e}") from e
        
        # Update _meta/indexes.md registry
        _update_index_registry(backlog_root, item_id, title, "add")
    
    return CreateItemResult(
        id=item_id,
        uid=uid,
        path=item_path,
        type=item_type,
    )


def update_state(
    item_ref: str,
    new_state: ItemState,
    *,
    agent: str,
    message: Optional[str] = None,
    product: Optional[str] = None,
    sync_parent: bool = True,
    refresh_dashboards: bool = True,
    backlog_root: Optional[Path] = None,
) -> UpdateStateResult:
    """
    Update work item state (direct implementation).

    Args:
        item_ref: Item reference (ID, UID, or path)
        new_state: Target state
        agent: Agent identity for audit logging
        message: Worklog message (optional)
        product: Product name (for disambiguation)
        sync_parent: Whether to sync parent state forward
        refresh_dashboards: Whether to refresh dashboards after update
        backlog_root: Root path for backlog

    Returns:
        UpdateStateResult with transition details

    Raises:
        FileNotFoundError: If item not found
        ValueError: If state transition is invalid
    """
    # Resolve item path
    if item_ref.startswith("/") or ":\\" in item_ref:
        # It's a path
        item_path = Path(item_ref).resolve()
    else:
        # It's an ID or UID - need to search for it
        if backlog_root is None:
            # Find backlog root
            current = Path.cwd()
            while current != current.parent:
                backlog_check = current / "_kano" / "backlog"
                if backlog_check.exists():
                    backlog_root = backlog_check
                    break
                current = current.parent
            if backlog_root is None:
                raise ValueError("Cannot find backlog root")
        
        # Search for item by ID in items/
        items_root = backlog_root / "items"
        item_path = None
        for path in items_root.rglob("*.md"):
            if path.name.endswith(".index.md"):
                continue
            # Extract ID from filename
            stem = path.stem
            file_id = stem.split("_", 1)[0] if "_" in stem else stem
            if file_id == item_ref:
                item_path = path
                break
        
        if item_path is None:
            raise FileNotFoundError(f"Item not found: {item_ref}")
    
    # Verify item exists
    if not item_path.exists():
        raise FileNotFoundError(f"Item not found: {item_path}")
    
    # Load and parse item
    lines = frontmatter.load_lines(item_path)
    fm = frontmatter.parse_frontmatter(lines)
    
    old_state_str = fm.get("state", "Proposed")
    old_state = ItemState(old_state_str) if old_state_str in [s.value for s in ItemState] else ItemState.NEW
    
    # Update frontmatter
    today = item_utils.get_today()
    
    # Auto-set owner when moving to InProgress
    owner_to_set = None
    current_owner = fm.get("owner", "").strip()
    if new_state == ItemState.IN_PROGRESS:
        if not current_owner or current_owner.lower() == "null":
            owner_to_set = agent
        elif current_owner == agent:
            owner_to_set = agent
    
    lines = frontmatter.update_frontmatter(lines, new_state.value, today, owner=owner_to_set)
    
    # Append worklog
    worklog_message = message or f"State -> {new_state.value}."
    lines = worklog.append_worklog_entry(lines, worklog_message, agent)
    
    # Write updated file
    try:
        frontmatter.write_lines(item_path, lines)
    except OSError as e:
        raise OSError(f"Failed to write item file {item_path}: {e}") from e
    
    return UpdateStateResult(
        id=fm.get("id", item_ref),
        old_state=old_state,
        new_state=new_state,
        worklog_appended=True,
        parent_synced=False,  # TODO: Implement parent sync
        dashboards_refreshed=False,  # TODO: Implement dashboard refresh
    )


def validate_ready(
    item_ref: str,
    *,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> ValidationResult:
    """
    Validate item meets Ready gate criteria (direct implementation).

    For Task/Bug, checks that these sections are non-empty:
    - Context
    - Goal
    - Approach
    - Acceptance Criteria
    - Risks / Dependencies

    Args:
        item_ref: Item reference (ID, UID, or path)
        product: Product name (for disambiguation)
        backlog_root: Root path for backlog

    Returns:
        ValidationResult with validation details

    Raises:
        FileNotFoundError: If item not found
    """
    # Resolve item path
    if item_ref.startswith("/") or ":\\" in item_ref:
        # It's a path
        item_path = Path(item_ref).resolve()
    else:
        # It's an ID - search for it
        if backlog_root is None:
            # Find backlog root
            current = Path.cwd()
            while current != current.parent:
                backlog_check = current / "_kano" / "backlog"
                if backlog_check.exists():
                    backlog_root = backlog_check
                    break
                current = current.parent
            if backlog_root is None:
                raise ValueError("Cannot find backlog root")
        
        # Search for item by ID
        items_root = backlog_root / "items"
        item_path = None
        for path in items_root.rglob("*.md"):
            if path.name.endswith(".index.md"):
                continue
            stem = path.stem
            file_id = stem.split("_", 1)[0] if "_" in stem else stem
            if file_id == item_ref:
                item_path = path
                break
        
        if item_path is None:
            raise FileNotFoundError(f"Item not found: {item_ref}")
    
    if not item_path.exists():
        raise FileNotFoundError(f"Item not found: {item_path}")
    
    # Load and parse
    lines = frontmatter.load_lines(item_path)
    fm = frontmatter.parse_frontmatter(lines)
    item_type = fm.get("type", "").strip()
    item_id = fm.get("id", item_ref)
    
    # Ready gate sections (required for Task/Bug)
    required_sections = {"Context", "Goal", "Approach", "Acceptance Criteria", "Risks / Dependencies"}
    
    # Extract sections from content
    sections_found = set()
    for line in lines:
        if line.startswith("# "):
            section_name = line[2:].strip()
            sections_found.add(section_name)
    
    # Check for required sections (apply to Task/Bug)
    missing_sections = []
    if item_type in ("Task", "Bug"):
        for section in required_sections:
            if section not in sections_found:
                missing_sections.append(section)
    
    is_valid = len(missing_sections) == 0
    
    return ValidationResult(
        id=item_id,
        is_valid=is_valid,
        missing_sections=missing_sections,
        warnings=[],
    )


def list_items(
    *,
    product: Optional[str] = None,
    item_type: Optional[ItemType] = None,
    state: Optional[ItemState] = None,
    parent: Optional[str] = None,
    tags: Optional[List[str]] = None,
    backlog_root: Optional[Path] = None,
) -> List[BacklogItem]:
    """
    List work items with optional filters.

    Args:
        product: Filter by product
        item_type: Filter by type
        state: Filter by state
        parent: Filter by parent ID
        tags: Filter by tags (AND)
        backlog_root: Root path for backlog

    Returns:
        List of matching BacklogItem objects
    """
    # TODO: Implement
    raise NotImplementedError("list_items not yet implemented")


def get_item(
    item_ref: str,
    *,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> BacklogItem:
    """
    Get a single work item by reference.

    Args:
        item_ref: Item reference (ID, UID, or path)
        product: Product name (for disambiguation)
        backlog_root: Root path for backlog

    Returns:
        BacklogItem object

    Raises:
        FileNotFoundError: If item not found
        ValueError: If reference is ambiguous
    """
    # TODO: Implement - currently delegates to workitem_resolve_ref.py
    raise NotImplementedError("get_item not yet implemented - use workitem_resolve_ref.py")


def _update_index_registry(
    backlog_root: Path,
    item_id: str,
    title: str,
    action: str,
) -> None:
    """
    Update _meta/indexes.md registry when epic index is created/deleted.
    
    Args:
        backlog_root: Root of backlog
        item_id: Epic ID
        title: Epic title
        action: "add" or "remove"
    """
    registry_path = backlog_root / "_meta" / "indexes.md"
    
    if not registry_path.exists():
        # Create basic registry if missing
        content = "# Index Registry\n\n## Epics\n"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(content, encoding="utf-8")
    
    content = registry_path.read_text(encoding="utf-8")
    
    if action == "add":
        # Add entry if not already present
        entry = f"- [{title}]({item_id}_{item_utils.slugify(title)}.index.md) (ID: {item_id})"
        if entry not in content:
            lines = content.rstrip().split("\n")
            lines.append(entry)
            content = "\n".join(lines) + "\n"
    elif action == "remove":
        # Remove entry
        lines = [
            line for line in content.split("\n")
            if item_id not in line
        ]
        content = "\n".join(lines) + "\n"
    
    registry_path.write_text(content, encoding="utf-8")
