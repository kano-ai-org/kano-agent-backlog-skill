from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from .types import VectorChunk, VectorQueryResult


class VectorBackendAdapter(ABC):
    """Abstract base class for vector store backends."""

    @abstractmethod
    def prepare(self, schema: Dict[str, Any], dims: int, metric: str = "cosine") -> None:
        """
        Prepare the index (create if not exists).

        Args:
            schema: Schema definition (backend-specific).
            dims: Vector dimensions.
            metric: Distance metric ('cosine', 'l2', 'ip').
        """
        pass

    @abstractmethod
    def upsert(self, chunk: VectorChunk) -> None:
        """Insert or update a chunk vector."""
        pass

    @abstractmethod
    def delete(self, chunk_id: str) -> None:
        """Delete a chunk by ID."""
        pass

    @abstractmethod
    def query(
        self, vector: List[float], k: int = 10, filters: Dict[str, Any] | None = None
    ) -> List[VectorQueryResult]:
        """
        Query for similar vectors.

        Args:
            vector: Query vector.
            k: Number of results to return.
            filters: Metadata filters (backend-specific syntax).
        """
        pass

    @abstractmethod
    def persist(self) -> None:
        """Persist in-memory state to disk (if applicable)."""
        pass

    @abstractmethod
    def load(self) -> None:
        """Load state from disk."""
        pass
