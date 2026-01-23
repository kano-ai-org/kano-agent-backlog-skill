"""Tokenizer adapter interfaces and defaults."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type, Tuple

from .chunking import token_spans
from .tokenizer_errors import (
    TokenizerError,
    AdapterNotAvailableError,
    DependencyMissingError,
    TokenizationFailedError,
    FallbackChainExhaustedError,
    ErrorRecoveryManager,
    wrap_adapter_error,
    log_error_with_context,
    create_user_friendly_error_message,
)
from .tokenizer_dependencies import (
    DependencyManager,
    get_dependency_manager,
    check_adapter_readiness,
)

from .tokenizer_cache import (
    TokenCountCache,
    CachingTokenizerAdapter,
    get_global_cache,
    CacheStats
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 8192

# Optional dependency: tiktoken
try:
    import tiktoken  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    tiktoken = None  # type: ignore

# Optional dependency: transformers
try:
    import transformers  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    transformers = None  # type: ignore

# Model to max tokens mapping with expanded OpenAI model support
MODEL_MAX_TOKENS: Dict[str, int] = {
    # OpenAI embedding models
    "text-embedding-ada-002": 8192,
    "text-embedding-3-small": 8192,
    "text-embedding-3-large": 8192,
    # OpenAI GPT models
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-16k": 16384,
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    # OpenAI legacy models
    "text-davinci-003": 4097,
    "text-davinci-002": 4097,
    "code-davinci-002": 8001,
    # HuggingFace sentence-transformers models
    "sentence-transformers/all-MiniLM-L6-v2": 512,
    "sentence-transformers/all-mpnet-base-v2": 512,
    "sentence-transformers/all-MiniLM-L12-v2": 512,
    "sentence-transformers/paraphrase-MiniLM-L6-v2": 512,
    "sentence-transformers/paraphrase-mpnet-base-v2": 512,
    "sentence-transformers/multi-qa-MiniLM-L6-cos-v1": 512,
    "sentence-transformers/multi-qa-mpnet-base-cos-v1": 512,
    "sentence-transformers/distilbert-base-nli-stsb-mean-tokens": 512,
    "sentence-transformers/roberta-base-nli-stsb-mean-tokens": 512,
    "sentence-transformers/stsb-roberta-large": 512,
    # HuggingFace BERT family models
    "bert-base-uncased": 512,
    "bert-base-cased": 512,
    "bert-large-uncased": 512,
    "bert-large-cased": 512,
    "distilbert-base-uncased": 512,
    "distilbert-base-cased": 512,
    # HuggingFace RoBERTa family models
    "roberta-base": 512,
    "roberta-large": 1024,
    "distilroberta-base": 512,
    # HuggingFace other popular models
    "microsoft/DialoGPT-medium": 1024,
    "microsoft/DialoGPT-large": 1024,
    "facebook/bart-base": 1024,
    "facebook/bart-large": 1024,
    "t5-small": 512,
    "t5-base": 512,
    "t5-large": 512,
}

# Model to encoding mapping for tiktoken
MODEL_TO_ENCODING: Dict[str, str] = {
    # GPT-4 and newer models use cl100k_base
    "gpt-4": "cl100k_base",
    "gpt-4-32k": "cl100k_base", 
    "gpt-4-turbo": "cl100k_base",
    "gpt-4o": "cl100k_base",
    "gpt-4o-mini": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "gpt-3.5-turbo-16k": "cl100k_base",
    "text-embedding-ada-002": "cl100k_base",
    "text-embedding-3-small": "cl100k_base",
    "text-embedding-3-large": "cl100k_base",
    # Legacy models use different encodings
    "text-davinci-003": "p50k_base",
    "text-davinci-002": "p50k_base",
    "code-davinci-002": "p50k_base",
}


@dataclass(frozen=True)
class TokenCount:
    """Token count information."""

    count: int
    method: str
    tokenizer_id: str
    is_exact: bool
    model_max_tokens: Optional[int] = None


# Import telemetry components after TokenCount is defined to avoid circular imports.
try:
    from .tokenizer_telemetry import get_default_collector
    _TELEMETRY_AVAILABLE = True
except ImportError:  # pragma: no cover - telemetry is optional
    _TELEMETRY_AVAILABLE = False


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

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier for this adapter."""
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> TokenCount:
        """Count tokens for the given text."""

    @abstractmethod
    def max_tokens(self) -> int:
        """Return the max token budget for the model."""


class TelemetryEnabledAdapter(TokenizerAdapter):
    """Wrapper that adds telemetry tracking to any tokenizer adapter."""
    
    def __init__(self, wrapped_adapter: TokenizerAdapter, enable_telemetry: bool = True):
        """Initialize telemetry-enabled adapter wrapper.
        
        Args:
            wrapped_adapter: The tokenizer adapter to wrap
            enable_telemetry: Whether to enable telemetry collection
        """
        # Initialize parent with wrapped adapter's properties
        super().__init__(wrapped_adapter.model_name, wrapped_adapter._max_tokens)
        self._wrapped_adapter = wrapped_adapter
        self._enable_telemetry = enable_telemetry and _TELEMETRY_AVAILABLE
        
        # Get telemetry collector if available
        self._collector = None
        if self._enable_telemetry:
            try:
                self._collector = get_default_collector()
            except Exception as e:
                logger.debug(f"Failed to get telemetry collector: {e}")
                self._enable_telemetry = False
    
    @property
    def adapter_id(self) -> str:
        """Unique identifier for this adapter."""
        return self._wrapped_adapter.adapter_id
    
    def count_tokens(self, text: str) -> TokenCount:
        """Count tokens with telemetry tracking."""
        if not self._enable_telemetry or not self._collector:
            # No telemetry, just call wrapped adapter
            return self._wrapped_adapter.count_tokens(text)
        
        # Get fallback context if available
        fallback_context = getattr(self, '_fallback_context', {})
        was_fallback = fallback_context.get('was_fallback', False)
        fallback_from = fallback_context.get('fallback_from', None)
        
        # Track operation with telemetry
        with self._collector.track_operation(
            adapter_name=self._wrapped_adapter.adapter_id,
            adapter_id=f"{self._wrapped_adapter.adapter_id}:{self._wrapped_adapter.model_name}",
            model_name=self._wrapped_adapter.model_name,
            text=text,
            was_fallback=was_fallback,
            fallback_from=fallback_from,
            metadata={"wrapped_adapter": type(self._wrapped_adapter).__name__}
        ) as tracker:
            try:
                result = self._wrapped_adapter.count_tokens(text)
                tracker.set_result(result)
                return result
            except Exception as e:
                tracker.set_error(e)
                raise
    
    def max_tokens(self) -> int:
        """Return the max token budget for the model."""
        return self._wrapped_adapter.max_tokens()
    
    def __getattr__(self, name):
        """Delegate attribute access to wrapped adapter."""
        return getattr(self._wrapped_adapter, name)


class HeuristicTokenizer(TokenizerAdapter):
    """Tokenizer adapter using deterministic heuristics with configurable ratios."""

    def __init__(self, model_name: str, max_tokens: Optional[int] = None, chars_per_token: float = 4.0, **kwargs) -> None:
        super().__init__(model_name, max_tokens)
        
        # Extract heuristic-specific options
        chars_per_token = kwargs.get("chars_per_token", chars_per_token)
        
        if chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")
        self._chars_per_token = chars_per_token

    @property
    def adapter_id(self) -> str:
        """Unique identifier for this adapter."""
        return "heuristic"

    @property
    def chars_per_token(self) -> float:
        """Get the configured chars-per-token ratio."""
        return self._chars_per_token

    def count_tokens(self, text: str) -> TokenCount:
        if text is None:
            from .tokenizer_errors import TokenizationFailedError
            raise TokenizationFailedError(
                adapter_name="heuristic",
                model_name=self._model_name,
                text_preview="None",
                original_error=ValueError("text must be a string, not None")
            )
        
        try:
            # Use character-based estimation with language detection
            token_count = self._estimate_tokens_with_language_detection(text)
            
            return TokenCount(
                count=token_count,
                method="heuristic",
                tokenizer_id=f"heuristic:{self._model_name}:chars_{self._chars_per_token}",
                is_exact=False,
                model_max_tokens=self.max_tokens(),
            )
        except Exception as e:
            logger.error(f"Heuristic tokenization failed for model {self._model_name}: {e}")
            
            # Enhanced error handling for heuristic adapter
            from .tokenizer_errors import TokenizationFailedError
            
            text_preview = str(text)[:100] + "..." if len(str(text)) > 100 else str(text)
            raise TokenizationFailedError(
                adapter_name="heuristic",
                model_name=self._model_name,
                text_preview=text_preview,
                original_error=e
            )

    def _estimate_tokens_with_language_detection(self, text: str) -> int:
        """Estimate token count using character-based approach with language detection."""
        if not text:
            return 0
        
        # For very short text, use a more conservative approach
        if len(text) <= 3:
            return 1
        
        # Detect text composition for adaptive estimation
        char_count = len(text)
        cjk_count = sum(1 for ch in text if self._is_cjk_char(ch))
        
        # Calculate CJK ratio to adjust estimation
        cjk_ratio = cjk_count / char_count if char_count > 0 else 0
        
        if cjk_ratio > 0.5:
            # Predominantly CJK text - each character is roughly a token
            # Use a lower ratio since CJK characters are typically 1 token each
            effective_ratio = 1.2  # Slightly more than 1 to account for punctuation
        elif cjk_ratio > 0.1:
            # Mixed text - blend the ratios
            # Weight towards CJK behavior for mixed content
            cjk_weight = min(cjk_ratio * 3, 0.7)  # Cap the CJK influence
            ascii_weight = 1 - cjk_weight
            effective_ratio = (1.2 * cjk_weight + self._chars_per_token * ascii_weight)
        else:
            # Predominantly ASCII/Latin text - use configured ratio
            effective_ratio = self._chars_per_token
        
        # Calculate estimated tokens
        estimated_tokens = max(1, int(char_count / effective_ratio))
        
        # For punctuation-heavy text, add some tokens
        punct_count = sum(1 for ch in text if not ch.isalnum() and not ch.isspace() and not self._is_cjk_char(ch))
        if punct_count > 0:
            # Add roughly half the punctuation marks as additional tokens
            estimated_tokens += max(0, punct_count // 2)
        
        return estimated_tokens

    def _is_cjk_char(self, ch: str) -> bool:
        """Check if character is CJK (Chinese, Japanese, Korean)."""
        code = ord(ch)
        return (
            0x3400 <= code <= 0x4DBF  # CJK Ext A
            or 0x4E00 <= code <= 0x9FFF  # CJK Unified
            or 0x3040 <= code <= 0x30FF  # Hiragana/Katakana
            or 0xAC00 <= code <= 0xD7AF  # Hangul
        )

    def max_tokens(self) -> int:
        if self._max_tokens is not None:
            return self._max_tokens
        return resolve_model_max_tokens(self._model_name)



class TiktokenAdapter(TokenizerAdapter):
    """Tokenizer using the tiktoken library (OpenAI models)."""

    def __init__(self, model_name: str, encoding: Any = None, max_tokens: Optional[int] = None, **kwargs) -> None:
        super().__init__(model_name, max_tokens)
        
        # Extract tiktoken-specific options
        encoding_name = kwargs.get("encoding_name") or kwargs.get("encoding")
        
        # Check if tiktoken is available
        if tiktoken is None:
            raise ImportError(
                "tiktoken package required for TiktokenAdapter. "
                "Install with: pip install tiktoken"
            )
        
        if encoding:
            # Use provided encoding directly
            self._encoding = encoding
            self._encoding_name = getattr(encoding, 'name', 'custom')
        elif encoding_name:
            # Use specified encoding name
            try:
                self._encoding = tiktoken.get_encoding(encoding_name)
                self._encoding_name = encoding_name
            except Exception as e:
                # Fall back to model-based resolution
                self._encoding, self._encoding_name = self._resolve_encoding(tiktoken, model_name)
        else:
            # Resolve encoding based on model name
            self._encoding, self._encoding_name = self._resolve_encoding(tiktoken, model_name)

    def _resolve_encoding(self, tiktoken_module: Any, model_name: str) -> Tuple[Any, str]:
        """Resolve the appropriate encoding for the given model.
        
        Args:
            tiktoken_module: The imported tiktoken module
            model_name: Name of the model
            
        Returns:
            Tuple of (encoding, encoding_name)
        """
        # First try tiktoken's model-based resolution.
        #
        # In tests we often patch `kano_backlog_core.tokenizer.tiktoken` with a MagicMock.
        # If `encoding_for_model()` isn't configured, it may return a mock object whose
        # `.name` is not a real string; detect that and fall back to explicit mappings.
        try:
            encoding = tiktoken_module.encoding_for_model(model_name)
            encoding_name = getattr(encoding, "name", None)
            if isinstance(encoding_name, str) and encoding_name:
                return encoding, encoding_name
        except KeyError:
            pass

        # Prefer our explicit mapping for well-known models (deterministic and easy to mock).
        if model_name in MODEL_TO_ENCODING:
            encoding_name = MODEL_TO_ENCODING[model_name]
            try:
                encoding = tiktoken_module.get_encoding(encoding_name)
                logger.debug(f"Using {encoding_name} encoding for model {model_name}")
                return encoding, encoding_name
            except Exception as e:
                logger.warning(f"Failed to load {encoding_name} encoding: {e}")

        # Fallback to cl100k_base (most common for newer models)
        try:
            encoding = tiktoken_module.get_encoding("cl100k_base")
            logger.info(f"Using cl100k_base fallback encoding for unknown model: {model_name}")
            return encoding, "cl100k_base"
        except Exception as e:
            logger.warning(f"Failed to load cl100k_base encoding: {e}")

        # Final fallback to p50k_base
        try:
            encoding = tiktoken_module.get_encoding("p50k_base")
            logger.info(f"Using p50k_base fallback encoding for model: {model_name}")
            return encoding, "p50k_base"
        except Exception as e:
            raise RuntimeError(f"Failed to load any tiktoken encoding: {e}")

    @property
    def adapter_id(self) -> str:
        """Unique identifier for this adapter."""
        return "tiktoken"

    @property
    def encoding_name(self) -> str:
        """Get the name of the encoding being used."""
        return self._encoding_name

    def count_tokens(self, text: str) -> TokenCount:
        if text is None:
            return TokenCount(
                count=0,
                method="tiktoken",
                tokenizer_id=f"tiktoken:{self._model_name}:{self._encoding_name}",
                is_exact=True,
                model_max_tokens=self.max_tokens(),
            )
        
        try:
            # tiktoken encode can fail on special tokens if not allowed, 
            # but for counting we generally want to process them or ignore them.
            # "all" allows special tokens.
            tokens = self._encoding.encode(text, disallowed_special=())
            return TokenCount(
                count=len(tokens),
                method="tiktoken",
                tokenizer_id=f"tiktoken:{self._model_name}:{self._encoding_name}",
                is_exact=True,
                model_max_tokens=self.max_tokens(),
            )
        except Exception as e:
            logger.error(f"TikToken encoding failed for model {self._model_name}: {e}")
            
            # Enhanced error handling with recovery suggestions
            from .tokenizer_errors import TokenizationFailedError
            
            # Create preview of problematic text
            text_preview = text[:100] + "..." if len(text) > 100 else text
            
            # Raise enhanced error with recovery suggestions
            raise TokenizationFailedError(
                adapter_name="tiktoken",
                model_name=self._model_name,
                text_preview=text_preview,
                original_error=e
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


def get_supported_huggingface_models() -> List[str]:
    """Get list of HuggingFace models with known token limits.
    
    Returns:
        List of model names that have predefined token limits.
    """
    return [model for model in MODEL_MAX_TOKENS.keys() 
            if model.startswith(('sentence-transformers/', 'bert-', 'distilbert-', 
                               'roberta-', 'distilroberta-', 'microsoft/', 
                               'facebook/', 't5-'))]


def is_sentence_transformers_model(model_name: str) -> bool:
    """Check if a model name corresponds to a sentence-transformers model.
    
    Args:
        model_name: The HuggingFace model identifier
        
    Returns:
        True if the model is a sentence-transformers model
    """
    return model_name.startswith('sentence-transformers/')


def suggest_huggingface_model(task_type: str = "embedding") -> str:
    """Suggest an appropriate HuggingFace model for a given task.
    
    Args:
        task_type: Type of task ("embedding", "classification", "generation")
        
    Returns:
        Recommended model name for the task
    """
    recommendations = {
        "embedding": "sentence-transformers/all-MiniLM-L6-v2",
        "semantic_search": "sentence-transformers/all-mpnet-base-v2", 
        "classification": "bert-base-uncased",
        "generation": "t5-base",
        "question_answering": "bert-large-uncased",
    }
    
    return recommendations.get(task_type, "sentence-transformers/all-MiniLM-L6-v2")


class HuggingFaceAdapter(TokenizerAdapter):
    """HuggingFace tokenizer adapter for transformer models.
    
    Supports a wide range of HuggingFace models including:
    - sentence-transformers models for semantic similarity
    - BERT family models (bert-base-uncased, distilbert, etc.)
    - RoBERTa family models
    - T5, BART, and other transformer architectures
    
    Features:
    - Automatic model detection and tokenizer loading
    - Configurable model selection with validation
    - Graceful fallback when transformers not available
    - Support for custom max_tokens override
    """

    def __init__(self, model_name: str, max_tokens: Optional[int] = None, **kwargs) -> None:
        super().__init__(model_name, max_tokens)

        # Validate model name format (after base non-empty validation).
        if not self._is_valid_model_name(model_name):
            raise ValueError(f"Invalid HuggingFace model name format: {model_name}")
        
        # Extract HuggingFace-specific options
        self._use_fast = kwargs.get("use_fast", True)
        self._trust_remote_code = kwargs.get("trust_remote_code", False)

        if transformers is None:
            raise ImportError("transformers package required for HuggingFaceAdapter")

        try:
            # Load tokenizer with error handling and options
            self._tokenizer = self._load_tokenizer_safely(
                transformers.AutoTokenizer, model_name
            )
        except Exception as e:
            raise ValueError(f"Failed to load HuggingFace tokenizer for {model_name}: {e}")

    def _is_valid_model_name(self, model_name: str) -> bool:
        """Validate HuggingFace model name format."""
        if not model_name or not isinstance(model_name, str):
            return False
        
        # Allow common patterns:
        # - organization/model-name (e.g., sentence-transformers/all-MiniLM-L6-v2)
        # - simple model names (e.g., bert-base-uncased)
        # - microsoft/model-name, facebook/model-name, etc.
        import re
        pattern = (
            r"^[a-zA-Z0-9](?:[a-zA-Z0-9._-]*[a-zA-Z0-9])?"
            r"(?:/[a-zA-Z0-9](?:[a-zA-Z0-9._-]*[a-zA-Z0-9])?)?$"
        )
        return bool(re.match(pattern, model_name))

    def _load_tokenizer_safely(self, AutoTokenizer, model_name: str):
        """Load tokenizer with comprehensive error handling."""
        try:
            # Try loading with configured settings
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                use_fast=self._use_fast,
                trust_remote_code=self._trust_remote_code
            )
            return tokenizer
        except Exception as e:
            # Try with fallback options for problematic models
            try:
                tokenizer = AutoTokenizer.from_pretrained(
                    model_name, 
                    use_fast=False,  # Fallback to slow tokenizer
                    trust_remote_code=False  # Security: don't execute remote code
                )
                return tokenizer
            except Exception as e2:
                # If both attempts fail, raise the original error
                raise e

    @property
    def adapter_id(self) -> str:
        """Unique identifier for this adapter."""
        return "huggingface"

    def count_tokens(self, text: str) -> TokenCount:
        if text is None:
            return TokenCount(
                count=0,
                method="huggingface",
                tokenizer_id=f"huggingface:{self._model_name}",
                is_exact=True,
                model_max_tokens=self.max_tokens(),
            )
        
        try:
            # Use add_special_tokens=True for consistency with model behavior
            tokens = self._tokenizer.encode(text, add_special_tokens=True)
            return TokenCount(
                count=len(tokens),
                method="huggingface",
                tokenizer_id=f"huggingface:{self._model_name}",
                is_exact=True,
                model_max_tokens=self.max_tokens(),
            )
        except Exception as e:
            logger.warning(f"HuggingFace tokenization failed for {self._model_name}: {e}")
            
            # Enhanced error handling with graceful fallback
            from .tokenizer_errors import TokenizationFailedError
            
            # Try graceful fallback to heuristic counting
            try:
                spans = token_spans(text)
                
                logger.info(f"Using heuristic fallback for HuggingFace tokenization failure")
                return TokenCount(
                    count=len(spans),
                    method="huggingface_fallback",
                    tokenizer_id=f"huggingface_fallback:{self._model_name}",
                    is_exact=False,
                    model_max_tokens=self.max_tokens(),
                )
            except Exception as fallback_error:
                # If even fallback fails, raise the original error with context
                text_preview = text[:100] + "..." if len(text) > 100 else text
                raise TokenizationFailedError(
                    adapter_name="huggingface",
                    model_name=self._model_name,
                    text_preview=text_preview,
                    original_error=e
                )

    def max_tokens(self) -> int:
        if self._max_tokens is not None:
            return self._max_tokens
        return resolve_model_max_tokens(self._model_name)

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model and tokenizer.
        
        Returns:
            Dictionary with model information including:
            - model_name: The HuggingFace model identifier
            - vocab_size: Size of the tokenizer vocabulary
            - max_tokens: Maximum token limit for the model
            - tokenizer_type: Type of tokenizer (fast/slow)
            - special_tokens: Information about special tokens
        """
        try:
            info = {
                "model_name": self._model_name,
                "max_tokens": self.max_tokens(),
                "adapter_id": self.adapter_id,
            }
            
            if hasattr(self, '_tokenizer'):
                info.update({
                    "vocab_size": self._tokenizer.vocab_size,
                    "tokenizer_type": "fast" if getattr(self._tokenizer, 'is_fast', False) else "slow",
                    "special_tokens": {
                        "pad_token": getattr(self._tokenizer, 'pad_token', None),
                        "unk_token": getattr(self._tokenizer, 'unk_token', None),
                        "cls_token": getattr(self._tokenizer, 'cls_token', None),
                        "sep_token": getattr(self._tokenizer, 'sep_token', None),
                        "mask_token": getattr(self._tokenizer, 'mask_token', None),
                    }
                })
            
            return info
        except Exception as e:
            logger.warning(f"Failed to get model info for {self._model_name}: {e}")
            return {
                "model_name": self._model_name,
                "max_tokens": self.max_tokens(),
                "adapter_id": self.adapter_id,
                "error": str(e)
            }


class TokenizerRegistry:
    """Registry for tokenizer adapters with enhanced fallback chain and error handling."""

    def __init__(self) -> None:
        self._adapters: Dict[str, Tuple[Type[TokenizerAdapter], Dict[str, Any]]] = {}
        self._fallback_chain: List[str] = ["tiktoken", "huggingface", "heuristic"]
        self._error_recovery = ErrorRecoveryManager()
        self._dependency_manager = get_dependency_manager()
        self._register_default_adapters()

    def _register_default_adapters(self) -> None:
        """Register default tokenizer adapters."""
        self.register("heuristic", HeuristicTokenizer, chars_per_token=4.0)
        self.register("tiktoken", TiktokenAdapter)
        self.register("huggingface", HuggingFaceAdapter)

    def register(
        self, 
        name: str, 
        adapter_class: Type[TokenizerAdapter], 
        **default_kwargs: Any
    ) -> None:
        """Register an adapter with default configuration.
        
        Args:
            name: Adapter name for resolution
            adapter_class: TokenizerAdapter subclass
            **default_kwargs: Default keyword arguments for adapter creation
        """
        if not name:
            raise ValueError("Adapter name must be non-empty")
        if not issubclass(adapter_class, TokenizerAdapter):
            raise ValueError("Adapter class must inherit from TokenizerAdapter")
        
        self._adapters[name.lower().strip()] = (adapter_class, default_kwargs)
        logger.debug(f"Registered tokenizer adapter: {name}")

    def set_fallback_chain(self, chain: List[str]) -> None:
        """Set the fallback chain for adapter resolution.
        
        Args:
            chain: List of adapter names in fallback order
        """
        if not chain:
            raise ValueError("Fallback chain must not be empty")
        
        # Validate all adapters in chain are registered
        for adapter_name in chain:
            if adapter_name.lower().strip() not in self._adapters:
                raise ValueError(f"Unknown adapter in fallback chain: {adapter_name}")
        
        self._fallback_chain = [name.lower().strip() for name in chain]
        logger.debug(f"Set fallback chain: {self._fallback_chain}")

    def resolve(
        self, 
        adapter_name: Optional[str] = None, 
        model_name: str = "default-model",
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> TokenizerAdapter:
        """Resolve adapter by name or use fallback chain with enhanced error handling.
        
        Args:
            adapter_name: Specific adapter name, or None for auto-resolution
            model_name: Model name for the adapter
            max_tokens: Optional max tokens override
            **kwargs: Additional adapter-specific arguments
            
        Returns:
            Configured TokenizerAdapter instance
            
        Raises:
            FallbackChainExhaustedError: If no adapter can be created
        """
        attempted_adapters: List[str] = []
        errors: List[str] = []
        primary_adapter_requested = adapter_name and adapter_name.lower().strip() != "auto"
        
        # Try specific adapter first
        if primary_adapter_requested:
            adapter_name_clean = adapter_name.lower().strip()
            try:
                adapter = self._create_adapter_with_recovery(
                    adapter_name_clean, 
                    model_name, 
                    max_tokens, 
                    **kwargs
                )
                logger.info(f"Successfully created {adapter_name_clean} adapter for model {model_name}")
                
                # Wrap with enhancements (caching + telemetry)
                return self._wrap_with_enhancements(
                    adapter, 
                    cache_config=kwargs.get('cache_config'),
                    was_fallback=False
                )
            except Exception as e:
                error_msg = f"{adapter_name_clean}: {e}"
                errors.append(error_msg)
                attempted_adapters.append(adapter_name_clean)
                
                # Get recovery strategy for user notification
                strategy = self.suggest_recovery_strategy(e, adapter_name_clean, model_name)
                
                # Log the specific adapter failure with context
                wrapped_error = wrap_adapter_error(e, adapter_name_clean, model_name)
                log_error_with_context(wrapped_error, {
                    "requested_adapter": adapter_name_clean,
                    "model_name": model_name,
                    "fallback_available": True,
                    "recovery_strategy": strategy
                })
                
                logger.warning(f"Requested adapter {adapter_name_clean} failed: {e}")
                
                # If this is a dependency issue and user specifically requested this adapter,
                # provide immediate guidance
                if strategy["recommended_action"] == "install_dependency":
                    logger.info(f"💡 {strategy['user_message']}")
        
        # Try fallback chain
        for fallback_name in self._fallback_chain:
            if fallback_name in attempted_adapters:
                continue  # Skip already attempted adapters
                
            try:
                adapter = self._create_adapter_with_recovery(
                    fallback_name, 
                    model_name, 
                    max_tokens, 
                    **kwargs
                )
                
                # Notify user about fallback usage with context
                if attempted_adapters:
                    if primary_adapter_requested:
                        # User specifically requested an adapter that failed
                        primary_adapter = attempted_adapters[0]
                        strategy = self.suggest_recovery_strategy(
                            Exception(errors[0]), primary_adapter, model_name
                        )
                        
                        notification = self.create_user_notification(
                            primary_adapter, fallback_name, model_name, strategy
                        )
                        logger.info(f"Adapter fallback notification:\n{notification}")
                    else:
                        # Auto-resolution fallback
                        logger.info(
                            f"Auto-resolved to {fallback_name} adapter for model '{model_name}' "
                            f"after {len(attempted_adapters)} failed attempt(s): {', '.join(attempted_adapters)}"
                        )
                
                # Reset recovery attempts on success
                recovery_key = f"{fallback_name}:{model_name}"
                self._error_recovery.reset_recovery_attempts(recovery_key)
                
                # Wrap with enhancements, marking as fallback
                was_fallback = len(attempted_adapters) > 0
                fallback_from = attempted_adapters[0] if attempted_adapters else None
                return self._wrap_with_enhancements(
                    adapter, 
                    cache_config=kwargs.get('cache_config'),
                    was_fallback=was_fallback, 
                    fallback_from=fallback_from
                )
                
            except Exception as e:
                error_msg = f"{fallback_name}: {e}"
                errors.append(error_msg)
                attempted_adapters.append(fallback_name)
                
                logger.debug(f"Fallback adapter {fallback_name} failed: {e}")
        
        # All adapters failed - create comprehensive error with recovery guidance
        exhausted_error = FallbackChainExhaustedError(attempted_adapters, errors, model_name)
        
        # Add comprehensive recovery guidance
        recovery_context = {
            "attempted_adapters": attempted_adapters,
            "fallback_chain": self._fallback_chain,
            "model_name": model_name,
            "primary_adapter_requested": primary_adapter_requested,
            "recovery_statistics": self.get_recovery_statistics()
        }
        
        log_error_with_context(exhausted_error, recovery_context)
        
        # Create user-friendly error message with actionable guidance
        user_message = self._create_comprehensive_error_message(
            exhausted_error, attempted_adapters, errors, model_name, primary_adapter_requested
        )
        logger.error(f"All tokenizer adapters failed:\n{user_message}")
        
        raise exhausted_error
    
    def _create_comprehensive_error_message(
        self, 
        error: FallbackChainExhaustedError,
        attempted_adapters: List[str],
        errors: List[str], 
        model_name: str,
        primary_requested: bool
    ) -> str:
        """Create comprehensive error message with recovery guidance."""
        message_parts = [
            "❌ All Tokenizer Adapters Failed",
            f"   Model: {model_name}",
            f"   Attempted: {', '.join(attempted_adapters)}",
            ""
        ]
        
        # Analyze errors for common patterns
        has_dependency_errors = any("import" in err.lower() or "module" in err.lower() for err in errors)
        has_config_errors = any("config" in err.lower() or "invalid" in err.lower() for err in errors)
        has_network_errors = any("network" in err.lower() or "timeout" in err.lower() for err in errors)
        
        # Provide specific guidance based on error patterns
        if has_dependency_errors:
            message_parts.extend([
                "🔧 Dependency Issues Detected:",
                "   Install missing packages:",
                "   • For OpenAI models: pip install tiktoken",
                "   • For HuggingFace models: pip install transformers",
                ""
            ])
        
        if has_config_errors:
            message_parts.extend([
                "⚙️  Configuration Issues Detected:",
                "   • Check model name format",
                "   • Verify adapter settings in config file",
                "   • Use 'kano tokenizer validate' to check configuration",
                ""
            ])
        
        if has_network_errors:
            message_parts.extend([
                "🌐 Network Issues Detected:",
                "   • Check internet connection",
                "   • Try again later",
                "   • Use offline adapters (heuristic)",
                ""
            ])
        
        # General recovery suggestions
        message_parts.extend([
            "💡 Recovery Options:",
            "   1. Install missing dependencies (see above)",
            "   2. Use heuristic adapter: KANO_TOKENIZER_ADAPTER=heuristic",
            "   3. Check system requirements: kano tokenizer diagnose",
            "   4. Create minimal config: kano tokenizer create-example",
            ""
        ])
        
        # Add specific error details
        message_parts.extend([
            "🔍 Error Details:",
        ])
        
        for adapter, error in zip(attempted_adapters, errors):
            message_parts.append(f"   • {adapter}: {error[:100]}{'...' if len(error) > 100 else ''}")
        
        return "\n".join(message_parts)

    def _create_adapter(
        self, 
        adapter_name: str, 
        model_name: str, 
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> TokenizerAdapter:
        """Create adapter instance without recovery mechanisms (for backward compatibility).
        
        This method is used by the legacy resolve_tokenizer function to maintain
        backward compatibility with existing error handling behavior.
        """
        if adapter_name not in self._adapters:
            raise ValueError(f"Unknown tokenizer adapter: {adapter_name}")
        
        adapter_class, default_kwargs = self._adapters[adapter_name]
        
        # Merge default kwargs with provided kwargs
        merged_kwargs = {**default_kwargs, **kwargs}
        if max_tokens is not None:
            merged_kwargs["max_tokens"] = max_tokens
        
        try:
            return adapter_class(model_name, **merged_kwargs)
        except ImportError:
            # Re-raise ImportError for backward compatibility
            raise
        except Exception as e:
            # Convert other exceptions to ValueError for backward compatibility
            raise ValueError(f"Failed to create {adapter_name} adapter: {e}")

    def _create_adapter_with_recovery(
        self, 
        adapter_name: str, 
        model_name: str, 
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> TokenizerAdapter:
        """Create adapter instance with error recovery and enhanced error handling."""
        if adapter_name not in self._adapters:
            raise AdapterNotAvailableError(
                adapter_name, 
                f"Adapter '{adapter_name}' is not registered", 
                model_name
            )
        
        adapter_class, default_kwargs = self._adapters[adapter_name]
        
        # Merge default kwargs with provided kwargs
        merged_kwargs = {**default_kwargs, **kwargs}
        if max_tokens is not None:
            merged_kwargs["max_tokens"] = max_tokens
        
        recovery_key = f"{adapter_name}:{model_name}"
        
        try:
            # Check if we should attempt recovery
            if not self._error_recovery.should_attempt_recovery(recovery_key):
                raise AdapterNotAvailableError(
                    adapter_name,
                    f"Maximum recovery attempts exceeded for {adapter_name} with model {model_name}",
                    model_name
                )
            
            # Record recovery attempt
            self._error_recovery.record_recovery_attempt(recovery_key)
            
            # Create adapter with enhanced error context
            adapter = adapter_class(model_name, **merged_kwargs)
            
            # Test the adapter with a simple tokenization to ensure it works
            try:
                test_result = adapter.count_tokens("test")
                if test_result.count < 0:
                    raise TokenizationFailedError(
                        adapter_name, model_name, "test", 
                        ValueError("Negative token count returned")
                    )
                logger.debug(f"Adapter {adapter_name} passed validation test")
            except Exception as test_error:
                # For validation failures, try graceful degradation
                if adapter_name != "heuristic":
                    logger.warning(f"Adapter {adapter_name} validation failed, attempting graceful degradation")
                    return self._attempt_graceful_degradation(adapter_name, model_name, test_error, **merged_kwargs)
                else:
                    raise TokenizationFailedError(
                        adapter_name, model_name, "test", test_error
                    )
            
            return adapter
            
        except ImportError as e:
            # Handle dependency errors with specific guidance and graceful degradation
            if "tiktoken" in str(e):
                error = DependencyMissingError("tiktoken", adapter_name, model_name)
                logger.warning(f"TikToken dependency missing for {adapter_name} adapter: {e}")
                if adapter_name != "heuristic":
                    return self._attempt_graceful_degradation(adapter_name, model_name, error, **merged_kwargs)
                else:
                    raise error
            elif "transformers" in str(e):
                error = DependencyMissingError("transformers", adapter_name, model_name)
                logger.warning(f"Transformers dependency missing for {adapter_name} adapter: {e}")
                if adapter_name != "heuristic":
                    return self._attempt_graceful_degradation(adapter_name, model_name, error, **merged_kwargs)
                else:
                    raise error
            else:
                error = DependencyMissingError("unknown", adapter_name, model_name)
                if adapter_name != "heuristic":
                    return self._attempt_graceful_degradation(adapter_name, model_name, error, **merged_kwargs)
                else:
                    raise error
                
        except Exception as e:
            # Wrap other exceptions with enhanced context and attempt recovery
            wrapped_error = wrap_adapter_error(e, adapter_name, model_name)
            
            # Add recovery context
            recovery_context = self._error_recovery.create_recovery_context(
                e, adapter_name, model_name
            )
            log_error_with_context(wrapped_error, recovery_context)
            
            # Attempt graceful degradation for non-heuristic adapters
            if adapter_name != "heuristic":
                logger.warning(f"Adapter {adapter_name} creation failed, attempting graceful degradation")
                return self._attempt_graceful_degradation(adapter_name, model_name, wrapped_error, **merged_kwargs)
            
            raise wrapped_error
    
    def _attempt_graceful_degradation(
        self, 
        failed_adapter: str, 
        model_name: str, 
        original_error: Exception,
        **kwargs: Any
    ) -> TokenizerAdapter:
        """Attempt graceful degradation to a fallback adapter.
        
        Args:
            failed_adapter: Name of the adapter that failed
            model_name: Model name for the adapter
            original_error: The original error that caused the failure
            **kwargs: Additional adapter arguments
            
        Returns:
            Fallback TokenizerAdapter instance
            
        Raises:
            Original error if no graceful degradation is possible
        """
        # Find suitable fallback adapter
        fallback_adapter = self._error_recovery.suggest_fallback_adapter(
            failed_adapter, 
            [name for name in self._fallback_chain if name != failed_adapter]
        )
        
        if not fallback_adapter:
            logger.error(f"No fallback adapter available for {failed_adapter}")
            raise original_error
        
        try:
            # Create fallback adapter with simplified configuration
            fallback_class, fallback_defaults = self._adapters[fallback_adapter]
            
            # Use fallback-specific defaults, but preserve essential kwargs
            fallback_kwargs = {**fallback_defaults}
            
            # Preserve max_tokens if specified
            if "max_tokens" in kwargs:
                fallback_kwargs["max_tokens"] = kwargs["max_tokens"]
            
            # For heuristic fallback, use conservative settings
            if fallback_adapter == "heuristic":
                if "chars_per_token" in kwargs:
                    fallback_kwargs["chars_per_token"] = kwargs["chars_per_token"]
                else:
                    fallback_kwargs.setdefault("chars_per_token", 4.0)
            
            fallback_instance = fallback_class(model_name, **fallback_kwargs)
            
            # Test the fallback adapter
            test_result = fallback_instance.count_tokens("test")
            if test_result.count < 0:
                raise ValueError("Fallback adapter returned negative token count")
            
            # Notify user about graceful degradation
            logger.info(
                f"Gracefully degraded from {failed_adapter} to {fallback_adapter} adapter "
                f"for model {model_name}. Accuracy may be reduced."
            )
            
            # Log the degradation for monitoring
            self._log_degradation_event(failed_adapter, fallback_adapter, model_name, original_error)
            
            return fallback_instance
            
        except Exception as fallback_error:
            logger.error(f"Fallback adapter {fallback_adapter} also failed: {fallback_error}")
            
            # If fallback also fails, try heuristic as last resort
            if fallback_adapter != "heuristic" and "heuristic" in self._adapters:
                try:
                    heuristic_class, heuristic_defaults = self._adapters["heuristic"]
                    heuristic_kwargs = {**heuristic_defaults}
                    
                    if "max_tokens" in kwargs:
                        heuristic_kwargs["max_tokens"] = kwargs["max_tokens"]
                    
                    if "chars_per_token" in kwargs:
                        heuristic_kwargs["chars_per_token"] = kwargs["chars_per_token"]
                    
                    heuristic_instance = heuristic_class(model_name, **heuristic_kwargs)
                    
                    # Test heuristic adapter
                    test_result = heuristic_instance.count_tokens("test")
                    if test_result.count < 0:
                        raise ValueError("Heuristic adapter returned negative token count")
                    
                    logger.warning(
                        f"Emergency fallback to heuristic adapter for model {model_name} "
                        f"after both {failed_adapter} and {fallback_adapter} failed"
                    )
                    
                    self._log_degradation_event(failed_adapter, "heuristic", model_name, original_error)
                    
                    return heuristic_instance
                    
                except Exception as heuristic_error:
                    logger.error(f"Even heuristic fallback failed: {heuristic_error}")
            
            # All fallbacks failed, raise original error
            raise original_error
    
    def _log_degradation_event(
        self, 
        failed_adapter: str, 
        fallback_adapter: str, 
        model_name: str, 
        original_error: Exception
    ) -> None:
        """Log graceful degradation event for monitoring and analysis."""
        degradation_info = {
            "event": "adapter_degradation",
            "failed_adapter": failed_adapter,
            "fallback_adapter": fallback_adapter,
            "model_name": model_name,
            "error_type": type(original_error).__name__,
            "error_message": str(original_error)[:200],  # Truncate long error messages
        }
        
        logger.info(f"Adapter degradation event: {degradation_info}")
        
        # Record in error recovery manager for future decisions
        self._error_recovery.record_degradation_event(
            failed_adapter, fallback_adapter, model_name, original_error
        )
        
        # Could be extended to send to monitoring system
        # self._send_to_monitoring(degradation_info)
    
    def get_recovery_statistics(self) -> Dict[str, Any]:
        """Get recovery and degradation statistics for monitoring.
        
        Returns:
            Dictionary with recovery statistics and health metrics
        """
        return self._error_recovery.get_recovery_statistics()
    
    def suggest_recovery_strategy(self, error: Exception, adapter_name: str, 
                                model_name: str) -> Dict[str, Any]:
        """Get recovery strategy recommendations for a specific error.
        
        Args:
            error: The error that occurred
            adapter_name: Name of the failing adapter
            model_name: Model name involved
            
        Returns:
            Dictionary with recovery strategy recommendations
        """
        return self._error_recovery.suggest_recovery_strategy(error, adapter_name, model_name)
    
    def create_user_notification(self, failed_adapter: str, fallback_adapter: str, 
                               model_name: str, strategy: Dict[str, Any]) -> str:
        """Create user-friendly notification about adapter fallback.
        
        Args:
            failed_adapter: Name of the adapter that failed
            fallback_adapter: Name of the fallback adapter being used
            model_name: Model name involved
            strategy: Recovery strategy from suggest_recovery_strategy
            
        Returns:
            Formatted user notification message
        """
        message_parts = [
            f"⚠️  Tokenizer Adapter Fallback",
            f"   Primary adapter '{failed_adapter}' failed for model '{model_name}'",
            f"   Using fallback adapter '{fallback_adapter}'"
        ]
        
        if strategy.get("user_message"):
            message_parts.extend([
                "",
                f"💡 {strategy['user_message']}"
            ])
        
        if strategy.get("technical_details"):
            message_parts.extend([
                f"🔧 Technical details: {strategy['technical_details']}"
            ])
        
        if strategy.get("retry_recommended"):
            message_parts.extend([
                "",
                "🔄 You can retry after addressing the issue above."
            ])
        
        # Add accuracy warning for heuristic fallback
        if fallback_adapter == "heuristic":
            message_parts.extend([
                "",
                "⚠️  Note: Using approximate tokenization. Results may be less accurate."
            ])
        
        return "\n".join(message_parts)

    def list_adapters(self) -> List[str]:
        """List all registered adapter names."""
        return list(self._adapters.keys())

    def get_fallback_chain(self) -> List[str]:
        """Get current fallback chain."""
        return self._fallback_chain.copy()
    
    def get_adapter_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status information for all registered adapters.
        
        Returns:
            Dictionary mapping adapter names to their status information
        """
        status = {}
        
        for adapter_name in self._adapters.keys():
            try:
                # Try to create adapter with minimal test
                test_adapter = self._create_adapter_with_recovery(
                    adapter_name, "test-model"
                )
                status[adapter_name] = {
                    "available": True,
                    "adapter_id": test_adapter.adapter_id,
                    "error": None
                }
            except Exception as e:
                status[adapter_name] = {
                    "available": False,
                    "adapter_id": adapter_name,
                    "error": str(e)
                }
        
        return status
    
    def suggest_best_adapter(self, model_name: str, 
                           requirements: Optional[Dict[str, Any]] = None) -> str:
        """Suggest the best adapter for a given model and requirements.
        
        Args:
            model_name: Target model name
            requirements: Optional requirements dict with keys like 'accuracy', 'speed'
            
        Returns:
            Recommended adapter name
        """
        requirements = requirements or {}
        
        # Check adapter availability with dependency validation
        status = self.get_adapter_status_with_dependencies()
        available_adapters = [name for name, info in status.items() if info["available"]]
        
        if not available_adapters:
            return "heuristic"  # Always available fallback
        
        # Model-specific recommendations
        if any(openai_model in model_name.lower() for openai_model in 
               ["gpt", "text-embedding", "davinci", "curie", "babbage", "ada"]):
            if "tiktoken" in available_adapters:
                return "tiktoken"
        
        if any(hf_indicator in model_name.lower() for hf_indicator in 
               ["bert", "roberta", "distil", "sentence-transformers", "t5", "bart"]):
            if "huggingface" in available_adapters:
                return "huggingface"
        
        # Requirement-based recommendations
        if requirements.get("accuracy") == "high":
            for adapter in ["tiktoken", "huggingface"]:
                if adapter in available_adapters:
                    return adapter
        
        if requirements.get("speed") == "high":
            if "heuristic" in available_adapters:
                return "heuristic"
        
        # Default to first available in fallback chain
        for adapter in self._fallback_chain:
            if adapter in available_adapters:
                return adapter
        
        return "heuristic"  # Final fallback
    
    def get_adapter_status_with_dependencies(self) -> Dict[str, Dict[str, Any]]:
        """Get status information for all registered adapters including dependency checks.
        
        Returns:
            Dictionary mapping adapter names to their status information with dependency details
        """
        status = {}
        
        for adapter_name in self._adapters.keys():
            try:
                # Check dependencies first
                is_ready, missing_deps, issues = self._dependency_manager.check_adapter_readiness(adapter_name)
                
                if not is_ready:
                    status[adapter_name] = {
                        "available": False,
                        "adapter_id": adapter_name,
                        "error": f"Missing dependencies: {', '.join(missing_deps)}",
                        "missing_dependencies": missing_deps,
                        "dependency_issues": issues,
                        "dependency_ready": False
                    }
                    continue
                
                # Try to create adapter with minimal test
                test_adapter = self._create_adapter_with_recovery(
                    adapter_name, "test-model"
                )
                status[adapter_name] = {
                    "available": True,
                    "adapter_id": test_adapter.adapter_id,
                    "error": None,
                    "missing_dependencies": [],
                    "dependency_issues": [],
                    "dependency_ready": True
                }
            except Exception as e:
                # Get dependency status for better error reporting
                is_ready, missing_deps, issues = self._dependency_manager.check_adapter_readiness(adapter_name)
                
                status[adapter_name] = {
                    "available": False,
                    "adapter_id": adapter_name,
                    "error": str(e),
                    "missing_dependencies": missing_deps,
                    "dependency_issues": issues,
                    "dependency_ready": is_ready
                }
        
        return status
    
    def get_dependency_report(self) -> Dict[str, Any]:
        """Get comprehensive dependency report for all tokenizer adapters.
        
        Returns:
            Dictionary with dependency report and adapter-specific information
        """
        dependency_report = self._dependency_manager.check_all_dependencies()
        adapter_status = self.get_adapter_status_with_dependencies()
        
        return {
            "overall_health": dependency_report.overall_health,
            "python_version": dependency_report.python_version,
            "python_compatible": dependency_report.python_compatible,
            "dependencies": {
                name: {
                    "available": status.available,
                    "version": status.version,
                    "version_compatible": status.version_compatible,
                    "version_issues": status.version_issues,
                    "test_passed": status.test_passed,
                    "installation_instructions": status.installation_instructions
                }
                for name, status in dependency_report.dependencies.items()
            },
            "adapters": adapter_status,
            "recommendations": dependency_report.recommendations,
            "missing_dependencies": dependency_report.get_missing_dependencies(),
            "incompatible_dependencies": dependency_report.get_incompatible_dependencies(),
            "failed_tests": dependency_report.get_failed_tests()
        }
    
    def get_installation_guide(self) -> str:
        """Get formatted installation guide for missing dependencies.
        
        Returns:
            Formatted installation guide string
        """
        return self._dependency_manager.get_installation_summary()
    
    def validate_adapter_dependencies(self, adapter_name: str) -> Dict[str, Any]:
        """Validate dependencies for a specific adapter.
        
        Args:
            adapter_name: Name of the adapter to validate
            
        Returns:
            Dictionary with validation results
        """
        if adapter_name not in self._adapters:
            return {
                "valid": False,
                "error": f"Unknown adapter: {adapter_name}",
                "missing_dependencies": [],
                "dependency_issues": [],
                "recommendations": [f"Available adapters: {', '.join(self.list_adapters())}"]
            }
        
        is_ready, missing_deps, issues = self._dependency_manager.check_adapter_readiness(adapter_name)
        
        recommendations = []
        if missing_deps:
            recommendations.append(f"Install missing dependencies: {', '.join(missing_deps)}")
        if issues:
            recommendations.append("Resolve dependency issues listed above")
        if not is_ready:
            recommendations.append(f"Use fallback adapter: {self.suggest_best_adapter('default-model')}")
        
        return {
            "valid": is_ready,
            "error": None if is_ready else f"Dependencies not ready: {', '.join(missing_deps + issues)}",
            "missing_dependencies": missing_deps,
            "dependency_issues": issues,
            "recommendations": recommendations
        }
    
    def _wrap_with_enhancements(
        self, 
        adapter: TokenizerAdapter, 
        cache_config: Optional[Dict[str, Any]] = None,
        was_fallback: bool = False, 
        fallback_from: Optional[str] = None
    ) -> TokenizerAdapter:
        """Wrap adapter with caching and telemetry enhancements.
        
        Args:
            adapter: The tokenizer adapter to wrap
            cache_config: Cache configuration (enabled, max_size, ttl_seconds)
            was_fallback: Whether this adapter was used as a fallback
            fallback_from: Name of the adapter that failed (if fallback)
            
        Returns:
            Enhanced adapter with caching and telemetry
        """
        enhanced_adapter = adapter
        
        # Add caching if enabled
        if cache_config and cache_config.get("enabled", True):
            try:
                cache = get_global_cache(
                    max_size=cache_config.get("max_size", 1000),
                    ttl_seconds=cache_config.get("ttl_seconds")
                )
                enhanced_adapter = CachingTokenizerAdapter(enhanced_adapter, cache)
                logger.debug(f"Added caching to {adapter.adapter_id} adapter")
            except Exception as e:
                logger.warning(f"Failed to add caching to adapter: {e}")
        
        # Add telemetry if available
        enhanced_adapter = self._wrap_with_telemetry(
            enhanced_adapter, was_fallback, fallback_from
        )
        
        return enhanced_adapter
        
    def _wrap_with_telemetry(
        self, 
        adapter: TokenizerAdapter, 
        was_fallback: bool = False, 
        fallback_from: Optional[str] = None
    ) -> TokenizerAdapter:
        """Wrap adapter with telemetry tracking if available.
        
        Args:
            adapter: The tokenizer adapter to wrap
            was_fallback: Whether this adapter was used as a fallback
            fallback_from: Name of the adapter that failed (if fallback)
            
        Returns:
            Telemetry-enabled adapter or original adapter if telemetry unavailable
        """
        if not _TELEMETRY_AVAILABLE:
            return adapter
        
        try:
            # Create telemetry-enabled wrapper
            telemetry_adapter = TelemetryEnabledAdapter(adapter, enable_telemetry=True)
            
            # If this was a fallback, record the fallback information
            if was_fallback and fallback_from:
                # Store fallback context for later use in telemetry
                telemetry_adapter._fallback_context = {
                    "was_fallback": was_fallback,
                    "fallback_from": fallback_from
                }
            
            logger.debug(f"Wrapped {adapter.adapter_id} adapter with telemetry")
            return telemetry_adapter
            
        except Exception as e:
            logger.debug(f"Failed to wrap adapter with telemetry: {e}")
            return adapter  # Return original adapter if telemetry wrapping fails


# Global registry instance
_default_registry = TokenizerRegistry()


def resolve_tokenizer(
    adapter_name: str,
    model_name: str,
    max_tokens: Optional[int] = None,
    registry: Optional[TokenizerRegistry] = None,
) -> TokenizerAdapter:
    """Resolve a tokenizer adapter by name.
    
    Args:
        adapter_name: Name of the adapter to resolve
        model_name: Model name for the adapter
        max_tokens: Optional max tokens override
        registry: Optional registry instance (uses default if None)
        
    Returns:
        Configured TokenizerAdapter instance
        
    Raises:
        ValueError: If adapter_name is unknown
        ImportError: If required dependencies are missing
    """
    if registry is None:
        registry = _default_registry
    
    adapter_name_clean = adapter_name.lower().strip()
    
    # Handle "auto" - use fallback chain
    if adapter_name_clean == "auto":
        return registry.resolve(
            adapter_name=None,  # Use fallback chain
            model_name=model_name,
            max_tokens=max_tokens
        )
    
    # For specific adapter names, try direct resolution without fallback
    # to maintain backward compatibility with error handling
    if adapter_name_clean in registry.list_adapters():
        try:
            return registry._create_adapter(
                adapter_name_clean,
                model_name,
                max_tokens
            )
        except ImportError:
            # Re-raise ImportError for backward compatibility
            raise
        except Exception as e:
            # Convert other exceptions to ValueError for backward compatibility
            raise ValueError(f"Failed to create {adapter_name} adapter: {e}")
    
    # Unknown adapter - raise ValueError for backward compatibility
    raise ValueError(f"Unknown tokenizer adapter: {adapter_name}")


def get_default_registry() -> TokenizerRegistry:
    """Get the default tokenizer registry instance."""
    return _default_registry


def resolve_tokenizer_with_fallback(
    adapter_name: Optional[str] = None,
    model_name: str = "default-model",
    max_tokens: Optional[int] = None,
    registry: Optional[TokenizerRegistry] = None,
    **kwargs: Any
) -> TokenizerAdapter:
    """Resolve tokenizer with full fallback chain support.
    
    This is the enhanced version that supports fallback chains and
    graceful degradation. Use this for new code that wants the full
    registry functionality.
    
    Args:
        adapter_name: Specific adapter name, or None for auto-resolution
        model_name: Model name for the adapter
        max_tokens: Optional max tokens override
        registry: Optional registry instance (uses default if None)
        **kwargs: Additional adapter-specific arguments
        
    Returns:
        Configured TokenizerAdapter instance
        
    Raises:
        RuntimeError: If no adapter can be created
    """
    if registry is None:
        registry = _default_registry
    
    return registry.resolve(
        adapter_name=adapter_name,
        model_name=model_name,
        max_tokens=max_tokens,
        **kwargs
    )
