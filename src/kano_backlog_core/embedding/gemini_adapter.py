"""Gemini embedding adapter implementation."""

# pyright: reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false

from typing import Any, List, Optional
import importlib
import time

from ..tokenizer import TokenCount, resolve_model_max_tokens
from .adapter import EmbeddingAdapter
from .types import EmbeddingResult, EmbeddingTelemetry


class GeminiEmbeddingAdapter(EmbeddingAdapter):
    """Embedding adapter for the Google Gemini embedding API (google-genai)."""

    def __init__(
        self,
        model_name: str = "gemini-embedding-001",
        api_key: Optional[str] = None,
        output_dimensionality: Optional[int] = None,
        task_type: Optional[str] = None,
        dimension: Optional[int] = None,
    ) -> None:
        super().__init__(model_name)

        if output_dimensionality is not None and int(output_dimensionality) <= 0:
            raise ValueError("output_dimensionality must be > 0")
        if dimension is not None and int(dimension) <= 0:
            raise ValueError("dimension must be > 0")

        self._api_key = api_key
        self._output_dimensionality = (
            int(output_dimensionality) if output_dimensionality is not None else None
        )
        self._task_type = task_type.strip() if isinstance(task_type, str) else None
        self._dimension = int(dimension) if dimension is not None else None

        self._client: Optional[Any] = None
        self._genai_types: Optional[Any] = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return

        try:
            genai_module = importlib.import_module("google.genai")
            genai_types = importlib.import_module("google.genai.types")
        except Exception as e:
            raise ImportError(
                "google-genai package required for Gemini embeddings. "
                "Install with: pip install google-genai"
            ) from e

        client_factory = getattr(genai_module, "Client", None)
        if client_factory is None:
            raise ImportError("google-genai client is missing Client")

        if self._api_key:
            self._client = client_factory(api_key=self._api_key)
        else:
            self._client = client_factory()

        self._genai_types = genai_types

    def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        self._ensure_client()

        t0 = time.perf_counter()

        client = self._client
        genai_types = self._genai_types
        if client is None or genai_types is None:
            raise RuntimeError("Gemini client is not initialized")

        assert client is not None
        assert genai_types is not None

        config = None
        if self._output_dimensionality is not None or self._task_type is not None:
            config_kwargs = {}
            if self._output_dimensionality is not None:
                config_kwargs["output_dimensionality"] = self._output_dimensionality
            if self._task_type is not None:
                config_kwargs["task_type"] = self._task_type
            config_factory = getattr(genai_types, "EmbedContentConfig", None)
            if config_factory is None:
                raise RuntimeError("Gemini client is missing EmbedContentConfig")
            config = config_factory(**config_kwargs)

        try:
            models = getattr(client, "models", None)
            if models is None:
                raise RuntimeError("Gemini client is missing models")
            embed_content = getattr(models, "embed_content", None)
            if embed_content is None:
                raise RuntimeError("Gemini client is missing embed_content")

            if config is None:
                response = embed_content(model=self.model_name, contents=texts)
            else:
                response = embed_content(
                    model=self.model_name,
                    contents=texts,
                    config=config,
                )
        except Exception as e:
            raise RuntimeError(f"Gemini embedding failed: {e}")

        duration_ms = (time.perf_counter() - t0) * 1000

        embeddings = getattr(response, "embeddings", None)
        if embeddings is None:
            raise RuntimeError("Gemini embedding failed: missing embeddings in response")
        if len(embeddings) != len(texts):
            raise RuntimeError(
                "Gemini embedding failed: embeddings count does not match input"
            )

        results: List[EmbeddingResult] = []
        max_tokens = resolve_model_max_tokens(self.model_name)
        per_item_ms = duration_ms / max(1, len(texts))

        for idx, embedding_data in enumerate(embeddings):
            values = getattr(embedding_data, "values", None)
            if values is None:
                raise RuntimeError("Gemini embedding failed: missing values")

            vector = list(values)
            dimension = len(vector)
            if self._dimension is not None and dimension != self._dimension:
                raise ValueError(
                    f"Configured embedding.dimension={self._dimension} does not match "
                    f"response dimension={dimension} for model={self.model_name!r}"
                )

            token_count_est = len(texts[idx]) // 4
            telemetry = EmbeddingTelemetry(
                provider_id="gemini",
                model_name=self.model_name,
                dimension=dimension,
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
