import hashlib
import time
from typing import List

from ..tokenizer import TokenCount
from .adapter import EmbeddingAdapter
from .types import EmbeddingResult, EmbeddingTelemetry


class NoOpEmbeddingAdapter(EmbeddingAdapter):
    """Deterministic NoOp adapter for testing.

    It generates a pseudo-vector based on sha256(text), so it is stable across
    platforms as long as UTF-8 encoding is used.
    """

    def __init__(self, model_name: str = "noop-embedding", dimension: int = 1536):
        super().__init__(model_name)
        self._dimension = dimension

    def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        results: List[EmbeddingResult] = []
        for text in texts:
            t0 = time.perf_counter()

            h = hashlib.sha256(text.encode("utf-8")).digest()
            vector: List[float] = []
            for i in range(self._dimension):
                b = h[i % len(h)]
                vector.append((b / 255.0) * 2 - 1)

            duration_ms = (time.perf_counter() - t0) * 1000

            token_count_est = len(text) // 4
            telemetry = EmbeddingTelemetry(
                provider_id="noop",
                model_name=self.model_name,
                dimension=self._dimension,
                token_count=TokenCount(
                    count=token_count_est,
                    method="heuristic",
                    tokenizer_id=f"heuristic:{self.model_name}",
                    is_exact=False,
                ),
                max_tokens=8192,
                target_budget=8192,
                safety_margin=0,
                duration_ms=duration_ms,
                trimmed=False,
                warnings=None,
            )
            results.append(EmbeddingResult(vector=vector, telemetry=telemetry))

        return results

