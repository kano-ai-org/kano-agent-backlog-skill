from __future__ import annotations

import importlib
import time
from typing import Any, List, Optional

from ..tokenizer import TokenCount
from .adapter import EmbeddingAdapter
from .types import EmbeddingResult, EmbeddingTelemetry


class SentenceTransformersEmbeddingAdapter(EmbeddingAdapter):
    """Embedding adapter using sentence-transformers (local, optional dependency)."""

    def __init__(
        self,
        *,
        model_name: str,
        dimension: int,
        device: Optional[str] = None,
        batch_size: int = 32,
        normalize_embeddings: bool = False,
        max_seq_length: Optional[int] = None,
    ) -> None:
        super().__init__(model_name)

        if dimension <= 0:
            raise ValueError("dimension must be > 0")
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")

        self._dimension = int(dimension)
        self._device = device
        self._batch_size = int(batch_size)
        self._normalize_embeddings = bool(normalize_embeddings)
        self._max_seq_length = int(max_seq_length) if max_seq_length is not None else None

        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            module_name = "sentence" + "_" + "transformers"
            mod = importlib.import_module(module_name)
            SentenceTransformer = getattr(mod, "SentenceTransformer")
        except Exception as e:
            raise ImportError(
                "sentence-transformers is required for local embeddings. "
                "Install with: pip install sentence-transformers"
            ) from e

        kwargs: dict[str, Any] = {}
        if self._device:
            kwargs["device"] = self._device

        model = SentenceTransformer(self.model_name, **kwargs)
        if self._max_seq_length is not None:
            # sentence-transformers exposes max_seq_length on the model wrapper.
            model.max_seq_length = self._max_seq_length

        # Validate dimension matches the underlying model.
        dim = int(model.get_sentence_embedding_dimension())
        if dim != self._dimension:
            raise ValueError(
                f"Configured embedding.dimension={self._dimension} does not match "
                f"model dimension={dim} for model={self.model_name!r}"
            )

        self._model = model
        return model

    def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        model = self._ensure_model()

        t0 = time.perf_counter()
        vectors = model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            normalize_embeddings=self._normalize_embeddings,
        )
        duration_ms = (time.perf_counter() - t0) * 1000

        # vectors may be a numpy array; we avoid importing numpy directly.
        n = max(1, len(texts))
        per_item_ms = duration_ms / n

        results: List[EmbeddingResult] = []
        max_tokens = int(getattr(model, "max_seq_length", 512) or 512)

        for idx, text in enumerate(texts):
            vec_any = vectors[idx]
            vector: List[float]
            if hasattr(vec_any, "tolist"):
                vector = vec_any.tolist()
            else:
                vector = list(vec_any)

            token_count_est = len(text) // 4
            telemetry = EmbeddingTelemetry(
                provider_id="sentence-transformers",
                model_name=self.model_name,
                dimension=self._dimension,
                token_count=TokenCount(
                    count=token_count_est,
                    method="heuristic",
                    tokenizer_id=f"heuristic:{self.model_name}",
                    is_exact=False,
                ),
                max_tokens=max_tokens,
                target_budget=max_tokens,
                safety_margin=0,
                duration_ms=per_item_ms,
                trimmed=False,
                warnings=None,
            )
            results.append(EmbeddingResult(vector=vector, telemetry=telemetry))

        return results
