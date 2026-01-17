"""Token-budget fitting and trimming policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .chunking import ChunkingOptions, build_chunk_id, chunk_text, token_spans
from .tokenizer import TokenCount, TokenizerAdapter


@dataclass(frozen=True)
class TokenBudgetPolicy:
    """Policy for enforcing token budgets."""

    safety_margin_ratio: float = 0.05
    safety_margin_min_tokens: int = 16

    def __post_init__(self) -> None:
        if self.safety_margin_ratio < 0:
            raise ValueError("safety_margin_ratio must be >= 0")
        if self.safety_margin_min_tokens < 0:
            raise ValueError("safety_margin_min_tokens must be >= 0")


@dataclass(frozen=True)
class TokenBudgetResult:
    """Result of enforcing a token budget."""

    content: str
    token_count: TokenCount
    trimmed: bool
    target_budget: int
    safety_margin: int


@dataclass(frozen=True)
class BudgetedChunk:
    """Chunk with enforced token budget metadata."""

    source_id: str
    start_char: int
    end_char: int
    text: str
    chunk_id: str
    token_count: TokenCount
    trimmed: bool
    target_budget: int
    safety_margin: int


def enforce_token_budget(
    text: str,
    tokenizer: TokenizerAdapter,
    max_tokens: Optional[int] = None,
    policy: Optional[TokenBudgetPolicy] = None,
) -> TokenBudgetResult:
    """Enforce token budget with deterministic tail trimming.

    Args:
        text: Raw input text.
        tokenizer: Tokenizer adapter to count tokens.
        max_tokens: Optional max tokens override.
        policy: Optional policy override.

    Returns:
        TokenBudgetResult with trimmed content and counts.
    """
    if policy is None:
        policy = TokenBudgetPolicy()

    budget = max_tokens if max_tokens is not None else tokenizer.max_tokens()
    if budget <= 0:
        raise ValueError("max_tokens must be positive")

    safety_margin = max(int(budget * policy.safety_margin_ratio), policy.safety_margin_min_tokens)
    target_budget = max(1, budget - safety_margin)

    token_count = tokenizer.count_tokens(text)
    if token_count.count <= target_budget:
        return TokenBudgetResult(
            content=text,
            token_count=token_count,
            trimmed=False,
            target_budget=target_budget,
            safety_margin=safety_margin,
        )

    trimmed_text, trimmed_count = _trim_to_budget(text, tokenizer, target_budget)
    return TokenBudgetResult(
        content=trimmed_text,
        token_count=trimmed_count,
        trimmed=True,
        target_budget=target_budget,
        safety_margin=safety_margin,
    )


def budget_chunks(
    source_id: str,
    text: str,
    options: ChunkingOptions,
    tokenizer: TokenizerAdapter,
    max_tokens: Optional[int] = None,
    policy: Optional[TokenBudgetPolicy] = None,
) -> List[BudgetedChunk]:
    """Chunk text and enforce token budgets for each chunk."""
    chunks = chunk_text(source_id, text, options)
    budgeted: List[BudgetedChunk] = []
    for chunk in chunks:
        result = enforce_token_budget(
            chunk.text,
            tokenizer,
            max_tokens=max_tokens,
            policy=policy,
        )
        end_char = chunk.start_char + len(result.content)
        chunk_id = build_chunk_id(
            source_id=source_id,
            version=options.version,
            start_char=chunk.start_char,
            end_char=end_char,
            span_text=result.content,
        )
        budgeted.append(
            BudgetedChunk(
                source_id=source_id,
                start_char=chunk.start_char,
                end_char=end_char,
                text=result.content,
                chunk_id=chunk_id,
                token_count=result.token_count,
                trimmed=result.trimmed,
                target_budget=result.target_budget,
                safety_margin=result.safety_margin,
            )
        )
    return budgeted


def _trim_to_budget(
    text: str, tokenizer: TokenizerAdapter, target_budget: int
) -> Tuple[str, TokenCount]:
    spans = token_spans(text)
    if not spans:
        empty_count = tokenizer.count_tokens(text)
        return text, empty_count

    if target_budget <= 0:
        target_budget = 1

    target_index = min(target_budget, len(spans)) - 1
    end_char = spans[target_index][1]
    candidate = text[:end_char]
    candidate_count = tokenizer.count_tokens(candidate)
    if candidate_count.count <= target_budget:
        return candidate, candidate_count

    return _binary_search_prefix(text, tokenizer, target_budget)


def _binary_search_prefix(
    text: str, tokenizer: TokenizerAdapter, target_budget: int
) -> Tuple[str, TokenCount]:
    low = 1
    high = len(text)
    best_text = text[:1]
    best_count = tokenizer.count_tokens(best_text)

    while low <= high:
        mid = (low + high) // 2
        candidate = text[:mid]
        candidate_count = tokenizer.count_tokens(candidate)
        if candidate_count.count <= target_budget:
            best_text = candidate
            best_count = candidate_count
            low = mid + 1
        else:
            high = mid - 1

    return best_text, best_count
