
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
    product: str
    frontmatter: Dict

class BacklogIndex:
    def __init__(self, backlog_root: Path):
        self.root = backlog_root
        self.items_by_uid: Dict[str, BacklogItem] = {}
        self.items_by_id: Dict[str, List[BacklogItem]] = {}
        self.items_by_uidshort: Dict[str, List[BacklogItem]] = {}
        self._scan()

    def _scan(self):
        # 1. Try loading from SQLite
        db_path = self.root / "_index" / "backlog.sqlite3"
        if db_path.exists():
            try:
                self._load_from_db(db_path)
                return
            except Exception as e:
                print(f"Warning: DB load failed, falling back to file scan: {e}")
        
        # 2. Fallback to File Scan
        self._scan_files()

    def _load_from_db(self, db_path: Path):
        import sqlite3
        import json
        
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        try:
            cur.execute("SELECT uid, id, type, title, state, source_path, created, updated, product, frontmatter_json FROM items")
            for row in cur.fetchall():
                uid, did, type_, title, state, rel_path, created, updated, product, fm_json = row
                
                fm = {}
                if fm_json:
                    try:
                        fm = json.loads(fm_json)
                    except json.JSONDecodeError:
                        pass
                
                # Reconstruct item
                # Ensure path is absolute for tool consistency
                full_path = self.root.parent.parent / rel_path # root is _kano/backlog, repo is parent.parent?
                # Wait, rel_path in DB is relative to REPO ROOT.
                # self.root is usually _kano/backlog.
                # If index_db.py stores path relative to repo root (e.g. _kano/backlog/items/...).
                # And self.root is e.g. D:/.../_kano/backlog
                # Then we need to know repo root.
                # Assuming standard layout: repo_root = self.root.parent.parent
                
                # Check if self.root is absolute. 
                # Better: resolve relative to cwd? 
                # index_db.py uses: rel_path = f.relative_to(repo_root).as_posix()
                # Here we need to reconstruct full path.
                
                # Attempt to find repo root from self.root
                # If self.root ends with _kano/backlog, walk up.
                repo_root = self.root
                if self.root.name == "backlog" and self.root.parent.name == "_kano":
                    repo_root = self.root.parent.parent
                
                item_path = repo_root / rel_path
                
                uidshort = uid.replace("-", "")[:8] if uid else ""
                
                item = BacklogItem(
                    uid=uid,
                    id=did,
                    uidshort=uidshort,
                    type=type_,
                    title=title,
                    state=state,
                    path=item_path,
                    created=created,
                    updated=updated,
                    product=product or "kano-agent-backlog-skill",
                    frontmatter=fm
                )
                self._add_to_index(item)
        finally:
            conn.close()

    def _scan_files(self):
        items_dir = self.root / "items"
        if not items_dir.exists():
            return
            
        for f in items_dir.rglob("*.md"):
            try:
                content = f.read_text(encoding="utf-8")
                fm, _, _ = parse_frontmatter(content)
                
                if not fm or 'id' not in fm:
                    continue
                
                uid = fm.get('uid', '')
                uidshort = uid.replace("-", "")[:8] if uid else ""
                
                # Extract product from path
                product = self._extract_product_from_path(f)
                
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
                    product=product,
                    frontmatter=fm
                )
                self._add_to_index(item)
                
            except Exception as e:
                print(f"Warning: Failed to index {f}: {e}")

    def _add_to_index(self, item: BacklogItem):
        # Index by UID
        if item.uid:
            self.items_by_uid[item.uid] = item
        
        # Index by UID Short
        if item.uidshort:
            if item.uidshort not in self.items_by_uidshort:
                self.items_by_uidshort[item.uidshort] = []
            self.items_by_uidshort[item.uidshort].append(item)
            
        # Index by Display ID
        did = item.id
        if did not in self.items_by_id:
            self.items_by_id[did] = []
        self.items_by_id[did].append(item)

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

    def get_by_id(self, display_id: str, product: Optional[str] = None) -> List[BacklogItem]:
        items = self.items_by_id.get(display_id, [])
        if product:
            return [item for item in items if item.product == product]
        return items
    
    def get_collisions(self) -> Dict[str, List[BacklogItem]]:
        collisions = {}
        for did, items in self.items_by_id.items():
            if len(items) > 1:
                collisions[did] = items
        return collisions
    
    def _extract_product_from_path(self, path: Path) -> str:
        """Extract product name from file path.
        
        Handles three path patterns:
        - products/<product-name>/items/...  → product-name
        - sandboxes/<product-name>/items/... → product-name
        - items/...                          → kano-agent-backlog-skill (legacy)
        """
        parts = path.parts
        for i, part in enumerate(parts):
            if part == "products" and i + 1 < len(parts):
                return parts[i + 1]
            elif part == "sandboxes" and i + 1 < len(parts):
                return parts[i + 1]
        # Legacy: items/ without products/ or sandboxes/ prefix
        return "kano-agent-backlog-skill"
