"""
topic.py - Topic-based context management operations.

This module provides use-case functions for managing topic-based context groupings.
Topics provide a higher-level grouping mechanism that enables rapid context switching
when users change focus areas during a conversation.

Per ADR-0011 and ADR-0012, topics are derived data that can be deleted and rebuilt.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from kano_backlog_core.errors import BacklogError


# =============================================================================
# Error Types (Task 8.2)
# =============================================================================


class TopicError(BacklogError):
    """Base error for topic operations."""

    def __init__(self, message: str, suggestion: Optional[str] = None):
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class TopicNotFoundError(TopicError):
    """Topic does not exist."""

    def __init__(self, topic_name: str):
        self.topic_name = topic_name
        super().__init__(
            f"Topic not found: {topic_name}",
            suggestion="Run 'kano topic create <name>' first",
        )


class TopicExistsError(TopicError):
    """Topic already exists."""

    def __init__(self, topic_name: str):
        self.topic_name = topic_name
        super().__init__(
            f"Topic already exists: {topic_name}",
            suggestion="Use a different topic name or delete the existing topic",
        )


class TopicValidationError(TopicError):
    """Topic validation failed."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        error_list = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"Topic validation failed:\n{error_list}")


# =============================================================================
# Data Models (Task 8.1)
# =============================================================================


@dataclass
class TopicManifest:
    """Topic manifest.json structure."""

    topic: str  # Topic name (directory name)
    agent: str  # Agent who created
    seed_items: List[str] = field(default_factory=list)  # List of item UIDs
    pinned_docs: List[str] = field(default_factory=list)  # List of document paths
    created_at: str = ""  # ISO 8601 timestamp
    updated_at: str = ""  # ISO 8601 timestamp

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TopicManifest":
        """Create from dictionary (JSON deserialization)."""
        return cls(
            topic=data["topic"],
            agent=data["agent"],
            seed_items=data.get("seed_items", []),
            pinned_docs=data.get("pinned_docs", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def save(self, path: Path) -> None:
        """Save manifest to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "TopicManifest":
        """Load manifest from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


@dataclass
class TopicCreateResult:
    """Result of creating a topic."""

    topic_path: Path
    manifest: TopicManifest


@dataclass
class TopicAddResult:
    """Result of adding item to topic."""

    topic: str
    item_uid: str
    added: bool  # False if already present


@dataclass
class TopicPinResult:
    """Result of pinning a document to topic."""

    topic: str
    doc_path: str
    pinned: bool  # False if already pinned


@dataclass
class TopicSwitchResult:
    """Result of switching active topic."""

    topic: str
    item_count: int
    pinned_doc_count: int
    previous_topic: Optional[str]


@dataclass
class TopicContextBundle:
    """Exported context bundle."""

    topic: str
    items: List[Dict[str, Any]]  # Item summaries
    pinned_docs: List[Dict[str, str]]  # Doc path + content
    generated_at: str


# =============================================================================
# Topic Name Validation (Task 8.3)
# =============================================================================

# Valid topic name pattern: alphanumeric, hyphens, underscores
# Must start with a letter (not a number), no consecutive special chars
TOPIC_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")


def validate_topic_name(topic_name: str) -> List[str]:
    """
    Validate a topic name.

    Valid topic names:
    - Start with a letter (a-z, A-Z)
    - Contain only alphanumeric characters, hyphens, and underscores
    - Are not empty
    - Are not too long (max 64 characters)

    Args:
        topic_name: Topic name to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if not topic_name:
        errors.append("Topic name cannot be empty")
        return errors

    if len(topic_name) > 64:
        errors.append(f"Topic name too long ({len(topic_name)} chars, max 64)")

    if not TOPIC_NAME_PATTERN.match(topic_name):
        errors.append(
            "Topic name must start with a letter and contain only "
            "alphanumeric characters, hyphens, and underscores"
        )

    # Check for reserved names
    reserved_names = {"items", "topics", "cache", "index", "meta"}
    if topic_name.lower() in reserved_names:
        errors.append(f"Topic name '{topic_name}' is reserved")

    return errors


def is_valid_topic_name(topic_name: str) -> bool:
    """
    Check if a topic name is valid.

    Args:
        topic_name: Topic name to check

    Returns:
        True if valid, False otherwise
    """
    return len(validate_topic_name(topic_name)) == 0


# =============================================================================
# Directory Utilities (Task 8.3)
# =============================================================================


def _find_backlog_root(start: Optional[Path] = None) -> Path:
    """
    Find the backlog root directory.

    Args:
        start: Starting path for search (defaults to cwd)

    Returns:
        Path to _kano/backlog directory

    Raises:
        TopicError: If backlog root not found
    """
    current = (start or Path.cwd()).resolve()
    while current != current.parent:
        backlog_check = current / "_kano" / "backlog"
        if backlog_check.exists():
            return backlog_check
        current = current.parent
    raise TopicError(
        "Cannot find backlog root (_kano/backlog)",
        suggestion="Ensure you are in a directory with a _kano/backlog structure",
    )


def get_topics_root(backlog_root: Optional[Path] = None) -> Path:
    """
    Get the root directory for topic caches.

    Args:
        backlog_root: Root path for backlog (defaults to _kano/backlog)

    Returns:
        Path to _kano/backlog/.cache/worksets/topics/
    """
    if backlog_root is None:
        backlog_root = Path.cwd() / "_kano" / "backlog"
    return backlog_root / ".cache" / "worksets" / "topics"


def get_topic_path(topic_name: str, backlog_root: Optional[Path] = None) -> Path:
    """
    Get the topic directory path.

    Args:
        topic_name: Topic name
        backlog_root: Root path for backlog

    Returns:
        Path to _kano/backlog/.cache/worksets/topics/<topic-name>/
    """
    topics_root = get_topics_root(backlog_root)
    return topics_root / topic_name


def get_active_topic_path(agent: str, backlog_root: Optional[Path] = None) -> Path:
    """
    Get the path to the active topic file for an agent.

    Args:
        agent: Agent identity
        backlog_root: Root path for backlog

    Returns:
        Path to _kano/backlog/.cache/worksets/active_topic.<agent>.txt
    """
    if backlog_root is None:
        backlog_root = Path.cwd() / "_kano" / "backlog"
    cache_root = backlog_root / ".cache" / "worksets"
    return cache_root / f"active_topic.{agent}.txt"


def ensure_topic_dirs(backlog_root: Optional[Path] = None) -> Path:
    """
    Ensure topic cache directory structure exists.

    Creates:
        _kano/backlog/.cache/worksets/topics/

    Args:
        backlog_root: Root path for backlog

    Returns:
        Path to the topics cache root
    """
    topics_root = get_topics_root(backlog_root)
    topics_root.mkdir(parents=True, exist_ok=True)
    return topics_root


# =============================================================================
# Stub Functions (to be implemented in later tasks)
# =============================================================================


def create_topic(
    topic_name: str,
    *,
    agent: str,
    backlog_root: Optional[Path] = None,
    create_notes: bool = True,
) -> TopicCreateResult:
    """
    Create a new topic.

    Args:
        topic_name: Name for the topic
        agent: Agent identity
        backlog_root: Root path for backlog
        create_notes: Whether to create notes.md (default: True)

    Returns:
        TopicCreateResult with creation details

    Raises:
        TopicExistsError: If topic already exists
        TopicValidationError: If topic name is invalid
    """
    # Validate topic name (Requirement 6.5)
    validation_errors = validate_topic_name(topic_name)
    if validation_errors:
        raise TopicValidationError(validation_errors)

    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()

    # Get topic path
    topic_path = get_topic_path(topic_name, backlog_root)

    # Check if topic already exists (Requirement 6.4)
    if topic_path.exists():
        raise TopicExistsError(topic_name)

    # Ensure topic directories exist
    ensure_topic_dirs(backlog_root)

    # Create topic directory (Requirement 6.1)
    topic_path.mkdir(parents=True, exist_ok=True)

    # Generate timestamps
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")

    # Create manifest (Requirement 6.2)
    manifest = TopicManifest(
        topic=topic_name,
        agent=agent,
        seed_items=[],
        pinned_docs=[],
        created_at=timestamp,
        updated_at=timestamp,
    )

    # Save manifest.json
    manifest_path = topic_path / "manifest.json"
    manifest.save(manifest_path)

    # Optionally create notes.md (Requirement 6.3)
    if create_notes:
        notes_content = _generate_topic_notes_template(topic_name)
        notes_path = topic_path / "notes.md"
        notes_path.write_text(notes_content, encoding="utf-8")

    return TopicCreateResult(
        topic_path=topic_path,
        manifest=manifest,
    )


def _generate_topic_notes_template(topic_name: str) -> str:
    """
    Generate notes.md template for a topic.

    Args:
        topic_name: Topic name

    Returns:
        Notes template content
    """
    return f"""# Topic Notes: {topic_name}

## Overview

{{Brief description of this topic's focus area}}

## Related Items

{{Notes about the items in this topic}}

## Key Decisions

{{Important decisions related to this topic}}

## Open Questions

- {{questions to resolve}}
"""


def add_item_to_topic(
    topic_name: str,
    item_ref: str,
    *,
    backlog_root: Optional[Path] = None,
) -> TopicAddResult:
    """
    Add an item to a topic.

    Args:
        topic_name: Topic name
        item_ref: Item reference (ID, UID, or path)
        backlog_root: Root path for backlog

    Returns:
        TopicAddResult with add details

    Raises:
        TopicNotFoundError: If topic does not exist
        ItemNotFoundError: If item does not exist
    """
    # Import here to avoid circular imports
    from kano_backlog_ops.workset import _resolve_item_ref, ItemNotFoundError as WorksetItemNotFoundError

    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()

    # Get topic path and verify it exists (Requirement 7.5)
    topic_path = get_topic_path(topic_name, backlog_root)
    manifest_path = topic_path / "manifest.json"

    if not manifest_path.exists():
        raise TopicNotFoundError(topic_name)

    # Verify item exists (Requirement 7.2)
    try:
        _, item_metadata = _resolve_item_ref(item_ref, backlog_root)
    except WorksetItemNotFoundError as e:
        # Re-raise with topic-specific error
        raise TopicError(
            f"Item not found: {item_ref}",
            suggestion="Check the item ID, UID, or path is correct",
        ) from e

    # Get item UID (prefer UID, fallback to ID)
    item_uid = item_metadata.get("uid") or item_metadata.get("id", item_ref)

    # Load manifest
    manifest = TopicManifest.load(manifest_path)

    # Check if item is already in topic (Requirement 7.4)
    if item_uid in manifest.seed_items:
        return TopicAddResult(
            topic=topic_name,
            item_uid=item_uid,
            added=False,
        )

    # Add item UID to seed_items (Requirement 7.1)
    manifest.seed_items.append(item_uid)

    # Update timestamp (Requirement 7.3)
    now = datetime.now(timezone.utc)
    manifest.updated_at = now.isoformat().replace("+00:00", "Z")

    # Save updated manifest
    manifest.save(manifest_path)

    return TopicAddResult(
        topic=topic_name,
        item_uid=item_uid,
        added=True,
    )


def pin_document(
    topic_name: str,
    doc_path: str,
    *,
    backlog_root: Optional[Path] = None,
) -> TopicPinResult:
    """
    Pin a document to a topic.

    Args:
        topic_name: Topic name
        doc_path: Document path (relative to backlog root)
        backlog_root: Root path for backlog

    Returns:
        TopicPinResult with pin details

    Raises:
        TopicNotFoundError: If topic does not exist
        TopicError: If document does not exist
    """
    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()

    # Get topic path and verify it exists (Requirement 8.1)
    topic_path = get_topic_path(topic_name, backlog_root)
    manifest_path = topic_path / "manifest.json"

    if not manifest_path.exists():
        raise TopicNotFoundError(topic_name)

    # Normalize document path (support relative paths from backlog root)
    # Requirement 8.4: Support relative paths from backlog root
    if Path(doc_path).is_absolute():
        full_doc_path = Path(doc_path)
        # Convert to relative path for storage
        try:
            relative_doc_path = str(full_doc_path.relative_to(backlog_root.parent.parent))
        except ValueError:
            relative_doc_path = doc_path
    else:
        relative_doc_path = doc_path
        # Resolve full path for existence check
        full_doc_path = backlog_root.parent.parent / doc_path

    # Verify document exists (Requirement 8.2)
    if not full_doc_path.exists():
        raise TopicError(
            f"Document not found: {doc_path}",
            suggestion="Check the document path is correct (relative to workspace root)",
        )

    # Load manifest
    manifest = TopicManifest.load(manifest_path)

    # Check if document is already pinned (Requirement 8.3)
    if relative_doc_path in manifest.pinned_docs:
        return TopicPinResult(
            topic=topic_name,
            doc_path=relative_doc_path,
            pinned=False,
        )

    # Add document path to pinned_docs (Requirement 8.1)
    manifest.pinned_docs.append(relative_doc_path)

    # Update timestamp
    now = datetime.now(timezone.utc)
    manifest.updated_at = now.isoformat().replace("+00:00", "Z")

    # Save updated manifest
    manifest.save(manifest_path)

    return TopicPinResult(
        topic=topic_name,
        doc_path=relative_doc_path,
        pinned=True,
    )


def switch_topic(
    topic_name: str,
    *,
    agent: str,
    backlog_root: Optional[Path] = None,
) -> TopicSwitchResult:
    """
    Switch active topic for an agent.

    Args:
        topic_name: Topic name to switch to
        agent: Agent identity
        backlog_root: Root path for backlog

    Returns:
        TopicSwitchResult with switch details

    Raises:
        TopicNotFoundError: If topic does not exist
    """
    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()

    # Get topic path and verify it exists (Requirement 9.3)
    topic_path = get_topic_path(topic_name, backlog_root)
    manifest_path = topic_path / "manifest.json"

    if not manifest_path.exists():
        raise TopicNotFoundError(topic_name)

    # Load manifest to get counts
    manifest = TopicManifest.load(manifest_path)

    # Get previous active topic (if any)
    previous_topic = get_active_topic(agent, backlog_root=backlog_root)

    # Write topic name to active_topic.<agent>.txt (Requirement 9.1)
    active_topic_path = get_active_topic_path(agent, backlog_root)
    
    # Ensure parent directory exists
    active_topic_path.parent.mkdir(parents=True, exist_ok=True)
    
    active_topic_path.write_text(topic_name, encoding="utf-8")

    # Return summary with item count and pinned doc count (Requirement 9.2)
    return TopicSwitchResult(
        topic=topic_name,
        item_count=len(manifest.seed_items),
        pinned_doc_count=len(manifest.pinned_docs),
        previous_topic=previous_topic,
    )


def get_active_topic(
    agent: str,
    *,
    backlog_root: Optional[Path] = None,
) -> Optional[str]:
    """
    Get current active topic for an agent.

    Args:
        agent: Agent identity
        backlog_root: Root path for backlog

    Returns:
        Topic name or None if no active topic
    """
    # Resolve backlog root
    if backlog_root is None:
        try:
            backlog_root = _find_backlog_root()
        except TopicError:
            return None

    # Get active topic file path (Requirement 9.1)
    active_topic_path = get_active_topic_path(agent, backlog_root)

    # Read active_topic.<agent>.txt if exists
    if not active_topic_path.exists():
        return None

    topic_name = active_topic_path.read_text(encoding="utf-8").strip()
    
    # Return None if file is empty
    if not topic_name:
        return None

    return topic_name


def export_topic_context(
    topic_name: str,
    *,
    backlog_root: Optional[Path] = None,
    format: str = "markdown",
) -> TopicContextBundle:
    """
    Export topic context as a bundle.

    Args:
        topic_name: Topic name
        backlog_root: Root path for backlog
        format: Output format ("markdown" or "json")

    Returns:
        TopicContextBundle with exported context

    Raises:
        TopicNotFoundError: If topic does not exist
    """
    # Import here to avoid circular imports
    from kano_backlog_ops.workset import _resolve_item_ref, _parse_item_frontmatter

    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()

    # Get topic path and verify it exists
    topic_path = get_topic_path(topic_name, backlog_root)
    manifest_path = topic_path / "manifest.json"

    if not manifest_path.exists():
        raise TopicNotFoundError(topic_name)

    # Load manifest
    manifest = TopicManifest.load(manifest_path)

    # Generate timestamp
    now = datetime.now(timezone.utc)
    generated_at = now.isoformat().replace("+00:00", "Z")

    # Load item summaries (Requirement 10.2)
    items: List[Dict[str, Any]] = []
    for item_uid in sorted(manifest.seed_items):  # Sort for deterministic output
        try:
            item_path, metadata = _resolve_item_ref(item_uid, backlog_root)
            
            # Extract summary (title, state, key sections)
            item_summary = {
                "uid": item_uid,
                "id": metadata.get("id", ""),
                "title": metadata.get("title", ""),
                "type": metadata.get("type", ""),
                "state": metadata.get("state", ""),
                "priority": metadata.get("priority", ""),
                "path": str(item_path.relative_to(backlog_root.parent.parent)),
            }
            items.append(item_summary)
        except Exception:
            # Skip items that can't be resolved (may have been deleted)
            items.append({
                "uid": item_uid,
                "error": "Item not found or could not be loaded",
            })

    # Load pinned document content (Requirement 10.3)
    pinned_docs: List[Dict[str, str]] = []
    workspace_root = backlog_root.parent.parent
    for doc_path_str in sorted(manifest.pinned_docs):  # Sort for deterministic output
        doc_path = workspace_root / doc_path_str
        doc_entry = {
            "path": doc_path_str,
        }
        if doc_path.exists():
            try:
                doc_entry["content"] = doc_path.read_text(encoding="utf-8")
            except Exception as e:
                doc_entry["error"] = f"Could not read: {e}"
        else:
            doc_entry["error"] = "Document not found"
        pinned_docs.append(doc_entry)

    return TopicContextBundle(
        topic=topic_name,
        items=items,
        pinned_docs=pinned_docs,
        generated_at=generated_at,
    )


def list_topics(
    *,
    backlog_root: Optional[Path] = None,
    agent: Optional[str] = None,
) -> List[TopicManifest]:
    """
    List all topics.

    Args:
        backlog_root: Root path for backlog
        agent: Optional agent to check active topic for

    Returns:
        List of TopicManifest for all topics (sorted by topic name)
    """
    # Resolve backlog root
    if backlog_root is None:
        try:
            backlog_root = _find_backlog_root()
        except TopicError:
            return []

    # Get topics root
    topics_root = get_topics_root(backlog_root)

    if not topics_root.exists():
        return []

    # Scan for topic directories
    topics: List[TopicManifest] = []
    for topic_dir in sorted(topics_root.iterdir()):  # Sort for deterministic output
        if not topic_dir.is_dir():
            continue
        
        manifest_path = topic_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        
        try:
            manifest = TopicManifest.load(manifest_path)
            topics.append(manifest)
        except Exception:
            # Skip invalid manifests
            continue

    return topics
