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
import hashlib
import subprocess

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
class SnippetRef:
    """Reference to a code snippet (reference-first approach to avoid massive copy-paste)."""

    type: str = "snippet"  # Always "snippet"
    repo: str = "local"  # "local" or git remote URL
    revision: Optional[str] = None  # commit hash (None if not in git or dirty)
    file: str = ""  # Relative file path from repo root
    lines: List[int] = field(default_factory=list)  # [start, end] 1-based inclusive
    hash: str = ""  # sha256 of content for staleness check
    cached_text: Optional[str] = None  # Optional snapshot of content
    collected_at: Optional[str] = None  # ISO 8601 timestamp
    collector: Optional[str] = None  # Agent identity

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SnippetRef":
        return cls(
            type=data.get("type", "snippet"),
            repo=data.get("repo", "local"),
            revision=data.get("revision"),
            file=data.get("file", ""),
            lines=data.get("lines", []),
            hash=data.get("hash", ""),
            cached_text=data.get("cached_text"),
            collected_at=data.get("collected_at"),
            collector=data.get("collector"),
        )


@dataclass
class TopicManifest:
    """Topic manifest.json structure."""

    topic: str  # Topic name (directory name)
    agent: str  # Agent who created
    seed_items: List[str] = field(default_factory=list)  # List of item UIDs
    pinned_docs: List[str] = field(default_factory=list)  # List of document paths
    snippet_refs: List[SnippetRef] = field(default_factory=list)  # List of code snippet refs
    status: str = "open"  # open|closed
    closed_at: Optional[str] = None  # ISO 8601 timestamp
    created_at: str = ""  # ISO 8601 timestamp
    updated_at: str = ""  # ISO 8601 timestamp

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Convert SnippetRef objects to dicts for JSON serialization
        d["snippet_refs"] = [s.to_dict() if isinstance(s, SnippetRef) else s for s in self.snippet_refs]
        return d

    def to_dict_legacy(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TopicManifest":
        """Create from dictionary (JSON deserialization)."""
        raw_snippets = data.get("snippet_refs", [])
        snippet_refs = [SnippetRef.from_dict(s) if isinstance(s, dict) else s for s in raw_snippets]
        return cls(
            topic=data["topic"],
            agent=data["agent"],
            seed_items=data.get("seed_items", []),
            pinned_docs=data.get("pinned_docs", []),
            snippet_refs=snippet_refs,
            status=data.get("status", "open"),
            closed_at=data.get("closed_at"),
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


@dataclass
class TopicAddSnippetResult:
    topic: str
    snippet: SnippetRef
    added: bool


@dataclass
class TopicCloseResult:
    topic: str
    closed: bool
    closed_at: str


@dataclass
class TopicCleanupResult:
    topics_scanned: int
    topics_cleaned: int
    materials_deleted: int
    deleted_paths: List[Path]


# =============================================================================
# Topic Name Validation (Task 8.3)
# =============================================================================

# Valid topic name pattern: alphanumeric, hyphens, underscores
# Must start with a letter (not a number), no consecutive special chars
TOPIC_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")


def _normalize_topic_name(topic_name: str) -> str:
    """Canonicalize to avoid collisions on case-insensitive filesystems (e.g., Windows)."""
    return (topic_name or "").strip().lower()


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

    topic_name = (topic_name or "").strip()

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
    Get the root directory for topics.

    Args:
        backlog_root: Root path for backlog (defaults to _kano/backlog)

    Returns:
        Path to _kano/backlog/topics/

    Note:
        Changed from .cache/worksets/topics/ to topics/ per KABSD-FTR-0037
        so that brief.md can optionally be version-controlled.
    """
    if backlog_root is None:
        backlog_root = Path.cwd() / "_kano" / "backlog"
    return backlog_root / "topics"


def get_topic_path(topic_name: str, backlog_root: Optional[Path] = None) -> Path:
    """
    Get the topic directory path.

    Args:
        topic_name: Topic name
        backlog_root: Root path for backlog

    Returns:
        Path to _kano/backlog/topics/<topic-name>/
    """
    topics_root = get_topics_root(backlog_root)
    return topics_root / _normalize_topic_name(topic_name)


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
    Ensure topic directory structure exists.

    Creates:
        _kano/backlog/topics/

    Args:
        backlog_root: Root path for backlog

    Returns:
        Path to the topics root
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
    create_brief: bool = True,
) -> TopicCreateResult:
    """
    Create a new topic with materials buffer structure.

    Args:
        topic_name: Name for the topic
        agent: Agent identity
        backlog_root: Root path for backlog
        create_notes: Whether to create notes.md (default: True)
        create_brief: Whether to create brief.md template (default: True)

    Returns:
        TopicCreateResult with creation details

    Raises:
        TopicExistsError: If topic already exists
        TopicValidationError: If topic name is invalid

    Directory structure created:
        topics/<topic>/
            manifest.json
            brief.md           (if create_brief=True)
            notes.md           (if create_notes=True, for backward compat)
            materials/
                clips/         # code snippet refs + cached text
                links/         # urls / notes
                extracts/      # extracted paragraphs
                logs/          # build logs / command outputs
            synthesis/         # intermediate drafts
            publish/           # prepared write-backs
    """
    # Validate topic name (Requirement 6.5)
    validation_errors = validate_topic_name(topic_name)
    if validation_errors:
        raise TopicValidationError(validation_errors)

    canonical_name = _normalize_topic_name(topic_name)

    # Resolve backlog root
    if backlog_root is None:
        backlog_root = _find_backlog_root()

    # Get topic path
    topic_path = get_topic_path(canonical_name, backlog_root)

    # Check if topic already exists (Requirement 6.4)
    if topic_path.exists():
        raise TopicExistsError(canonical_name)

    # Ensure topic directories exist
    ensure_topic_dirs(backlog_root)

    # Create topic directory (Requirement 6.1)
    topic_path.mkdir(parents=True, exist_ok=True)

    # Create materials buffer subdirectories (KABSD-FTR-0037)
    materials_subdirs = ["clips", "links", "extracts", "logs"]
    materials_root = topic_path / "materials"
    for subdir in materials_subdirs:
        (materials_root / subdir).mkdir(parents=True, exist_ok=True)

    # Create synthesis and publish directories
    (topic_path / "synthesis").mkdir(parents=True, exist_ok=True)
    (topic_path / "publish").mkdir(parents=True, exist_ok=True)

    # Generate timestamps
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")

    # Create manifest (Requirement 6.2)
    manifest = TopicManifest(
        topic=canonical_name,
        agent=agent,
        seed_items=[],
        pinned_docs=[],
        snippet_refs=[],
        status="open",
        closed_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )

    # Save manifest.json
    manifest_path = topic_path / "manifest.json"
    manifest.save(manifest_path)

    # Optionally create brief.md (KABSD-FTR-0037)
    if create_brief:
        brief_content = _generate_topic_brief_template(canonical_name, timestamp)
        brief_path = topic_path / "brief.md"
        brief_path.write_text(brief_content, encoding="utf-8")

    # Optionally create notes.md (Requirement 6.3, backward compat)
    if create_notes:
        notes_content = _generate_topic_notes_template(canonical_name)
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


def _generate_topic_brief_template(topic_name: str, timestamp: str) -> str:
    """
    Generate brief.md template for a topic (distilled briefing).

    The brief is the synthesized output that helps agents quickly understand
    task context without re-collecting materials.

    Args:
        topic_name: Topic name
        timestamp: ISO 8601 timestamp

    Returns:
        Brief template content (deterministic format per KABSD-FTR-0037)
    """
    return f"""# Topic Brief: {topic_name}

Generated: {timestamp}

## Facts

<!-- Verified facts with citations to materials/items/docs -->
- [ ] {{fact}} — [source](ref)

## Unknowns / Risks

<!-- Open questions and potential blockers -->
- [ ] {{unknown or risk}}

## Proposed Actions

<!-- Concrete next steps, linked to workitems -->
- [ ] {{action}} → {{workitem ref or "new ticket needed"}}

## Decision Candidates

<!-- Tradeoffs requiring ADR -->
- [ ] {{decision}} → {{ADR ref or "draft needed"}}

---
_This brief is auto-generated. Edit after distill to finalize._
"""


def _now_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _workspace_root(backlog_root: Path) -> Path:
    # backlog_root is _kano/backlog, workspace root is two levels up.
    return backlog_root.parent.parent


def _try_git_revision(workspace_root: Path) -> Optional[str]:
    git_dir = workspace_root / ".git"
    if not git_dir.exists():
        return None
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(workspace_root),
            stderr=subprocess.DEVNULL,
        )
        rev = out.decode("utf-8").strip()
        return rev or None
    except Exception:
        return None


def add_snippet_to_topic(
    topic_name: str,
    *,
    file_path: str,
    start_line: int,
    end_line: int,
    agent: Optional[str] = None,
    include_snapshot: bool = False,
    backlog_root: Optional[Path] = None,
) -> TopicAddSnippetResult:
    """Collect a code snippet reference into the topic materials buffer.

    Reference-first: stores file+line range+hash (+optional snapshot) in manifest.json.
    """
    if start_line <= 0 or end_line <= 0 or end_line < start_line:
        raise TopicError(
            f"Invalid line range: {start_line}-{end_line}",
            suggestion="Use 1-based inclusive line numbers where end >= start",
        )

    if backlog_root is None:
        backlog_root = _find_backlog_root()

    canonical_name = _normalize_topic_name(topic_name)
    topic_path = get_topic_path(canonical_name, backlog_root)
    manifest_path = topic_path / "manifest.json"
    if not manifest_path.exists():
        raise TopicNotFoundError(canonical_name)

    ws_root = _workspace_root(backlog_root)
    abs_path = Path(file_path)
    if not abs_path.is_absolute():
        abs_path = (ws_root / file_path).resolve()
    if not abs_path.exists() or not abs_path.is_file():
        raise TopicError(
            f"Snippet file not found: {file_path}",
            suggestion="Provide a workspace-relative path or an absolute path",
        )

    # Read snippet text
    raw_lines = abs_path.read_text(encoding="utf-8").splitlines()
    if start_line > len(raw_lines):
        raise TopicError(
            f"Start line out of range: {start_line} > {len(raw_lines)}",
            suggestion="Check the file length and line numbers",
        )
    end_line = min(end_line, len(raw_lines))
    snippet_text = "\n".join(raw_lines[start_line - 1 : end_line])

    sha = hashlib.sha256(snippet_text.encode("utf-8")).hexdigest()
    rel_file = str(abs_path.relative_to(ws_root)).replace("\\", "/")

    snippet = SnippetRef(
        repo="local",
        revision=_try_git_revision(ws_root),
        file=rel_file,
        lines=[start_line, end_line],
        hash=f"sha256:{sha}",
        cached_text=snippet_text if include_snapshot else None,
        collected_at=_now_timestamp(),
        collector=(agent.strip() if agent and agent.strip() else None),
    )

    manifest = TopicManifest.load(manifest_path)

    def _same(a: SnippetRef, b: SnippetRef) -> bool:
        return (
            a.repo == b.repo
            and a.revision == b.revision
            and a.file == b.file
            and a.lines == b.lines
            and a.hash == b.hash
        )

    for existing in manifest.snippet_refs:
        if isinstance(existing, SnippetRef) and _same(existing, snippet):
            return TopicAddSnippetResult(topic=canonical_name, snippet=existing, added=False)

    manifest.snippet_refs.append(snippet)
    manifest.updated_at = _now_timestamp()
    manifest.save(manifest_path)

    # Ensure materials dir exists (collector can also drop raw logs/files there).
    (topic_path / "materials").mkdir(parents=True, exist_ok=True)
    return TopicAddSnippetResult(topic=canonical_name, snippet=snippet, added=True)


def distill_topic(
    topic_name: str,
    *,
    backlog_root: Optional[Path] = None,
) -> Path:
    """Generate/overwrite a deterministic brief.md from the manifest + materials index."""
    if backlog_root is None:
        backlog_root = _find_backlog_root()

    canonical_name = _normalize_topic_name(topic_name)
    topic_path = get_topic_path(canonical_name, backlog_root)
    manifest_path = topic_path / "manifest.json"
    if not manifest_path.exists():
        raise TopicNotFoundError(canonical_name)

    manifest = TopicManifest.load(manifest_path)
    generated_at = _now_timestamp()

    items = "\n".join(f"- {uid}" for uid in sorted(manifest.seed_items)) or "- (none)"
    docs = "\n".join(f"- {p}" for p in sorted(manifest.pinned_docs)) or "- (none)"
    snippets_lines: List[str] = []
    for s in sorted(
        manifest.snippet_refs,
        key=lambda x: (x.file, x.lines[0] if x.lines else 0, x.lines[1] if len(x.lines) > 1 else 0, x.hash),
    ):
        rng = "" if not s.lines else f"#L{s.lines[0]}-L{s.lines[1]}"
        snippets_lines.append(f"- {s.file}{rng} ({s.hash})")
    snippets = "\n".join(snippets_lines) or "- (none)"

    brief = (
        f"# Topic Brief: {canonical_name}\n\n"
        f"Generated: {generated_at}\n\n"
        "## Facts\n\n"
        "<!-- Verified facts with citations to materials/items/docs -->\n"
        "- [ ] {fact} — [source](ref)\n\n"
        "## Unknowns / Risks\n\n"
        "- [ ] {unknown or risk}\n\n"
        "## Proposed Actions\n\n"
        "- [ ] {action} → {workitem ref or \"new ticket needed\"}\n\n"
        "## Decision Candidates\n\n"
        "- [ ] {decision} → {ADR ref or \"draft needed\"}\n\n"
        "## Materials Index (Deterministic)\n\n"
        "### Items\n"
        f"{items}\n\n"
        "### Pinned Docs\n"
        f"{docs}\n\n"
        "### Snippet Refs\n"
        f"{snippets}\n"
    )

    brief_path = topic_path / "brief.md"
    brief_path.write_text(brief, encoding="utf-8")

    manifest.updated_at = generated_at
    manifest.save(manifest_path)
    return brief_path


def close_topic(
    topic_name: str,
    *,
    agent: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> TopicCloseResult:
    if backlog_root is None:
        backlog_root = _find_backlog_root()

    canonical_name = _normalize_topic_name(topic_name)
    topic_path = get_topic_path(canonical_name, backlog_root)
    manifest_path = topic_path / "manifest.json"
    if not manifest_path.exists():
        raise TopicNotFoundError(canonical_name)

    manifest = TopicManifest.load(manifest_path)
    if manifest.status == "closed":
        return TopicCloseResult(topic=canonical_name, closed=False, closed_at=manifest.closed_at or "")

    ts = _now_timestamp()
    manifest.status = "closed"
    manifest.closed_at = ts
    manifest.updated_at = ts
    manifest.save(manifest_path)
    return TopicCloseResult(topic=canonical_name, closed=True, closed_at=ts)


def cleanup_topics(
    *,
    ttl_days: int,
    backlog_root: Optional[Path] = None,
    dry_run: bool = True,
    delete_topic_dir: bool = False,
) -> TopicCleanupResult:
    """Cleanup raw materials for closed topics older than ttl_days.

    Default behavior deletes materials/ only; optionally deletes the whole topic dir.
    """
    if ttl_days <= 0:
        raise TopicError("ttl_days must be > 0")

    if backlog_root is None:
        backlog_root = _find_backlog_root()

    topics_root = get_topics_root(backlog_root)
    if not topics_root.exists():
        return TopicCleanupResult(0, 0, 0, [])

    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - (ttl_days * 24 * 3600)

    topics_scanned = 0
    topics_cleaned = 0
    materials_deleted = 0
    deleted_paths: List[Path] = []

    for topic_dir in sorted([p for p in topics_root.iterdir() if p.is_dir()]):
        topics_scanned += 1
        manifest_path = topic_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = TopicManifest.load(manifest_path)
        except Exception:
            continue
        if manifest.status != "closed" or not manifest.closed_at:
            continue
        try:
            closed_dt = datetime.fromisoformat(manifest.closed_at.replace("Z", "+00:00"))
        except Exception:
            continue
        if closed_dt.timestamp() > cutoff:
            continue

        targets: List[Path] = []
        materials_dir = topic_dir / "materials"
        if materials_dir.exists():
            targets.append(materials_dir)
        if delete_topic_dir:
            targets = [topic_dir]

        if not targets:
            continue

        topics_cleaned += 1
        for target in targets:
            if dry_run:
                deleted_paths.append(target)
                continue
            # Delete directory tree
            for child in target.rglob("*"):
                pass
            import shutil

            shutil.rmtree(target, ignore_errors=True)
            deleted_paths.append(target)
            materials_deleted += 1

    return TopicCleanupResult(
        topics_scanned=topics_scanned,
        topics_cleaned=topics_cleaned,
        materials_deleted=materials_deleted,
        deleted_paths=deleted_paths,
    )


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
    canonical_name = _normalize_topic_name(topic_name)
    topic_path = get_topic_path(canonical_name, backlog_root)
    manifest_path = topic_path / "manifest.json"

    if not manifest_path.exists():
        raise TopicNotFoundError(canonical_name)

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
            topic=canonical_name,
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
        topic=canonical_name,
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
    canonical_name = _normalize_topic_name(topic_name)
    topic_path = get_topic_path(canonical_name, backlog_root)
    manifest_path = topic_path / "manifest.json"

    if not manifest_path.exists():
        raise TopicNotFoundError(canonical_name)

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
            topic=canonical_name,
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
        topic=canonical_name,
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
    canonical_name = _normalize_topic_name(topic_name)
    topic_path = get_topic_path(canonical_name, backlog_root)
    manifest_path = topic_path / "manifest.json"

    if not manifest_path.exists():
        raise TopicNotFoundError(canonical_name)

    # Load manifest to get counts
    manifest = TopicManifest.load(manifest_path)

    # Get previous active topic (if any)
    previous_topic = get_active_topic(agent, backlog_root=backlog_root)

    # Write topic name to active_topic.<agent>.txt (Requirement 9.1)
    active_topic_path = get_active_topic_path(agent, backlog_root)
    
    # Ensure parent directory exists
    active_topic_path.parent.mkdir(parents=True, exist_ok=True)
    
    active_topic_path.write_text(canonical_name, encoding="utf-8")

    # Return summary with item count and pinned doc count (Requirement 9.2)
    return TopicSwitchResult(
        topic=canonical_name,
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

    topic_name = _normalize_topic_name(active_topic_path.read_text(encoding="utf-8"))
    
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
    canonical_name = _normalize_topic_name(topic_name)
    topic_path = get_topic_path(canonical_name, backlog_root)
    manifest_path = topic_path / "manifest.json"

    if not manifest_path.exists():
        raise TopicNotFoundError(canonical_name)

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
        topic=canonical_name,
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
