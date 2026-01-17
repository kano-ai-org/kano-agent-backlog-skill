from __future__ import annotations

import logging
from typing import Optional

from .adapter import TokenizerAdapter
from .implementations import CharacterAdapter, TiktokenAdapter

logger = logging.getLogger(__name__)


def get_tokenizer(model_name: Optional[str] = None) -> TokenizerAdapter:
    """
    Factory to get the best available tokenizer for the given model.

    Algorithm:
    1. If tiktoken is available and model is supported, use TiktokenAdapter.
    2. Otherwise, fallback to CharacterAdapter.
    """
    target_model = model_name or "gpt-3.5-turbo"

    try:
        import tiktoken
        try:
            encoding = tiktoken.encoding_for_model(target_model)
            return TiktokenAdapter(model_name=target_model, encoding=encoding)
        except KeyError:
            # Model not found in tiktoken, try cl100k_base generic if it looks like GPT
            if "gpt" in target_model.lower():
                try:
                    encoding = tiktoken.get_encoding("cl100k_base")
                    return TiktokenAdapter(model_name=target_model, encoding=encoding)
                except Exception:
                    pass
    except ImportError:
        logger.debug("tiktoken not installed, falling back to CharacterAdapter")
        pass
    except Exception as e:
        logger.warning(f"Error initializing tiktoken for {target_model}: {e}. using fallback.")

    return CharacterAdapter(model_name=target_model)
