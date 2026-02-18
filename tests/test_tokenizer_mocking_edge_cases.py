"""Focused unit tests for tokenizer adapters with extensive mocking and edge cases.

This module provides focused unit tests that emphasize:
1. Comprehensive mocking of external dependencies
2. Edge case testing for unusual inputs and conditions
3. Error injection and recovery testing
4. Performance and resource usage testing
5. Thread safety and concurrency testing

These tests complement the main test suite by providing deep coverage
of edge cases and error conditions that are difficult to test otherwise.
"""

import pytest
import threading
import time
import gc
from unittest.mock import Mock, patch, MagicMock, PropertyMock, call
from typing import Any, Dict, List, Optional
import sys
import weakref

from kano_backlog_core.tokenizer import (
    TokenizerAdapter,
    HeuristicTokenizer,
    TiktokenAdapter,
    HuggingFaceAdapter,
    TokenCount,
    TokenizerRegistry,
)
from kano_backlog_core.tokenizer_errors import (
    TokenizationFailedError,
    DependencyMissingError,
    AdapterNotAvailableError,
    FallbackChainExhaustedError,
)


class TestHeuristicTokenizerEdgeCases:
    """Edge case tests for HeuristicTokenizer."""
    
    _UNICODE_EDGE_CASES = [
        # Unicode edge cases
        ("\u0000\u0001\u0002", "null and control characters"),
        ("\ufeff", "byte order mark"),
        ("\u200b\u200c\u200d", "zero-width characters"),
        ("\U0001f600\U0001f601\U0001f602", "emoji characters"),
        ("\U00010000\U00010001", "supplementary plane characters"),
        # Whitespace variations
        ("\t\n\r\f\v", "various whitespace characters"),
        ("   \t\t\n\n   ", "mixed whitespace"),
        ("\u00a0\u2000\u2001\u2002", "unicode whitespace"),
        # Extreme lengths
        ("a" * 100000, "very long text"),
        ("你" * 50000, "very long CJK text"),
        # Mixed scripts
        ("Hello мир 世界 🌍", "mixed scripts with emoji"),
        ("αβγδε АБВГД עברית العربية", "multiple non-Latin scripts"),
        # Special formatting
        ("line1\nline2\r\nline3\rline4", "mixed line endings"),
        ("word\u00adword", "soft hyphen"),
        ("café naïve résumé", "accented characters"),
    ]

    @pytest.mark.parametrize(
        "text,description",
        _UNICODE_EDGE_CASES,
        ids=[description for _, description in _UNICODE_EDGE_CASES],
    )
    def test_unicode_and_edge_case_handling(self, text: str, description: str):
        """Test handling of various Unicode and edge case inputs."""
        tokenizer = HeuristicTokenizer("test-model")
        
        # Should not raise exceptions
        result = tokenizer.count_tokens(text)
        
        assert isinstance(result, TokenCount)
        assert result.count >= 0
        assert result.method == "heuristic"
        assert result.is_exact is False
        
        # For non-empty text, should have at least some tokens
        if text.strip():
            assert result.count > 0
    
    def test_extreme_chars_per_token_values(self):
        """Test extreme chars_per_token values."""
        text = "This is a test sentence with multiple words."
        
        # Very small ratio (many tokens)
        tokenizer_tiny = HeuristicTokenizer("test-model", chars_per_token=0.1)
        result_tiny = tokenizer_tiny.count_tokens(text)
        
        # Very large ratio (few tokens)
        tokenizer_huge = HeuristicTokenizer("test-model", chars_per_token=1000.0)
        result_huge = tokenizer_huge.count_tokens(text)
        
        # Tiny ratio should produce many more tokens
        assert result_tiny.count > result_huge.count
        assert result_huge.count >= 1  # Should always be at least 1 for non-empty text
    
    def test_memory_usage_with_large_inputs(self):
        """Test memory usage with large inputs."""
        tokenizer = HeuristicTokenizer("test-model")
        
        # Create large text
        large_text = "This is a test sentence. " * 10000  # ~250KB
        
        # Measure memory before
        gc.collect()
        
        # Process large text
        result = tokenizer.count_tokens(large_text)
        
        # Should complete successfully
        assert result.count > 0
        assert result.method == "heuristic"
        
        # Clean up
        del large_text
        gc.collect()
    
    def test_concurrent_tokenization(self):
        """Test concurrent tokenization from multiple threads."""
        tokenizer = HeuristicTokenizer("test-model")
        results = []
        errors = []
        
        def tokenize_worker(text_id: int):
            try:
                text = f"Test text number {text_id} with some content"
                result = tokenizer.count_tokens(text)
                results.append((text_id, result.count))
            except Exception as e:
                errors.append((text_id, e))
        
        # Create multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=tokenize_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
        
        # All results should be positive
        for text_id, count in results:
            assert count > 0


class TestTiktokenAdapterMockingEdgeCases:
    """Edge case tests for TiktokenAdapter with extensive mocking."""
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_tiktoken_import_variations(self, mock_tiktoken):
        """Test various tiktoken import and initialization scenarios."""
        # Test successful import
        mock_encoding = Mock()
        mock_encoding.name = "cl100k_base"
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        adapter = TiktokenAdapter("gpt-4")
        assert adapter.encoding_name == "cl100k_base"
        
        # Test import with module loading issues
        mock_tiktoken.get_encoding.side_effect = [
            Exception("First attempt failed"),
            mock_encoding  # Second attempt succeeds
        ]
        
        # Should eventually succeed with fallback
        adapter = TiktokenAdapter("gpt-4")
        assert adapter.encoding_name == "cl100k_base"
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_encoding_edge_cases(self, mock_tiktoken):
        """Test encoding edge cases and error conditions."""
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        adapter = TiktokenAdapter("gpt-4")
        
        # Test various encoding scenarios
        encoding_scenarios = [
            # Normal case
            ("hello world", [1, 2, 3], 3),
            
            # Empty result
            ("", [], 0),
            
            # Large token list
            ("long text", list(range(10000)), 10000),
            
            # Single token
            ("a", [42], 1),
        ]
        
        for text, tokens, expected_count in encoding_scenarios:
            mock_encoding.encode.return_value = tokens
            result = adapter.count_tokens(text)
            
            assert result.count == expected_count
            assert result.method == "tiktoken"
            assert result.is_exact is True
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_encoding_error_injection(self, mock_tiktoken):
        """Test various encoding error scenarios."""
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        adapter = TiktokenAdapter("gpt-4")
        
        # Test different types of encoding errors
        error_scenarios = [
            ValueError("Invalid character encoding"),
            UnicodeDecodeError("utf-8", b"", 0, 1, "invalid start byte"),
            MemoryError("Not enough memory"),
            RuntimeError("Encoding failed"),
            Exception("Generic encoding error"),
        ]
        
        for error in error_scenarios:
            mock_encoding.encode.side_effect = error
            
            with pytest.raises(TokenizationFailedError) as exc_info:
                adapter.count_tokens("test text")
            
            tokenization_error = exc_info.value
            assert tokenization_error.adapter_name == "tiktoken"
            assert tokenization_error.model_name == "gpt-4"
            assert str(error) in str(tokenization_error.original_error)
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_encoding_performance_edge_cases(self, mock_tiktoken):
        """Test encoding performance with edge cases."""
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        adapter = TiktokenAdapter("gpt-4")
        
        # Test with slow encoding (simulated)
        def slow_encode(text, **kwargs):
            time.sleep(0.01)  # Simulate slow encoding
            return [1] * len(text.split())
        
        mock_encoding.encode.side_effect = slow_encode
        
        start_time = time.time()
        result = adapter.count_tokens("test text with multiple words")
        elapsed = time.time() - start_time
        
        assert result.count == 5  # 5 words
        assert elapsed >= 0.01  # Should take at least the simulated time
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_memory_management_with_large_tokens(self, mock_tiktoken):
        """Test memory management with large token lists."""
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        adapter = TiktokenAdapter("gpt-4")
        
        # Create large token list
        large_token_list = list(range(100000))
        mock_encoding.encode.return_value = large_token_list
        
        # Process and verify
        result = adapter.count_tokens("large text")
        assert result.count == 100000
        
        # Clean up
        del large_token_list
        gc.collect()
    
    @patch('kano_backlog_core.tokenizer.tiktoken', create=True)
    def test_encoding_with_special_tokens(self, mock_tiktoken):
        """Test encoding behavior with special tokens."""
        mock_encoding = Mock()
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        adapter = TiktokenAdapter("gpt-4")
        
        # Test that disallowed_special=() is used
        mock_encoding.encode.return_value = [1, 2, 3]
        adapter.count_tokens("text with <|special|> tokens")
        
        # Verify encode was called with correct parameters
        mock_encoding.encode.assert_called_once_with(
            "text with <|special|> tokens",
            disallowed_special=()
        )


class TestHuggingFaceAdapterMockingEdgeCases:
    """Edge case tests for HuggingFaceAdapter with extensive mocking."""
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_transformers_import_variations(self, mock_transformers):
        """Test various transformers import scenarios."""
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        # Test successful import
        adapter = HuggingFaceAdapter("bert-base-uncased")
        assert adapter.adapter_id == "huggingface"
        
        # Test import with retry logic
        mock_transformers.AutoTokenizer.from_pretrained.side_effect = [
            Exception("First attempt failed"),
            mock_tokenizer  # Second attempt succeeds
        ]
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        assert adapter.adapter_id == "huggingface"
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_tokenizer_loading_edge_cases(self, mock_transformers):
        """Test tokenizer loading edge cases."""
        # Test various loading scenarios
        loading_scenarios = [
            # Normal loading
            (Mock(), None),
            
            # Loading with warnings
            (Mock(), UserWarning("Tokenizer warning")),
            
            # Loading with custom attributes
            (Mock(vocab_size=50000, is_fast=True), None),
        ]
        
        for mock_tokenizer, side_effect in loading_scenarios:
            if side_effect:
                mock_transformers.AutoTokenizer.from_pretrained.side_effect = side_effect
            else:
                mock_transformers.AutoTokenizer.from_pretrained.side_effect = None
                mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
            
            if isinstance(side_effect, Exception):
                with pytest.raises(ValueError):
                    HuggingFaceAdapter("bert-base-uncased")
            else:
                adapter = HuggingFaceAdapter("bert-base-uncased")
                assert adapter.adapter_id == "huggingface"
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_tokenization_edge_cases(self, mock_transformers):
        """Test tokenization edge cases."""
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        
        # Test various tokenization scenarios
        tokenization_scenarios = [
            # Normal tokenization
            ("hello world", [101, 7592, 2088, 102], 4),
            
            # Empty tokenization
            ("", [101, 102], 2),
            
            # Very long tokenization
            ("long text", [101] + list(range(1000, 2000)) + [102], 1002),
            
            # Single token
            ("hello", [101, 7592, 102], 3),
        ]
        
        for text, tokens, expected_count in tokenization_scenarios:
            mock_tokenizer.encode.return_value = tokens
            result = adapter.count_tokens(text)
            
            assert result.count == expected_count
            assert result.method == "huggingface"
            assert result.is_exact is True
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    @patch('kano_backlog_core.tokenizer.token_spans')
    def test_fallback_mechanism_comprehensive(self, mock_token_spans, mock_transformers):
        """Test comprehensive fallback mechanism."""
        mock_tokenizer = Mock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        
        # Test primary encoding failure with successful fallback
        mock_tokenizer.encode.side_effect = Exception("Encoding failed")
        mock_token_spans.return_value = ["hello", "world", "test"]
        
        result = adapter.count_tokens("hello world test")
        
        assert result.count == 3
        assert result.method == "huggingface_fallback"
        assert result.is_exact is False
        
        # Verify fallback was called
        mock_token_spans.assert_called_once_with("hello world test")
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_model_info_edge_cases(self, mock_transformers):
        """Test get_model_info with various edge cases."""
        # Test with minimal tokenizer
        mock_tokenizer = Mock()
        mock_tokenizer.vocab_size = 30522
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        info = adapter.get_model_info()
        
        assert info["model_name"] == "bert-base-uncased"
        assert info["vocab_size"] == 30522
        
        # Test with missing attributes
        mock_tokenizer_minimal = Mock()
        del mock_tokenizer_minimal.vocab_size  # Remove vocab_size
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer_minimal
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        info = adapter.get_model_info()
        
        assert info["model_name"] == "bert-base-uncased"
        # Should handle missing attributes gracefully
    
    @patch('kano_backlog_core.tokenizer.transformers', create=True)
    def test_special_tokens_handling(self, mock_transformers):
        """Test special tokens handling."""
        mock_tokenizer = Mock()
        
        # Configure special tokens
        mock_tokenizer.pad_token = "[PAD]"
        mock_tokenizer.unk_token = "[UNK]"
        mock_tokenizer.cls_token = "[CLS]"
        mock_tokenizer.sep_token = "[SEP]"
        mock_tokenizer.mask_token = "[MASK]"
        
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        
        adapter = HuggingFaceAdapter("bert-base-uncased")
        info = adapter.get_model_info()
        
        assert info["special_tokens"]["pad_token"] == "[PAD]"
        assert info["special_tokens"]["cls_token"] == "[CLS]"
        assert info["special_tokens"]["sep_token"] == "[SEP]"


class TestTokenizerRegistryEdgeCases:
    """Edge case tests for TokenizerRegistry."""
    
    def test_registry_with_custom_error_recovery(self):
        """Test registry with custom error recovery settings."""
        registry = TokenizerRegistry()
        
        # Modify error recovery settings
        registry._error_recovery.max_recovery_attempts = 1
        
        # Create failing adapter
        def failing_adapter(*args, **kwargs):
            raise ImportError("Always fails")
        
        original_adapters = registry._adapters.copy()
        registry._adapters["tiktoken"] = (failing_adapter, {})
        
        try:
            # Should gracefully degrade to an available fallback adapter
            adapter = registry.resolve("tiktoken", "test-model")
            assert adapter.adapter_id == "heuristic"
            
            # Verify recovery attempts were tracked
            stats = registry.get_recovery_statistics()
            assert stats["total_recovery_attempts"] > 0
        finally:
            registry._adapters = original_adapters
    
    def test_registry_memory_management(self):
        """Test registry memory management with many adapters."""
        registry = TokenizerRegistry()
        
        # Create many custom adapters
        class TestAdapter(TokenizerAdapter):
            def __init__(self, model_name: str, max_tokens: Optional[int] = None, test_id: int = 0):
                super().__init__(model_name, max_tokens)
                self.test_id = test_id
            
            @property
            def adapter_id(self) -> str:
                return f"test_{self.test_id}"
            
            def count_tokens(self, text: str) -> TokenCount:
                return TokenCount(1, "test", f"test_{self.test_id}", False)
            
            def max_tokens(self) -> int:
                return 1000
        
        # Register many adapters
        for i in range(100):
            registry.register(f"test_{i}", TestAdapter, test_id=i)
        
        # Verify all were registered
        adapters = registry.list_adapters()
        assert len([a for a in adapters if a.startswith("test_")]) == 100
        
        # Clean up
        for i in range(100):
            if f"test_{i}" in registry._adapters:
                del registry._adapters[f"test_{i}"]
    
    def test_registry_concurrent_access(self):
        """Test registry concurrent access."""
        registry = TokenizerRegistry()
        results = []
        errors = []
        
        def resolve_worker(worker_id: int):
            try:
                adapter = registry.resolve("heuristic", f"model_{worker_id}")
                results.append((worker_id, adapter.adapter_id))
            except Exception as e:
                errors.append((worker_id, e))
        
        # Create multiple threads
        threads = []
        for i in range(20):
            thread = threading.Thread(target=resolve_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 20
        
        # All should have resolved to heuristic
        for worker_id, adapter_id in results:
            assert adapter_id == "heuristic"
    
    def test_registry_with_circular_dependencies(self):
        """Test registry behavior with circular dependency scenarios."""
        registry = TokenizerRegistry()
        
        # Create adapters that reference each other
        class CircularAdapter(TokenizerAdapter):
            def __init__(self, model_name: str, max_tokens: Optional[int] = None, 
                         other_adapter: str = None):
                super().__init__(model_name, max_tokens)
                self.other_adapter = other_adapter
            
            @property
            def adapter_id(self) -> str:
                return "circular"
            
            def count_tokens(self, text: str) -> TokenCount:
                # Try to use other adapter (would cause circular reference)
                if self.other_adapter:
                    # This would cause infinite recursion if not handled
                    pass
                return TokenCount(1, "circular", "circular", False)
            
            def max_tokens(self) -> int:
                return 1000
        
        registry.register("circular1", CircularAdapter, other_adapter="circular2")
        registry.register("circular2", CircularAdapter, other_adapter="circular1")
        
        # Should still work without infinite recursion
        adapter = registry.resolve("circular1", "test-model")
        assert adapter.adapter_id == "circular"


class TestErrorInjectionAndRecovery:
    """Tests for error injection and recovery mechanisms."""
    
    def test_systematic_error_injection(self):
        """Test systematic error injection across all adapters."""
        registry = TokenizerRegistry()
        
        # Define various error types to inject
        error_types = [
            ImportError("Module not found"),
            ValueError("Invalid configuration"),
            RuntimeError("Runtime failure"),
            MemoryError("Out of memory"),
            OSError("System error"),
        ]
        
        for error in error_types:
            # Create failing adapter
            def failing_adapter(*args, **kwargs):
                raise error
            
            original_adapters = registry._adapters.copy()
            
            # Replace all adapters with failing ones
            for adapter_name in ["tiktoken", "huggingface", "heuristic"]:
                registry._adapters[adapter_name] = (failing_adapter, {})
            
            try:
                # Should raise FallbackChainExhaustedError
                with pytest.raises(FallbackChainExhaustedError) as exc_info:
                    registry.resolve("tiktoken", "test-model")
                
                exhausted_error = exc_info.value
                assert len(exhausted_error.attempted_adapters) > 0
                assert len(exhausted_error.errors) > 0
                
                # Error messages should be populated and include adapter context.
                assert all(isinstance(err, str) and err for err in exhausted_error.errors)
                assert all(
                    any(name in err for name in ("tiktoken", "huggingface", "heuristic"))
                    for err in exhausted_error.errors
                )
                
            finally:
                # Restore original adapters
                registry._adapters = original_adapters
    
    def test_partial_recovery_scenarios(self):
        """Test partial recovery scenarios where some adapters work."""
        registry = TokenizerRegistry()
        
        # Test scenarios where different numbers of adapters fail
        for num_failing in range(1, 3):  # 1 or 2 adapters fail
            original_adapters = registry._adapters.copy()
            
            def failing_adapter(*args, **kwargs):
                raise ImportError("Adapter failed")
            
            # Make some adapters fail
            adapter_names = ["tiktoken", "huggingface", "heuristic"]
            for i in range(num_failing):
                registry._adapters[adapter_names[i]] = (failing_adapter, {})
            
            try:
                # Should still succeed with remaining adapters
                adapter = registry.resolve("tiktoken", "test-model")
                assert adapter is not None
                assert adapter.adapter_id in ["tiktoken", "huggingface", "heuristic"]
                
            finally:
                # Restore original adapters
                registry._adapters = original_adapters
    
    def test_recovery_statistics_accuracy(self):
        """Test accuracy of recovery statistics tracking."""
        registry = TokenizerRegistry()
        
        # Inject controlled failures
        failure_count = 0
        
        def counting_failing_adapter(*args, **kwargs):
            nonlocal failure_count
            failure_count += 1
            raise ImportError(f"Failure #{failure_count}")
        
        original_adapters = registry._adapters.copy()
        registry._adapters["tiktoken"] = (counting_failing_adapter, {})
        
        try:
            # Trigger multiple failures
            for i in range(5):
                try:
                    registry.resolve("tiktoken", f"model_{i}")
                except Exception:
                    pass
            
            # Check statistics
            stats = registry.get_recovery_statistics()
            assert stats["total_degradation_events"] >= 5
            
        finally:
            registry._adapters = original_adapters


class TestResourceManagementAndCleanup:
    """Tests for resource management and cleanup."""
    
    def test_memory_leak_prevention(self):
        """Test prevention of memory leaks in adapters."""
        # Create adapters and verify they can be garbage collected
        adapters = []
        weak_refs = []
        
        for i in range(10):
            adapter = HeuristicTokenizer(f"model_{i}")
            adapters.append(adapter)
            weak_refs.append(weakref.ref(adapter))
        
        # Clear strong references
        adapters.clear()
        gc.collect()
        
        # Check if objects were garbage collected
        alive_count = sum(1 for ref in weak_refs if ref() is not None)
        
        # Some may still be alive due to test framework, but shouldn't be all
        assert alive_count < len(weak_refs)
    
    def test_registry_cleanup(self):
        """Test registry cleanup and resource management."""
        registry = TokenizerRegistry()
        
        # Add many custom adapters
        for i in range(50):
            registry.register(f"test_{i}", HeuristicTokenizer)
        
        # Clear error recovery cache
        registry._error_recovery.clear_cache()
        
        # Verify cache was cleared
        assert len(registry._error_recovery.recovery_attempts) == 0
        assert len(registry._error_recovery.degradation_history) == 0
    
    def test_large_text_processing_cleanup(self):
        """Test cleanup after processing large texts."""
        tokenizer = HeuristicTokenizer("test-model")
        
        # Process multiple large texts
        for i in range(5):
            large_text = f"Large text content {i} " * 10000
            result = tokenizer.count_tokens(large_text)
            assert result.count > 0
            
            # Force cleanup
            del large_text
            gc.collect()
        
        # Should complete without memory issues


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
