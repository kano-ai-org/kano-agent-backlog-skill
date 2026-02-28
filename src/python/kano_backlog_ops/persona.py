"""Persona summary and reporting operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from collections import defaultdict

from kano_backlog_core.canonical import CanonicalStore
from kano_backlog_core.models import ItemState
from .init import _resolve_backlog_root


@dataclass
class PersonaSummaryResult:
    """Result of generating a persona summary."""
    artifact_path: Path
    items_analyzed: int
    worklog_entries: int


@dataclass
class PersonaReportResult:
    """Result of generating a persona report."""
    artifact_path: Path
    items_by_state: Dict[str, int]
    total_items: int


def generate_summary(
    *,
    product: str,
    agent: str,
    backlog_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> PersonaSummaryResult:
    """
    Generate a persona activity summary from worklog entries.

    Aggregates all worklog entries across items to show what the persona
    (agent) has been working on. Writes to artifacts/.

    Args:
        product: Product name
        agent: Agent/persona identifier
        backlog_root: Backlog root path (auto-detected if None)
        output_path: Override output path (default: product artifacts/)

    Returns:
        PersonaSummaryResult with summary details

    Raises:
        FileNotFoundError: If product not initialized
    """
    backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)
    product_root = backlog_root_path / "products" / product
    if not product_root.exists():
        raise FileNotFoundError(f"Product not initialized: {product_root}")

    store = CanonicalStore(product_root)
    
    # Collect worklog entries
    worklog_entries: List[tuple[str, str, str]] = []  # (timestamp, item_id, message)
    items_count = 0
    
    for item_path in store.list_items():
        try:
            item = store.read(item_path)
            items_count += 1
            if item.worklog:
                for entry in item.worklog:
                    # Parse worklog line format: "YYYY-MM-DD HH:MM [agent=X] Message"
                    if f"[agent={agent}]" in entry or entry.startswith(f"{agent}:"):
                        worklog_entries.append((entry[:16], item.id, entry))
        except Exception:
            continue
    
    # Generate summary
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    if output_path is None:
        artifacts_dir = product_root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        output_path = artifacts_dir / f"persona_summary_{agent}_{timestamp}.md"
    
    content = f"""# Persona Activity Summary: {agent}

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Product:** {product}  
**Items Analyzed:** {items_count}  
**Worklog Entries:** {len(worklog_entries)}

## Recent Activity

"""
    
    # Sort by timestamp (recent first)
    worklog_entries.sort(reverse=True)
    
    for ts, item_id, entry in worklog_entries[:50]:  # Limit to 50 most recent
        content += f"- **{item_id}**: {entry}\n"
    
    if len(worklog_entries) > 50:
        content += f"\n_({len(worklog_entries) - 50} older entries omitted)_\n"
    
    output_path.write_text(content, encoding="utf-8")
    
    return PersonaSummaryResult(
        artifact_path=output_path,
        items_analyzed=items_count,
        worklog_entries=len(worklog_entries),
    )


def generate_report(
    *,
    product: str,
    agent: str,
    backlog_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> PersonaReportResult:
    """
    Generate a full persona activity report with state breakdown.

    Analyzes all items to show distribution by state, priority, and type.
    Writes to artifacts/.

    Args:
        product: Product name
        agent: Agent/persona identifier (for audit context)
        backlog_root: Backlog root path (auto-detected if None)
        output_path: Override output path (default: product artifacts/)

    Returns:
        PersonaReportResult with report details

    Raises:
        FileNotFoundError: If product not initialized
    """
    backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)
    product_root = backlog_root_path / "products" / product
    if not product_root.exists():
        raise FileNotFoundError(f"Product not initialized: {product_root}")

    store = CanonicalStore(product_root)
    
    # Collect stats
    by_state: Dict[str, int] = defaultdict(int)
    by_type: Dict[str, int] = defaultdict(int)
    by_priority: Dict[str, int] = defaultdict(int)
    total = 0
    
    for item_path in store.list_items():
        try:
            item = store.read(item_path)
            total += 1
            by_state[item.state.value] += 1
            by_type[item.type.value] += 1
            if item.priority:
                by_priority[item.priority] += 1
        except Exception:
            continue
    
    # Generate report
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    if output_path is None:
        artifacts_dir = product_root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        output_path = artifacts_dir / f"persona_report_{agent}_{timestamp}.md"
    
    content = f"""# Persona Activity Report: {agent}

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Product:** {product}  
**Total Items:** {total}

## Items by State

| State | Count | Percentage |
|-------|------:|----------:|
"""
    
    for state in sorted(by_state.keys()):
        count = by_state[state]
        pct = (count / total * 100) if total > 0 else 0
        content += f"| {state} | {count} | {pct:.1f}% |\n"
    
    content += "\n## Items by Type\n\n| Type | Count |\n|------|------:|\n"
    for item_type in sorted(by_type.keys()):
        content += f"| {item_type} | {by_type[item_type]} |\n"
    
    if by_priority:
        content += "\n## Items by Priority\n\n| Priority | Count |\n|----------|------:|\n"
        for priority in sorted(by_priority.keys()):
            content += f"| {priority} | {by_priority[priority]} |\n"
    
    output_path.write_text(content, encoding="utf-8")
    
    return PersonaReportResult(
        artifact_path=output_path,
        items_by_state=dict(by_state),
        total_items=total,
    )
