"""Tests for tokenizer adapter functionality.

This module tests both HeuristicTokenizer and TiktokenAdapter with:
- Adapter resolution and factory functions
- Token counting with various text types
- Fallback behavior for unknown models
- Conditional testing based on tiktoken availability
- New registry system and HuggingFace adapter
"""

import pytest
from typing import Optional
from unittest.mock import Mock, patch

from kano_backlog_core.tokenizer import (
    HeuristicTokenizer,
    TiktokenAdapter,
    HuggingFaceAdapter,
    TokenCount,
    TokenizerAdapter,
    TokenizerRegistry,
    resolve_tokenizer,
    resolve_tokenizer_with_fallback,
    get_default_registry,
    resolve_model_max_tokens,
    DEFAULT_MAX_TOKENS,
    MODEL_MAX_TOKENS,
)
from kano_backlog_core.tokenizer_errors import (
    FallbackChainExhaustedError,
    TokenizationFailedError,
)

# Check if tiktoken is available
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

# Check if transformers is available
try:
    import transformers
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False


class TestHeuristicTokenizer:
    """Test suite for HeuristicTokenizer."""

    def test_heuristic_tokenizer_creation(self) -> None:
        """Test HeuristicTokenizer can be created with valid parameters."""
        tokenizer = HeuristicTokenizer("test-model")
        assert tokenizer.model_name == "test-model"
        assert isinstance(tokenizer, TokenizerAdapter)

    def test_heuristic_tokenizer_creation_with_max_tokens(self) -> None:
        """Test HeuristicTokenizer creation with custom max_tokens."""
        tokenizer = HeuristicTokenizer("test-model", max_tokens=1024)
        assert tokenizer.model_name == "test-model"
        assert tokenizer.max_tokens() == 1024

    def test_heuristic_tokenizer_empty_model_name_raises(self) -> None:
        """Test HeuristicTokenizer raises error for empty model name."""
        with pytest.raises(ValueError, match="model_name must be non-empty"):
            HeuristicTokenizer("")

    @pytest.mark.parametrize("text,expected_min_tokens", [
        ("Hello world", 2),  # At least 2 tokens
        ("Hello, world!", 3),  # Hello, world, ! (adjusted for new algorithm)
        ("", 0),  # Empty text
        ("a", 1),  # Single character
        ("test_function_name", 4),  # Longer text gets more tokens (adjusted)
        ("你好世界", 3),  # CJK characters (roughly 1 token per char, adjusted)
        ("Hello 你好", 2),  # Mixed ASCII and CJK (adjusted)
    ])
    def test_heuristic_token_counting(self, text: str, expected_min_tokens: int) -> None:
        """Test HeuristicTokenizer token counting with various inputs."""
        tokenizer = HeuristicTokenizer("test-model")
        result = tokenizer.count_tokens(text)
        
        assert isinstance(result, TokenCount)
        assert result.count >= expected_min_tokens
        assert result.method == "heuristic"
        assert result.tokenizer_id.startswith("heuristic:test-model:chars_")
        assert result.is_exact is False

    def test_heuristic_tokenizer_none_text_raises(self) -> None:
        """Test HeuristicTokenizer raises error for None text."""
        tokenizer = HeuristicTokenizer("test-model")
        with pytest.raises(TokenizationFailedError, match="text must be a string"):
            tokenizer.count_tokens(None)

    def test_heuristic_max_tokens_default(self) -> None:
        """Test HeuristicTokenizer uses default max tokens for unknown model."""
        tokenizer = HeuristicTokenizer("unknown-model")
        assert tokenizer.max_tokens() == DEFAULT_MAX_TOKENS

    def test_heuristic_max_tokens_known_model(self) -> None:
        """Test HeuristicTokenizer uses known model max tokens."""
        tokenizer = HeuristicTokenizer("text-embedding-3-small")
        assert tokenizer.max_tokens() == MODEL_MAX_TOKENS["text-embedding-3-small"]

    def test_heuristic_max_tokens_override(self) -> None:
        """Test HeuristicTokenizer respects max_tokens override."""
        tokenizer = HeuristicTokenizer("text-embedding-3-small", max_tokens=2048)
        assert tokenizer.max_tokens() == 2048

    def test_heuristic_chars_per_token_configuration(self) -> None:
        """Test HeuristicTokenizer with different chars_per_token ratios."""
        text = "Hello world test"
        
        # Test with default ratio (4.0)
        tokenizer_default = HeuristicTokenizer("test-model")
        result_default = tokenizer_default.count_tokens(text)
        assert tokenizer_default.chars_per_token == 4.0
        
        # Test with higher ratio (more chars per token = fewer tokens)
        tokenizer_high = HeuristicTokenizer("test-model", chars_per_token=6.0)
        result_high = tokenizer_high.count_tokens(text)
        assert tokenizer_high.chars_per_token == 6.0
        
        # Test with lower ratio (fewer chars per token = more tokens)
        tokenizer_low = HeuristicTokenizer("test-model", chars_per_token=2.0)
        result_low = tokenizer_low.count_tokens(text)
        assert tokenizer_low.chars_per_token == 2.0
        
        # Verify the tokenizer_id includes the ratio
        assert "chars_4.0" in result_default.tokenizer_id
        assert "chars_6.0" in result_high.tokenizer_id
        assert "chars_2.0" in result_low.tokenizer_id

    def test_heuristic_chars_per_token_invalid_raises(self) -> None:
        """Test HeuristicTokenizer raises error for invalid chars_per_token."""
        with pytest.raises(ValueError, match="chars_per_token must be positive"):
            HeuristicTokenizer("test-model", chars_per_token=0)
        
        with pytest.raises(ValueError, match="chars_per_token must be positive"):
            HeuristicTokenizer("test-model", chars_per_token=-1.0)

    def test_heuristic_language_detection(self) -> None:
        """Test HeuristicTokenizer language detection behavior."""
        # Pure ASCII text
        ascii_text = "Hello world"
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
        ascii_result = tokenizer.count_tokens(ascii_text)
        
        # Pure CJK text (should have different token density)
        cjk_text = "你好世界"  # 4 characters
        cjk_result = tokenizer.count_tokens(cjk_text)
        
        # CJK should have higher token density (closer to 1 token per character)
        assert cjk_result.count >= 3  # Should be close to 4 tokens for 4 CJK chars
        
        # Mixed text
        mixed_text = "Hello 你好"
        mixed_result = tokenizer.count_tokens(mixed_text)
        assert mixed_result.count >= 2


@pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")
class TestTiktokenAdapter:
    """Test suite for TiktokenAdapter (requires tiktoken)."""

    def test_tiktoken_adapter_creation(self) -> None:
        """Test TiktokenAdapter can be created with valid parameters."""
        tokenizer = TiktokenAdapter("text-embedding-3-small")
        assert tokenizer.model_name == "text-embedding-3-small"
        assert isinstance(tokenizer, TokenizerAdapter)

    def test_tiktoken_adapter_creation_with_max_tokens(self) -> None:
        """Test TiktokenAdapter creation with custom max_tokens."""
        tokenizer = TiktokenAdapter("text-embedding-3-small", max_tokens=1024)
        assert tokenizer.model_name == "text-embedding-3-small"
        assert tokenizer.max_tokens() == 1024

    def test_tiktoken_adapter_empty_model_name_raises(self) -> None:
        """Test TiktokenAdapter raises error for empty model name."""
        with pytest.raises(ValueError, match="model_name must be non-empty"):
            TiktokenAdapter("")

    @pytest.mark.parametrize("text,expected_min_tokens", [
        ("Hello world", 2),  # At least 2 tokens
        ("Hello, world!", 3),  # Punctuation handling
        ("", 0),  # Empty text
        ("a", 1),  # Single character
        ("The quick brown fox jumps over the lazy dog", 8),  # Longer text
    ])
    def test_tiktoken_token_counting(self, text: str, expected_min_tokens: int) -> None:
        """Test TiktokenAdapter token counting with various inputs."""
        tokenizer = TiktokenAdapter("text-embedding-3-small")
        result = tokenizer.count_tokens(text)
        
        assert isinstance(result, TokenCount)
        assert result.count >= expected_min_tokens
        assert result.method == "tiktoken"
        assert result.tokenizer_id == "tiktoken:text-embedding-3-small:cl100k_base"
        assert result.is_exact is True

    def test_tiktoken_none_text_handling(self) -> None:
        """Test TiktokenAdapter handles None text gracefully."""
        tokenizer = TiktokenAdapter("text-embedding-3-small")
        result = tokenizer.count_tokens(None)
        
        assert isinstance(result, TokenCount)
        assert result.count == 0
        assert result.method == "tiktoken"
        assert result.is_exact is True

    def test_tiktoken_fallback_to_cl100k_base(self) -> None:
        """Test TiktokenAdapter falls back to cl100k_base for unknown models."""
        # This should not raise an error even for unknown model names
        tokenizer = TiktokenAdapter("unknown-model-name")
        result = tokenizer.count_tokens("Hello world")
        
        assert isinstance(result, TokenCount)
        assert result.count > 0
        assert result.method == "tiktoken"
        assert result.tokenizer_id == "tiktoken:unknown-model-name:cl100k_base"

    def test_tiktoken_with_custom_encoding(self) -> None:
        """Test TiktokenAdapter with custom encoding."""
        import tiktoken
        custom_encoding = tiktoken.get_encoding("cl100k_base")
        
        tokenizer = TiktokenAdapter("custom-model", encoding=custom_encoding)
        result = tokenizer.count_tokens("Hello world")
        
        assert isinstance(result, TokenCount)
        assert result.count > 0
        assert result.method == "tiktoken"

    def test_tiktoken_encoding_resolution(self) -> None:
        """Test TiktokenAdapter resolves encodings correctly for different models."""
        test_cases = [
            ("gpt-4", "cl100k_base"),
            ("gpt-3.5-turbo", "cl100k_base"),
            ("text-embedding-3-small", "cl100k_base"),
            ("text-davinci-003", "p50k_base"),
            ("code-davinci-002", "p50k_base"),
            ("unknown-model", "cl100k_base"),  # Should fallback to cl100k_base
        ]
        
        for model_name, expected_encoding in test_cases:
            tokenizer = TiktokenAdapter(model_name)
            assert tokenizer.encoding_name == expected_encoding, f"Model {model_name} should use {expected_encoding}"
            
            result = tokenizer.count_tokens("Hello world")
            assert result.tokenizer_id == f"tiktoken:{model_name}:{expected_encoding}"

    def test_tiktoken_expanded_model_support(self) -> None:
        """Test TiktokenAdapter supports expanded model list with correct max tokens."""
        test_cases = [
            ("gpt-4", 8192),
            ("gpt-4-32k", 32768),
            ("gpt-4-turbo", 128000),
            ("gpt-4o", 128000),
            ("gpt-3.5-turbo", 4096),
            ("gpt-3.5-turbo-16k", 16384),
            ("text-davinci-003", 4097),
            ("code-davinci-002", 8001),
        ]
        
        for model_name, expected_max_tokens in test_cases:
            tokenizer = TiktokenAdapter(model_name)
            assert tokenizer.max_tokens() == expected_max_tokens, f"Model {model_name} should have {expected_max_tokens} max tokens"

    def test_tiktoken_max_tokens_default(self) -> None:
        """Test TiktokenAdapter uses default max tokens for unknown model."""
        tokenizer = TiktokenAdapter("unknown-model")
        assert tokenizer.max_tokens() == DEFAULT_MAX_TOKENS

    def test_tiktoken_max_tokens_known_model(self) -> None:
        """Test TiktokenAdapter uses known model max tokens."""
        tokenizer = TiktokenAdapter("text-embedding-3-small")
        assert tokenizer.max_tokens() == MODEL_MAX_TOKENS["text-embedding-3-small"]

    def test_tiktoken_max_tokens_override(self) -> None:
        """Test TiktokenAdapter respects max_tokens override."""
        tokenizer = TiktokenAdapter("text-embedding-3-small", max_tokens=2048)
        assert tokenizer.max_tokens() == 2048


@pytest.mark.skipif(not TRANSFORMERS_AVAILABLE, reason="transformers not installed")
class TestHuggingFaceAdapter:
    """Test suite for HuggingFaceAdapter (requires transformers)."""

    def test_huggingface_adapter_creation(self) -> None:
        """Test HuggingFaceAdapter can be created with valid parameters."""
        # Use a small model that should be available
        tokenizer = HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2")
        assert tokenizer.model_name == "sentence-transformers/all-MiniLM-L6-v2"
        assert isinstance(tokenizer, TokenizerAdapter)
        assert tokenizer.adapter_id == "huggingface"

    def test_huggingface_adapter_creation_with_max_tokens(self) -> None:
        """Test HuggingFaceAdapter creation with custom max_tokens."""
        tokenizer = HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2", max_tokens=1024)
        assert tokenizer.model_name == "sentence-transformers/all-MiniLM-L6-v2"
        assert tokenizer.max_tokens() == 1024

    def test_huggingface_adapter_empty_model_name_raises(self) -> None:
        """Test HuggingFaceAdapter raises error for empty model name."""
        with pytest.raises(ValueError, match="model_name must be non-empty"):
            HuggingFaceAdapter("")

    @pytest.mark.parametrize("text,expected_min_tokens", [
        ("Hello world", 2),  # At least 2 tokens
        ("Hello, world!", 3),  # Punctuation handling
        ("", 0),  # Empty text
        ("a", 1),  # Single character
        ("The quick brown fox jumps over the lazy dog", 8),  # Longer text
    ])
    def test_huggingface_token_counting(self, text: str, expected_min_tokens: int) -> None:
        """Test HuggingFaceAdapter token counting with various inputs."""
        tokenizer = HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2")
        result = tokenizer.count_tokens(text)
        
        assert isinstance(result, TokenCount)
        assert result.count >= expected_min_tokens
        assert result.method in ["huggingface", "huggingface_fallback"]
        assert result.tokenizer_id.startswith("huggingface")
        assert result.model_max_tokens is not None

    def test_huggingface_none_text_handling(self) -> None:
        """Test HuggingFaceAdapter handles None text gracefully."""
        tokenizer = HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2")
        result = tokenizer.count_tokens(None)
        
        assert isinstance(result, TokenCount)
        assert result.count == 0
        assert result.method == "huggingface"
        assert result.is_exact is True

    def test_huggingface_max_tokens_default(self) -> None:
        """Test HuggingFaceAdapter uses default max tokens for unknown model."""
        # This test might fail if the model is not in MODEL_MAX_TOKENS
        tokenizer = HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2")
        max_tokens = tokenizer.max_tokens()
        assert max_tokens > 0  # Should have some reasonable default

    def test_huggingface_max_tokens_override(self) -> None:
        """Test HuggingFaceAdapter respects max_tokens override."""
        tokenizer = HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2", max_tokens=2048)
        assert tokenizer.max_tokens() == 2048

    def test_huggingface_model_validation(self) -> None:
        """Test HuggingFaceAdapter validates model names."""
        # Valid model names should work
        valid_names = [
            "sentence-transformers/all-MiniLM-L6-v2",
            "bert-base-uncased",
            "microsoft/DialoGPT-medium",
            "facebook/bart-base",
            "t5-small"
        ]
        
        for model_name in valid_names:
            try:
                # This will fail due to missing transformers, but should pass validation
                HuggingFaceAdapter(model_name)
            except ImportError:
                pass  # Expected when transformers not available
            except ValueError as e:
                if "Invalid HuggingFace model name format" in str(e):
                    pytest.fail(f"Valid model name {model_name} was rejected")

    def test_huggingface_invalid_model_names(self) -> None:
        """Test HuggingFaceAdapter rejects invalid model names."""
        invalid_names = [
            "",  # Empty string
            "   ",  # Whitespace only
            "invalid/model/with/too/many/slashes",
            "model-with-@-symbol",
            "model with spaces",
        ]
        
        for model_name in invalid_names:
            try:
                HuggingFaceAdapter(model_name)
                pytest.fail(f"Invalid model name {model_name} was accepted")
            except (ValueError, ImportError) as e:
                if isinstance(e, ValueError) and (
                    "Invalid HuggingFace model name format" in str(e)
                    or "model_name must be non-empty" in str(e)
                ):
                    continue  # Expected validation error
                elif isinstance(e, ImportError):
                    # If transformers not available, we can't test validation
                    # but the model name validation should happen first
                    continue
                else:
                    pytest.fail(f"Unexpected error for {model_name}: {e}")

    def test_huggingface_get_model_info(self) -> None:
        """Test HuggingFaceAdapter get_model_info method."""
        try:
            tokenizer = HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2")
            info = tokenizer.get_model_info()
            
            assert isinstance(info, dict)
            assert info["model_name"] == "sentence-transformers/all-MiniLM-L6-v2"
            assert info["adapter_id"] == "huggingface"
            assert "max_tokens" in info
            assert info["max_tokens"] > 0
            
            # If transformers is available, should have more detailed info
            if "error" not in info:
                assert "vocab_size" in info
                assert "tokenizer_type" in info
                assert "special_tokens" in info
                
        except ImportError:
            # If transformers not available, test the error case
            try:
                tokenizer = HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2")
            except ImportError:
                pass  # Expected


class TestHuggingFaceAdapterWithoutTransformers:
    """Test HuggingFaceAdapter behavior when transformers is not available."""

    @pytest.mark.skipif(TRANSFORMERS_AVAILABLE, reason="transformers is installed")
    def test_huggingface_adapter_import_error(self) -> None:
        """Test HuggingFaceAdapter raises ImportError when transformers not available."""
        with pytest.raises(ImportError, match="transformers package required"):
            HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2")

    def test_huggingface_adapter_with_mocked_import_error(self) -> None:
        """Test HuggingFaceAdapter behavior with mocked import error."""
        if not TRANSFORMERS_AVAILABLE:
            with pytest.raises(ImportError, match="transformers package required"):
                HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2")
        else:
            pytest.skip("transformers is available, cannot test import error")


class TestTokenizerRegistry:
    """Test suite for TokenizerRegistry."""

    def test_registry_creation(self) -> None:
        """Test TokenizerRegistry can be created and has default adapters."""
        registry = TokenizerRegistry()
        adapters = registry.list_adapters()
        
        assert "heuristic" in adapters
        assert "tiktoken" in adapters
        assert "huggingface" in adapters
        assert len(adapters) >= 3

    def test_registry_register_adapter(self) -> None:
        """Test registering a custom adapter."""
        registry = TokenizerRegistry()
        
        class CustomAdapter(TokenizerAdapter):
            @property
            def adapter_id(self) -> str:
                return "custom"
            
            def count_tokens(self, text: str) -> TokenCount:
                return TokenCount(count=1, method="custom", tokenizer_id="custom", is_exact=False)
            
            def max_tokens(self) -> int:
                return 1000
        
        registry.register("custom", CustomAdapter)
        assert "custom" in registry.list_adapters()

    def test_registry_register_invalid_adapter(self) -> None:
        """Test registering invalid adapter raises error."""
        registry = TokenizerRegistry()
        
        class NotAnAdapter:
            pass
        
        with pytest.raises(ValueError, match="must inherit from TokenizerAdapter"):
            registry.register("invalid", NotAnAdapter)

    def test_registry_register_empty_name(self) -> None:
        """Test registering adapter with empty name raises error."""
        registry = TokenizerRegistry()
        
        with pytest.raises(ValueError, match="Adapter name must be non-empty"):
            registry.register("", HeuristicTokenizer)

    def test_registry_set_fallback_chain(self) -> None:
        """Test setting custom fallback chain."""
        registry = TokenizerRegistry()
        
        new_chain = ["heuristic", "tiktoken"]
        registry.set_fallback_chain(new_chain)
        
        assert registry.get_fallback_chain() == new_chain

    def test_registry_set_invalid_fallback_chain(self) -> None:
        """Test setting fallback chain with unknown adapter raises error."""
        registry = TokenizerRegistry()
        
        with pytest.raises(ValueError, match="Unknown adapter in fallback chain"):
            registry.set_fallback_chain(["unknown_adapter"])

    def test_registry_set_empty_fallback_chain(self) -> None:
        """Test setting empty fallback chain raises error."""
        registry = TokenizerRegistry()
        
        with pytest.raises(ValueError, match="Fallback chain must not be empty"):
            registry.set_fallback_chain([])

    def test_registry_resolve_heuristic(self) -> None:
        """Test resolving heuristic adapter through registry."""
        registry = TokenizerRegistry()
        
        adapter = registry.resolve("heuristic", "test-model")
        assert adapter.adapter_id == "heuristic"
        assert adapter.model_name == "test-model"

    @pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")
    def test_registry_resolve_tiktoken(self) -> None:
        """Test resolving tiktoken adapter through registry."""
        registry = TokenizerRegistry()
        
        adapter = registry.resolve("tiktoken", "text-embedding-3-small")
        assert adapter.adapter_id == "tiktoken"
        assert adapter.model_name == "text-embedding-3-small"

    @pytest.mark.skipif(not TRANSFORMERS_AVAILABLE, reason="transformers not installed")
    def test_registry_resolve_huggingface(self) -> None:
        """Test resolving huggingface adapter through registry."""
        registry = TokenizerRegistry()
        
        adapter = registry.resolve("huggingface", "sentence-transformers/all-MiniLM-L6-v2")
        assert adapter.adapter_id == "huggingface"
        assert adapter.model_name == "sentence-transformers/all-MiniLM-L6-v2"

    def test_registry_resolve_auto_fallback(self) -> None:
        """Test auto-resolution uses fallback chain."""
        registry = TokenizerRegistry()
        
        # Should resolve to first available adapter in fallback chain
        adapter = registry.resolve(None, "test-model")
        assert isinstance(adapter, TokenizerAdapter)
        assert adapter.model_name == "test-model"

    def test_registry_resolve_unknown_adapter(self) -> None:
        """Test resolving unknown adapter with empty fallback chain raises error."""
        # Create a registry with no adapters available.
        empty_registry = TokenizerRegistry()
        empty_registry._adapters.clear()  # Remove all adapters

        with pytest.raises(FallbackChainExhaustedError, match="All tokenizer adapters failed"):
            empty_registry.resolve("unknown_adapter", "test-model")

    def test_registry_resolve_with_max_tokens(self) -> None:
        """Test resolving adapter with max_tokens override."""
        registry = TokenizerRegistry()
        
        adapter = registry.resolve("heuristic", "test-model", max_tokens=2048)
        assert adapter.max_tokens() == 2048

    def test_get_default_registry(self) -> None:
        """Test getting default registry instance."""
        registry = get_default_registry()
        assert isinstance(registry, TokenizerRegistry)
        assert "heuristic" in registry.list_adapters()


class TestResolveTokenizerWithFallback:
    """Test suite for resolve_tokenizer_with_fallback function."""

    def test_resolve_with_fallback_heuristic(self) -> None:
        """Test resolve_tokenizer_with_fallback returns HeuristicTokenizer."""
        tokenizer = resolve_tokenizer_with_fallback("heuristic", "test-model")
        assert tokenizer.adapter_id == "heuristic"
        assert tokenizer.model_name == "test-model"

    def test_resolve_with_fallback_auto(self) -> None:
        """Test resolve_tokenizer_with_fallback with auto resolution."""
        tokenizer = resolve_tokenizer_with_fallback(None, "test-model")
        assert isinstance(tokenizer, TokenizerAdapter)
        assert tokenizer.model_name == "test-model"

    def test_resolve_with_fallback_max_tokens(self) -> None:
        """Test resolve_tokenizer_with_fallback with max_tokens."""
        tokenizer = resolve_tokenizer_with_fallback("heuristic", "test-model", max_tokens=1024)
        assert tokenizer.max_tokens() == 1024

    def test_resolve_with_fallback_custom_registry(self) -> None:
        """Test resolve_tokenizer_with_fallback with custom registry."""
        custom_registry = TokenizerRegistry()
        tokenizer = resolve_tokenizer_with_fallback(
            "heuristic", "test-model", registry=custom_registry
        )
        assert tokenizer.adapter_id == "heuristic"


class TestTiktokenAdapterWithoutTiktoken:
    """Test TiktokenAdapter behavior when tiktoken is not available."""

    @pytest.mark.skipif(TIKTOKEN_AVAILABLE, reason="tiktoken is installed")
    def test_tiktoken_adapter_import_error(self) -> None:
        """Test TiktokenAdapter raises ImportError when tiktoken not available."""
        with pytest.raises(ImportError):
            TiktokenAdapter("text-embedding-3-small")

    def test_tiktoken_adapter_with_mocked_import_error(self) -> None:
        """Test TiktokenAdapter behavior with mocked import error."""
        # Since tiktoken is not available in this environment, 
        # TiktokenAdapter should raise ImportError
        if not TIKTOKEN_AVAILABLE:
            with pytest.raises(ImportError):
                TiktokenAdapter("text-embedding-3-small")
        else:
            pytest.skip("tiktoken is available, cannot test import error")


class TestResolveTokenizer:
    """Test suite for resolve_tokenizer factory function."""

    def test_resolve_heuristic_tokenizer(self) -> None:
        """Test resolve_tokenizer returns HeuristicTokenizer for 'heuristic'."""
        tokenizer = resolve_tokenizer("heuristic", "test-model")
        assert isinstance(tokenizer, HeuristicTokenizer)
        assert tokenizer.model_name == "test-model"

    def test_resolve_heuristic_tokenizer_case_insensitive(self) -> None:
        """Test resolve_tokenizer is case insensitive."""
        tokenizer = resolve_tokenizer("HEURISTIC", "test-model")
        assert isinstance(tokenizer, HeuristicTokenizer)
        
        tokenizer = resolve_tokenizer(" Heuristic ", "test-model")
        assert isinstance(tokenizer, HeuristicTokenizer)

    @pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")
    def test_resolve_tiktoken_adapter(self) -> None:
        """Test resolve_tokenizer returns TiktokenAdapter for 'tiktoken'."""
        tokenizer = resolve_tokenizer("tiktoken", "text-embedding-3-small")
        assert isinstance(tokenizer, TiktokenAdapter)
        assert tokenizer.model_name == "text-embedding-3-small"

    @pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")
    def test_resolve_tiktoken_adapter_case_insensitive(self) -> None:
        """Test resolve_tokenizer is case insensitive for tiktoken."""
        tokenizer = resolve_tokenizer("TIKTOKEN", "text-embedding-3-small")
        assert isinstance(tokenizer, TiktokenAdapter)
        
        tokenizer = resolve_tokenizer(" TikToken ", "text-embedding-3-small")
        assert isinstance(tokenizer, TiktokenAdapter)

    def test_resolve_tokenizer_with_max_tokens(self) -> None:
        """Test resolve_tokenizer passes max_tokens parameter."""
        tokenizer = resolve_tokenizer("heuristic", "test-model", max_tokens=1024)
        assert isinstance(tokenizer, HeuristicTokenizer)
        assert tokenizer.max_tokens() == 1024

    def test_resolve_tokenizer_unknown_adapter_raises(self) -> None:
        """Test resolve_tokenizer raises error for unknown adapter."""
        with pytest.raises(ValueError, match="Unknown tokenizer adapter: unknown"):
            resolve_tokenizer("unknown", "test-model")

    @pytest.mark.skipif(TIKTOKEN_AVAILABLE, reason="tiktoken is installed")
    def test_resolve_tiktoken_without_tiktoken_raises(self) -> None:
        """Test resolve_tokenizer raises ImportError for tiktoken when not available."""
        with pytest.raises(ImportError):
            resolve_tokenizer("tiktoken", "text-embedding-3-small")

    def test_resolve_tokenizer_auto(self) -> None:
        """Test resolve_tokenizer with 'auto' uses fallback chain."""
        tokenizer = resolve_tokenizer("auto", "test-model")
        assert isinstance(tokenizer, TokenizerAdapter)
        assert tokenizer.model_name == "test-model"

    def test_resolve_tokenizer_auto_case_insensitive(self) -> None:
        """Test resolve_tokenizer 'auto' is case insensitive."""
        tokenizer = resolve_tokenizer("AUTO", "test-model")
        assert isinstance(tokenizer, TokenizerAdapter)
        
        tokenizer = resolve_tokenizer(" Auto ", "test-model")
        assert isinstance(tokenizer, TokenizerAdapter)

    @pytest.mark.skipif(not TRANSFORMERS_AVAILABLE, reason="transformers not installed")
    def test_resolve_huggingface_adapter(self) -> None:
        """Test resolve_tokenizer returns HuggingFaceAdapter for 'huggingface'."""
        tokenizer = resolve_tokenizer("huggingface", "sentence-transformers/all-MiniLM-L6-v2")
        assert isinstance(tokenizer, HuggingFaceAdapter)
        assert tokenizer.model_name == "sentence-transformers/all-MiniLM-L6-v2"

    @pytest.mark.skipif(not TRANSFORMERS_AVAILABLE, reason="transformers not installed")
    def test_resolve_huggingface_adapter_case_insensitive(self) -> None:
        """Test resolve_tokenizer is case insensitive for huggingface."""
        tokenizer = resolve_tokenizer("HUGGINGFACE", "sentence-transformers/all-MiniLM-L6-v2")
        assert isinstance(tokenizer, HuggingFaceAdapter)
        
        tokenizer = resolve_tokenizer(" HuggingFace ", "sentence-transformers/all-MiniLM-L6-v2")
        assert isinstance(tokenizer, HuggingFaceAdapter)

    @pytest.mark.skipif(TRANSFORMERS_AVAILABLE, reason="transformers is installed")
    def test_resolve_huggingface_without_transformers_raises(self) -> None:
        """Test resolve_tokenizer raises ImportError for huggingface when not available."""
        with pytest.raises(ImportError):
            resolve_tokenizer("huggingface", "sentence-transformers/all-MiniLM-L6-v2")


class TestResolveModelMaxTokens:
    """Test suite for resolve_model_max_tokens function."""

    def test_resolve_known_model(self) -> None:
        """Test resolve_model_max_tokens returns correct value for known models."""
        for model_name, expected_tokens in MODEL_MAX_TOKENS.items():
            result = resolve_model_max_tokens(model_name)
            assert result == expected_tokens

    def test_resolve_unknown_model_default(self) -> None:
        """Test resolve_model_max_tokens returns default for unknown models."""
        result = resolve_model_max_tokens("unknown-model")
        assert result == DEFAULT_MAX_TOKENS

    def test_resolve_with_overrides(self) -> None:
        """Test resolve_model_max_tokens respects overrides."""
        overrides = {"custom-model": 4096, "text-embedding-3-small": 2048}
        
        # Override for custom model
        result = resolve_model_max_tokens("custom-model", overrides=overrides)
        assert result == 4096
        
        # Override for known model
        result = resolve_model_max_tokens("text-embedding-3-small", overrides=overrides)
        assert result == 2048
        
        # No override, use default
        result = resolve_model_max_tokens("unknown-model", overrides=overrides)
        assert result == DEFAULT_MAX_TOKENS

    def test_resolve_with_custom_default(self) -> None:
        """Test resolve_model_max_tokens respects custom default."""
        result = resolve_model_max_tokens("unknown-model", default=16384)
        assert result == 16384

    def test_resolve_empty_overrides(self) -> None:
        """Test resolve_model_max_tokens handles empty overrides."""
        result = resolve_model_max_tokens("text-embedding-3-small", overrides={})
        assert result == MODEL_MAX_TOKENS["text-embedding-3-small"]


class TestHuggingFaceUtilities:
    """Test suite for HuggingFace utility functions."""

    def test_get_supported_huggingface_models(self) -> None:
        """Test get_supported_huggingface_models returns expected models."""
        from kano_backlog_core.tokenizer import get_supported_huggingface_models
        
        models = get_supported_huggingface_models()
        assert isinstance(models, list)
        assert len(models) > 0
        
        # Should include sentence-transformers models
        sentence_transformers_models = [m for m in models if m.startswith('sentence-transformers/')]
        assert len(sentence_transformers_models) > 0
        
        # Should include BERT models
        bert_models = [m for m in models if m.startswith('bert-')]
        assert len(bert_models) > 0
        
        # Should include specific known models
        assert "sentence-transformers/all-MiniLM-L6-v2" in models
        assert "bert-base-uncased" in models

    def test_is_sentence_transformers_model(self) -> None:
        """Test is_sentence_transformers_model correctly identifies models."""
        from kano_backlog_core.tokenizer import is_sentence_transformers_model
        
        # Should return True for sentence-transformers models
        assert is_sentence_transformers_model("sentence-transformers/all-MiniLM-L6-v2")
        assert is_sentence_transformers_model("sentence-transformers/all-mpnet-base-v2")
        
        # Should return False for other models
        assert not is_sentence_transformers_model("bert-base-uncased")
        assert not is_sentence_transformers_model("microsoft/DialoGPT-medium")
        assert not is_sentence_transformers_model("gpt-4")
        assert not is_sentence_transformers_model("")

    def test_suggest_huggingface_model(self) -> None:
        """Test suggest_huggingface_model returns appropriate models."""
        from kano_backlog_core.tokenizer import suggest_huggingface_model
        
        # Test different task types
        embedding_model = suggest_huggingface_model("embedding")
        assert embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
        
        semantic_model = suggest_huggingface_model("semantic_search")
        assert semantic_model == "sentence-transformers/all-mpnet-base-v2"
        
        classification_model = suggest_huggingface_model("classification")
        assert classification_model == "bert-base-uncased"
        
        generation_model = suggest_huggingface_model("generation")
        assert generation_model == "t5-base"
        
        qa_model = suggest_huggingface_model("question_answering")
        assert qa_model == "bert-large-uncased"
        
        # Test unknown task type (should return default)
        unknown_model = suggest_huggingface_model("unknown_task")
        assert unknown_model == "sentence-transformers/all-MiniLM-L6-v2"
        
        # Test default case
        default_model = suggest_huggingface_model()
        assert default_model == "sentence-transformers/all-MiniLM-L6-v2"


class TestTokenizerIntegration:
    """Integration tests for tokenizer adapters."""

    def test_heuristic_vs_tiktoken_consistency(self) -> None:
        """Test that both tokenizers handle the same text consistently."""
        text = "This is a test sentence for tokenizer comparison."
        
        heuristic = HeuristicTokenizer("test-model")
        heuristic_result = heuristic.count_tokens(text)
        
        if TIKTOKEN_AVAILABLE:
            tiktoken_adapter = TiktokenAdapter("text-embedding-3-small")
            tiktoken_result = tiktoken_adapter.count_tokens(text)
            
            # Both should return positive token counts
            assert heuristic_result.count > 0
            assert tiktoken_result.count > 0
            
            # Methods should be different
            assert heuristic_result.method != tiktoken_result.method
            assert heuristic_result.is_exact != tiktoken_result.is_exact

    def test_deterministic_token_counting(self) -> None:
        """Test that token counting is deterministic."""
        text = "Deterministic test text for tokenizer validation."
        
        tokenizer = HeuristicTokenizer("test-model")
        
        # Multiple calls should return identical results
        result1 = tokenizer.count_tokens(text)
        result2 = tokenizer.count_tokens(text)
        
        assert result1.count == result2.count
        assert result1.method == result2.method
        assert result1.tokenizer_id == result2.tokenizer_id
        assert result1.is_exact == result2.is_exact

    @pytest.mark.parametrize("adapter_name,model_name", [
        ("heuristic", "any-model"),
        ("heuristic", "text-embedding-3-small"),
        ("auto", "test-model"),  # Test auto-resolution
        pytest.param("tiktoken", "text-embedding-3-small", 
                    marks=pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")),
        pytest.param("tiktoken", "unknown-model", 
                    marks=pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")),
        pytest.param("huggingface", "sentence-transformers/all-MiniLM-L6-v2", 
                    marks=pytest.mark.skipif(not TRANSFORMERS_AVAILABLE, reason="transformers not installed")),
    ])
    def test_adapter_factory_integration(self, adapter_name: str, model_name: str) -> None:
        """Test adapter factory creates working tokenizers."""
        tokenizer = resolve_tokenizer(adapter_name, model_name)
        
        # Test basic functionality
        result = tokenizer.count_tokens("Hello world")
        assert isinstance(result, TokenCount)
        assert result.count > 0
        assert result.method in ["heuristic", "tiktoken", "huggingface", "huggingface_fallback"]
        assert tokenizer.model_name == model_name
        assert tokenizer.max_tokens() > 0

    def test_registry_fallback_behavior(self) -> None:
        """Test that registry fallback works correctly."""
        registry = TokenizerRegistry()
        
        # Test that auto-resolution works
        adapter = registry.resolve(None, "test-model")
        assert isinstance(adapter, TokenizerAdapter)
        
        # Test that fallback chain is respected
        fallback_chain = registry.get_fallback_chain()
        assert len(fallback_chain) > 0
        assert "heuristic" in fallback_chain  # Should always have heuristic as fallback

    def test_registry_graceful_error_handling(self) -> None:
        """Test registry provides helpful error messages for missing dependencies."""
        registry = TokenizerRegistry()
        
        # Create a custom adapter that always fails with ImportError
        class FailingAdapter(TokenizerAdapter):
            def __init__(self, model_name: str, max_tokens: Optional[int] = None):
                super().__init__(model_name, max_tokens)
                raise ImportError("test dependency not available")
            
            @property
            def adapter_id(self) -> str:
                return "failing"
            
            def count_tokens(self, text: str) -> TokenCount:
                return TokenCount(0, "failing", "failing", False)
            
            def max_tokens(self) -> int:
                return 1000
        
        registry.register("failing", FailingAdapter)
        registry.set_fallback_chain(["failing", "heuristic"])
        
        # Should fall back to heuristic with appropriate logging
        tokenizer = registry.resolve("failing", "test-model")
        assert tokenizer.adapter_id == "heuristic"

    def test_enhanced_token_count_metadata(self) -> None:
        """Test that TokenCount includes enhanced metadata."""
        tokenizer = HeuristicTokenizer("test-model")
        result = tokenizer.count_tokens("Hello world")
        
        assert isinstance(result, TokenCount)
        assert result.count > 0
        assert result.method == "heuristic"
        assert result.tokenizer_id.startswith("heuristic:test-model:chars_")
        assert result.is_exact is False
        assert result.model_max_tokens is not None
        assert result.model_max_tokens > 0


if __name__ == "__main__":
    pytest.main([__file__])
