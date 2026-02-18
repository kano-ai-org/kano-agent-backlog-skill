"""
item_utils.py - Shared utilities for work item operations.

Extracted from scripts/backlog/workitem_create.py and other item scripts.
Per ADR-0013, this is a utility module for ops layer functions.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime


from kano_backlog_core.config import ConfigLoader
from kano_backlog_core.models import ItemType


def sync_id_sequences(
    product: str,
    backlog_root: Optional[Path] = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Initialize DB ID sequences from existing files.
    
    Scans filesystem for max ID per type and updates DB sequence table.
    
    Args:
        product: Product name
        backlog_root: Optional backlog root override
        dry_run: If True, don't modify DB
        
    Returns:
        Dict of {type_code: next_number}
    """
    if backlog_root is None:
        ctx = ConfigLoader.from_path(Path.cwd(), product=product)
        backlog_root = ctx.product_root
    else:
        backlog_root = backlog_root / "products" / product
        
    # Load prefix from project config
    try:
        from kano_backlog_core.project_config import ProjectConfigLoader
        
        project_config = ProjectConfigLoader.load_project_config_optional(backlog_root)
        if project_config:
            # Find product by name
            for prod_name, prod_def in project_config.products.items():
                if prod_name == product:
                    prefix = prod_def.prefix
                    break
            else:
                prefix = derive_prefix(product)
        else:
            prefix = derive_prefix(product)
    except Exception:
        prefix = derive_prefix(product)
    
    items_root = backlog_root / "items"
    
    ctx, effective = ConfigLoader.load_effective_config(backlog_root, product=product)
    cache_dir = ConfigLoader.get_chunks_cache_root(ctx.backlog_root, effective)
    db_path = cache_dir / f"backlog.{product}.chunks.v1.db"
    
    type_code_map = {
        ItemType.EPIC: "EPIC",
        ItemType.FEATURE: "FTR",
        ItemType.USER_STORY: "USR",
        ItemType.TASK: "TSK",
        ItemType.BUG: "BUG",
    }
    
    results = {}
    
    # Ensure DB exists if not dry run
    if not dry_run and not db_path.exists():
        # Ideally we should init the DB here, but for now we assume chunks build handles it
        # or we create a minimal one.
        # For simplicity, we just create the table if connection succeeds
        pass
        
    conn = None
    if not dry_run:
        cache_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS id_sequences (
                prefix TEXT NOT NULL,
                type_code TEXT NOT NULL,
                next_number INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (prefix, type_code)
            )
        """)
    
    try:
        for item_type, type_code in type_code_map.items():
            # Find max from files
            next_from_files = find_next_number(items_root, prefix, type_code)
            
            # Find current from DB (if exists)
            next_from_db = 1
            if conn:
                try:
                    cursor = conn.execute(
                        "SELECT next_number FROM id_sequences WHERE prefix = ? AND type_code = ?",
                        (prefix, type_code)
                    )
                    row = cursor.fetchone()
                    if row:
                        next_from_db = row[0]
                except sqlite3.Error:
                    pass
            
            # Target is max of both (to be safe)
            target_next = max(next_from_files, next_from_db)
            
            results[type_code] = target_next
            
            if not dry_run and conn:
                conn.execute("""
                    INSERT INTO id_sequences (prefix, type_code, next_number)
                    VALUES (?, ?, ?)
                    ON CONFLICT(prefix, type_code) DO UPDATE SET
                        next_number = excluded.next_number
                    WHERE excluded.next_number > id_sequences.next_number
                """, (prefix, type_code, target_next))
        
        if conn:
            conn.commit()
            
    finally:
        if conn:
            conn.close()
            
    return results


def resolve_product_prefix(product_root: Path, product: str) -> str:
    """Resolve the ID prefix for a product."""
    try:
        from kano_backlog_core.project_config import ProjectConfigLoader

        project_config = ProjectConfigLoader.load_project_config_optional(product_root)
        if project_config:
            product_def = project_config.get_product(product)
            if product_def:
                return product_def.prefix
    except Exception:
        pass
    return derive_prefix(product)


def load_db_sequences(db_path: Path, prefix: str) -> Dict[str, int]:
    """Load ID sequence counters from the SQLite DB."""
    if not db_path.exists():
        return {}

    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='id_sequences'"
        )
        if not cursor.fetchone():
            return {}
        cursor = conn.execute(
            "SELECT type_code, next_number FROM id_sequences WHERE prefix = ?",
            (prefix,),
        )
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    except sqlite3.Error:
        return {}
    finally:
        if conn:
            conn.close()


def check_sequence_health(
    product: str,
    product_root: Path,
) -> Tuple[Path, Dict[str, Dict[str, Any]]]:
    """Compare DB sequences against filesystem max IDs."""
    ctx, effective = ConfigLoader.load_effective_config(product_root, product=product)
    cache_dir = ConfigLoader.get_chunks_cache_root(ctx.backlog_root, effective)
    db_path = cache_dir / f"backlog.{product}.chunks.v1.db"

    prefix = resolve_product_prefix(product_root, product)
    items_root = product_root / "items"

    type_code_map = {
        ItemType.EPIC: "EPIC",
        ItemType.FEATURE: "FTR",
        ItemType.USER_STORY: "USR",
        ItemType.TASK: "TSK",
        ItemType.BUG: "BUG",
    }

    db_sequences = load_db_sequences(db_path, prefix)
    status_map: Dict[str, Dict[str, Any]] = {}

    for item_type, type_code in type_code_map.items():
        file_next = find_next_number(items_root, prefix, type_code)
        file_max = max(file_next - 1, 0)
        db_next = db_sequences.get(type_code)
        if db_next is None:
            status = "MISSING"
        elif db_next < file_max:
            status = "STALE"
        else:
            status = "OK"
        status_map[type_code] = {
            "status": status,
            "db_next": db_next,
            "file_next": file_next,
            "file_max": file_max,
        }

    return db_path, status_map


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


def get_next_id_from_db(
    db_path: Path,
    prefix: str,
    type_code: str,
) -> int:
    """Get the next ID number atomically from SQLite sequence table.
    
    Uses `id_sequences` table in the provided DB path.
    If table doesn't exist, raises sqlite3.OperationalError.
    
    Args:
        db_path: Path to SQLite database (e.g. chunks.sqlite3)
        prefix: Project prefix
        type_code: Item type code
        
    Returns:
        Next available number (1-based)
        
    Raises:
        sqlite3.Error: If DB error occurs
        FileNotFoundError: If DB file doesn't exist
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
        
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        
        query = """
            INSERT INTO id_sequences (prefix, type_code, next_number)
            VALUES (?, ?, 1)
            ON CONFLICT(prefix, type_code) DO UPDATE SET
                next_number = next_number + 1
        """
        conn.execute(query, (prefix, type_code))
        
        cursor = conn.execute(
            "SELECT next_number FROM id_sequences WHERE prefix = ? AND type_code = ?", 
            (prefix, type_code)
        )
        row = cursor.fetchone()
        
        if not row:
            raise sqlite3.IntegrityError("Failed to retrieve sequence number after update")
            
        return row[0]


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
