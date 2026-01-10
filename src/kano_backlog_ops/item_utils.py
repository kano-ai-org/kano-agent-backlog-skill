"""
item_utils.py - Shared utilities for work item operations.

Extracted from scripts/backlog/workitem_create.py and other item scripts.
Per ADR-0013, this is a utility module for ops layer functions.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime


def slugify(text: str, max_len: int = 80) -> str:
    """Convert text to URL-safe slug for use in filenames."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "untitled"


def generate_id(prefix: str, type_code: str, number: int) -> str:
    """Generate a backlog item ID.
    
    Format: PREFIX-TYPECODE-0001 (e.g., KABSD-TSK-0001)
    
    Args:
        prefix: Project prefix (e.g., KABSD)
        type_code: Item type code (e.g., TSK, FTR, EPIC)
        number: Sequential number (1-based)
    
    Returns:
        Generated item ID
    """
    return f"{prefix}-{type_code}-{number:04d}"


def find_next_number(
    items_root: Path,
    prefix: str,
    type_code: str,
) -> int:
    """Find the next sequential number for an item type within a product.
    
    Scans all items under items_root to find the highest number used,
    returns next number to use.
    
    Args:
        items_root: Root directory for backlog items
        prefix: Project prefix
        type_code: Item type code (TSK, FTR, EPIC, etc.)
    
    Returns:
        Next available number (1-based)
    """
    pattern = re.compile(rf"{re.escape(prefix)}-{type_code}-(\d{{4}})")
    max_num = 0
    
    if not items_root.exists():
        return 1
    
    for path in items_root.rglob("*.md"):
        # Skip special files
        if path.name == "README.md" or path.name.endswith(".index.md"):
            continue
        
        # Extract ID from filename
        item_id = _extract_id_from_filename(path.name)
        if not item_id:
            continue
        
        match = pattern.search(item_id)
        if not match:
            continue
        
        number = int(match.group(1))
        if number > max_num:
            max_num = number
    
    return max_num + 1


def _extract_id_from_filename(filename: str) -> Optional[str]:
    """Extract item ID from markdown filename.
    
    Filename format: KABSD-TSK-0001_slug.md
    
    Args:
        filename: Markdown filename
    
    Returns:
        Item ID or None if not found
    """
    if not filename.endswith(".md"):
        return None
    
    stem = filename[:-3]  # Remove .md
    parts = stem.split("_", 1)
    
    if len(parts) != 2:
        return None
    
    item_id = parts[0]
    
    # Validate format: PREFIX-TYPECODE-0000
    if re.match(r"^[A-Z]+-[A-Z]+-\d{4}$", item_id):
        return item_id
    
    return None


def calculate_bucket(number: int) -> str:
    """Calculate bucket directory for a number.
    
    Numbers are organized in buckets of 100:
    - 1-99: 0000
    - 100-199: 0100
    - 200-299: 0200
    etc.
    
    Args:
        number: Item number
    
    Returns:
        Bucket string (e.g., "0100")
    """
    bucket = (number // 100) * 100
    return f"{bucket:04d}"


def construct_item_path(
    items_root: Path,
    item_type: str,
    item_id: str,
    title: str,
    type_folder_name: str = None,
) -> Path:
    """Construct full path for a work item file.
    
    Structure: items_root/<type>/<bucket>/<ID>_<slug>.md
    
    Example: items/task/0100/KABSD-TSK-0001_create-feature.md
    
    Args:
        items_root: Root items directory
        item_type: Item type (epic, feature, task, etc.)
        item_id: Generated item ID (e.g., KABSD-TSK-0001)
        title: Item title
        type_folder_name: Optional alternative folder name (e.g., "tasks" instead of "task")
    
    Returns:
        Full path for the item file
    """
    if type_folder_name is None:
        type_folder_name = item_type.lower()
    
    # Extract number from ID for bucket calculation
    parts = item_id.rsplit("-", 1)
    number = int(parts[1])
    bucket = calculate_bucket(number)
    
    slug = slugify(title)
    filename = f"{item_id}_{slug}.md"
    
    path = items_root / type_folder_name / bucket / filename
    return path


def pick_items_subdir(items_root: Path, type_folder_candidates: Tuple[str, ...]) -> str:
    """Pick the correct item type subdirectory.
    
    Handles migration scenarios where both old and new naming might exist
    (e.g., 'tasks' and 'task').
    
    Args:
        items_root: Root items directory
        type_folder_candidates: Tuple of candidate names, in preference order
    
    Returns:
        The name of the directory that exists, or first candidate
    """
    for candidate in type_folder_candidates:
        candidate_path = items_root / candidate
        if candidate_path.exists():
            return candidate
    
    # Default to first candidate
    return type_folder_candidates[0]


def derive_prefix(project_name: str) -> str:
    """Derive a project prefix from project name.
    
    Examples:
        'my-project' -> 'MP'
        'kano-agent-backlog-skill' -> 'KA'
        'a' -> 'A' (single letter expanded if possible)
    
    Args:
        project_name: Project name
    
    Returns:
        2+ character prefix in uppercase
    """
    # Normalize
    project_name = project_name.strip().lower()
    
    # Try: take first letter of each word
    segments = re.split(r"[-_\s]", project_name)
    segments = [s for s in segments if s]
    
    if len(segments) >= 2:
        prefix = "".join(s[0] for s in segments[:2])
        return prefix.upper()
    
    # If only one segment or no segments, use different logic
    if len(segments) == 1:
        seed = segments[0]
        prefix = seed[0] if seed else ""
        
        # Try to find a consonant for second letter
        consonant = ""
        for ch in seed[1:]:
            if ch.isalpha() and ch.upper() not in "AEIOU":
                consonant = ch
                break
        
        if consonant:
            prefix += consonant
        else:
            # Use any letter
            for ch in seed[1:]:
                if ch.isalpha():
                    prefix += ch
                    break
        
        if len(prefix) >= 2:
            return prefix.upper()
    
    # Fallback
    return "XX"


def get_today() -> str:
    """Get today's date in ISO format (YYYY-MM-DD)."""
    return datetime.now().strftime("%Y-%m-%d")
