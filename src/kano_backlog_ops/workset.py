"""
workset.py - Workset cache management operations.

This module provides use-case functions for managing per-item workset caches.
Worksets provide a focused execution context during task work, preventing agent drift.

Per ADR-0011 and ADR-0012, worksets are derived data that can be deleted and rebuilt.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from kano_backlog_core.errors import BacklogError


# =============================================================================
# Error Types (Task 1.3)
# =============================================================================


class WorksetError(BacklogError):
    """Base error for workset operations."""

    def __init__(self, message: str, suggestion: Optional[str] = None):
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class ItemNotFoundError(WorksetError):
    """Item reference not found."""

    def __init__(self, item_ref: str):
        self.item_ref = item_ref
        super().__init__(
            f"Item not found: {item_ref}",
            suggestion="Check the item ID, UID, or path is correct",
        )


class WorksetNotFoundError(WorksetError):
    """Workset not initialized."""

    def __init__(self, item_ref: str):
        self.item_ref = item_ref
        super().__init__(
            f"Workset not found for item: {item_ref}",
            suggestion="Run 'kano workset init --item <id>' first",
        )


class WorksetValidationError(WorksetError):
    """Validation failed."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        error_list = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"Validation failed:\n{error_list}")


# =============================================================================
# Data Models (Task 1.2)
# =============================================================================


@dataclass
class WorksetMetadata:
    """Workset meta.json structure."""

    workset_id: str  # UUID for this workset instance
    item_id: str  # Source item ID (e.g., KABSD-TSK-0124)
    item_uid: str  # Source item UID
    item_path: str  # Relative path to source item
    agent: str  # Agent who initialized
    created_at: str  # ISO 8601 timestamp
    refreshed_at: str  # ISO 8601 timestamp
    ttl_hours: int = 72  # Time-to-live (default: 72)
    source_commit: Optional[str] = None  # Git commit hash at creation

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorksetMetadata":
        """Create from dictionary (JSON deserialization)."""
        return cls(
            workset_id=data["workset_id"],
            item_id=data["item_id"],
            item_uid=data["item_uid"],
            item_path=data["item_path"],
            agent=data["agent"],
            created_at=data["created_at"],
            refreshed_at=data["refreshed_at"],
            ttl_hours=data.get("ttl_hours", 72),
            source_commit=data.get("source_commit"),
        )

    def save(self, path: Path) -> None:
        """Save metadata to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "WorksetMetadata":
        """Load metadata from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


@dataclass
class WorksetInitResult:
    """Result of initializing a workset."""

    workset_path: Path
    item_count: int
    created: bool  # True if newly created, False if existing


@dataclass
class WorksetRefreshResult:
    """Result of refreshing a workset."""

    workset_path: Path
    items_added: int
    items_removed: int
    items_updated: int


@dataclass
class WorksetNextResult:
    """Result of getting next action."""

    step_number: int
    description: str
    is_complete: bool  # True if all steps done


@dataclass
class WorksetPromoteResult:
    """Result of promoting deliverables."""

    promoted_files: List[str]
    target_path: Path
    worklog_entry: str


@dataclass
class WorksetCleanupResult:
    """Result of cleanup operation."""

    deleted_count: int
    deleted_paths: List[Path]
    space_reclaimed_bytes: int


# =============================================================================
# Directory Utilities (Task 1.1)
# =============================================================================


def _find_backlog_root(start: Optional[Path] = None) -> Path:
    """
    Find the backlog root directory.
    
    Args:
        start: Starting path for search (defaults to cwd)
    
    Returns:
        Path to _kano/backlog directory
    
    Raises:
        WorksetError: If backlog root not found
    """
    current = (start or Path.cwd()).resolve()
    while current != current.parent:
        backlog_check = current / "_kano" / "backlog"
        if backlog_check.exists():
            return backlog_check
        current = current.parent
    raise WorksetError(
        "Cannot find backlog root (_kano/backlog)",
        suggestion="Ensure you are in a directory with a _kano/backlog structure",
    )


def _resolve_item_ref(
    item_ref: str,
    backlog_root: Path,
) -> tuple[Path, Dict[str, Any]]:
    """
    Resolve an item reference to its path and metadata.
    
    Args:
        item_ref: Item reference (ID, UID, or path)
        backlog_root: Root path for backlog
    
    Returns:
        Tuple of (item_path, metadata_dict)
    
    Raises:
        ItemNotFoundError: If item not found
    """
    # Check if it's a path
    if item_ref.startswith("/") or ":\\" in item_ref or item_ref.endswith(".md"):
        item_path = Path(item_ref)
        if not item_path.is_absolute():
            item_path = backlog_root / item_ref
        item_path = item_path.resolve()
        
        if not item_path.exists():
            raise ItemNotFoundError(item_ref)
        
        # Parse frontmatter to get metadata
        metadata = _parse_item_frontmatter(item_path)
        return item_path, metadata
    
    # Search for item by ID in products/*/items/
    products_dir = backlog_root / "products"
    if products_dir.exists():
        for product_dir in products_dir.iterdir():
            if not product_dir.is_dir():
                continue
            items_root = product_dir / "items"
            if not items_root.exists():
                continue
            
            # Quick filename match first
            for path in items_root.rglob(f"{item_ref}_*.md"):
                if not path.name.endswith(".index.md"):
                    metadata = _parse_item_frontmatter(path)
                    return path, metadata
            
            # Fallback: scan all and check frontmatter ids/uids
            for path in items_root.rglob("*.md"):
                if path.name.endswith(".index.md"):
                    continue
                try:
                    metadata = _parse_item_frontmatter(path)
                    if metadata.get("id") == item_ref or metadata.get("uid") == item_ref:
                        return path, metadata
                except Exception:
                    continue
    
    # Also check legacy single-product layout (items/ directly under backlog_root)
    items_root = backlog_root / "items"
    if items_root.exists():
        for path in items_root.rglob(f"{item_ref}_*.md"):
            if not path.name.endswith(".index.md"):
                metadata = _parse_item_frontmatter(path)
                return path, metadata
        
        for path in items_root.rglob("*.md"):
            if path.name.endswith(".index.md"):
                continue
            try:
                metadata = _parse_item_frontmatter(path)
                if metadata.get("id") == item_ref or metadata.get("uid") == item_ref:
                    return path, metadata
            except Exception:
                continue
    
    raise ItemNotFoundError(item_ref)


def _parse_item_frontmatter(item_path: Path) -> Dict[str, Any]:
    """
    Parse YAML frontmatter from an item file.
    
    Args:
        item_path: Path to item file
    
    Returns:
        Dictionary of frontmatter key-value pairs
    """
    content = item_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    
    if not lines or lines[0].strip() != "---":
        return {}
    
    # Find end of frontmatter
    end_idx = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    
    if end_idx == -1:
        return {}
    
    # Parse frontmatter
    data: Dict[str, Any] = {}
    for line in lines[1:end_idx]:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        # Strip quotes if present
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        data[key.strip()] = value
    
    return data


def _get_git_commit() -> Optional[str]:
    """
    Get the current git commit hash.
    
    Returns:
        Git commit hash or None if not in a git repo
    """
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]  # Short hash
    except Exception:
        pass
    return None


def _extract_acceptance_criteria(item_path: Path) -> List[str]:
    """
    Extract acceptance criteria from an item file.
    
    Args:
        item_path: Path to item file
    
    Returns:
        List of acceptance criteria strings
    """
    content = item_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    
    criteria = []
    in_ac_section = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check for Acceptance Criteria section header
        if stripped.startswith("# Acceptance Criteria"):
            in_ac_section = True
            continue
        
        # Check for next section header (end of AC section)
        if in_ac_section and stripped.startswith("# "):
            break
        
        # Collect criteria lines
        if in_ac_section and stripped:
            # Handle bullet points and numbered lists
            if stripped.startswith("- ") or stripped.startswith("* "):
                criteria.append(stripped[2:])
            elif re.match(r"^\d+\.\s+", stripped):
                criteria.append(re.sub(r"^\d+\.\s+", "", stripped))
            elif stripped and not stripped.startswith("#"):
                # Plain text line in AC section
                criteria.append(stripped)
    
    return criteria


def _generate_plan_template(
    item_id: str,
    item_path: str,
    created_at: str,
    item_metadata: Dict[str, Any],
) -> str:
    """
    Generate plan.md template from item's acceptance criteria.
    
    Args:
        item_id: Item ID
        item_path: Relative path to item
        created_at: Creation timestamp
        item_metadata: Item frontmatter metadata
    
    Returns:
        Plan template content
    """
    # Try to extract acceptance criteria from the item file
    try:
        full_path = Path(item_path)
        if not full_path.is_absolute():
            # Try to find the actual file
            backlog_root = _find_backlog_root()
            full_path = backlog_root.parent.parent / item_path
        
        if full_path.exists():
            criteria = _extract_acceptance_criteria(full_path)
        else:
            criteria = []
    except Exception:
        criteria = []
    
    # Build checklist from acceptance criteria
    if criteria:
        checklist_items = "\n".join(f"- [ ] Step {i+1}: {c}" for i, c in enumerate(criteria))
    else:
        checklist_items = """- [ ] Step 1: Review requirements and context
- [ ] Step 2: Implement core functionality
- [ ] Step 3: Write tests
- [ ] Step 4: Update documentation"""
    
    title = item_metadata.get("title", item_id)
    
    return f"""# Execution Plan: {item_id}

## Source
- Item: [{item_id}]({item_path})
- Title: {title}
- Created: {created_at}

## Checklist

Based on acceptance criteria from the source item:

{checklist_items}

## Notes

Add execution notes here. Use `Decision:` markers for ADR candidates.
"""


def _generate_notes_template(item_id: str) -> str:
    """
    Generate notes.md template with Decision: marker guidance.
    
    Args:
        item_id: Item ID
    
    Returns:
        Notes template content
    """
    return f"""# Notes: {item_id}

## Research

{{space for research notes}}

## Decisions

Use `Decision:` markers to flag ADR candidates:

Decision: {{description of decision and rationale}}

## Open Questions

- {{questions to resolve}}
"""


def _append_worklog_to_item(item_path: Path, message: str, agent: str) -> None:
    """
    Append a worklog entry to an item file.
    
    Uses the existing worklog module to ensure consistent formatting.
    
    Args:
        item_path: Path to item file
        message: Worklog message
        agent: Agent identity
    """
    # Import worklog module for consistent formatting
    from . import worklog as worklog_module
    
    # Read current content
    lines = item_path.read_text(encoding="utf-8").splitlines()
    
    # Append worklog entry using existing module
    lines = worklog_module.append_worklog_entry(lines, message, agent)
    
    # Write back
    item_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_workset_cache_root(backlog_root: Optional[Path] = None) -> Path:
    """
    Get the root directory for workset caches.

    Args:
        backlog_root: Root path for backlog (defaults to _kano/backlog)

    Returns:
        Path to _kano/backlog/.cache/worksets/
    """
    if backlog_root is None:
        # Default to current directory's _kano/backlog
        backlog_root = Path.cwd() / "_kano" / "backlog"
    return backlog_root / ".cache" / "worksets"


def get_item_workset_path(item_id: str, backlog_root: Optional[Path] = None) -> Path:
    """
    Get the workset directory path for a specific item.

    Args:
        item_id: Item ID (e.g., KABSD-TSK-0124)
        backlog_root: Root path for backlog

    Returns:
        Path to _kano/backlog/.cache/worksets/items/<item-id>/
    """
    cache_root = get_workset_cache_root(backlog_root)
    return cache_root / "items" / item_id


def get_topic_path(topic_name: str, backlog_root: Optional[Path] = None) -> Path:
    """
    Get the topic directory path.

    Args:
        topic_name: Topic name
        backlog_root: Root path for backlog

    Returns:
        Path to _kano/backlog/.cache/worksets/topics/<topic-name>/
    """
    cache_root = get_workset_cache_root(backlog_root)
    return cache_root / "topics" / topic_name


def ensure_workset_dirs(backlog_root: Optional[Path] = None) -> Path:
    """
    Ensure workset cache directory structure exists.

    Creates:
        _kano/backlog/.cache/worksets/
        _kano/backlog/.cache/worksets/items/
        _kano/backlog/.cache/worksets/topics/

    Args:
        backlog_root: Root path for backlog

    Returns:
        Path to the workset cache root
    """
    cache_root = get_workset_cache_root(backlog_root)
    items_dir = cache_root / "items"
    topics_dir = cache_root / "topics"

    cache_root.mkdir(parents=True, exist_ok=True)
    items_dir.mkdir(parents=True, exist_ok=True)
    topics_dir.mkdir(parents=True, exist_ok=True)

    return cache_root


# =============================================================================
# Stub Functions (to be implemented in later tasks)
# =============================================================================


def init_workset(
    item_ref: str,
    *,
    agent: str,
    backlog_root: Optional[Path] = None,
    ttl_hours: int = 72,
    append_worklog: bool = True,
) -> WorksetInitResult:
    """
    Initialize a workset for an item.

    Args:
        item_ref: Item reference (ID, UID, or path)
        agent: Agent identity
        backlog_root: Root path for backlog
        ttl_hours: Time-to-live in hours
        append_worklog: Whether to append worklog entry to source item

    Returns:
        WorksetInitResult with initialization details

    Raises:
        ItemNotFoundError: If item reference is invalid
    """
    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()
    
    # Resolve item reference to path and metadata
    item_path, item_metadata = _resolve_item_ref(item_ref, backlog_root)
    
    item_id = item_metadata["id"]
    item_uid = item_metadata.get("uid", "")
    
    # Get workset path
    workset_path = get_item_workset_path(item_id, backlog_root)
    meta_path = workset_path / "meta.json"
    
    # Handle idempotent case - return existing if already exists
    if meta_path.exists():
        return WorksetInitResult(
            workset_path=workset_path,
            item_count=1,
            created=False,
        )
    
    # Ensure workset directories exist
    ensure_workset_dirs(backlog_root)
    
    # Create workset directory
    workset_path.mkdir(parents=True, exist_ok=True)
    
    # Create deliverables directory
    deliverables_path = workset_path / "deliverables"
    deliverables_path.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamps
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")
    
    # Get git commit hash if available
    source_commit = _get_git_commit()
    
    # Calculate relative item path from backlog root
    try:
        relative_item_path = item_path.relative_to(backlog_root.parent.parent)
    except ValueError:
        relative_item_path = item_path
    
    # Create metadata
    metadata = WorksetMetadata(
        workset_id=str(uuid.uuid4()),
        item_id=item_id,
        item_uid=item_uid,
        item_path=str(relative_item_path),
        agent=agent,
        created_at=timestamp,
        refreshed_at=timestamp,
        ttl_hours=ttl_hours,
        source_commit=source_commit,
    )
    
    # Save metadata
    metadata.save(meta_path)
    
    # Generate plan.md from item's acceptance criteria
    plan_content = _generate_plan_template(item_id, str(relative_item_path), timestamp, item_metadata)
    plan_path = workset_path / "plan.md"
    plan_path.write_text(plan_content, encoding="utf-8")
    
    # Generate notes.md template
    notes_content = _generate_notes_template(item_id)
    notes_path = workset_path / "notes.md"
    notes_path.write_text(notes_content, encoding="utf-8")
    
    # Append worklog entry to source item (Task 2.2)
    if append_worklog:
        _append_worklog_to_item(item_path, f"Workset initialized: {workset_path}", agent)
    
    return WorksetInitResult(
        workset_path=workset_path,
        item_count=1,
        created=True,
    )


def refresh_workset(
    item_ref: str,
    *,
    agent: str,
    backlog_root: Optional[Path] = None,
    append_worklog: bool = True,
) -> WorksetRefreshResult:
    """
    Refresh workset from canonical files.

    Args:
        item_ref: Item reference (ID, UID, or path)
        agent: Agent identity
        backlog_root: Root path for backlog
        append_worklog: Whether to append worklog entry to source item

    Returns:
        WorksetRefreshResult with refresh details

    Raises:
        WorksetNotFoundError: If workset not initialized
        ItemNotFoundError: If source item has been deleted
    """
    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()
    
    # First, try to find the workset by item reference
    # We need to resolve the item_ref to get the item_id for the workset path
    
    # Check if item_ref is already an item_id that has a workset
    workset_path = get_item_workset_path(item_ref, backlog_root)
    meta_path = workset_path / "meta.json"
    
    if not meta_path.exists():
        # Try to resolve item_ref to get the actual item_id
        try:
            _, item_metadata = _resolve_item_ref(item_ref, backlog_root)
            item_id = item_metadata["id"]
            workset_path = get_item_workset_path(item_id, backlog_root)
            meta_path = workset_path / "meta.json"
        except ItemNotFoundError:
            # Item doesn't exist - check if workset exists for the original ref
            pass
    
    # Verify workset exists (Requirement 2.4)
    if not meta_path.exists():
        raise WorksetNotFoundError(item_ref)
    
    # Load existing metadata
    metadata = WorksetMetadata.load(meta_path)
    
    # Verify source item still exists (Requirement 2.2, 2.5)
    try:
        item_path, item_metadata = _resolve_item_ref(metadata.item_id, backlog_root)
    except ItemNotFoundError:
        raise WorksetError(
            f"Source item has been deleted: {metadata.item_id}",
            suggestion="Run 'kano workset cleanup' to remove orphaned worksets",
        )
    
    # Update refreshed_at timestamp (Requirement 2.1)
    now = datetime.now(timezone.utc)
    metadata.refreshed_at = now.isoformat().replace("+00:00", "Z")
    
    # Save updated metadata
    metadata.save(meta_path)
    
    # Append worklog entry to source item (Requirement 2.3)
    if append_worklog:
        _append_worklog_to_item(item_path, f"Workset refreshed: {workset_path}", agent)
    
    return WorksetRefreshResult(
        workset_path=workset_path,
        items_added=0,
        items_removed=0,
        items_updated=1,
    )


def get_next_action(
    item_ref: str,
    *,
    backlog_root: Optional[Path] = None,
) -> WorksetNextResult:
    """
    Get next unchecked action from plan.md.

    Args:
        item_ref: Item reference (ID, UID, or path)
        backlog_root: Root path for backlog

    Returns:
        WorksetNextResult with next action details

    Raises:
        WorksetNotFoundError: If workset not initialized
    """
    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()
    
    # Find the workset path
    workset_path = get_item_workset_path(item_ref, backlog_root)
    meta_path = workset_path / "meta.json"
    
    if not meta_path.exists():
        # Try to resolve item_ref to get the actual item_id
        try:
            _, item_metadata = _resolve_item_ref(item_ref, backlog_root)
            item_id = item_metadata["id"]
            workset_path = get_item_workset_path(item_id, backlog_root)
            meta_path = workset_path / "meta.json"
        except ItemNotFoundError:
            pass
    
    # Verify workset exists (Requirement 3.3)
    if not meta_path.exists():
        raise WorksetNotFoundError(item_ref)
    
    # Read plan.md
    plan_path = workset_path / "plan.md"
    if not plan_path.exists():
        raise WorksetError(
            f"plan.md not found in workset: {workset_path}",
            suggestion="Workset may be corrupted, try re-initializing",
        )
    
    plan_content = plan_path.read_text(encoding="utf-8")
    lines = plan_content.splitlines()
    
    # Parse checkbox items (Requirement 3.1)
    # Pattern matches: - [ ] or - [x] or - [X]
    checkbox_pattern = re.compile(r"^(\s*)-\s*\[([ xX])\]\s*(.+)$")
    
    step_number = 0
    for line in lines:
        match = checkbox_pattern.match(line)
        if match:
            step_number += 1
            checked = match.group(2).lower() == "x"
            description = match.group(3).strip()
            
            # Return first unchecked item (Requirement 3.1)
            if not checked:
                return WorksetNextResult(
                    step_number=step_number,
                    description=description,
                    is_complete=False,
                )
    
    # All items checked - return completion message (Requirement 3.2)
    return WorksetNextResult(
        step_number=step_number,
        description="All steps complete",
        is_complete=True,
    )


def promote_deliverables(
    item_ref: str,
    *,
    agent: str,
    backlog_root: Optional[Path] = None,
    dry_run: bool = False,
    append_worklog: bool = True,
) -> WorksetPromoteResult:
    """
    Promote deliverables to canonical artifacts.

    Scans the workset's deliverables/ directory and copies files to the
    canonical artifacts location for the item's product.

    Args:
        item_ref: Item reference (ID, UID, or path)
        agent: Agent identity
        backlog_root: Root path for backlog
        dry_run: If True, list files without making changes
        append_worklog: Whether to append worklog entry to source item

    Returns:
        WorksetPromoteResult with promotion details

    Raises:
        WorksetNotFoundError: If workset not initialized
        ItemNotFoundError: If source item not found
    """
    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()
    
    # Find the workset path
    workset_path = get_item_workset_path(item_ref, backlog_root)
    meta_path = workset_path / "meta.json"
    
    if not meta_path.exists():
        # Try to resolve item_ref to get the actual item_id
        try:
            _, item_metadata = _resolve_item_ref(item_ref, backlog_root)
            item_id = item_metadata["id"]
            workset_path = get_item_workset_path(item_id, backlog_root)
            meta_path = workset_path / "meta.json"
        except ItemNotFoundError:
            pass
    
    # Verify workset exists (Requirement 4.1)
    if not meta_path.exists():
        raise WorksetNotFoundError(item_ref)
    
    # Load metadata to get item info
    metadata = WorksetMetadata.load(meta_path)
    item_id = metadata.item_id
    
    # Resolve source item to get product path
    item_path, item_metadata = _resolve_item_ref(item_id, backlog_root)
    
    # Determine the product from the item path
    # Item path format: _kano/backlog/products/<product>/items/...
    # We need to find the product directory
    product_name = _extract_product_from_item_path(item_path, backlog_root)
    
    # Scan deliverables directory (Requirement 4.1)
    deliverables_dir = workset_path / "deliverables"
    if not deliverables_dir.exists():
        return WorksetPromoteResult(
            promoted_files=[],
            target_path=Path(""),
            worklog_entry="No deliverables directory found",
        )
    
    # Collect all files in deliverables (recursively)
    files_to_promote = []
    for file_path in deliverables_dir.rglob("*"):
        if file_path.is_file():
            # Get relative path from deliverables dir
            rel_path = file_path.relative_to(deliverables_dir)
            files_to_promote.append((file_path, rel_path))
    
    # Handle empty deliverables case (Requirement 4.5)
    if not files_to_promote:
        return WorksetPromoteResult(
            promoted_files=[],
            target_path=Path(""),
            worklog_entry="No deliverables to promote",
        )
    
    # Determine target artifacts directory (Requirement 4.2)
    # Format: _kano/backlog/products/<product>/artifacts/<item-id>/
    target_dir = backlog_root / "products" / product_name / "artifacts" / item_id
    
    promoted_files = []
    
    if not dry_run:
        # Create target directory
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy files (Requirement 4.2)
        for src_path, rel_path in files_to_promote:
            dest_path = target_dir / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_path)
            promoted_files.append(str(rel_path))
    else:
        # Dry run - just list files (Requirement 4.4)
        promoted_files = [str(rel_path) for _, rel_path in files_to_promote]
    
    # Generate worklog entry (Requirement 4.3)
    if promoted_files:
        file_list = ", ".join(promoted_files[:5])
        if len(promoted_files) > 5:
            file_list += f" (+{len(promoted_files) - 5} more)"
        worklog_entry = f"Promoted {len(promoted_files)} deliverable(s) to {target_dir}: {file_list}"
    else:
        worklog_entry = "No deliverables to promote"
    
    # Append worklog entry to source item (Requirement 4.3)
    if append_worklog and not dry_run and promoted_files:
        _append_worklog_to_item(item_path, worklog_entry, agent)
    
    return WorksetPromoteResult(
        promoted_files=promoted_files,
        target_path=target_dir,
        worklog_entry=worklog_entry,
    )


def _extract_product_from_item_path(item_path: Path, backlog_root: Path) -> str:
    """
    Extract the product name from an item's file path.
    
    Args:
        item_path: Path to the item file
        backlog_root: Root path for backlog
    
    Returns:
        Product name string
    
    Raises:
        WorksetError: If product cannot be determined
    """
    # Try to find 'products' in the path and get the next component
    parts = item_path.parts
    for i, part in enumerate(parts):
        if part == "products" and i + 1 < len(parts):
            return parts[i + 1]
    
    # Fallback: check if items/ is directly under backlog_root (legacy layout)
    try:
        rel_path = item_path.relative_to(backlog_root)
        if rel_path.parts[0] == "items":
            # Legacy single-product layout - use a default product name
            return "default"
    except ValueError:
        pass
    
    raise WorksetError(
        f"Cannot determine product from item path: {item_path}",
        suggestion="Ensure item is in _kano/backlog/products/<product>/items/",
    )


def cleanup_worksets(
    *,
    agent: Optional[str] = None,
    ttl_hours: int = 72,
    backlog_root: Optional[Path] = None,
    dry_run: bool = False,
) -> WorksetCleanupResult:
    """
    Clean up expired worksets.

    Scans the worksets/items/ directory and deletes worksets older than
    the specified TTL. Only affects item worksets, not topics.

    Args:
        agent: Optional agent filter (not currently used, reserved for future)
        ttl_hours: Time-to-live in hours (default: 72)
        backlog_root: Root path for backlog
        dry_run: If True, list worksets without deleting

    Returns:
        WorksetCleanupResult with cleanup details
    """
    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()
    
    # Get the items workset directory (Requirement 5.3 - only items/, not topics/)
    cache_root = get_workset_cache_root(backlog_root)
    items_dir = cache_root / "items"
    
    if not items_dir.exists():
        return WorksetCleanupResult(
            deleted_count=0,
            deleted_paths=[],
            space_reclaimed_bytes=0,
        )
    
    # Calculate cutoff time
    now = datetime.now(timezone.utc)
    cutoff_hours = ttl_hours
    
    deleted_paths: List[Path] = []
    space_reclaimed = 0
    
    # Scan worksets (Requirement 5.1)
    for workset_dir in items_dir.iterdir():
        if not workset_dir.is_dir():
            continue
        
        meta_path = workset_dir / "meta.json"
        if not meta_path.exists():
            # Skip directories without meta.json (not valid worksets)
            continue
        
        try:
            # Load metadata to get created_at timestamp
            metadata = WorksetMetadata.load(meta_path)
            
            # Parse created_at timestamp
            created_at_str = metadata.created_at
            # Handle both 'Z' suffix and '+00:00' format
            if created_at_str.endswith("Z"):
                created_at_str = created_at_str[:-1] + "+00:00"
            created_at = datetime.fromisoformat(created_at_str)
            
            # Calculate age in hours
            age = now - created_at
            age_hours = age.total_seconds() / 3600
            
            # Check if older than TTL (Requirement 5.1)
            if age_hours > cutoff_hours:
                # Calculate size before deletion (Requirement 5.2)
                workset_size = _calculate_directory_size(workset_dir)
                
                if not dry_run:
                    # Delete the workset directory
                    shutil.rmtree(workset_dir)
                
                deleted_paths.append(workset_dir)
                space_reclaimed += workset_size
        except Exception:
            # Skip worksets with invalid metadata
            continue
    
    return WorksetCleanupResult(
        deleted_count=len(deleted_paths),
        deleted_paths=deleted_paths,
        space_reclaimed_bytes=space_reclaimed,
    )


def _calculate_directory_size(directory: Path) -> int:
    """
    Calculate the total size of a directory in bytes.
    
    Args:
        directory: Path to directory
    
    Returns:
        Total size in bytes
    """
    total_size = 0
    for file_path in directory.rglob("*"):
        if file_path.is_file():
            try:
                total_size += file_path.stat().st_size
            except OSError:
                pass
    return total_size


def detect_adr_candidates(
    item_ref: str,
    *,
    backlog_root: Optional[Path] = None,
) -> List[Dict[str, str]]:
    """
    Detect Decision: markers in notes.md.

    Scans the workset's notes.md file for lines containing "Decision:" markers
    and extracts the decision text to suggest ADR creation.

    Args:
        item_ref: Item reference (ID, UID, or path)
        backlog_root: Root path for backlog

    Returns:
        List of dicts with 'text' and 'suggested_title' keys

    Raises:
        WorksetNotFoundError: If workset not initialized
    """
    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()
    
    # Find the workset path
    workset_path = get_item_workset_path(item_ref, backlog_root)
    meta_path = workset_path / "meta.json"
    
    if not meta_path.exists():
        # Try to resolve item_ref to get the actual item_id
        try:
            _, item_metadata = _resolve_item_ref(item_ref, backlog_root)
            item_id = item_metadata["id"]
            workset_path = get_item_workset_path(item_id, backlog_root)
            meta_path = workset_path / "meta.json"
        except ItemNotFoundError:
            pass
    
    # Verify workset exists
    if not meta_path.exists():
        raise WorksetNotFoundError(item_ref)
    
    # Read notes.md
    notes_path = workset_path / "notes.md"
    if not notes_path.exists():
        return []
    
    notes_content = notes_path.read_text(encoding="utf-8")
    lines = notes_content.splitlines()
    
    # Pattern to match Decision: markers (case-insensitive)
    # Matches lines like:
    #   Decision: Use SQLite for local storage
    #   decision: prefer JSON over YAML
    #   DECISION: implement caching layer
    decision_pattern = re.compile(r"^\s*decision:\s*(.+)$", re.IGNORECASE)
    
    candidates = []
    for line in lines:
        match = decision_pattern.match(line)
        if match:
            decision_text = match.group(1).strip()
            if decision_text:
                # Generate suggested ADR title from decision text
                suggested_title = _generate_adr_title(decision_text)
                candidates.append({
                    "text": decision_text,
                    "suggested_title": suggested_title,
                })
    
    return candidates


def _generate_adr_title(decision_text: str) -> str:
    """
    Generate a suggested ADR title from decision text.
    
    Args:
        decision_text: The decision text extracted from notes
    
    Returns:
        A suggested ADR title in kebab-case format
    """
    # Take first 50 chars or up to first period/newline
    text = decision_text[:50]
    if "." in text:
        text = text.split(".")[0]
    
    # Convert to lowercase and replace non-alphanumeric with hyphens
    title = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower())
    
    # Remove leading/trailing hyphens
    title = title.strip("-")
    
    # Truncate if too long
    if len(title) > 40:
        title = title[:40].rsplit("-", 1)[0]
    
    # If title is empty after processing, use a default
    if not title:
        title = "untitled-decision"
    
    return title


def list_worksets(
    *,
    backlog_root: Optional[Path] = None,
) -> List[WorksetMetadata]:
    """
    List all item worksets.

    Scans the worksets/items/ directory and returns metadata for all worksets.

    Args:
        backlog_root: Root path for backlog

    Returns:
        List of WorksetMetadata for all worksets
    """
    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()
    
    # Get the items workset directory
    cache_root = get_workset_cache_root(backlog_root)
    items_dir = cache_root / "items"
    
    worksets = []
    
    if not items_dir.exists():
        return worksets
    
    # Scan worksets
    for workset_dir in items_dir.iterdir():
        if not workset_dir.is_dir():
            continue
        
        meta_path = workset_dir / "meta.json"
        if not meta_path.exists():
            continue
        
        try:
            metadata = WorksetMetadata.load(meta_path)
            worksets.append(metadata)
        except Exception:
            # Skip worksets with invalid metadata
            continue
    
    return worksets


# Legacy aliases for backward compatibility with __init__.py
def get_next_item(*args, **kwargs):
    """Legacy alias for get_next_action."""
    raise NotImplementedError("get_next_item renamed to get_next_action")


def promote_item(*args, **kwargs):
    """Legacy alias for promote_deliverables."""
    raise NotImplementedError("promote_item renamed to promote_deliverables")
