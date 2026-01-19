from dataclasses import dataclass
from typing import List, Optional

from ..tokenizer import TokenCount


@dataclass(frozen=True)
class EmbeddingTelemetry:
    """Telemetry data for an embedding operation.

    Notes:
    - token_count should represent the tokens for the actual embedded text.
    - max_tokens/target_budget/safety_margin reflect the embedding window policy.
    """

    provider_id: str
    model_name: str
    dimension: int
    token_count: TokenCount
    max_tokens: int
    target_budget: int
    safety_margin: int
    duration_ms: float = 0.0
    trimmed: bool = False
    warnings: Optional[List[str]] = None


@dataclass(frozen=True)
class EmbeddingResult:
    """Result of an embedding operation for a single text chunk."""

    vector: List[float]
    telemetry: EmbeddingTelemetry

