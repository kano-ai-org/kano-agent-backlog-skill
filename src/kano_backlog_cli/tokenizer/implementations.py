from __future__ import annotations

import math
from typing import Any

from .adapter import TokenizerAdapter
from .defaults import get_model_budget


class CharacterAdapter(TokenizerAdapter):
    """
    Fallback tokenizer that roughly estimates tokens based on character count.
    Rule of thumb: 1 token ~= 4 chars (for English).
    """

    def __init__(self, model_name: str | None = None):
        self._budget = get_model_budget(model_name)

    def count(self, text: str) -> int:
        if not text:
            return 0
        return math.ceil(len(text) / 4)

    def max_tokens(self) -> int:
        return self._budget


class TiktokenAdapter(TokenizerAdapter):
    """
    Tokenizer using the tiktoken library (OpenAI models).
    """

    def __init__(self, model_name: str, encoding: Any):
        """
        Args:
            model_name: The model identifier (used for budget lookup).
            encoding: The initialized tiktoken encoding object.
        """
        self._budget = get_model_budget(model_name)
        self._encoding = encoding

    def count(self, text: str) -> int:
        if not text:
            return 0
        try:
            # disallow_special=() ensures we don't crash on special tokens, 
            # merely encoding them as text or failing depending on config. 
            # For general counting, 'all' or ignoring is typical. 
            # We'll use encode(text) defaults which usually handle text safely.
            tokens = self._encoding.encode(text)
            return len(tokens)
        except Exception:
            # Fallback to char count if encoding fails unexpectedly
            return math.ceil(len(text) / 4)

    def max_tokens(self) -> int:
        return self._budget
