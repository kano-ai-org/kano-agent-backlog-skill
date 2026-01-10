"""
frontmatter.py - YAML frontmatter parsing and manipulation for work items.

Per ADR-0013: Extracted frontmatter logic for use in ops layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple


def find_frontmatter_delimiters(lines: List[str]) -> Tuple[int, int]:
    """Find the start and end indices of YAML frontmatter.
    
    Args:
        lines: List of content lines
    
    Returns:
        Tuple of (start_index, end_index) where both are inclusive, or (-1, -1) if not found
    """
    if not lines or lines[0].strip() != "---":
        return -1, -1
    
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return 0, idx
    
    return -1, -1


def parse_frontmatter(lines: List[str]) -> Dict[str, str]:
    """Parse YAML frontmatter from markdown lines.
    
    Extracts key-value pairs from the YAML frontmatter block.
    Handles quoted values.
    
    Args:
        lines: List of content lines
    
    Returns:
        Dictionary of parsed frontmatter key-value pairs
    """
    start, end = find_frontmatter_delimiters(lines)
    if start == -1:
        return {}
    
    data: Dict[str, str] = {}
    for line in lines[start + 1 : end]:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        # Strip quotes if present
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        data[key.strip()] = value
    
    return data


def update_frontmatter_field(
    lines: List[str],
    field_name: str,
    new_value: str,
) -> List[str]:
    """Update a single field in frontmatter.
    
    Args:
        lines: List of content lines
        field_name: Name of field to update
        new_value: New value (unquoted)
    
    Returns:
        Updated lines
        
    Raises:
        ValueError: If frontmatter not found or field not found
    """
    start, end = find_frontmatter_delimiters(lines)
    if start == -1:
        raise ValueError("Frontmatter not found")
    
    field_found = False
    for idx in range(start + 1, end):
        if lines[idx].startswith(f"{field_name}:"):
            lines[idx] = f"{field_name}: {new_value}"
            field_found = True
            break
    
    if not field_found:
        raise ValueError(f"Frontmatter field not found: {field_name}")
    
    return lines


def add_frontmatter_field_before_closing(
    lines: List[str],
    field_name: str,
    value: str,
) -> List[str]:
    """Add a new field to frontmatter before the closing delimiter.
    
    Args:
        lines: List of content lines
        field_name: Name of field to add
        value: Value (unquoted)
    
    Returns:
        Updated lines
        
    Raises:
        ValueError: If frontmatter not found
    """
    start, end = find_frontmatter_delimiters(lines)
    if start == -1:
        raise ValueError("Frontmatter not found")
    
    lines.insert(end, f"{field_name}: {value}")
    return lines


def update_frontmatter(
    lines: List[str],
    state: str,
    updated_date: str,
    owner: Optional[str] = None,
) -> List[str]:
    """Update state and updated date in frontmatter, and optionally owner.
    
    Args:
        lines: List of content lines
        state: New state value
        updated_date: New updated date (YYYY-MM-DD format)
        owner: Optional owner to set
    
    Returns:
        Updated lines
        
    Raises:
        ValueError: If frontmatter not found or required fields missing
    """
    start, end = find_frontmatter_delimiters(lines)
    if start == -1:
        raise ValueError("Frontmatter not found")
    
    state_found = False
    updated_found = False
    owner_found = False
    
    for idx in range(start + 1, end):
        if lines[idx].startswith("state:"):
            lines[idx] = f"state: {state}"
            state_found = True
        elif lines[idx].startswith("updated:"):
            lines[idx] = f"updated: {updated_date}"
            updated_found = True
        elif lines[idx].startswith("owner:"):
            owner_found = True
            if owner is not None:
                lines[idx] = f"owner: {owner}"
    
    if not state_found:
        raise ValueError("Frontmatter missing state field")
    if not updated_found:
        raise ValueError("Frontmatter missing updated field")
    
    # If owner should be set but field doesn't exist, add it
    if owner is not None and not owner_found:
        lines.insert(end, f"owner: {owner}")
    
    return lines


def load_lines(path: Path) -> List[str]:
    """Load lines from file, splitting on newlines.
    
    Args:
        path: Path to file
    
    Returns:
        List of lines (without newline characters)
    """
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines: List[str]) -> None:
    """Write lines to file, joining with newlines.
    
    Args:
        path: Path to file
        lines: List of lines
    """
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
