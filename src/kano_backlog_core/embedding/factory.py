from __future__ import annotations

from typing import Any, Dict

from .adapter import EmbeddingAdapter
from .noop import NoOpEmbeddingAdapter


def resolve_embedder(config: Dict[str, Any]) -> EmbeddingAdapter:
    """Resolve embedding adapter from configuration."""

    provider = str(config.get("provider", "noop")).strip().lower()
    model_name = str(config.get("model", "noop-embedding")).strip()

    if provider == "noop":
        dimension = int(config.get("dimension", 1536))
        return NoOpEmbeddingAdapter(model_name=model_name, dimension=dimension)

    if provider == "openai":
        api_key = config.get("api_key")
        try:
            from .openai_adapter import OpenAIEmbeddingAdapter

            return OpenAIEmbeddingAdapter(model_name=model_name, api_key=api_key)
        except ImportError as e:
            raise ValueError(f"OpenAI adapter not available: {e}")

    raise ValueError(f"Unknown embedding provider: {provider}")

