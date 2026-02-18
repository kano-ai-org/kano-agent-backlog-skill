"""Isolated unit tests for tokenizer adapters with proper mocking.

This module provides focused unit tests that:
1. Test each adapter implementation independently with proper isolation
2. Use comprehensive mocking for external dependencies
3. Cover error conditions and edge cases thoroughly
4. Validate configuration parsing and validation logic
5. Ensure reliable, fast testing without external dependencies

These tests complement the existing integration tests by providing
isolated unit testing with extensive mocking.
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from typing import Any, Dict, List, Optional

from kano_backlog_core.tokenizer import (
    TokenizerAdapter,
    HeuristicTokenizer,
    TokenCount,
    resolve_model_max_tokens,
    MODEL_MAX_TOKENS,
    DEFAULT_MAX_TOKENS,
)
from kano_backlog_core.tokenizer_errors import (
    TokenizationFailedError,
    DependencyMissingError,
    AdapterNotAvailableError,
)


class TestHeuristicTokenizerIsolated:
    """Isolated unit tests for HeuristicTokenizer."""
    
    def test_initialization_valid_parameters(self):
        """Test HeuristicTokenizer initialization with valid parameters."""
        # Test minimal parameters
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
    
    def test_initialization_invalid_parameters(self):
        """Test HeuristicTokenizer initialization with invalid parameters."""
        # Test empty model name
        with pytest.raises(ValueError, match="model_name must be non-empty"):
            HeuristicTokenizer("")
        
        # Test None model name
        with pytest.raises(ValueError, match="model_name must be non-empty"):
            HeuristicTokenizer(None)
        
        # Test invalid chars_per_token
        with pytest.raises(ValueError, match="chars_per_token must be positive"):
            HeuristicTokenizer("test-model", chars_per_token=0)
        
        with pytest.raises(ValueError, match="chars_per_token must be positive"):
            HeuristicTokenizer("test-model", chars_per_token=-1.5)
    
    @pytest.mark.parametrize("text,expected_min_tokens", [
        ("", 0),  # Empty string
        ("a", 1),  # Single character
        ("hello", 1),  # Short word
        ("hello world", 2),  # Two words
        ("The quick brown fox", 3),  # Multiple words
        ("你好", 1),  # CJK characters
        ("Hello 你好", 2),  # Mixed ASCII and CJK
        ("!@#$%", 1),  # Special characters
    ])
    def test_token_counting_various_inputs(self, text: str, expected_min_tokens: int):
        """Test token counting with various text inputs."""
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
        result = tokenizer.count_tokens(text)
        
        assert isinstance(result, TokenCount)
        assert result.count >= expected_min_tokens
        assert result.method == "heuristic"
        assert result.tokenizer_id == "heuristic:test-model:chars_4.0"
        assert result.is_exact is False
        assert result.model_max_tokens is not None
    
    def test_token_counting_none_input(self):
        """Test token counting with None input raises appropriate error."""
        tokenizer = HeuristicTokenizer("test-model")
        
        with pytest.raises(TokenizationFailedError) as exc_info:
            tokenizer.count_tokens(None)
        
        error = exc_info.value
        assert error.adapter_name == "heuristic"
        assert error.model_name == "test-model"
        assert "text must be a string" in str(error)
    
    def test_language_detection_behavior(self):
        """Test language detection affects token estimation."""
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
        
        # ASCII text
        ascii_result = tokenizer.count_tokens("Hello world test")
        
        # CJK text (should have different density)
        cjk_result = tokenizer.count_tokens("你好世界")
        
        # Both should return valid results
        assert ascii_result.count > 0
        assert cjk_result.count > 0
        
        # CJK should generally have higher token density
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
    
    def test_chars_per_token_variations(self):
        """Test different chars_per_token ratios produce expected results."""
        text = "This is a test sentence"
        
        # Test different ratios
        tokenizer_low = HeuristicTokenizer("test-model", chars_per_token=2.0)
        tokenizer_high = HeuristicTokenizer("test-model", chars_per_token=8.0)
        
        result_low = tokenizer_low.count_tokens(text)
        result_high = tokenizer_high.count_tokens(text)
        
        # Lower ratio should produce more tokens
        assert result_low.count >= result_high.count
        
        # Verify tokenizer_id reflects the ratio
        assert "chars_2.0" in result_low.tokenizer_id
        assert "chars_8.0" in result_high.tokenizer_id


class TestTiktokenAdapterMocked:
    """Isolated unit tests for TiktokenAdapter with mocking."""
    
    def test_initialization_without_tiktoken(self):
        """Test TiktokenAdapter initialization when tiktoken is not available."""
        # Mock tokenizer module's optional dependency to simulate missing tiktoken.
        from kano_backlog_core import tokenizer as tokenizer_module

        with patch.object(tokenizer_module, "tiktoken", None):
            with pytest.raises(ImportError, match="tiktoken package required"):
                from kano_backlog_core.tokenizer import TiktokenAdapter
                TiktokenAdapter("gpt-4")
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_initialization_with_mocked_tiktoken(self, mock_tiktoken):
        """Test TiktokenAdapter initialization with mocked tiktoken."""
        from kano_backlog_core.tokenizer import TiktokenAdapter
        
        # Mock encoding
        mock_encoding = Mock()
        mock_encoding.name = "cl100k_base"
        mock_tiktoken.encoding_for_model.return_value = mock_encoding
        
        adapter = TiktokenAdapter("gpt-4")
        assert adapter.model_name == "gpt-4"
        assert adapter.adapter_id == "tiktoken"
        assert adapter.encoding_name == "cl100k_base"
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_token_counting_with_mocked_tiktoken(self, mock_tiktoken):
        """Test token counting with mocked tiktoken."""
        from kano_backlog_core.tokenizer import TiktokenAdapter
        
        # Mock encoding and its methods
        mock_encoding = Mock()
        mock_encoding.name = "cl100k_base"
        mock_encoding.encode.return_value = [1, 2, 3, 4, 5]
        mock_tiktoken.encoding_for_model.return_value = mock_encoding
        
        adapter = TiktokenAdapter("gpt-4")
        result = adapter.count_tokens("Hello world")
        
        assert result.count == 5
        assert result.method == "tiktoken"
        assert result.is_exact is True
        assert "tiktoken:gpt-4:cl100k_base" in result.tokenizer_id
        
        # Verify encode was called correctly
        mock_encoding.encode.assert_called_once_with("Hello world", disallowed_special=())
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_token_counting_none_input(self, mock_tiktoken):
        """Test token counting with None input."""
        from kano_backlog_core.tokenizer import TiktokenAdapter
        
        mock_encoding = Mock()
        mock_encoding.name = "cl100k_base"
        mock_tiktoken.encoding_for_model.return_value = mock_encoding
        
        adapter = TiktokenAdapter("gpt-4")
        result = adapter.count_tokens(None)
        
        assert result.count == 0
        assert result.method == "tiktoken"
        assert result.is_exact is True
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_token_counting_error_handling(self, mock_tiktoken):
        """Test token counting error handling."""
        from kano_backlog_core.tokenizer import TiktokenAdapter
        
        mock_encoding = Mock()
        mock_encoding.name = "cl100k_base"
        mock_encoding.encode.side_effect = ValueError("Encoding failed")
        mock_tiktoken.encoding_for_model.return_value = mock_encoding
        
        adapter = TiktokenAdapter("gpt-4")
        
        with pytest.raises(TokenizationFailedError) as exc_info:
            adapter.count_tokens("problematic text")
        
        error = exc_info.value
        assert error.adapter_name == "tiktoken"
        assert error.model_name == "gpt-4"
        assert "Encoding failed" in str(error.original_error)
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_encoding_fallback_behavior(self, mock_tiktoken):
        """Test encoding fallback behavior."""
        from kano_backlog_core.tokenizer import TiktokenAdapter
        
        # Mock encoding_for_model to fail, get_encoding to succeed
        mock_tiktoken.encoding_for_model.side_effect = KeyError("Model not found")
        
        mock_encoding = Mock()
        mock_encoding.name = "cl100k_base"
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        adapter = TiktokenAdapter("unknown-model")
        assert adapter.encoding_name == "cl100k_base"
        
        # Should have tried encoding_for_model first, then get_encoding
        mock_tiktoken.encoding_for_model.assert_called_once_with("unknown-model")
        mock_tiktoken.get_encoding.assert_called()


class TestHuggingFaceAdapterMocked:
    """Isolated unit tests for HuggingFaceAdapter with mocking."""
    
    def test_initialization_without_transformers(self):
        """Test HuggingFaceAdapter initialization when transformers is not available."""
        # HuggingFaceAdapter checks the module-level `transformers` handle.
        from kano_backlog_core import tokenizer as tok

        with patch.object(tok, "transformers", None):
            with pytest.raises(ImportError, match="transformers package required"):
                tok.HuggingFaceAdapter("bert-base-uncased")
    
    def test_model_name_validation(self):
        """Test model name validation."""
        from kano_backlog_core.tokenizer import HuggingFaceAdapter
        
        # Test invalid model names - these should fail at the parent class level
        with pytest.raises(ValueError, match="model_name must be non-empty"):
            HuggingFaceAdapter("")
        
        with pytest.raises(ValueError, match="model_name must be non-empty"):
            HuggingFaceAdapter(None)
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_initialization_with_mocked_transformers(self, mock_transformers):
        """Test HuggingFaceAdapter initialization with mocked transformers."""
        from kano_backlog_core.tokenizer import HuggingFaceAdapter
        
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
    def test_token_counting_with_mocked_transformers(self, mock_transformers):
        """Test token counting with mocked transformers."""
        from kano_backlog_core.tokenizer import HuggingFaceAdapter
        
        mock_tokenizer = Mock()
        mock_tokenizer.encode.return_value = [101, 7592, 2088, 102]  # [CLS] hello world [SEP]
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        result = adapter.count_tokens("hello world")
        
        assert result.count == 4
        assert result.method == "huggingface"
        assert result.is_exact is True
        assert "huggingface:bert-base-uncased" in result.tokenizer_id
        
        # Verify encode was called with correct parameters
        mock_tokenizer.encode.assert_called_once_with("hello world", add_special_tokens=True)
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_token_counting_none_input(self, mock_transformers):
        """Test token counting with None input."""
        from kano_backlog_core.tokenizer import HuggingFaceAdapter
        
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        result = adapter.count_tokens(None)
        
        assert result.count == 0
        assert result.method == "huggingface"
        assert result.is_exact is True
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    @patch('kano_backlog_core.tokenizer.token_spans')
    def test_token_counting_with_fallback(self, mock_token_spans, mock_transformers):
        """Test token counting with fallback to heuristic."""
        from kano_backlog_core.tokenizer import HuggingFaceAdapter
        
        mock_tokenizer = Mock()
        mock_tokenizer.encode.side_effect = Exception("Encoding failed")
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        # Mock token_spans fallback
        mock_token_spans.return_value = ["hello", "world"]
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        result = adapter.count_tokens("hello world")
        
        assert result.count == 2
        assert result.method == "huggingface_fallback"
        assert result.is_exact is False
        
        # Verify fallback was used
        mock_token_spans.assert_called_once_with("hello world")
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_get_model_info(self, mock_transformers):
        """Test get_model_info method."""
        from kano_backlog_core.tokenizer import HuggingFaceAdapter
        
        mock_tokenizer = Mock()
        mock_tokenizer.vocab_size = 30522
        mock_tokenizer.is_fast = True
        mock_tokenizer.pad_token = "[PAD]"
        mock_tokenizer.cls_token = "[CLS]"
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        info = adapter.get_model_info()
        
        assert info["model_name"] == "bert-base-uncased"
        assert info["adapter_id"] == "huggingface"
        assert info["vocab_size"] == 30522
        assert info["tokenizer_type"] == "fast"
        assert info["special_tokens"]["pad_token"] == "[PAD]"
        assert info["special_tokens"]["cls_token"] == "[CLS]"


class TestTokenizerRegistryMocked:
    """Isolated unit tests for TokenizerRegistry with mocking."""
    
    def test_registry_initialization(self):
        """Test TokenizerRegistry initialization."""
        from kano_backlog_core.tokenizer import TokenizerRegistry
        
        registry = TokenizerRegistry()
        adapters = registry.list_adapters()
        
        assert "heuristic" in adapters
        assert "tiktoken" in adapters
        assert "huggingface" in adapters
        
        fallback_chain = registry.get_fallback_chain()
        assert fallback_chain == ["tiktoken", "huggingface", "heuristic"]
    
    def test_custom_adapter_registration(self):
        """Test registering custom adapters."""
        from kano_backlog_core.tokenizer import TokenizerRegistry
        
        registry = TokenizerRegistry()
        
        # Create mock custom adapter class
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
        from kano_backlog_core.tokenizer import TokenizerRegistry
        
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
        from kano_backlog_core.tokenizer import TokenizerRegistry
        
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
    
    def test_heuristic_adapter_resolution(self):
        """Test resolving heuristic adapter (always available)."""
        from kano_backlog_core.tokenizer import TokenizerRegistry
        
        registry = TokenizerRegistry()
        
        adapter = registry.resolve("heuristic", "test-model", max_tokens=1024)
        
        assert adapter.adapter_id == "heuristic"
        assert adapter.model_name == "test-model"
        assert adapter.max_tokens() == 1024


class TestConfigurationValidation:
    """Tests for configuration validation and parsing."""
    
    def test_tokenizer_config_validation(self):
        """Test TokenizerConfig validation."""
        from kano_backlog_core.tokenizer_config import TokenizerConfig
        from kano_backlog_core.errors import ConfigError
        
        # Test valid configuration
        config = TokenizerConfig(
            adapter="heuristic",
            model="test-model",
            max_tokens=1024
        )
        assert config.adapter == "heuristic"
        assert config.model == "test-model"
        assert config.max_tokens == 1024
        
        # Test invalid configurations
        with pytest.raises(ConfigError, match="Tokenizer adapter must be specified"):
            TokenizerConfig(adapter="")
        
        with pytest.raises(ConfigError, match="Tokenizer model must be specified"):
            TokenizerConfig(model="")
        
        with pytest.raises(ConfigError, match="max_tokens must be positive"):
            TokenizerConfig(max_tokens=-1)
    
    def test_environment_variable_parsing(self):
        """Test environment variable parsing."""
        from kano_backlog_core.tokenizer_config import TokenizerConfigLoader
        import os
        
        # Test basic environment variable override
        with patch.dict(os.environ, {"KANO_TOKENIZER_ADAPTER": "heuristic"}):
            result = TokenizerConfigLoader._apply_environment_overrides({})
            assert result["adapter"] == "heuristic"
        
        # Test numeric conversion
        with patch.dict(os.environ, {"KANO_TOKENIZER_MAX_TOKENS": "2048"}):
            result = TokenizerConfigLoader._apply_environment_overrides({})
            assert result["max_tokens"] == 2048
        
        # Test boolean conversion
        with patch.dict(os.environ, {"KANO_TOKENIZER_HUGGINGFACE_USE_FAST": "false"}):
            result = TokenizerConfigLoader._apply_environment_overrides({})
            assert result["huggingface"]["use_fast"] is False


class TestErrorHandling:
    """Tests for error handling and recovery mechanisms."""
    
    def test_tokenization_failed_error(self):
        """Test TokenizationFailedError creation and properties."""
        original_error = ValueError("Test error")
        error = TokenizationFailedError(
            adapter_name="test_adapter",
            model_name="test_model",
            text_preview="test text",
            original_error=original_error
        )
        
        assert error.adapter_name == "test_adapter"
        assert error.model_name == "test_model"
        assert error.text_preview == "test text"
        assert error.original_error is original_error
        assert "test_adapter" in str(error)
        assert "test_model" in str(error)
    
    def test_dependency_missing_error(self):
        """Test DependencyMissingError creation and recovery suggestions."""
        error = DependencyMissingError(
            dependency="tiktoken",
            adapter_name="tiktoken",
            model_name="gpt-4"
        )
        
        assert error.dependency == "tiktoken"
        assert error.adapter_name == "tiktoken"
        assert error.model_name == "gpt-4"
        assert len(error.recovery_suggestions) > 0
        assert any("pip install tiktoken" in suggestion for suggestion in error.recovery_suggestions)
    
    def test_error_recovery_manager(self):
        """Test ErrorRecoveryManager functionality."""
        from kano_backlog_core.tokenizer_errors import ErrorRecoveryManager
        
        manager = ErrorRecoveryManager()
        error_key = "test_adapter:test_model"
        
        # Test recovery attempt tracking
        assert manager.should_attempt_recovery(error_key) is True
        
        # Record attempts up to limit
        for i in range(3):
            manager.record_recovery_attempt(error_key)
            if i < 2:
                assert manager.should_attempt_recovery(error_key) is True
            else:
                assert manager.should_attempt_recovery(error_key) is False
        
        # Reset should allow attempts again
        manager.reset_recovery_attempts(error_key)
        assert manager.should_attempt_recovery(error_key) is True
    
    def test_fallback_adapter_suggestion(self):
        """Test fallback adapter suggestion logic."""
        from kano_backlog_core.tokenizer_errors import ErrorRecoveryManager
        
        manager = ErrorRecoveryManager()
        
        # Test tiktoken fallback preferences
        fallback = manager.suggest_fallback_adapter("tiktoken", ["huggingface", "heuristic"])
        assert fallback == "huggingface"
        
        fallback = manager.suggest_fallback_adapter("tiktoken", ["heuristic"])
        assert fallback == "heuristic"
        
        # Test no available fallbacks
        fallback = manager.suggest_fallback_adapter("tiktoken", [])
        assert fallback is None


class TestUtilityFunctions:
    """Tests for utility functions."""
    
    def test_resolve_model_max_tokens(self):
        """Test resolve_model_max_tokens function."""
        # Test known model
        result = resolve_model_max_tokens("text-embedding-3-small")
        assert result == MODEL_MAX_TOKENS["text-embedding-3-small"]
        
        # Test unknown model
        result = resolve_model_max_tokens("unknown-model")
        assert result == DEFAULT_MAX_TOKENS
        
        # Test with overrides
        overrides = {"custom-model": 4096}
        result = resolve_model_max_tokens("custom-model", overrides=overrides)
        assert result == 4096
        
        # Test with custom default
        result = resolve_model_max_tokens("unknown-model", default=16384)
        assert result == 16384
    
    def test_model_max_tokens_constants(self):
        """Test MODEL_MAX_TOKENS constants are reasonable."""
        # Test that all values are positive
        for model, max_tokens in MODEL_MAX_TOKENS.items():
            assert max_tokens > 0, f"Model {model} has non-positive max_tokens: {max_tokens}"
            assert max_tokens <= 200000, f"Model {model} has unreasonably high max_tokens: {max_tokens}"
        
        # Test that common models are present
        expected_models = [
            "text-embedding-3-small",
            "text-embedding-3-large",
            "gpt-4",
            "gpt-3.5-turbo",
            "bert-base-uncased",
        ]
        
        for model in expected_models:
            assert model in MODEL_MAX_TOKENS, f"Expected model {model} not found in MODEL_MAX_TOKENS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
