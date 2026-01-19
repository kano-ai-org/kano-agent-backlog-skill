from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .types import EmbeddingResult


class EmbeddingAdapter(ABC):
    """Abstract base class for embedding providers."""

    def __init__(self, model_name: str):
        if not model_name:
            raise ValueError("model_name must be non-empty")
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for a batch of texts."""
        raise NotImplementedError

