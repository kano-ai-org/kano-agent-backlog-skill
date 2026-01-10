"""
item_templates.py - Templates for generating backlog item content.

Per ADR-0013, this module provides template rendering for work items.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional


def render_item_frontmatter(
    item_id: str,
    uid: str,
    item_type: str,
    title: str,
    priority: str,
    parent: str,
    area: str,
    iteration: str,
    tags: List[str],
    created: str,
    updated: str,
    owner: Optional[str],
) -> str:
    """Render YAML frontmatter for a work item.
    
    Args:
        item_id: Item ID (e.g., KABSD-TSK-0001)
        uid: Unique ID
        item_type: Item type (Epic, Feature, Task, etc.)
        title: Item title
        priority: Priority (P0-P4)
        parent: Parent item ID or "null"
        area: Area/component
        iteration: Sprint/iteration
        tags: List of tags
        created: Creation date (YYYY-MM-DD)
        updated: Last updated date (YYYY-MM-DD)
        owner: Owner name or null
    
    Returns:
        YAML frontmatter string (without outer ---)
    """
    tags_str = repr(tags) if tags else "[]"
    
    lines = [
        "---",
        f"id: {item_id}",
        f"uid: {uid}",
        f"type: {item_type}",
        f'title: "{title}"',
        "state: Proposed",
        f"priority: {priority}",
        f"parent: {parent}",
        f"area: {area}",
        f"iteration: {iteration}",
        f"tags: {tags_str}",
        f"created: {created}",
        f"updated: {updated}",
        f"owner: {owner}",
        "external:",
        "  azure_id: null",
        "  jira_key: null",
        "links:",
        "  relates: []",
        "  blocks: []",
        "  blocked_by: []",
        "decisions: []",
        "---",
    ]
    return "\n".join(lines)


def render_item_body(
    item_id: str,
    uid: str,
    item_type: str,
    title: str,
    priority: str,
    parent: str,
    area: str,
    iteration: str,
    tags: List[str],
    created: str,
    updated: str,
    owner: Optional[str],
    agent: str,
    worklog_message: str,
) -> str:
    """Render complete work item markdown.
    
    Includes frontmatter + body sections.
    
    Args:
        item_id: Item ID
        uid: Unique ID
        item_type: Item type
        title: Item title
        priority: Priority
        parent: Parent item ID
        area: Area
        iteration: Sprint
        tags: Tag list
        created: Creation date
        updated: Last updated date
        owner: Owner name
        agent: Agent creating item
        worklog_message: Initial worklog message
    
    Returns:
        Complete markdown content
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    frontmatter = render_item_frontmatter(
        item_id=item_id,
        uid=uid,
        item_type=item_type,
        title=title,
        priority=priority,
        parent=parent,
        area=area,
        iteration=iteration,
        tags=tags,
        created=created,
        updated=updated,
        owner=owner,
    )
    
    body_sections = [
        "",
        "# Context",
        "",
        "# Goal",
        "",
        "# Non-Goals",
        "",
        "# Approach",
        "",
        "# Alternatives",
        "",
        "# Acceptance Criteria",
        "",
        "# Risks / Dependencies",
        "",
        "# Worklog",
        "",
        f"{timestamp} [agent={agent}] {worklog_message}",
    ]
    
    body = "\n".join(body_sections)
    return frontmatter + "\n" + body + "\n"


def render_epic_index(
    item_id: str,
    title: str,
    updated: str,
    backlog_root_label: str,
) -> str:
    """Render index MOC for an Epic.
    
    Args:
        item_id: Epic ID
        title: Epic title
        updated: Last updated date
        backlog_root_label: Relative path to backlog root (for dataview)
    
    Returns:
        Index markdown content
    """
    lines = [
        "---",
        "type: Index",
        f"for: {item_id}",
        f'title: "{title} Index"',
        f"updated: {updated}",
        "---",
        "",
        "# MOC",
        "",
        "## Auto list (Dataview)",
        "",
        "```dataview",
        "table id, state, priority",
        f'from "{backlog_root_label}/items"',
        f'where parent = "{item_id}"',
        "sort priority asc",
        "```",
        "",
        "## Manual list",
        "",
        "<!-- Add children manually here if needed -->",
        "",
    ]
    return "\n".join(lines)
