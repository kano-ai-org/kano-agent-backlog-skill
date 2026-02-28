"""
changelog.py - Generate CHANGELOG.md from backlog Done items.

This module generates Keep-a-Changelog format entries by reading
completed backlog items, grouping them by type, and formatting them
with appropriate emojis and links.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from .view import ItemSnapshot, _collect_items, _normalize_backlog_root, _resolve_target_root


TYPE_EMOJI_MAP = {
    "Epic": "🎯",
    "Feature": "✨",
    "UserStory": "📋",
    "Task": "✅",
    "Bug": "🐛",
}

SECTION_ORDER = ["Epic", "Feature", "UserStory", "Task", "Bug"]


@dataclass
class ChangelogResult:
    """Result of changelog generation."""

    version: str
    content: str
    item_count: int
    output_path: Optional[Path] = None


def generate_changelog_from_backlog(
    *,
    version: str,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
    state_filter: Optional[List[str]] = None,
    date_str: Optional[str] = None,
) -> ChangelogResult:
    """
    Generate a changelog section from backlog Done items.

    Args:
        version: Version string (e.g., "0.0.1")
        product: Product name (if multi-product backlog)
        backlog_root: Path to backlog root
        state_filter: List of states to include (default: ["Done"])
        date_str: Release date (default: today in YYYY-MM-DD format)

    Returns:
        ChangelogResult with generated markdown content
    """
    root = _normalize_backlog_root(backlog_root)
    target_root = _resolve_target_root(root, product)
    items_root = target_root / "items"

    if not items_root.exists():
        raise FileNotFoundError(f"Items directory not found: {items_root}")

    # Collect all items
    all_items = _collect_items(items_root)

    # Filter by state (default: Done items only)
    states = state_filter or ["Done"]
    filtered_items = [item for item in all_items if item.state in states]

    # Group by type
    grouped: Dict[str, List[ItemSnapshot]] = {}
    for item in filtered_items:
        grouped.setdefault(item.type, []).append(item)

    # Sort within each type by ID
    for items_list in grouped.values():
        items_list.sort(key=lambda x: x.id)

    # Format changelog
    release_date = date_str or date.today().strftime("%Y-%m-%d")
    content = _format_changelog_section(
        version=version,
        release_date=release_date,
        grouped_items=grouped,
        items_root=items_root,
    )

    return ChangelogResult(
        version=version,
        content=content,
        item_count=len(filtered_items),
    )


def merge_unreleased_to_version(
    changelog_path: Path,
    version: str,
    date_str: Optional[str] = None,
) -> str:
    """
    Merge [Unreleased] section into specified version in existing CHANGELOG.md.

    Args:
        changelog_path: Path to existing CHANGELOG.md
        version: Version to merge into (e.g., "0.0.1")
        date_str: Release date (default: today)

    Returns:
        Updated CHANGELOG.md content
    """
    if not changelog_path.exists():
        raise FileNotFoundError(f"CHANGELOG.md not found: {changelog_path}")

    content = changelog_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    release_date = date_str or date.today().strftime("%Y-%m-%d")

    # Find [Unreleased] section
    unreleased_start = None
    unreleased_end = None
    version_start = None

    for i, line in enumerate(lines):
        if "## [Unreleased]" in line:
            unreleased_start = i
        elif unreleased_start is not None and version_start is None:
            if line.startswith("## ["):
                unreleased_end = i
                break
            elif line.startswith("## Option") or line.startswith("## Recommendation"):
                # Found Option sections, stop
                unreleased_end = i
                break

    for i, line in enumerate(lines):
        if f"## [{version}]" in line:
            version_start = i
            break

    if unreleased_start is None:
        raise ValueError("No [Unreleased] section found in CHANGELOG.md")

    # Extract unreleased content
    if unreleased_end is None:
        unreleased_end = len(lines)

    unreleased_content = lines[unreleased_start + 1 : unreleased_end]

    # Update version header with date
    if version_start is not None:
        # Replace existing version line with dated one
        lines[version_start] = f"## [{version}] - {release_date}\n"
        # Insert unreleased content after version header
        lines[version_start + 1 : version_start + 1] = unreleased_content
    else:
        # No existing version section, insert new one
        new_version_lines = [f"## [{version}] - {release_date}\n"] + unreleased_content + ["\n"]
        lines[unreleased_end:unreleased_end] = new_version_lines

    # Clear [Unreleased] section
    lines[unreleased_start + 1 : unreleased_end] = ["\n"]

    return "".join(lines)


def _format_changelog_section(
    version: str,
    release_date: str,
    grouped_items: Dict[str, List[ItemSnapshot]],
    items_root: Path,
) -> str:
    """Format a changelog section for a given version."""
    lines: List[str] = []
    lines.append(f"## [{version}] - {release_date}\n")
    lines.append("\n")

    # Order sections by priority
    for type_name in SECTION_ORDER:
        if type_name not in grouped_items:
            continue

        items = grouped_items[type_name]
        if not items:
            continue

        emoji = TYPE_EMOJI_MAP.get(type_name, "📦")
        section_title = _get_section_title(type_name)
        lines.append(f"### {emoji} {section_title}\n")
        lines.append("\n")

        for item in items:
            # Calculate relative path from skill root
            try:
                # Get path relative to items_root parent (which should be product or backlog root)
                rel_path = item.path.relative_to(items_root.parent)
                link_path = f"../_kano/backlog/{rel_path.as_posix()}"
            except ValueError:
                link_path = item.path.as_posix()

            # Format: - **Title** ([ID](link))
            line = f"- **{item.title}** ([{item.id}]({link_path}))\n"
            lines.append(line)

        lines.append("\n")

    # Handle other types not in SECTION_ORDER
    for type_name, items in sorted(grouped_items.items()):
        if type_name in SECTION_ORDER or not items:
            continue

        lines.append(f"### 📦 {type_name}s\n")
        lines.append("\n")

        for item in items:
            try:
                rel_path = item.path.relative_to(items_root.parent)
                link_path = f"../_kano/backlog/{rel_path.as_posix()}"
            except ValueError:
                link_path = item.path.as_posix()

            line = f"- **{item.title}** ([{item.id}]({link_path}))\n"
            lines.append(line)

        lines.append("\n")

    return "".join(lines)


def _get_section_title(type_name: str) -> str:
    """Get friendly section title for a work item type."""
    titles = {
        "Epic": "Epics",
        "Feature": "Features",
        "UserStory": "User Stories",
        "Task": "Tasks Completed",
        "Bug": "Bug Fixes",
    }
    return titles.get(type_name, f"{type_name}s")
