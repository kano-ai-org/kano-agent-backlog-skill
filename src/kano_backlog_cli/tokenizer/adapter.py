from __future__ import annotations

from abc import ABC, abstractmethod


class TokenizerAdapter(ABC):
    """Abstract base class for tokenizer adapters."""

    @abstractmethod
    def count(self, text: str) -> int:
        """Count the number of tokens in a text string."""
        pass

    @abstractmethod
    def max_tokens(self) -> int:
        """Return the maximum context window size (tokens) for this model."""
        pass
