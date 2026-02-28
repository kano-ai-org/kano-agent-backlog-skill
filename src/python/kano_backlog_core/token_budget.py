"""Token-budget fitting and trimming policy."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .chunking import ChunkingOptions, build_chunk_id, chunk_text, token_spans
from .tokenizer import TokenCount, TokenizerAdapter

logger = logging.getLogger(__name__)


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
class BudgetResult:
    """Result of token budget application."""
    text: str
    token_count: TokenCount
    was_trimmed: bool
    original_token_count: int


class TokenBudgetManager:
    """Manages token budgets with safety margins and trimming."""
    
    def __init__(self, options: ChunkingOptions, tokenizer: TokenizerAdapter):
        """Initialize token budget manager.
        
        Args:
            options: Chunking configuration with token limits
            tokenizer: Tokenizer adapter for counting tokens
        """
        self.options = options
        self.tokenizer = tokenizer
        
        # Calculate effective max tokens with safety margin
        safety_margin = max(
            int(options.max_tokens * 0.1),  # 10% safety margin
            16  # Minimum 16 tokens safety margin
        )
        self.effective_max = max(1, options.max_tokens - safety_margin)
        self.safety_margin = safety_margin
        
        logger.debug(
            f"TokenBudgetManager initialized: max_tokens={options.max_tokens}, "
            f"effective_max={self.effective_max}, safety_margin={safety_margin}"
        )
    
    def apply_budget(self, text: str) -> BudgetResult:
        """Apply token budget with trimming if necessary.
        
        Args:
            text: Input text to apply budget to
            
        Returns:
            BudgetResult with potentially trimmed text and metadata
        """
        if not text:
            empty_count = self.tokenizer.count_tokens("")
            return BudgetResult(
                text="",
                token_count=empty_count,
                was_trimmed=False,
                original_token_count=0
            )
        
        original_count = self.tokenizer.count_tokens(text)
        
        if original_count.count <= self.effective_max:
            return BudgetResult(
                text=text,
                token_count=original_count,
                was_trimmed=False,
                original_token_count=original_count.count
            )
        
        # Apply deterministic trimming policy
        trimmed_text = self._trim_to_budget(text, self.effective_max)
        trimmed_count = self.tokenizer.count_tokens(trimmed_text)
        
        logger.debug(
            f"Applied token budget: original={original_count.count}, "
            f"trimmed={trimmed_count.count}, target={self.effective_max}"
        )
        
        return BudgetResult(
            text=trimmed_text,
            token_count=trimmed_count,
            was_trimmed=True,
            original_token_count=original_count.count
        )
    
    def _trim_to_budget(self, text: str, max_tokens: int) -> str:
        """Trim text to fit within token budget using binary search.
        
        This implements a deterministic tail-first trimming policy:
        1. Try to preserve complete sentences/paragraphs when possible
        2. Use binary search for efficient trimming
        3. Always make forward progress (never return empty string for non-empty input)
        
        Args:
            text: Text to trim
            max_tokens: Maximum allowed tokens
            
        Returns:
            Trimmed text that fits within budget
        """
        if max_tokens <= 0:
            # Edge case: if budget is 0 or negative, return minimal text
            return text[:1] if text else ""
        
        # First try token-span based trimming for better boundary detection
        spans = token_spans(text)
        if spans and len(spans) > max_tokens:
            # Use token spans to find a good cut point
            target_span_index = min(max_tokens - 1, len(spans) - 1)
            if target_span_index >= 0:
                end_char = spans[target_span_index][1]
                candidate = text[:end_char]
                candidate_count = self.tokenizer.count_tokens(candidate)
                if candidate_count.count <= max_tokens:
                    return candidate
        
        # Fall back to binary search for precise trimming
        return self._binary_search_trim(text, max_tokens)
    
    def _binary_search_trim(self, text: str, max_tokens: int) -> str:
        """Use binary search to find optimal trim point.
        
        Args:
            text: Text to trim
            max_tokens: Maximum allowed tokens
            
        Returns:
            Trimmed text that fits within budget
        """
        if not text:
            return text
        
        # Binary search on character positions
        left, right = 1, len(text)  # Start from 1 to ensure progress
        best_text = text[:1]  # Ensure we always return at least one character
        best_count = self.tokenizer.count_tokens(best_text)
        
        # If even one character exceeds budget, return it anyway (progress guarantee)
        if best_count.count > max_tokens:
            logger.warning(
                f"Single character exceeds token budget: {best_count.count} > {max_tokens}"
            )
            return best_text
        
        while left <= right:
            mid = (left + right) // 2
            candidate = text[:mid]
            candidate_count = self.tokenizer.count_tokens(candidate)
            
            if candidate_count.count <= max_tokens:
                # This candidate fits, try for a longer one
                best_text = candidate
                best_count = candidate_count
                left = mid + 1
            else:
                # This candidate is too long, try shorter
                right = mid - 1
        
        logger.debug(
            f"Binary search trim: original_length={len(text)}, "
            f"trimmed_length={len(best_text)}, tokens={best_count.count}/{max_tokens}"
        )
        
        return best_text
    
    def validate_budget_compliance(self, text: str) -> bool:
        """Validate that text complies with token budget.
        
        Args:
            text: Text to validate
            
        Returns:
            True if text fits within effective token budget
        """
        if not text:
            return True
        
        token_count = self.tokenizer.count_tokens(text)
        return token_count.count <= self.effective_max
    
    def get_budget_info(self) -> dict:
        """Get information about current budget configuration.
        
        Returns:
            Dictionary with budget configuration details
        """
        return {
            "max_tokens": self.options.max_tokens,
            "effective_max": self.effective_max,
            "safety_margin": self.safety_margin,
            "target_tokens": self.options.target_tokens,
            "tokenizer_id": self.tokenizer.adapter_id,
            "model_name": self.tokenizer.model_name
        }


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


@dataclass(frozen=True)
class TokenBudgetResult:
    """Result of enforcing a token budget (legacy interface)."""

    content: str
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
    """Enforce token budget with deterministic tail trimming (legacy interface).

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

    # Create a temporary ChunkingOptions for the TokenBudgetManager
    from .chunking import ChunkingOptions
    temp_options = ChunkingOptions(
        target_tokens=min(target_budget, budget // 2),  # Ensure valid target_tokens
        max_tokens=budget,
        overlap_tokens=min(32, budget // 8)  # Reasonable overlap
    )
    manager = TokenBudgetManager(temp_options, tokenizer)
    
    # Use the new manager to apply budget
    result = manager.apply_budget(text)
    
    # Convert to legacy format
    return TokenBudgetResult(
        content=result.text,
        token_count=result.token_count,
        trimmed=result.was_trimmed,
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
    
    # Create TokenBudgetManager for consistent budget application
    effective_options = ChunkingOptions(
        target_tokens=options.target_tokens,
        max_tokens=max_tokens if max_tokens is not None else options.max_tokens,
        overlap_tokens=options.overlap_tokens,
        version=options.version
    )
    manager = TokenBudgetManager(effective_options, tokenizer)
    
    for chunk in chunks:
        # Apply budget using the new manager
        budget_result = manager.apply_budget(chunk.text)
        
        # Calculate end character position based on trimmed text
        end_char = chunk.start_char + len(budget_result.text)
        chunk_id = build_chunk_id(
            source_id=source_id,
            version=options.version,
            start_char=chunk.start_char,
            end_char=end_char,
            span_text=budget_result.text,
        )
        
        budgeted.append(
            BudgetedChunk(
                source_id=source_id,
                start_char=chunk.start_char,
                end_char=end_char,
                text=budget_result.text,
                chunk_id=chunk_id,
                token_count=budget_result.token_count,
                trimmed=budget_result.was_trimmed,
                target_budget=manager.effective_max,
                safety_margin=manager.safety_margin,
            )
        )
    return budgeted


def _trim_to_budget(
    text: str, tokenizer: TokenizerAdapter, target_budget: int
) -> Tuple[str, TokenCount]:
    """Legacy helper function - use TokenBudgetManager for new code."""
    from .chunking import ChunkingOptions
    budget_with_margin = target_budget + 16  # Add some margin for legacy compatibility
    temp_options = ChunkingOptions(
        target_tokens=min(target_budget, budget_with_margin // 2),
        max_tokens=budget_with_margin,
        overlap_tokens=min(10, budget_with_margin // 8)
    )
    manager = TokenBudgetManager(temp_options, tokenizer)
    
    # Override the effective_max to match the target_budget exactly
    manager.effective_max = target_budget
    
    result = manager.apply_budget(text)
    return result.text, result.token_count


def _binary_search_prefix(
    text: str, tokenizer: TokenizerAdapter, target_budget: int
) -> Tuple[str, TokenCount]:
    """Legacy helper function - use TokenBudgetManager._binary_search_trim for new code."""
    from .chunking import ChunkingOptions
    budget_with_margin = target_budget + 16
    temp_options = ChunkingOptions(
        target_tokens=min(target_budget, budget_with_margin // 2),
        max_tokens=budget_with_margin,
        overlap_tokens=min(10, budget_with_margin // 8)
    )
    manager = TokenBudgetManager(temp_options, tokenizer)
    
    trimmed_text = manager._binary_search_trim(text, target_budget)
    token_count = tokenizer.count_tokens(trimmed_text)
    return trimmed_text, token_count
