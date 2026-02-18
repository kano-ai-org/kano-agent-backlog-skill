"""Tests for TokenBudgetManager and enhanced token budget functionality."""

import pytest
from typing import Optional

from kano_backlog_core.token_budget import (
    TokenBudgetManager,
    BudgetResult,
    TokenBudgetPolicy,
    enforce_token_budget,
    TokenBudgetResult,
)
from kano_backlog_core.chunking import ChunkingOptions
from kano_backlog_core.tokenizer import HeuristicTokenizer, TokenCount


class TestTokenBudgetManager:
    """Test suite for TokenBudgetManager class."""

    def create_test_manager(
        self, 
        max_tokens: int = 100, 
        target_tokens: int = 50,
        tokenizer: Optional[HeuristicTokenizer] = None
    ) -> TokenBudgetManager:
        """Create a test TokenBudgetManager instance."""
        if tokenizer is None:
            tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
        
        # Ensure target_tokens is valid relative to max_tokens
        if target_tokens > max_tokens:
            target_tokens = max(1, max_tokens // 2)
        
        options = ChunkingOptions(
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=min(10, max_tokens // 4)  # Ensure overlap is reasonable
        )
        return TokenBudgetManager(options, tokenizer)

    def test_manager_initialization(self) -> None:
        """Test TokenBudgetManager initialization."""
        manager = self.create_test_manager(max_tokens=100)
        
        assert manager.options.max_tokens == 100
        assert manager.effective_max == 84  # 100 - 16 (safety margin)
        assert manager.safety_margin == 16
        assert isinstance(manager.tokenizer, HeuristicTokenizer)

    def test_manager_initialization_with_large_safety_margin(self) -> None:
        """Test TokenBudgetManager with large token limit uses percentage-based safety margin."""
        manager = self.create_test_manager(max_tokens=1000)
        
        # Should use 10% safety margin (100 tokens) instead of minimum 16
        assert manager.effective_max == 900  # 1000 - 100
        assert manager.safety_margin == 100

    def test_apply_budget_no_trimming_needed(self) -> None:
        """Test apply_budget when text fits within budget."""
        manager = self.create_test_manager(max_tokens=100)
        text = "Short text"  # Should be well under budget
        
        result = manager.apply_budget(text)
        
        assert isinstance(result, BudgetResult)
        assert result.text == text
        assert result.was_trimmed is False
        assert result.token_count.count <= manager.effective_max
        assert result.original_token_count == result.token_count.count

    def test_apply_budget_with_trimming(self) -> None:
        """Test apply_budget when text exceeds budget and needs trimming."""
        manager = self.create_test_manager(max_tokens=20)  # Very small budget
        text = "This is a very long text that should definitely exceed the token budget and require trimming to fit within the specified limits."
        
        result = manager.apply_budget(text)
        
        assert isinstance(result, BudgetResult)
        assert result.was_trimmed is True
        assert len(result.text) < len(text)
        assert result.token_count.count <= manager.effective_max
        assert result.original_token_count > result.token_count.count
        assert len(result.text) > 0  # Progress guarantee

    def test_apply_budget_empty_text(self) -> None:
        """Test apply_budget with empty text."""
        manager = self.create_test_manager()
        
        result = manager.apply_budget("")
        
        assert result.text == ""
        assert result.was_trimmed is False
        assert result.token_count.count == 0
        assert result.original_token_count == 0

    def test_apply_budget_single_character(self) -> None:
        """Test apply_budget with single character (progress guarantee)."""
        manager = self.create_test_manager(max_tokens=1)  # Extremely small budget
        
        result = manager.apply_budget("A")
        
        # Should return at least the single character even if it exceeds budget
        assert len(result.text) >= 1
        assert result.text == "A"

    def test_binary_search_trim_optimization(self) -> None:
        """Test that binary search trimming works efficiently."""
        manager = self.create_test_manager(max_tokens=50)
        
        # Create text that will require binary search
        text = "Word " * 100  # 100 repetitions of "Word "
        
        result = manager.apply_budget(text)
        
        assert result.was_trimmed is True
        assert result.token_count.count <= manager.effective_max
        assert len(result.text) > 0
        
        # Verify the result is deterministic
        result2 = manager.apply_budget(text)
        assert result.text == result2.text

    def test_validate_budget_compliance(self) -> None:
        """Test budget compliance validation."""
        manager = self.create_test_manager(max_tokens=50)
        
        # Text that fits
        short_text = "Short text"
        assert manager.validate_budget_compliance(short_text) is True
        
        # Text that doesn't fit
        long_text = "Very long text " * 20
        assert manager.validate_budget_compliance(long_text) is False
        
        # Empty text
        assert manager.validate_budget_compliance("") is True

    def test_get_budget_info(self) -> None:
        """Test budget information retrieval."""
        tokenizer = HeuristicTokenizer("test-model-123", chars_per_token=3.5)
        manager = self.create_test_manager(max_tokens=200, tokenizer=tokenizer)
        
        info = manager.get_budget_info()
        
        assert isinstance(info, dict)
        assert info["max_tokens"] == 200
        assert info["effective_max"] == 180  # 200 - 20 (10% safety margin)
        assert info["safety_margin"] == 20
        assert info["tokenizer_id"] == "heuristic"
        assert info["model_name"] == "test-model-123"

    def test_deterministic_trimming(self) -> None:
        """Test that trimming is deterministic for the same input."""
        manager = self.create_test_manager(max_tokens=30)
        text = "This is a test text that will be trimmed consistently every time."
        
        # Apply budget multiple times
        results = [manager.apply_budget(text) for _ in range(5)]
        
        # All results should be identical
        first_result = results[0]
        for result in results[1:]:
            assert result.text == first_result.text
            assert result.token_count.count == first_result.token_count.count
            assert result.was_trimmed == first_result.was_trimmed

    def test_progress_guarantee(self) -> None:
        """Test that trimming always makes progress (never returns empty for non-empty input)."""
        manager = self.create_test_manager(max_tokens=1)  # Extremely restrictive budget
        
        test_cases = [
            "A",
            "Hello",
            "Very long text that exceeds any reasonable token budget",
            "你好",  # CJK characters
            "Mixed English and 中文 text",
        ]
        
        for text in test_cases:
            result = manager.apply_budget(text)
            assert len(result.text) > 0, f"Empty result for input: {text}"
            assert result.token_count.count > 0

    def test_cjk_text_handling(self) -> None:
        """Test token budget management with CJK text."""
        manager = self.create_test_manager(max_tokens=20)
        cjk_text = "你好世界这是一个测试文本用于验证中文字符的处理能力"
        
        result = manager.apply_budget(cjk_text)
        
        assert isinstance(result, BudgetResult)
        assert result.token_count.count <= manager.effective_max
        if result.was_trimmed:
            assert len(result.text) < len(cjk_text)
            assert len(result.text) > 0

    def test_mixed_language_text(self) -> None:
        """Test token budget management with mixed language text."""
        manager = self.create_test_manager(max_tokens=25)
        mixed_text = "Hello world 你好世界 this is mixed content with English and Chinese characters."
        
        result = manager.apply_budget(mixed_text)
        
        assert isinstance(result, BudgetResult)
        assert result.token_count.count <= manager.effective_max
        if result.was_trimmed:
            assert len(result.text) > 0


class TestTokenBudgetManagerIntegration:
    """Integration tests for TokenBudgetManager with different tokenizers."""

    def test_manager_with_different_tokenizers(self) -> None:
        """Test TokenBudgetManager works with different tokenizer configurations."""
        tokenizers = [
            HeuristicTokenizer("model1", chars_per_token=3.0),
            HeuristicTokenizer("model2", chars_per_token=5.0),
            HeuristicTokenizer("model3", chars_per_token=4.5),
        ]
        
        text = "This is a test text for tokenizer comparison."
        
        for tokenizer in tokenizers:
            options = ChunkingOptions(
                target_tokens=25,  # Set appropriate target_tokens
                max_tokens=50,
                overlap_tokens=5
            )
            manager = TokenBudgetManager(options, tokenizer)
            
            result = manager.apply_budget(text)
            assert isinstance(result, BudgetResult)
            assert result.token_count.count <= manager.effective_max

    def test_manager_budget_info_consistency(self) -> None:
        """Test that budget info remains consistent across operations."""
        manager = self.create_test_manager(max_tokens=100)
        
        # Get initial budget info
        initial_info = manager.get_budget_info()
        
        # Apply budget to some text
        manager.apply_budget("Some test text")
        
        # Budget info should remain the same
        final_info = manager.get_budget_info()
        assert initial_info == final_info

    def create_test_manager(self, max_tokens: int = 100) -> TokenBudgetManager:
        """Helper to create test manager."""
        tokenizer = HeuristicTokenizer("test-model")
        target_tokens = max(1, max_tokens // 2)  # Ensure valid target_tokens
        options = ChunkingOptions(
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=min(10, max_tokens // 4)
        )
        return TokenBudgetManager(options, tokenizer)


class TestBackwardCompatibility:
    """Test backward compatibility with existing token budget functions."""

    def test_enforce_token_budget_compatibility(self) -> None:
        """Test that enforce_token_budget still works with new implementation."""
        tokenizer = HeuristicTokenizer("test-model")
        text = "This is a test text for backward compatibility."
        
        result = enforce_token_budget(text, tokenizer, max_tokens=50)
        
        assert isinstance(result, TokenBudgetResult)
        assert result.content == text or len(result.content) < len(text)
        assert result.token_count.count > 0
        assert isinstance(result.trimmed, bool)
        assert result.target_budget > 0
        assert result.safety_margin >= 0

    def test_enforce_token_budget_with_policy(self) -> None:
        """Test enforce_token_budget with custom policy."""
        tokenizer = HeuristicTokenizer("test-model")
        policy = TokenBudgetPolicy(safety_margin_ratio=0.2, safety_margin_min_tokens=10)
        text = "Test text with custom policy."
        
        result = enforce_token_budget(text, tokenizer, max_tokens=100, policy=policy)
        
        assert isinstance(result, TokenBudgetResult)
        assert result.safety_margin >= 10  # Should respect minimum
        # With 20% margin on 100 tokens, should be 20 tokens margin
        assert result.target_budget <= 80

    def test_legacy_result_format(self) -> None:
        """Test that legacy TokenBudgetResult format is maintained."""
        tokenizer = HeuristicTokenizer("test-model")
        text = "Legacy format test"
        
        result = enforce_token_budget(text, tokenizer, max_tokens=50)
        
        # Check all expected fields exist
        assert hasattr(result, 'content')
        assert hasattr(result, 'token_count')
        assert hasattr(result, 'trimmed')
        assert hasattr(result, 'target_budget')
        assert hasattr(result, 'safety_margin')
        
        # Check field types
        assert isinstance(result.content, str)
        assert isinstance(result.token_count, TokenCount)
        assert isinstance(result.trimmed, bool)
        assert isinstance(result.target_budget, int)
        assert isinstance(result.safety_margin, int)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_zero_max_tokens(self) -> None:
        """Test behavior with zero max tokens."""
        tokenizer = HeuristicTokenizer("test-model")
        
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            enforce_token_budget("test", tokenizer, max_tokens=0)

    def test_negative_max_tokens(self) -> None:
        """Test behavior with negative max tokens."""
        tokenizer = HeuristicTokenizer("test-model")
        
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            enforce_token_budget("test", tokenizer, max_tokens=-1)

    def test_very_small_budget(self) -> None:
        """Test behavior with very small token budget."""
        options = ChunkingOptions(
            target_tokens=1,  # Set target_tokens appropriately
            max_tokens=2,  # Extremely small
            overlap_tokens=0  # No overlap for very small budget
        )
        tokenizer = HeuristicTokenizer("test-model")
        manager = TokenBudgetManager(options, tokenizer)
        
        text = "This is a longer text"
        result = manager.apply_budget(text)
        
        # Should still return something (progress guarantee)
        assert len(result.text) > 0
        assert result.was_trimmed is True

    def test_whitespace_only_text(self) -> None:
        """Test behavior with whitespace-only text."""
        manager = TokenBudgetManager(
            ChunkingOptions(
                target_tokens=25,  # Set target_tokens appropriately
                max_tokens=50,
                overlap_tokens=5
            ),
            HeuristicTokenizer("test-model")
        )
        
        whitespace_texts = ["   ", "\n\n\n", "\t\t", " \n \t "]
        
        for text in whitespace_texts:
            result = manager.apply_budget(text)
            assert isinstance(result, BudgetResult)
            # Whitespace might be trimmed or preserved depending on tokenizer


if __name__ == "__main__":
    pytest.main([__file__])