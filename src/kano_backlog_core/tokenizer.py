"""Tokenizer adapter interfaces and defaults."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .chunking import token_spans

DEFAULT_MAX_TOKENS = 8192
MODEL_MAX_TOKENS: Dict[str, int] = {
    "text-embedding-ada-002": 8192,
    "text-embedding-3-small": 8192,
    "text-embedding-3-large": 8192,
}


@dataclass(frozen=True)
class TokenCount:
    """Token count information."""

    count: int
    method: str
    tokenizer_id: str
    is_exact: bool


class TokenizerAdapter(ABC):
    """Abstract base class for tokenizer adapters."""

    def __init__(self, model_name: str, max_tokens: Optional[int] = None) -> None:
        if not model_name:
            raise ValueError("model_name must be non-empty")
        self._model_name = model_name
        self._max_tokens = max_tokens

    @property
    def model_name(self) -> str:
        """Return the model name for this adapter."""
        return self._model_name

    @abstractmethod
    def count_tokens(self, text: str) -> TokenCount:
        """Count tokens for the given text."""

    @abstractmethod
    def max_tokens(self) -> int:
        """Return the max token budget for the model."""


class HeuristicTokenizer(TokenizerAdapter):
    """Tokenizer adapter using deterministic heuristics."""

    def count_tokens(self, text: str) -> TokenCount:
        if text is None:
            raise ValueError("text must be a string")
        spans = token_spans(text)
        return TokenCount(
            count=len(spans),
            method="heuristic",
            tokenizer_id=f"heuristic:{self._model_name}",
            is_exact=False,
        )

    def max_tokens(self) -> int:
        if self._max_tokens is not None:
            return self._max_tokens
        return resolve_model_max_tokens(self._model_name)



class TiktokenAdapter(TokenizerAdapter):
    """Tokenizer using the tiktoken library (OpenAI models)."""

    def __init__(self, model_name: str, encoding: Any = None, max_tokens: Optional[int] = None) -> None:
        super().__init__(model_name, max_tokens)
        if encoding:
            self._encoding = encoding
        else:
            import tiktoken
            try:
                self._encoding = tiktoken.encoding_for_model(model_name)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> TokenCount:
        if text is None:
            return TokenCount(0, "tiktoken", self._model_name, True)
        
        # tiktoken encode can fail on special tokens if not allowed, 
        # but for counting we generally want to process them or ignore them.
        # "all" allows special tokens.
        tokens = self._encoding.encode(text, disallowed_special=())
        return TokenCount(
            count=len(tokens),
            method="tiktoken",
            tokenizer_id=f"tiktoken:{self._model_name}",
            is_exact=True,
        )

    def max_tokens(self) -> int:
        if self._max_tokens is not None:
            return self._max_tokens
        return resolve_model_max_tokens(self._model_name)


def resolve_model_max_tokens(
    model_name: str,
    overrides: Optional[Dict[str, int]] = None,
    default: int = DEFAULT_MAX_TOKENS,
) -> int:
    """Resolve max token budget for a model with optional overrides."""
    if overrides and model_name in overrides:
        return overrides[model_name]
    if model_name in MODEL_MAX_TOKENS:
        return MODEL_MAX_TOKENS[model_name]
    return default


def resolve_tokenizer(
    adapter_name: str,
    model_name: str,
    max_tokens: Optional[int] = None,
) -> TokenizerAdapter:
    """Resolve a tokenizer adapter by name."""
    adapter = adapter_name.lower().strip()
    if adapter == "heuristic":
        return HeuristicTokenizer(model_name=model_name, max_tokens=max_tokens)
    if adapter == "tiktoken":
        return TiktokenAdapter(model_name=model_name, max_tokens=max_tokens)
    raise ValueError(f"Unknown tokenizer adapter: {adapter_name}")
