"""
worklog.py - Work log management for items.

Per ADR-0013: Extracted worklog logic for use in ops layer.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional


def resolve_model(model: Optional[str]) -> str:
    """Resolve the model name for worklog attribution.

    Order:
    1) explicit argument
    2) env vars KANO_AGENT_MODEL, KANO_MODEL
    3) "unknown" (placeholder; typically omitted from Worklog output)
    """
    if model and model.strip():
        return model.strip()
    env_model = (os.environ.get("KANO_AGENT_MODEL") or os.environ.get("KANO_MODEL") or "").strip()
    return env_model or "unknown"


def find_worklog_section(lines: List[str]) -> int:
    """Find the index of the Worklog section header.
    
    Args:
        lines: List of content lines
    
    Returns:
        Index of "# Worklog" line, or -1 if not found
    """
    for idx, line in enumerate(lines):
        if line.strip() == "# Worklog":
            return idx
    return -1


def ensure_worklog_section(lines: List[str]) -> List[str]:
    """Ensure Worklog section exists, creating it if needed.
    
    Args:
        lines: List of content lines
    
    Returns:
        Updated lines with Worklog section guaranteed
    """
    if find_worklog_section(lines) != -1:
        return lines  # Already exists
    
    # Add worklog section at end
    return lines + ["", "# Worklog", ""]


def append_worklog_entry(
    lines: List[str],
    message: str,
    agent: str,
    model: Optional[str] = None,
) -> List[str]:
    """Append an entry to the Worklog section.
    
    Args:
        lines: List of content lines
        message: Entry message
        agent: Agent identity
        model: Optional AI model used
    
    Returns:
        Updated lines with new worklog entry appended
    """
    lines = ensure_worklog_section(lines)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    resolved_model = resolve_model(model)
    if resolved_model.strip().lower() == "unknown":
        entry = f"{timestamp} [agent={agent}] {message}"
    else:
        entry = f"{timestamp} [agent={agent}] [model={resolved_model}] {message}"
    
    lines.append(entry)
    return lines


def get_worklog_entries(lines: List[str]) -> List[str]:
    """Get all worklog entries from content.
    
    Args:
        lines: List of content lines
    
    Returns:
        List of worklog entry lines (excluding header and empty lines)
    """
    worklog_idx = find_worklog_section(lines)
    if worklog_idx == -1:
        return []
    
    entries = []
    for line in lines[worklog_idx + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        entries.append(line)
    
    return entries
