"""Derived store for querying backlog items (read-only index operations)."""

from abc import ABC, abstractmethod
import subprocess
from typing import List, Optional, Dict, Any
from pathlib import Path
from enum import Enum

from .canonical import CanonicalStore
from .models import BacklogItem, ItemType, ItemState


def get_git_sha(path: Path) -> Optional[str]:
    """Get current git HEAD SHA for the given path."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


class QueryFilter:
    """Filter criteria for item queries."""

    def __init__(
        self,
        item_type: Optional[ItemType] = None,
        state: Optional[ItemState] = None,
        owner: Optional[str] = None,
        tags: Optional[List[str]] = None,
        area: Optional[str] = None,
        iteration: Optional[str] = None,
        priority: Optional[str] = None,
        parent: Optional[str] = None,
    ):
        """Initialize filter criteria."""
        self.item_type = item_type
        self.state = state
        self.owner = owner
        self.tags = tags or []
        self.area = area
        self.iteration = iteration
        self.priority = priority
        self.parent = parent

    def matches(self, item: BacklogItem) -> bool:
        """Check if item matches all filter criteria."""
        if self.item_type and item.type != self.item_type:
            return False
        if self.state and item.state != self.state:
            return False
        if self.owner and item.owner != self.owner:
            return False
        if self.tags and not any(tag in item.tags for tag in self.tags):
            return False
        if self.area and item.area != self.area:
            return False
        if self.iteration and item.iteration != self.iteration:
            return False
        if self.priority and item.priority != self.priority:
            return False
        if self.parent and item.parent != self.parent:
            return False
        return True


class DerivedStore(ABC):
    """Abstract base for querying backlog items (read-only)."""

    @abstractmethod
    def list_items(self, filters: Optional[QueryFilter] = None) -> List[BacklogItem]:
        """
        List items optionally filtered.

        Args:
            filters: QueryFilter with criteria

        Returns:
            List of matching BacklogItem objects
        """
        pass

    @abstractmethod
    def get_by_id(self, display_id: str) -> Optional[BacklogItem]:
        """Get item by display ID (e.g., KABSD-TSK-0001)."""
        pass

    @abstractmethod
    def get_by_uid(self, uid: str) -> Optional[BacklogItem]:
        """Get item by UUIDv7."""
        pass

    @abstractmethod
    def search(self, query: str) -> List[BacklogItem]:
        """Search items by title/context/goal (substring match)."""
        pass

    @abstractmethod
    def get_by_state(self, state: ItemState) -> List[BacklogItem]:
        """Get all items in a specific state."""
        pass

    @abstractmethod
    def get_by_owner(self, owner: str) -> List[BacklogItem]:
        """Get all items owned by a specific person/agent."""
        pass

    @abstractmethod
    def get_children(self, parent_id: str) -> List[BacklogItem]:
        """Get all items with a specific parent."""
        pass

    @abstractmethod
    def get_by_tags(self, tags: List[str]) -> List[BacklogItem]:
        """Get items matching any of the given tags."""
        pass


class InMemoryDerivedStore(DerivedStore):
    """
    In-memory derived store (MVP).

    Loads all items from canonical storage into memory for fast queries.
    Suitable for small to medium backlogs (<5000 items).
    """

    def __init__(self, canonical: CanonicalStore):
        """
        Initialize in-memory store.

        Args:
            canonical: CanonicalStore instance to load items from
        """
        self.canonical = canonical
        self._items: List[BacklogItem] = []
        self._by_id: Dict[str, BacklogItem] = {}
        self._by_uid: Dict[str, BacklogItem] = {}
        self._reload()

    def _reload(self) -> None:
        """Reload all items from canonical storage."""
        self._items = []
        self._by_id = {}
        self._by_uid = {}

        # Load all items from canonical
        for item_path in self.canonical.list_items():
            try:
                item = self.canonical.read(item_path)
                self._items.append(item)
                self._by_id[item.id] = item
                self._by_uid[item.uid] = item
            except Exception:
                # Skip items that fail to parse
                pass

    def refresh(self) -> None:
        """Manually refresh items from disk."""
        self._reload()

    def list_items(self, filters: Optional[QueryFilter] = None) -> List[BacklogItem]:
        """List items optionally filtered."""
        if filters is None:
            return self._items.copy()

        return [item for item in self._items if filters.matches(item)]

    def get_by_id(self, display_id: str) -> Optional[BacklogItem]:
        """Get item by display ID."""
        return self._by_id.get(display_id)

    def get_by_uid(self, uid: str) -> Optional[BacklogItem]:
        """Get item by UUIDv7."""
        return self._by_uid.get(uid)

    def search(self, query: str) -> List[BacklogItem]:
        """Search items by title/context/goal (case-insensitive substring)."""
        query_lower = query.lower()
        results = []
        for item in self._items:
            if query_lower in item.title.lower():
                results.append(item)
            elif item.context and query_lower in item.context.lower():
                results.append(item)
            elif item.goal and query_lower in item.goal.lower():
                results.append(item)
        return results

    def get_by_state(self, state: ItemState) -> List[BacklogItem]:
        """Get all items in a specific state."""
        return [item for item in self._items if item.state == state]

    def get_by_owner(self, owner: str) -> List[BacklogItem]:
        """Get all items owned by a specific person/agent."""
        return [item for item in self._items if item.owner == owner]

    def get_children(self, parent_id: str) -> List[BacklogItem]:
        """Get all items with a specific parent."""
        return [item for item in self._items if item.parent == parent_id]

    def get_by_tags(self, tags: List[str]) -> List[BacklogItem]:
        """Get items matching any of the given tags."""
        results = []
        for item in self._items:
            if any(tag in item.tags for tag in tags):
                results.append(item)
        return results

    def stats(self) -> Dict[str, Any]:
        """Return statistics about loaded items."""
        items_by_state = {}
        for state in ItemState:
            items_by_state[state.value] = len(self.get_by_state(state))

        items_by_type = {}
        for item_type in ItemType:
            items_by_type[item_type.value] = len(
                self.list_items(QueryFilter(item_type=item_type))
            )

        return {
            "total_items": len(self._items),
            "by_state": items_by_state,
            "by_type": items_by_type,
            "by_owner": self._count_by_owner(),
        }

    def _count_by_owner(self) -> Dict[str, int]:
        """Count items by owner."""
        counts = {}
        for item in self._items:
            if item.owner:
                counts[item.owner] = counts.get(item.owner, 0) + 1
        return counts
