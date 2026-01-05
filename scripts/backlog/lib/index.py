
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from .utils import parse_frontmatter

@dataclass
class BacklogItem:
    uid: str
    id: str
    uidshort: str
    type: str
    title: str
    state: str
    path: Path
    created: str
    updated: str
    frontmatter: Dict

class BacklogIndex:
    def __init__(self, backlog_root: Path):
        self.root = backlog_root
        self.items_by_uid: Dict[str, BacklogItem] = {}
        self.items_by_id: Dict[str, List[BacklogItem]] = {}
        self.items_by_uidshort: Dict[str, List[BacklogItem]] = {}
        self._scan()

    def _scan(self):
        items_dir = self.root / "items"
        if not items_dir.exists():
            return
            
        for f in items_dir.rglob("*.md"):
            try:
                content = f.read_text(encoding="utf-8")
                fm, _, _ = parse_frontmatter(content)
                
                if not fm or 'id' not in fm:
                    continue
                
                # If uid missing, use empty string or generated logic (handled by migration script, not here)
                # But for index, we only verify strictly complying items?
                # Actually, during migration, items might NOT have proper uid yet.
                # For resolve_ref, we expect uid to exist.
                
                uid = fm.get('uid', '')
                uidshort = uid.replace("-", "")[:8] if uid else ""
                
                item = BacklogItem(
                    uid=uid,
                    id=fm['id'],
                    uidshort=uidshort,
                    type=fm.get('type', 'Unknown'),
                    title=fm.get('title', ''),
                    state=fm.get('state', 'Unknown'),
                    path=f,
                    created=str(fm.get('created', '')),
                    updated=str(fm.get('updated', '')),
                    frontmatter=fm
                )
                
                # Index by UID
                if uid:
                    self.items_by_uid[uid] = item
                
                # Index by UID Short
                if uidshort:
                    if uidshort not in self.items_by_uidshort:
                        self.items_by_uidshort[uidshort] = []
                    self.items_by_uidshort[uidshort].append(item)
                    
                # Index by Display ID
                did = item.id
                if did not in self.items_by_id:
                    self.items_by_id[did] = []
                self.items_by_id[did].append(item)
                
            except Exception as e:
                print(f"Warning: Failed to index {f}: {e}")

    def get_by_uid(self, uid: str) -> Optional[BacklogItem]:
        return self.items_by_uid.get(uid)

    def get_by_uidshort(self, prefix: str) -> List[BacklogItem]:
        # Exact match on pre-calculated short uid (8 chars)
        # If prefix is shorter/longer, we scan keys?
        # For simplicity, let's just prefix match on all uids if not 8 chars?
        # No, optimization:
        if len(prefix) == 8:
            return self.items_by_uidshort.get(prefix, [])
        
        # Fallback scan
        matches = []
        for uid, item in self.items_by_uid.items():
            if uid.replace("-", "").startswith(prefix):
                matches.append(item)
        return matches

    def get_by_id(self, display_id: str) -> List[BacklogItem]:
        return self.items_by_id.get(display_id, [])
    
    def get_collisions(self) -> Dict[str, List[BacklogItem]]:
        collisions = {}
        for did, items in self.items_by_id.items():
            if len(items) > 1:
                collisions[did] = items
        return collisions
