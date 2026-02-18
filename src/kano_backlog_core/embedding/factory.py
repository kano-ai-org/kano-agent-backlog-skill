from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict

from .adapter import EmbeddingAdapter
from .noop import NoOpEmbeddingAdapter


def resolve_embedder(config: Dict[str, Any]) -> EmbeddingAdapter:
    """Resolve embedding adapter from configuration."""

    def resolve_env_ref(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        s = value.strip()
        if not s.startswith("env:"):
            return value
        var = s[len("env:") :].strip()
        if not var:
            raise ValueError("Invalid env reference: 'env:' must include a variable name")
        resolved = os.environ.get(var)
        if resolved is None or not resolved.strip():
            raise ValueError(f"Missing env var for secret reference: {var}")
        return resolved

    provider = str(config.get("provider", "noop")).strip().lower()
    model_name = str(config.get("model", "noop-embedding")).strip()

    if provider == "noop":
        dimension = int(config.get("dimension", 1536))
        return NoOpEmbeddingAdapter(model_name=model_name, dimension=dimension)

    if provider == "openai":
        api_key = resolve_env_ref(config.get("api_key"))
        base_url = resolve_env_ref(config.get("base_url"))
        dimension = config.get("dimension")
        try:
            from .openai_adapter import OpenAIEmbeddingAdapter

            return OpenAIEmbeddingAdapter(
                model_name=model_name, 
                api_key=api_key,
                base_url=base_url,
                dimension=dimension
            )
        except ImportError as e:
            raise ValueError(f"OpenAI adapter not available: {e}")

    if provider in {"gemini", "google", "google-genai", "genai"}:
        module_name = "google.genai"
        try:
            has_genai = importlib.util.find_spec(module_name) is not None
        except ModuleNotFoundError:
            has_genai = False

        if not has_genai:
            raise ValueError(
                "google-genai adapter not available. Install with: pip install google-genai"
            )

        from .gemini_adapter import GeminiEmbeddingAdapter

        options = config.get("options")
        if isinstance(options, dict):
            merged = dict(options)
        else:
            merged = {}

        api_key = resolve_env_ref(config.get("api_key") or merged.get("api_key"))
        output_dimensionality = (
            config.get("output_dimensionality")
            if "output_dimensionality" in config
            else merged.get("output_dimensionality")
        )
        task_type = (
            config.get("task_type") if "task_type" in config else merged.get("task_type")
        )
        dimension = config.get("dimension")

        return GeminiEmbeddingAdapter(
            model_name=model_name,
            api_key=api_key,
            output_dimensionality=output_dimensionality,
            task_type=task_type,
            dimension=dimension,
        )

    if provider in {"sentence-transformers", "sentence_transformers", "huggingface"}:
        # Optional dependency gate: do not download a model here, but ensure the
        # library is available so config validation can fail fast.
        module_name = "sentence" + "_" + "transformers"
        if importlib.util.find_spec(module_name) is None:
            raise ValueError(
                "sentence-transformers adapter not available. Install with: pip install sentence-transformers"
            )

        from .sentence_transformers_adapter import SentenceTransformersEmbeddingAdapter

        dimension = int(config.get("dimension", 0) or 0)
        options = config.get("options")
        if isinstance(options, dict):
            # allow options nested under [embedding.options] as well as top-level
            merged = dict(options)
        else:
            merged = {}

        device = config.get("device") or merged.get("device")
        batch_size = int(config.get("batch_size") or merged.get("batch_size") or 32)
        normalize_embeddings = bool(
            config.get("normalize_embeddings")
            if "normalize_embeddings" in config
            else merged.get("normalize_embeddings", False)
        )
        max_seq_length = config.get("max_seq_length")
        if max_seq_length is None:
            max_seq_length = merged.get("max_seq_length")

        return SentenceTransformersEmbeddingAdapter(
            model_name=model_name,
            dimension=dimension,
            device=str(device) if device is not None else None,
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
            max_seq_length=int(max_seq_length) if max_seq_length is not None else None,
        )

    raise ValueError(f"Unknown embedding provider: {provider}")

