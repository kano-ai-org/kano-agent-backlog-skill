"""
view.py - Local-first view and dashboard generation operations.

This module regenerates Markdown dashboards directly from the canonical
backlog without shelling out to legacy scripts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import os

import frontmatter


STATE_GROUPS = {
    "Proposed": "New",
    "Planned": "New",
    "Ready": "New",
    "New": "New",
    "InProgress": "InProgress",
    "Review": "InProgress",
    "Blocked": "InProgress",
    "Done": "Done",
    "Dropped": "Done",
}

TYPE_ORDER = ["Epic", "Feature", "UserStory", "Task", "Bug"]
TYPE_LABELS = {
    "Epic": "Epic",
    "Feature": "Feature",
    "UserStory": "UserStory",
    "Task": "Task",
    "Bug": "Bug",
}

DASHBOARD_DEFINITIONS = [
    ("Dashboard_PlainMarkdown_Active.md", "InProgress Work", ["New", "InProgress"]),
    ("Dashboard_PlainMarkdown_New.md", "New Work", ["New"]),
    ("Dashboard_PlainMarkdown_Done.md", "Done Work", ["Done"]),
]


@dataclass
class ViewRefreshResult:
    """Result of refreshing views."""

    views_refreshed: List[Path]
    summaries_refreshed: List[Path]
    reports_refreshed: List[Path]


@dataclass
class GenerateViewResult:
    """Result of generating a single view."""

    path: Path
    item_count: int


@dataclass
class ItemSnapshot:
    """Simplified representation of a backlog item for dashboards."""

    id: str
    title: str
    type: str
    state: str
    group: str
    path: Path
    blocked_by: List[str]
    blocks: List[str]


def refresh_dashboards(
    *,
    product: Optional[str] = None,
    agent: str,
    all_personas: bool = False,
    backlog_root: Optional[Path] = None,
    config_path: Optional[Path] = None,  # noqa: ARG001 (reserved for parity with CLI signature)
) -> ViewRefreshResult:
    """Refresh Markdown dashboards directly from the canonical backlog."""

    root = _normalize_backlog_root(backlog_root)
    target_root = _resolve_target_root(root, product)
    items_root = target_root / "items"
    views_root = target_root / "views"

    if not items_root.exists():
        raise FileNotFoundError(f"Items directory not found: {items_root}")

    views_root.mkdir(parents=True, exist_ok=True)

    grouped_items = _group_items(_collect_items(items_root))
    source_label = _describe_source(items_root, target_root)

    dashboards: List[Path] = []
    for filename, title, groups in DASHBOARD_DEFINITIONS:
        output_path = views_root / filename
        content = _render_dashboard(
            title=title,
            groups=groups,
            grouped_items=grouped_items,
            output_path=output_path,
            source_label=source_label,
            agent=agent,
        )
        output_path.write_text(content, encoding="utf-8")
        dashboards.append(output_path)

    # Persona-aware summaries/reports will be reintroduced once the native
    # implementations land. For now we return empty lists to keep the CLIs
    # compatible with the previous signature.
    return ViewRefreshResult(
        views_refreshed=dashboards,
        summaries_refreshed=[],
        reports_refreshed=[],
    )


def generate_view(
    title: str,
    output_path: Path,
    *,
    groups: Optional[List[str]] = None,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> GenerateViewResult:
    """Generate a single dashboard file (utility for future customization)."""

    root = _normalize_backlog_root(backlog_root)
    target_root = _resolve_target_root(root, product)
    items_root = target_root / "items"
    if not items_root.exists():
        raise FileNotFoundError(f"Items directory not found: {items_root}")

    grouped = _group_items(_collect_items(items_root))
    actual_groups = groups or ["New", "InProgress", "Done"]
    content = _render_dashboard(
        title=title,
        groups=actual_groups,
        grouped_items=grouped,
        output_path=output_path,
        source_label=_describe_source(items_root, target_root),
        agent="unknown",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    total_items = sum(len(items) for mapping in grouped.values() for items in mapping.values())
    return GenerateViewResult(path=output_path, item_count=total_items)


def _normalize_backlog_root(backlog_root: Optional[Path]) -> Path:
    if backlog_root is not None:
        resolved = backlog_root.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Backlog root not found: {resolved}")
        return resolved

    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        possible = candidate / "_kano" / "backlog"
        if possible.exists() and possible.is_dir():
            return possible
    raise FileNotFoundError("Could not locate _kano/backlog; pass --backlog-root explicitly.")


def _resolve_target_root(backlog_root: Path, product: Optional[str]) -> Path:
    if not product:
        return backlog_root
    product_root = backlog_root / "products" / product
    if not product_root.exists():
        raise FileNotFoundError(f"Product backlog not found: {product_root}")
    return product_root


def _collect_items(items_root: Path) -> List[ItemSnapshot]:
    snapshots: List[ItemSnapshot] = []
    for path in sorted(items_root.rglob("*.md")):
        if path.name.endswith(".index.md") or path.name == "README.md":
            continue
        try:
            post = frontmatter.load(path)
        except Exception:
            continue

        metadata = post.metadata or {}
        raw_id = str(metadata.get("id", "")).strip()
        raw_type = str(metadata.get("type", "")).strip()
        raw_state = str(metadata.get("state", "")).strip()
        title = str(metadata.get("title", "")).strip() or raw_id
        group = STATE_GROUPS.get(raw_state)

        if not raw_id or not raw_type or not group:
            continue

        links = metadata.get("links", {}) if isinstance(metadata, dict) else {}
        blocked_by = _ensure_str_list(links.get("blocked_by", []) if isinstance(links, dict) else [])
        blocks = _ensure_str_list(links.get("blocks", []) if isinstance(links, dict) else [])

        snapshots.append(
            ItemSnapshot(
                id=raw_id,
                title=title,
                type=raw_type,
                state=raw_state,
                group=group,
                path=path,
                blocked_by=blocked_by,
                blocks=blocks,
            )
        )
    return snapshots


def _group_items(items: List[ItemSnapshot]) -> Dict[str, Dict[str, List[ItemSnapshot]]]:
    grouped: Dict[str, Dict[str, List[ItemSnapshot]]] = {}
    for item in items:
        grouped.setdefault(item.group, {}).setdefault(item.type, []).append(item)
    for group_mapping in grouped.values():
        for snapshots in group_mapping.values():
            snapshots.sort(key=lambda snap: snap.id)
    return grouped


def _render_dashboard(
    *,
    title: str,
    groups: List[str],
    grouped_items: Dict[str, Dict[str, List[ItemSnapshot]]],
    output_path: Path,
    source_label: str,
    agent: str,
) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"Generated: {timestamp}")
    lines.append(f"Source: {source_label}")
    lines.append(f"Agent: {agent}")
    lines.append("")

    for group in groups:
        lines.append(f"## {group}")
        lines.append("")
        type_mapping = grouped_items.get(group, {})
        ordered_types = _ordered_types(type_mapping.keys())
        if not ordered_types:
            lines.append("_No items._")
            lines.append("")
            continue

        for type_name in ordered_types:
            entries = type_mapping.get(type_name, [])
            if not entries:
                continue
            label = TYPE_LABELS.get(type_name, f"{type_name}s" if not type_name.endswith("s") else type_name)
            lines.append(f"### {label}")
            lines.append("")
            for entry in entries:
                rel = _relative_path(entry.path, output_path.parent)
                description = f"{entry.id} {entry.title}".strip()
                indicators = []
                if entry.blocked_by:
                    indicators.append(f"🔴 Blocked by: {', '.join(entry.blocked_by)}")
                if entry.blocks:
                    indicators.append(f"⛓️ Blocks: {', '.join(entry.blocks)}")
                if indicators:
                    description += " [" + " | ".join(indicators) + "]"
                lines.append(f"- [{description}]({rel})")
            lines.append("")
    return "\n".join(lines) + "\n"


def _ordered_types(types: List[str] | Dict[str, List[ItemSnapshot]]) -> List[str]:
    if isinstance(types, dict):
        candidates = list(types.keys())
    else:
        candidates = list(types)
    ordered = [t for t in TYPE_ORDER if t in candidates]
    extras = sorted(t for t in candidates if t not in TYPE_ORDER)
    return ordered + extras


def _describe_source(items_root: Path, target_root: Path) -> str:
    try:
        rel = items_root.relative_to(target_root)
        return rel.as_posix()
    except ValueError:
        return items_root.as_posix()


def _relative_path(target: Path, start: Path) -> str:
    try:
        return os.path.relpath(target, start).replace("\\", "/")
    except ValueError:
        return target.as_posix()


def _ensure_str_list(values: object) -> List[str]:
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    return []
