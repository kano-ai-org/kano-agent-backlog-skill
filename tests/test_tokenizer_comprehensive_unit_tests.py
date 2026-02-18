"""Comprehensive unit test suite for tokenizer adapters.

This module provides comprehensive unit tests that focus on:
1. Testing each adapter implementation independently with proper isolation
2. Using mocking for external dependencies to ensure reliable, fast testing
3. Covering error conditions and edge cases thoroughly
4. Validating configuration parsing and validation logic
5. Ensuring high test coverage for all implemented functionality

This complements the existing test files by providing more focused unit tests
with extensive mocking and edge case coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock, call
from typing import Any, Dict, List, Optional
import sys
import importlib

from kano_backlog_core.tokenizer import (
    TokenizerAdapter,
    HeuristicTokenizer,
    TiktokenAdapter,
    HuggingFaceAdapter,
    TokenCount,
    TokenizerRegistry,
    resolve_tokenizer,
    resolve_model_max_tokens,
    MODEL_MAX_TOKENS,
    DEFAULT_MAX_TOKENS,
)
from kano_backlog_core.tokenizer_errors import (
    TokenizerError,
    AdapterNotAvailableError,
    DependencyMissingError,
    TokenizationFailedError,
    FallbackChainExhaustedError,
    ErrorRecoveryManager,
)
from kano_backlog_core.tokenizer_config import (
    TokenizerConfig,
    TokenizerConfigLoader,
    load_tokenizer_config,
)


class TestHeuristicTokenizerIsolated:
    """Isolated unit tests for HeuristicTokenizer with comprehensive edge cases."""
    
    def test_initialization_with_valid_parameters(self):
        """Test HeuristicTokenizer initialization with various valid parameters."""
        # Test with minimal parameters
        tokenizer = HeuristicTokenizer("test-model")
        assert tokenizer.model_name == "test-model"
        assert tokenizer.adapter_id == "heuristic"
        assert tokenizer.chars_per_token == 4.0
        
        # Test with custom chars_per_token
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=3.5)
        assert tokenizer.chars_per_token == 3.5
        
        # Test with max_tokens
        tokenizer = HeuristicTokenizer("test-model", max_tokens=2048)
        assert tokenizer.max_tokens() == 2048
        
        # Test with all parameters
        tokenizer = HeuristicTokenizer("test-model", max_tokens=1024, chars_per_token=5.0)
        assert tokenizer.max_tokens() == 1024
        assert tokenizer.chars_per_token == 5.0
    
    def test_initialization_edge_cases(self):
        """Test HeuristicTokenizer initialization edge cases and error conditions."""
        # Test empty model name
        with pytest.raises(ValueError, match="model_name must be non-empty"):
            HeuristicTokenizer("")
        
        # Test None model name
        with pytest.raises(ValueError, match="model_name must be non-empty"):
            HeuristicTokenizer(None)
        
        # Test invalid chars_per_token values
        with pytest.raises(ValueError, match="chars_per_token must be positive"):
            HeuristicTokenizer("test-model", chars_per_token=0)
        
        with pytest.raises(ValueError, match="chars_per_token must be positive"):
            HeuristicTokenizer("test-model", chars_per_token=-1.5)
        
        # Test very small positive chars_per_token (should work)
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=0.1)
        assert tokenizer.chars_per_token == 0.1
    
    @pytest.mark.parametrize("text,expected_behavior", [
        ("", 0),  # Empty string
        ("a", 1),  # Single character
        ("ab", 1),  # Two characters (should still be 1 token with default ratio)
        ("hello", 1),  # Short word
        ("hello world", 2),  # Two words
        ("The quick brown fox", 4),  # Multiple words
        ("   ", 1),  # Whitespace only
        ("hello\nworld", 2),  # With newline
        ("hello\tworld", 2),  # With tab
        ("hello,world!", 3),  # With punctuation
        ("你好", 2),  # CJK characters (should be ~1 token each)
        ("Hello 你好", 2),  # Mixed ASCII and CJK
        ("你好世界测试", 4),  # Multiple CJK characters
        ("!@#$%^&*()", 5),  # Special characters only
        ("123456789", 2),  # Numbers
        ("test_function_name", 4),  # Underscore separated
        ("camelCaseFunction", 4),  # CamelCase
    ])
    def test_token_counting_comprehensive(self, text: str, expected_behavior: int):
        """Test token counting with comprehensive text variations."""
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
        result = tokenizer.count_tokens(text)
        
        assert isinstance(result, TokenCount)
        assert result.count >= 0
        assert result.method == "heuristic"
        assert result.tokenizer_id == "heuristic:test-model:chars_4.0"
        assert result.is_exact is False
        assert result.model_max_tokens is not None
        
        # For empty string, should be exactly 0
        if text == "":
            assert result.count == 0
        else:
            # For non-empty text, should be at least 1
            assert result.count >= 1
    
    def test_token_counting_error_conditions(self):
        """Test token counting error conditions and edge cases."""
        tokenizer = HeuristicTokenizer("test-model")
        
        # Test None input
        with pytest.raises(TokenizationFailedError) as exc_info:
            tokenizer.count_tokens(None)
        
        error = exc_info.value
        assert error.adapter_name == "heuristic"
        assert error.model_name == "test-model"
        assert "text must be a string" in str(error)
    
    def test_language_detection_behavior(self):
        """Test language detection and adaptive token estimation."""
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
        
        # Pure ASCII text
        ascii_result = tokenizer.count_tokens("Hello world test")
        
        # Pure CJK text (should have different density)
        cjk_result = tokenizer.count_tokens("你好世界")
        
        # Mixed text
        mixed_result = tokenizer.count_tokens("Hello 你好")
        
        # All should return valid results
        assert ascii_result.count > 0
        assert cjk_result.count > 0
        assert mixed_result.count > 0
        
        # CJK should generally have higher token density (more tokens per character)
        # This is a heuristic test, so we just verify reasonable behavior
        assert cjk_result.count >= 3  # 4 CJK chars should be at least 3 tokens
    
    def test_max_tokens_resolution(self):
        """Test max tokens resolution with various scenarios."""
        # Test with known model
        tokenizer = HeuristicTokenizer("text-embedding-3-small")
        assert tokenizer.max_tokens() == MODEL_MAX_TOKENS["text-embedding-3-small"]
        
        # Test with unknown model
        tokenizer = HeuristicTokenizer("unknown-model")
        assert tokenizer.max_tokens() == DEFAULT_MAX_TOKENS
        
        # Test with override
        tokenizer = HeuristicTokenizer("text-embedding-3-small", max_tokens=1024)
        assert tokenizer.max_tokens() == 1024
        
        # Test with None override (should use model default)
        tokenizer = HeuristicTokenizer("text-embedding-3-small", max_tokens=None)
        assert tokenizer.max_tokens() == MODEL_MAX_TOKENS["text-embedding-3-small"]
    
    def test_chars_per_token_variations(self):
        """Test different chars_per_token ratios produce expected relative results."""
        text = "This is a test sentence for ratio comparison"
        
        # Test different ratios
        tokenizer_low = HeuristicTokenizer("test-model", chars_per_token=2.0)
        tokenizer_medium = HeuristicTokenizer("test-model", chars_per_token=4.0)
        tokenizer_high = HeuristicTokenizer("test-model", chars_per_token=8.0)
        
        result_low = tokenizer_low.count_tokens(text)
        result_medium = tokenizer_medium.count_tokens(text)
        result_high = tokenizer_high.count_tokens(text)
        
        # Lower ratio should produce more tokens
        assert result_low.count >= result_medium.count
        assert result_medium.count >= result_high.count
        
        # Verify tokenizer_id reflects the ratio
        assert "chars_2.0" in result_low.tokenizer_id
        assert "chars_4.0" in result_medium.tokenizer_id
        assert "chars_8.0" in result_high.tokenizer_id


class TestTiktokenAdapterMocked:
    """Isolated unit tests for TiktokenAdapter with comprehensive mocking."""
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_initialization_with_mocked_tiktoken(self, mock_tiktoken):
        """Test TiktokenAdapter initialization with mocked tiktoken."""
        # Mock encoding
        mock_encoding = Mock()
        mock_encoding.name = "cl100k_base"
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        # Test basic initialization
        adapter = TiktokenAdapter("gpt-4")
        assert adapter.model_name == "gpt-4"
        assert adapter.adapter_id == "tiktoken"
        assert adapter.encoding_name == "cl100k_base"
        
        # Verify tiktoken was called correctly
        mock_tiktoken.get_encoding.assert_called_once_with("cl100k_base")
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_initialization_with_custom_encoding(self, mock_tiktoken):
        """Test TiktokenAdapter initialization with custom encoding."""
        # Mock custom encoding
        mock_encoding = Mock()
        mock_encoding.name = "custom_encoding"
        
        # Test with direct encoding object
        adapter = TiktokenAdapter("test-model", encoding=mock_encoding)
        assert adapter.encoding_name == "custom_encoding"
        
        # Should not call get_encoding when encoding is provided directly
        mock_tiktoken.get_encoding.assert_not_called()
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_initialization_with_encoding_name(self, mock_tiktoken):
        """Test TiktokenAdapter initialization with encoding name parameter."""
        mock_encoding = Mock()
        mock_encoding.name = "p50k_base"
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        adapter = TiktokenAdapter("test-model", encoding_name="p50k_base")
        assert adapter.encoding_name == "p50k_base"
        
        mock_tiktoken.get_encoding.assert_called_once_with("p50k_base")
    
    def test_initialization_without_tiktoken(self):
        """Test TiktokenAdapter initialization when tiktoken is not available."""
        with patch("kano_backlog_core.tokenizer.tiktoken", None):
            with pytest.raises(ImportError, match="tiktoken package required"):
                TiktokenAdapter("gpt-4")
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_encoding_resolution_comprehensive(self, mock_tiktoken):
        """Test encoding resolution for various models."""
        # Mock encoding_for_model to work for some models and fail for others
        def mock_encoding_for_model(model_name):
            if model_name in ["gpt-4", "gpt-3.5-turbo"]:
                mock_enc = Mock()
                mock_enc.name = "cl100k_base"
                return mock_enc
            else:
                raise KeyError(f"Model {model_name} not found")
        
        mock_tiktoken.encoding_for_model.side_effect = mock_encoding_for_model
        
        # Mock get_encoding for fallback scenarios
        def mock_get_encoding(encoding_name):
            mock_enc = Mock()
            mock_enc.name = encoding_name
            return mock_enc
        
        mock_tiktoken.get_encoding.side_effect = mock_get_encoding
        
        # Test known model (should use encoding_for_model)
        adapter = TiktokenAdapter("gpt-4")
        assert adapter.encoding_name == "cl100k_base"
        mock_tiktoken.encoding_for_model.assert_called_with("gpt-4")
        
        # Reset mocks
        mock_tiktoken.reset_mock()
        
        # Test model in our mapping but not in tiktoken's registry
        adapter = TiktokenAdapter("text-davinci-003")
        # Should fall back to our mapping (p50k_base)
        mock_tiktoken.get_encoding.assert_called_with("p50k_base")
        
        # Reset mocks
        mock_tiktoken.reset_mock()
        
        # Test completely unknown model
        adapter = TiktokenAdapter("unknown-model")
        # Should fall back to cl100k_base
        calls = mock_tiktoken.get_encoding.call_args_list
        assert any(call[0][0] == "cl100k_base" for call in calls)
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_token_counting_comprehensive(self, mock_tiktoken):
        """Test token counting with comprehensive scenarios."""
        # Mock encoding and its encode method
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        # Test normal text
        mock_encoding.encode.return_value = [1, 2, 3, 4, 5]
        adapter = TiktokenAdapter("gpt-4")
        result = adapter.count_tokens("Hello world")
        
        assert result.count == 5
        assert result.method == "tiktoken"
        assert result.is_exact is True
        assert "tiktoken:gpt-4:cl100k_base" in result.tokenizer_id
        
        # Verify encode was called with correct parameters
        mock_encoding.encode.assert_called_once_with("Hello world", disallowed_special=())
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_token_counting_edge_cases(self, mock_tiktoken):
        """Test token counting edge cases."""
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding
        adapter = TiktokenAdapter("gpt-4")
        
        # Test empty string
        mock_encoding.encode.return_value = []
        result = adapter.count_tokens("")
        assert result.count == 0
        
        # Test None input (should return 0 gracefully)
        result = adapter.count_tokens(None)
        assert result.count == 0
        assert result.method == "tiktoken"
        assert result.is_exact is True
        
        # Test very long text
        mock_encoding.encode.return_value = list(range(10000))
        result = adapter.count_tokens("very long text" * 1000)
        assert result.count == 10000
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_token_counting_error_handling(self, mock_tiktoken):
        """Test token counting error handling."""
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding
        adapter = TiktokenAdapter("gpt-4")
        
        # Test encoding error
        mock_encoding.encode.side_effect = ValueError("Invalid text encoding")
        
        with pytest.raises(TokenizationFailedError) as exc_info:
            adapter.count_tokens("problematic text")
        
        error = exc_info.value
        assert error.adapter_name == "tiktoken"
        assert error.model_name == "gpt-4"
        assert "Invalid text encoding" in str(error.original_error)
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_encoding_fallback_chain(self, mock_tiktoken):
        """Test encoding fallback chain when multiple encodings fail."""
        # Mock encoding_for_model to fail
        mock_tiktoken.encoding_for_model.side_effect = KeyError("Model not found")
        
        # Mock get_encoding to fail for some encodings
        def mock_get_encoding(encoding_name):
            if encoding_name == "cl100k_base":
                raise Exception("cl100k_base failed")
            elif encoding_name == "p50k_base":
                mock_enc = Mock()
                mock_enc.name = "p50k_base"
                return mock_enc
            else:
                raise Exception(f"Encoding {encoding_name} failed")
        
        mock_tiktoken.get_encoding.side_effect = mock_get_encoding
        
        # Should fall back to p50k_base
        adapter = TiktokenAdapter("unknown-model")
        assert adapter.encoding_name == "p50k_base"
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_encoding_complete_failure(self, mock_tiktoken):
        """Test behavior when all encoding attempts fail."""
        # Mock all encoding methods to fail
        mock_tiktoken.encoding_for_model.side_effect = KeyError("Model not found")
        mock_tiktoken.get_encoding.side_effect = Exception("All encodings failed")
        
        with pytest.raises(RuntimeError, match="Failed to load any tiktoken encoding"):
            TiktokenAdapter("unknown-model")


class TestHuggingFaceAdapterMocked:
    """Isolated unit tests for HuggingFaceAdapter with comprehensive mocking."""
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_initialization_with_mocked_transformers(self, mock_transformers):
        """Test HuggingFaceAdapter initialization with mocked transformers."""
        # Mock AutoTokenizer
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        assert adapter.model_name == "bert-base-uncased"
        assert adapter.adapter_id == "huggingface"
        
        # Verify transformers was called correctly
        mock_transformers.AutoTokenizer.from_pretrained.assert_called_once_with(
            "bert-base-uncased",
            use_fast=True,
            trust_remote_code=False
        )
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_initialization_with_custom_options(self, mock_transformers):
        """Test HuggingFaceAdapter initialization with custom options."""
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter(
            "bert-base-uncased",
            use_fast=False,
            trust_remote_code=True
        )
        
        mock_transformers.AutoTokenizer.from_pretrained.assert_called_once_with(
            "bert-base-uncased",
            use_fast=False,
            trust_remote_code=True
        )
    
    def test_initialization_without_transformers(self):
        """Test HuggingFaceAdapter initialization when transformers is not available."""
        with patch('kano_backlog_core.tokenizer.transformers', None):
            with pytest.raises(ImportError, match="transformers package required"):
                HuggingFaceAdapter("bert-base-uncased")
    
    def test_model_name_validation(self):
        """Test model name validation."""
        # Empty/None should fail base adapter validation.
        for invalid_name in ["", None]:
            with pytest.raises(ValueError, match="model_name must be non-empty"):
                HuggingFaceAdapter(invalid_name)

        # Other invalid formats should fail HuggingFace-specific validation.
        invalid_format_names = [
            "   ",  # Whitespace only
            "invalid/model/with/too/many/slashes",
            "model-with-@-symbol",
            "model with spaces",
        ]

        for invalid_name in invalid_format_names:
            with pytest.raises(ValueError, match="Invalid HuggingFace model name format"):
                HuggingFaceAdapter(invalid_name)
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_tokenizer_loading_fallback(self, mock_transformers):
        """Test tokenizer loading with fallback when fast tokenizer fails."""
        # Mock first call to fail, second to succeed
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.side_effect = [
            Exception("Fast tokenizer failed"),
            mock_tokenizer  # Fallback succeeds
        ]
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        
        # Should have been called twice (fast failed, slow succeeded)
        assert mock_transformers.AutoTokenizer.from_pretrained.call_count == 2
        
        # First call with use_fast=True
        first_call = mock_transformers.AutoTokenizer.from_pretrained.call_args_list[0]
        assert first_call[1]["use_fast"] is True
        
        # Second call with use_fast=False
        second_call = mock_transformers.AutoTokenizer.from_pretrained.call_args_list[1]
        assert second_call[1]["use_fast"] is False
        assert second_call[1]["trust_remote_code"] is False
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_tokenizer_loading_complete_failure(self, mock_transformers):
        """Test behavior when tokenizer loading completely fails."""
        mock_transformers.AutoTokenizer.from_pretrained.side_effect = Exception("Complete failure")
        
        with pytest.raises(ValueError, match="Failed to load HuggingFace tokenizer"):
            HuggingFaceAdapter("bert-base-uncased")
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_token_counting_comprehensive(self, mock_transformers):
        """Test token counting with comprehensive scenarios."""
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        
        # Test normal text
        mock_tokenizer.encode.return_value = [101, 7592, 2088, 102]  # [CLS] hello world [SEP]
        result = adapter.count_tokens("hello world")
        
        assert result.count == 4
        assert result.method == "huggingface"
        assert result.is_exact is True
        assert "huggingface:bert-base-uncased" in result.tokenizer_id
        
        # Verify encode was called with add_special_tokens=True
        mock_tokenizer.encode.assert_called_once_with("hello world", add_special_tokens=True)
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_token_counting_edge_cases(self, mock_transformers):
        """Test token counting edge cases."""
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        adapter = HuggingFaceAdapter("bert-base-uncased")
        
        # Test empty string
        mock_tokenizer.encode.return_value = [101, 102]  # Just [CLS] [SEP]
        result = adapter.count_tokens("")
        assert result.count == 2
        
        # Test None input
        result = adapter.count_tokens(None)
        assert result.count == 0
        assert result.method == "huggingface"
        assert result.is_exact is True
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    @patch('kano_backlog_core.tokenizer.token_spans')
    def test_token_counting_with_fallback(self, mock_token_spans, mock_transformers):
        """Test token counting with fallback to heuristic when encoding fails."""
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        adapter = HuggingFaceAdapter("bert-base-uncased")
        
        # Mock encode to fail
        mock_tokenizer.encode.side_effect = Exception("Encoding failed")
        
        # Mock token_spans fallback
        mock_token_spans.return_value = ["hello", "world"]
        
        result = adapter.count_tokens("hello world")
        
        assert result.count == 2
        assert result.method == "huggingface_fallback"
        assert result.is_exact is False
        
        # Verify fallback was used
        mock_token_spans.assert_called_once_with("hello world")
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_token_counting_fallback_failure(self, mock_transformers):
        """Test token counting when both primary and fallback fail."""
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        adapter = HuggingFaceAdapter("bert-base-uncased")
        
        # Mock encode to fail
        mock_tokenizer.encode.side_effect = Exception("Encoding failed")
        
        # Mock token_spans to also fail
        with patch('kano_backlog_core.tokenizer.token_spans', side_effect=Exception("Fallback failed")):
            with pytest.raises(TokenizationFailedError) as exc_info:
                adapter.count_tokens("hello world")
            
            error = exc_info.value
            assert error.adapter_name == "huggingface"
            assert error.model_name == "bert-base-uncased"
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_get_model_info_comprehensive(self, mock_transformers):
        """Test get_model_info method with comprehensive scenarios."""
        mock_tokenizer = Mock()
        mock_tokenizer.vocab_size = 30522
        mock_tokenizer.is_fast = True
        mock_tokenizer.pad_token = "[PAD]"
        mock_tokenizer.unk_token = "[UNK]"
        mock_tokenizer.cls_token = "[CLS]"
        mock_tokenizer.sep_token = "[SEP]"
        mock_tokenizer.mask_token = "[MASK]"
        
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        info = adapter.get_model_info()
        
        assert info["model_name"] == "bert-base-uncased"
        assert info["adapter_id"] == "huggingface"
        assert info["vocab_size"] == 30522
        assert info["tokenizer_type"] == "fast"
        assert info["special_tokens"]["pad_token"] == "[PAD]"
        assert info["special_tokens"]["cls_token"] == "[CLS]"
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_get_model_info_error_handling(self, mock_transformers):
        """Test get_model_info error handling."""
        mock_tokenizer = Mock()
        # Mock vocab_size to raise an exception
        type(mock_tokenizer).vocab_size = PropertyMock(side_effect=Exception("Vocab size error"))
        
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        info = adapter.get_model_info()
        
        assert info["model_name"] == "bert-base-uncased"
        assert info["adapter_id"] == "huggingface"
        assert "error" in info
        assert "Vocab size error" in info["error"]


class TestTokenizerRegistryIsolated:
    """Isolated unit tests for TokenizerRegistry with comprehensive mocking."""
    
    def test_initialization_and_default_adapters(self):
        """Test TokenizerRegistry initialization and default adapter registration."""
        registry = TokenizerRegistry()
        
        adapters = registry.list_adapters()
        assert "heuristic" in adapters
        assert "tiktoken" in adapters
        assert "huggingface" in adapters
        
        fallback_chain = registry.get_fallback_chain()
        assert fallback_chain == ["tiktoken", "huggingface", "heuristic"]
    
    def test_custom_adapter_registration(self):
        """Test registering custom adapters."""
        registry = TokenizerRegistry()
        
        # Create mock custom adapter
        class MockCustomAdapter(TokenizerAdapter):
            def __init__(self, model_name: str, max_tokens: Optional[int] = None, **kwargs):
                super().__init__(model_name, max_tokens)
                self.custom_option = kwargs.get("custom_option", "default")
            
            @property
            def adapter_id(self) -> str:
                return "custom"
            
            def count_tokens(self, text: str) -> TokenCount:
                return TokenCount(
                    count=len(text.split()) if text else 0,
                    method="custom",
                    tokenizer_id=f"custom:{self.model_name}",
                    is_exact=False
                )
            
            def max_tokens(self) -> int:
                return self._max_tokens or 1000
        
        # Register custom adapter
        registry.register("custom", MockCustomAdapter, custom_option="test_value")
        
        assert "custom" in registry.list_adapters()
        
        # Test creating custom adapter
        adapter = registry.resolve("custom", "test-model")
        assert adapter.adapter_id == "custom"
        assert adapter.custom_option == "test_value"
    
    def test_adapter_registration_validation(self):
        """Test adapter registration validation."""
        registry = TokenizerRegistry()
        
        # Test empty name
        with pytest.raises(ValueError, match="Adapter name must be non-empty"):
            registry.register("", HeuristicTokenizer)
        
        # Test invalid adapter class
        class NotAnAdapter:
            pass
        
        with pytest.raises(ValueError, match="must inherit from TokenizerAdapter"):
            registry.register("invalid", NotAnAdapter)
    
    def test_fallback_chain_management(self):
        """Test fallback chain management."""
        registry = TokenizerRegistry()
        
        # Test setting valid fallback chain
        new_chain = ["heuristic", "tiktoken"]
        registry.set_fallback_chain(new_chain)
        assert registry.get_fallback_chain() == new_chain
        
        # Test empty fallback chain
        with pytest.raises(ValueError, match="Fallback chain must not be empty"):
            registry.set_fallback_chain([])
        
        # Test unknown adapter in chain
        with pytest.raises(ValueError, match="Unknown adapter in fallback chain"):
            registry.set_fallback_chain(["unknown_adapter"])
    
    def test_adapter_resolution_success(self):
        """Test successful adapter resolution."""
        registry = TokenizerRegistry()
        
        mock_adapter = Mock()
        mock_adapter.adapter_id = "heuristic"
        
        with patch.object(
            registry, "_create_adapter_with_recovery", return_value=mock_adapter
        ) as mock_create, patch.object(
            registry, "_wrap_with_enhancements", return_value=mock_adapter
        ) as mock_wrap:
            adapter = registry.resolve("heuristic", "test-model", max_tokens=1024)
        
        assert adapter is mock_adapter
        mock_create.assert_called_once_with("heuristic", "test-model", 1024)
        mock_wrap.assert_called_once()
    
    def test_adapter_resolution_with_fallback(self):
        """Test adapter resolution with fallback chain."""
        registry = TokenizerRegistry()
        
        # Mock the registry's internal adapters to control behavior
        original_adapters = registry._adapters.copy()
        
        # Create mock adapters that fail and succeed
        def failing_adapter(*args, **kwargs):
            raise ImportError("Dependency not available")
        
        def working_adapter(*args, **kwargs):
            mock_adapter = Mock()
            mock_adapter.adapter_id = "heuristic"
            mock_adapter.count_tokens.return_value = TokenCount(
                count=1,
                method="heuristic",
                tokenizer_id="heuristic:test-model",
                is_exact=False,
                model_max_tokens=DEFAULT_MAX_TOKENS,
            )
            return mock_adapter
        
        # Set up registry with failing tiktoken and working heuristic
        registry._adapters["tiktoken"] = (failing_adapter, {})
        registry._adapters["heuristic"] = (working_adapter, {})
        
        try:
            # Should fall back to heuristic
            adapter = registry.resolve("tiktoken", "test-model")
            assert adapter.adapter_id == "heuristic"
        finally:
            # Restore original adapters
            registry._adapters = original_adapters
    
    def test_adapter_resolution_complete_failure(self):
        """Test adapter resolution when all adapters fail."""
        registry = TokenizerRegistry()
        
        # Mock all adapters to fail
        original_adapters = registry._adapters.copy()
        
        def failing_adapter(*args, **kwargs):
            raise Exception("Adapter failed")
        
        registry._adapters = {
            "heuristic": (failing_adapter, {}),
            "tiktoken": (failing_adapter, {}),
            "huggingface": (failing_adapter, {}),
        }
        
        try:
            with pytest.raises(FallbackChainExhaustedError) as exc_info:
                registry.resolve("tiktoken", "test-model")
            
            error = exc_info.value
            assert "test-model" in str(error)
            assert len(error.attempted_adapters) > 0
            assert len(error.errors) > 0
        finally:
            # Restore original adapters
            registry._adapters = original_adapters
    
    def test_adapter_status_checking(self):
        """Test adapter status checking functionality."""
        registry = TokenizerRegistry()
        
        # Mock dependency manager
        with patch.object(registry, '_dependency_manager') as mock_dep_manager:
            mock_dep_manager.check_adapter_readiness.return_value = (True, [], [])
            
            # Mock adapter creation to succeed for heuristic
            with patch.object(registry, '_create_adapter_with_recovery') as mock_create:
                mock_adapter = Mock()
                mock_adapter.adapter_id = "heuristic"
                mock_create.return_value = mock_adapter
                
                status = registry.get_adapter_status_with_dependencies()
                
                assert "heuristic" in status
                assert status["heuristic"]["available"] is True
                assert status["heuristic"]["dependency_ready"] is True
    
    def test_best_adapter_suggestion(self):
        """Test best adapter suggestion logic."""
        registry = TokenizerRegistry()
        
        # Mock adapter status
        with patch.object(registry, 'get_adapter_status_with_dependencies') as mock_status:
            mock_status.return_value = {
                "heuristic": {"available": True},
                "tiktoken": {"available": True},
                "huggingface": {"available": False},
            }
            
            # Test OpenAI model suggestion
            suggestion = registry.suggest_best_adapter("gpt-4")
            assert suggestion == "tiktoken"
            
            # Test HuggingFace model suggestion (but adapter not available)
            suggestion = registry.suggest_best_adapter("bert-base-uncased")
            assert suggestion == "tiktoken"  # Should fall back to available adapter
            
            # Test unknown model
            suggestion = registry.suggest_best_adapter("unknown-model")
            assert suggestion == "tiktoken"  # First in fallback chain
    
    def test_dependency_report_integration(self):
        """Test dependency report integration."""
        registry = TokenizerRegistry()
        
        # Mock dependency manager
        with patch.object(registry, '_dependency_manager') as mock_dep_manager:
            mock_report = Mock()
            mock_report.overall_health = "healthy"
            mock_report.python_version = "3.9.0"
            mock_report.python_compatible = True
            mock_report.dependencies = {}
            mock_report.recommendations = []
            mock_report.get_missing_dependencies.return_value = []
            mock_report.get_incompatible_dependencies.return_value = []
            mock_report.get_failed_tests.return_value = []
            
            mock_dep_manager.check_all_dependencies.return_value = mock_report
            
            with patch.object(registry, "get_adapter_status_with_dependencies") as mock_status:
                mock_status.return_value = {}
                report = registry.get_dependency_report()
            
            assert report["overall_health"] == "healthy"
            assert report["python_version"] == "3.9.0"
            assert report["python_compatible"] is True


class TestConfigurationValidationComprehensive:
    """Comprehensive tests for configuration validation and parsing."""
    
    def test_tokenizer_config_validation_comprehensive(self):
        """Test comprehensive TokenizerConfig validation."""
        from kano_backlog_core.tokenizer_config import TokenizerConfig
        from kano_backlog_core.errors import ConfigError
        
        # Test valid configurations
        valid_configs = [
            {"adapter": "auto", "model": "gpt-4"},
            {"adapter": "heuristic", "model": "test-model", "max_tokens": 1024},
            {"adapter": "tiktoken", "model": "gpt-3.5-turbo", "fallback_chain": ["tiktoken", "heuristic"]},
        ]
        
        for config_dict in valid_configs:
            config = TokenizerConfig.from_dict(config_dict)
            config.validate()  # Should not raise
        
        # Test invalid configurations
        invalid_configs = [
            ({"adapter": "", "model": "test"}, "Tokenizer adapter must be specified"),
            ({"adapter": "auto", "model": ""}, "Tokenizer model must be specified"),
            ({"adapter": "auto", "model": "test", "max_tokens": -1}, "max_tokens must be positive"),
            ({"adapter": "auto", "model": "test", "fallback_chain": []}, "Fallback chain must not be empty"),
            ({"adapter": "auto", "model": "test", "fallback_chain": ["unknown"]}, "Unknown adapter in fallback chain"),
            ({"adapter": "auto", "model": "test", "heuristic": {"chars_per_token": -1}}, "chars_per_token must be a positive number"),
            ({"adapter": "auto", "model": "test", "tiktoken": {"encoding": 123}}, "tiktoken.encoding must be a string"),
            ({"adapter": "auto", "model": "test", "huggingface": {"use_fast": "true"}}, "huggingface.use_fast must be a boolean"),
        ]
        
        for config_dict, expected_error in invalid_configs:
            with pytest.raises(ConfigError, match=expected_error):
                TokenizerConfig.from_dict(config_dict)
    
    def test_environment_variable_parsing(self):
        """Test environment variable parsing and type conversion."""
        from kano_backlog_core.tokenizer_config import TokenizerConfigLoader
        
        # Test various environment variable scenarios
        env_scenarios = [
            # Basic string overrides
            ({"KANO_TOKENIZER_ADAPTER": "heuristic"}, {"adapter": "heuristic"}),
            ({"KANO_TOKENIZER_MODEL": "custom-model"}, {"model": "custom-model"}),
            
            # Numeric conversion
            ({"KANO_TOKENIZER_MAX_TOKENS": "2048"}, {"max_tokens": 2048}),
            
            # Boolean conversion
            ({"KANO_TOKENIZER_HUGGINGFACE_USE_FAST": "false"}, {"huggingface": {"use_fast": False}}),
            ({"KANO_TOKENIZER_HUGGINGFACE_USE_FAST": "true"}, {"huggingface": {"use_fast": True}}),
            ({"KANO_TOKENIZER_HUGGINGFACE_USE_FAST": "1"}, {"huggingface": {"use_fast": True}}),
            ({"KANO_TOKENIZER_HUGGINGFACE_USE_FAST": "0"}, {"huggingface": {"use_fast": False}}),
            
            # Float conversion
            ({"KANO_TOKENIZER_HEURISTIC_CHARS_PER_TOKEN": "3.5"}, {"heuristic": {"chars_per_token": 3.5}}),
        ]
        
        for env_vars, expected_changes in env_scenarios:
            with patch.dict('os.environ', env_vars):
                result = TokenizerConfigLoader._apply_environment_overrides({})
                
                for key, value in expected_changes.items():
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            assert result[key][sub_key] == sub_value
                    else:
                        assert result[key] == value
    
    def test_environment_variable_error_handling(self):
        """Test environment variable error handling."""
        from kano_backlog_core.tokenizer_config import TokenizerConfigLoader
        
        # Test invalid numeric values
        with patch.dict('os.environ', {"KANO_TOKENIZER_MAX_TOKENS": "invalid"}):
            with patch('kano_backlog_core.tokenizer_config.logger') as mock_logger:
                result = TokenizerConfigLoader._apply_environment_overrides({})
                
                # Should not set max_tokens and should log warning
                assert "max_tokens" not in result
                mock_logger.warning.assert_called_once()
        
        # Test invalid float values
        with patch.dict('os.environ', {"KANO_TOKENIZER_HEURISTIC_CHARS_PER_TOKEN": "not_a_number"}):
            with patch('kano_backlog_core.tokenizer_config.logger') as mock_logger:
                result = TokenizerConfigLoader._apply_environment_overrides({})
                
                # Should not modify heuristic config and should log warning
                mock_logger.warning.assert_called_once()
    
    def test_configuration_migration_comprehensive(self):
        """Test comprehensive configuration migration scenarios."""
        from kano_backlog_core.tokenizer_config import TokenizerConfigMigrator
        
        # Test various old configuration formats
        migration_scenarios = [
            # Basic tokenizer config
            (
                {"tokenizer": {"adapter": "tiktoken", "model": "gpt-4"}},
                {"adapter": "tiktoken", "model": "gpt-4"}
            ),
            
            # Config with options
            (
                {
                    "tokenizer": {
                        "adapter": "heuristic",
                        "options": {
                            "chars_per_token": 3.5,
                            "encoding": "p50k_base",
                            "heuristic": {"extra_option": "value"}
                        }
                    }
                },
                {
                    "adapter": "heuristic",
                    "heuristic": {"chars_per_token": 3.5, "extra_option": "value"},
                    "tiktoken": {"encoding": "p50k_base"}
                }
            ),
            
            # Empty config
            ({}, {"adapter": "auto", "model": "text-embedding-3-small"}),
            
            # Config without tokenizer section
            ({"other_section": {"key": "value"}}, {"adapter": "auto", "model": "text-embedding-3-small"}),
        ]
        
        for old_config, expected_changes in migration_scenarios:
            result = TokenizerConfigMigrator.migrate_pipeline_config(old_config)
            
            for key, value in expected_changes.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        assert result[key][sub_key] == sub_value
                else:
                    assert result[key] == value


class TestErrorHandlingComprehensive:
    """Comprehensive tests for error handling and recovery mechanisms."""
    
    def test_error_recovery_manager_comprehensive(self):
        """Test ErrorRecoveryManager comprehensive functionality."""
        manager = ErrorRecoveryManager()
        
        # Test recovery attempt limits
        error_key = "test_adapter:test_model"
        
        # Should allow initial attempts
        for i in range(3):
            assert manager.should_attempt_recovery(error_key) is True
            manager.record_recovery_attempt(error_key)
        
        # Should block further attempts
        assert manager.should_attempt_recovery(error_key) is False
        
        # Reset should allow attempts again
        manager.reset_recovery_attempts(error_key)
        assert manager.should_attempt_recovery(error_key) is True
    
    def test_error_recovery_strategy_suggestions(self):
        """Test error recovery strategy suggestions for various error types."""
        manager = ErrorRecoveryManager()
        
        # Test dependency errors
        import_error = ImportError("No module named 'tiktoken'")
        strategy = manager.suggest_recovery_strategy(import_error, "tiktoken", "gpt-4")
        
        assert strategy["recommended_action"] == "install_dependency"
        assert "pip install tiktoken" in strategy["user_message"]
        assert strategy["retry_recommended"] is True
        
        # Test configuration errors
        config_error = ValueError("Invalid model name")
        strategy = manager.suggest_recovery_strategy(config_error, "tiktoken", "invalid")
        
        assert strategy["recommended_action"] == "fix_configuration"
        assert "Configuration error" in strategy["user_message"]
        
        # Test network errors
        network_error = Exception("Connection timeout")
        strategy = manager.suggest_recovery_strategy(network_error, "huggingface", "bert-base-uncased")
        
        assert strategy["recommended_action"] == "retry_with_fallback"
        assert "Network error" in strategy["user_message"]
    
    def test_degradation_event_tracking(self):
        """Test degradation event tracking and analysis."""
        manager = ErrorRecoveryManager()
        
        # Record multiple degradation events
        errors = [
            ImportError("tiktoken not found"),
            ValueError("Invalid configuration"),
            Exception("Network timeout"),
        ]
        
        for i, error in enumerate(errors):
            manager.record_degradation_event(
                f"adapter_{i}", "heuristic", f"model_{i}", error
            )
        
        # Check statistics
        stats = manager.get_recovery_statistics()
        assert stats["total_degradation_events"] == 3
        assert len(stats["degradation_by_adapter"]) == 3
    
    def test_error_message_quality(self):
        """Test error message quality and user-friendliness."""
        from kano_backlog_core.tokenizer_errors import (
            create_user_friendly_error_message,
            DependencyMissingError,
            TokenizationFailedError,
        )
        
        # Test dependency missing error
        dep_error = DependencyMissingError("tiktoken", "tiktoken", "gpt-4")
        message = create_user_friendly_error_message(dep_error)
        
        assert "❌ Tokenizer Error" in message
        assert "📍 Adapter: tiktoken" in message
        assert "🤖 Model: gpt-4" in message
        assert "💡 How to fix this:" in message
        assert "pip install tiktoken" in message
        
        # Test tokenization failed error
        token_error = TokenizationFailedError(
            "tiktoken", "gpt-4", "test text", ValueError("Encoding failed")
        )
        message = create_user_friendly_error_message(token_error)
        
        assert "❌ Tokenizer Error" in message
        assert "tiktoken" in message
        assert "gpt-4" in message


class TestIntegrationScenarios:
    """Integration tests for complex scenarios combining multiple components."""
    
    def test_end_to_end_adapter_resolution_with_config(self):
        """Test end-to-end adapter resolution with configuration."""
        from kano_backlog_core.tokenizer_config import TokenizerConfig
        
        # Create configuration
        config = TokenizerConfig(
            adapter="auto",
            model="gpt-4",
            fallback_chain=["tiktoken", "heuristic"],
            tiktoken={"encoding": "cl100k_base"},
            heuristic={"chars_per_token": 3.5}
        )
        
        # Create registry with configuration
        registry = TokenizerRegistry()
        registry.set_fallback_chain(config.fallback_chain)
        
        def failing_tiktoken(*args, **kwargs):
            raise ImportError("tiktoken not available")

        registry._adapters["tiktoken"] = (failing_tiktoken, {})

        # Should fall back to heuristic
        adapter = registry.resolve(
            adapter_name=config.adapter,
            model_name=config.model,
            **config.get_adapter_options("heuristic")
        )
        
        assert adapter.adapter_id == "heuristic"
        assert adapter.chars_per_token == 3.5
    
    def test_configuration_driven_error_recovery(self):
        """Test configuration-driven error recovery scenarios."""
        from kano_backlog_core.tokenizer_config import TokenizerConfig
        
        # Configuration with custom fallback chain
        config = TokenizerConfig(
            adapter="tiktoken",
            model="gpt-4",
            fallback_chain=["tiktoken", "heuristic"],  # Skip huggingface
            max_tokens=8192
        )
        
        registry = TokenizerRegistry()
        registry.set_fallback_chain(config.fallback_chain)
        
        def failing_tiktoken(*args, **kwargs):
            raise ImportError("tiktoken not available")

        registry._adapters["tiktoken"] = (failing_tiktoken, {})

        # Should fall back to heuristic (skipping huggingface)
        adapter = registry.resolve(
            adapter_name=config.adapter,
            model_name=config.model,
            max_tokens=config.max_tokens
        )
        
        assert adapter.adapter_id == "heuristic"
        assert adapter.max_tokens() == 8192
    
    def test_comprehensive_error_scenario(self):
        """Test comprehensive error scenario with multiple failures."""
        registry = TokenizerRegistry()
        
        def failing_tiktoken(*args, **kwargs):
            raise ImportError("tiktoken not found")

        def failing_huggingface(*args, **kwargs):
            raise ImportError("transformers not found")

        def failing_heuristic(*args, **kwargs):
            raise ValueError("Heuristic configuration error")

        registry._adapters["tiktoken"] = (failing_tiktoken, {})
        registry._adapters["huggingface"] = (failing_huggingface, {})
        registry._adapters["heuristic"] = (failing_heuristic, {})
        registry.set_fallback_chain(["tiktoken", "huggingface", "heuristic"])

        # Should raise FallbackChainExhaustedError
        with pytest.raises(FallbackChainExhaustedError) as exc_info:
            registry.resolve("tiktoken", "gpt-4")
        
        error = exc_info.value
        assert len(error.attempted_adapters) == 3
        assert len(error.errors) == 3
        assert "gpt-4" in str(error)
    
    def test_performance_under_error_conditions(self):
        """Test performance characteristics under error conditions."""
        import time
        
        registry = TokenizerRegistry()
        registry.set_fallback_chain(["tiktoken", "heuristic"])
        
        def failing_tiktoken(*args, **kwargs):
            raise ImportError("tiktoken not found")

        registry._adapters["tiktoken"] = (failing_tiktoken, {})

        start_time = time.time()
        
        # Multiple fallback attempts should still be fast
        for i in range(10):
            try:
                registry.resolve("tiktoken", f"model-{i}")
            except Exception:
                pass
        
        elapsed = time.time() - start_time
        
        # Should complete quickly even with errors
        assert elapsed < 2.0  # Less than 2 seconds for 10 attempts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
