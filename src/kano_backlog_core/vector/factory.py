from __future__ import annotations

from typing import Any, Dict

from .adapter import VectorBackendAdapter


class NoOpBackend(VectorBackendAdapter):
    """A no-op backend for testing or default initialization."""

    def prepare(self, schema: Dict[str, Any], dims: int, metric: str = "cosine") -> None:
        pass

    def upsert(self, chunk: Any) -> None:
        pass

    def delete(self, chunk_id: str) -> None:
        pass

    def query(
        self, vector: Any, k: int = 10, filters: Dict[str, Any] | None = None
    ) -> Any:
        return []

    def persist(self) -> None:
        pass

    def load(self) -> None:
        pass


def get_backend(config: Dict[str, Any]) -> VectorBackendAdapter:
    """Factory for vector backends."""
    backend_type = config.get("backend", "noop").lower()
    
    if backend_type == "noop":
        return NoOpBackend()
    
    if backend_type == "sqlite":
        path = config.get("path", ".kano/vector/index.db")
        collection = config.get("collection", "backlog")
        from .sqlite_backend import SQLiteVectorBackend
        return SQLiteVectorBackend(path=path, collection=collection)
    
    raise ValueError(f"Unknown vector backend: {backend_type}")
