
import re
import sys
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

try:
    import uuid6
except ImportError:
    # Fallback to internal if Python 3.12+ (not guaranteed here, so we rely on pip install uuid6)
    # If uuid6 not found, we will fail.
    print("Error: 'uuid6' package is required. Install with: pip install uuid6")
    sys.exit(1)

def generate_uid() -> str:
    """Generate a UUIDv7 string."""
    return str(uuid6.uuid7())

def get_uidshort(uid: str, length: int = 8) -> str:
    """Extract uidshort (first N hex chars, no hyphens)."""
    return uid.replace("-", "")[:length]

def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str, str]:
    """
    Parse frontmatter from markdown content.
    Returns (frontmatter_dict, body, raw_frontmatter_block).
    """
    match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not match:
        return {}, content, ""
    
    raw_fm = match.group(1)
    body = match.group(2)
    
    try:
        fm = yaml.safe_load(raw_fm)
        if not isinstance(fm, dict):
            fm = {}
    except yaml.YAMLError:
        fm = {}
        
    return fm, body, raw_fm

def update_frontmatter(file_path: Path, updates: Dict[str, Any], dry_run: bool = False) -> bool:
    """
    Update frontmatter fields in a file.
    Preserves comments and order is NOT guaranteed (limit of PyYAML).
    For a migration script, re-dumping YAML is usually acceptable if we don't destroy custom formatting too much.
    However, to be safer with comments, we might want to append if missing, or use a better parser.
    For this implementation, we will use safe_dump which is standard but loses comments.
    ToDo: Consider `ruamel.yaml` for round-trip preservation if comments are critical.
    
    Returns True if changed.
    """
    content = file_path.read_text(encoding="utf-8")
    fm, body, raw_fm = parse_frontmatter(content)
    
    changed = False
    for k, v in updates.items():
        if fm.get(k) != v:
            fm[k] = v
            changed = True
            
    if not changed:
        return False
        
    if dry_run:
        print(f"[Dry Run] Would update {file_path.name}: {updates}")
        return True
        
    # Reconstruct file
    # We explicitly sort keys to keep some order or specific keys first? 
    # Standard yaml dump might be random order. 
    # Let's try to keep 'id', 'uid' at top if possible via a custom representer or just simple dict order (Py3.7+)
    
    # Priority keys
    priority_keys = ['id', 'uid', 'type', 'title', 'state', 'priority', 'parent', 'area', 'iteration', 'tags', 'created', 'updated']
    ordered_fm = {k: fm[k] for k in priority_keys if k in fm}
    # Add remaining
    for k, v in fm.items():
        if k not in ordered_fm:
            ordered_fm[k] = v
            
    new_fm_str = yaml.safe_dump(ordered_fm, sort_keys=False, allow_unicode=True).strip()
    new_content = f"---\n{new_fm_str}\n---\n{body}"
    
    file_path.write_text(new_content, encoding="utf-8")
    return True
