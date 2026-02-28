from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class VectorChunk:
    """Represents a chunk of text with its embedding and metadata."""

    chunk_id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    vector: List[float] | None = None  # Vector might be computed later


@dataclass
class VectorQueryResult:
    """Represents a result from a vector similarity search."""

    chunk_id: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    text: str | None = None  # Optional, might be fetched separately
