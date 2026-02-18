"""Property-based tests for TokenBudgetManager correctness properties."""

import pytest
from hypothesis import given, strategies as st, assume

from kano_backlog_core.token_budget import TokenBudgetManager, BudgetResult
from kano_backlog_core.chunking import ChunkingOptions
from kano_backlog_core.tokenizer import HeuristicTokenizer


class TestTokenBudgetProperties:
    """Property-based tests for token budget management."""

    def create_test_manager(self, max_tokens: int, target_tokens: int = None) -> TokenBudgetManager:
        """Create a test TokenBudgetManager with valid configuration."""
        if target_tokens is None:
            target_tokens = max(1, max_tokens // 2)
        
        options = ChunkingOptions(
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=min(10, max_tokens // 4)
        )
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
        return TokenBudgetManager(options, tokenizer)

    @given(st.text(min_size=1, max_size=1000), st.integers(min_value=10, max_value=500))
    def test_property_budget_compliance(self, text: str, max_tokens: int) -> None:
        """Property 1.2: Token budget compliance - chunks never exceed max tokens.
        
        **Validates: Requirements US-2, FR-4**
        """
        assume(len(text.strip()) > 0)  # Ensure non-empty text
        
        manager = self.create_test_manager(max_tokens)
        result = manager.apply_budget(text)
        
        # Budget compliance: result should never exceed effective max tokens
        assert result.token_count.count <= manager.effective_max, (
            f"Token count {result.token_count.count} exceeds effective max {manager.effective_max}"
        )
        
        # Additional validation: result should be valid
        assert isinstance(result, BudgetResult)
        assert isinstance(result.text, str)
        assert result.token_count.count >= 0

    @given(st.text(min_size=1, max_size=1000))
    def test_property_deterministic_behavior(self, text: str) -> None:
        """Property 1.1: Deterministic behavior - same input produces identical output.
        
        **Validates: Requirements US-2, FR-3**
        """
        assume(len(text.strip()) > 0)
        
        manager = self.create_test_manager(max_tokens=100)
        
        # Apply budget multiple times
        result1 = manager.apply_budget(text)
        result2 = manager.apply_budget(text)
        result3 = manager.apply_budget(text)
        
        # All results should be identical
        assert result1.text == result2.text == result3.text
        assert result1.token_count.count == result2.token_count.count == result3.token_count.count
        assert result1.was_trimmed == result2.was_trimmed == result3.was_trimmed
        assert result1.original_token_count == result2.original_token_count == result3.original_token_count

    @given(st.text(min_size=1, max_size=2000), st.integers(min_value=5, max_value=100))
    def test_property_progress_guarantee(self, text: str, max_tokens: int) -> None:
        """Property 1.3: Progress guarantee - always makes forward progress.
        
        **Validates: Requirements FR-3, NFR-2**
        """
        assume(len(text.strip()) > 0)
        
        manager = self.create_test_manager(max_tokens)
        result = manager.apply_budget(text)
        
        # Progress guarantee: must produce non-empty output for non-empty input
        assert len(result.text) > 0, "Empty result for non-empty input violates progress guarantee"
        assert result.token_count.count > 0, "Zero token count for non-empty input"
        
        # If trimming occurred, result should be shorter than original
        if result.was_trimmed:
            assert len(result.text) <= len(text), "Trimmed text should not be longer than original"
            assert result.token_count.count < result.original_token_count

    @given(st.integers(min_value=10, max_value=1000))
    def test_property_safety_margin_consistency(self, max_tokens: int) -> None:
        """Property: Safety margin is consistently applied.
        
        **Validates: Requirements FR-4**
        """
        manager = self.create_test_manager(max_tokens)
        
        # Safety margin should be at least 10% or 16 tokens, whichever is larger
        expected_margin = max(int(max_tokens * 0.1), 16)
        expected_effective_max = max(1, max_tokens - expected_margin)
        
        assert manager.safety_margin == expected_margin
        assert manager.effective_max == expected_effective_max
        
        # Budget info should be consistent
        info = manager.get_budget_info()
        assert info["max_tokens"] == max_tokens
        assert info["effective_max"] == expected_effective_max
        assert info["safety_margin"] == expected_margin

    @given(st.text(min_size=1, max_size=500), st.integers(min_value=20, max_value=200))
    def test_property_trimming_preserves_prefix(self, text: str, max_tokens: int) -> None:
        """Property: Trimming preserves text prefix (tail-first trimming).
        
        **Validates: Requirements FR-4**
        """
        assume(len(text.strip()) > 0)
        
        manager = self.create_test_manager(max_tokens)
        result = manager.apply_budget(text)
        
        # If trimming occurred, result should be a prefix of the original
        if result.was_trimmed:
            assert text.startswith(result.text), "Trimmed text should be a prefix of original"
            assert len(result.text) < len(text), "Trimmed text should be shorter"
        else:
            # If no trimming, result should be identical to input
            assert result.text == text

    @given(st.text(min_size=0, max_size=100))
    def test_property_empty_and_short_text_handling(self, text: str) -> None:
        """Property: Correct handling of empty and very short text.
        
        **Validates: Requirements NFR-2**
        """
        manager = self.create_test_manager(max_tokens=50)
        result = manager.apply_budget(text)
        
        if len(text) == 0:
            # Empty input should produce empty output
            assert result.text == ""
            assert result.token_count.count == 0
            assert result.was_trimmed is False
            assert result.original_token_count == 0
        else:
            # Non-empty input should produce non-empty output (progress guarantee)
            assert len(result.text) > 0
            assert result.token_count.count > 0

    @given(st.integers(min_value=1, max_value=10))
    def test_property_extreme_budget_constraints(self, max_tokens: int) -> None:
        """Property: Handles extreme budget constraints gracefully.
        
        **Validates: Requirements NFR-2**
        """
        manager = self.create_test_manager(max_tokens)
        
        # Test with various text lengths
        test_texts = [
            "A",
            "Hello",
            "This is a longer text that will definitely exceed a very small budget",
            "你好",  # CJK
            "Mixed English and 中文 content"
        ]
        
        for text in test_texts:
            result = manager.apply_budget(text)
            
            # Should always produce valid result
            assert isinstance(result, BudgetResult)
            assert result.token_count.count <= manager.effective_max
            
            # Progress guarantee: non-empty input produces non-empty output
            if len(text) > 0:
                assert len(result.text) > 0
                assert result.token_count.count > 0

    @given(st.text(min_size=1, max_size=200).filter(lambda x: any(ord(c) > 127 for c in x)))
    def test_property_unicode_text_handling(self, text: str) -> None:
        """Property: Correct handling of Unicode text including CJK.
        
        **Validates: Requirements US-3**
        """
        assume(len(text.strip()) > 0)
        
        manager = self.create_test_manager(max_tokens=100)
        result = manager.apply_budget(text)
        
        # Should handle Unicode text without errors
        assert isinstance(result.text, str)
        assert result.token_count.count >= 0
        
        # If trimming occurred, result should still be valid Unicode
        if result.was_trimmed:
            # Should not break in the middle of multi-byte characters
            try:
                result.text.encode('utf-8')
            except UnicodeEncodeError:
                pytest.fail("Trimming broke Unicode character encoding")

    @given(st.text(min_size=1, max_size=100), st.integers(min_value=10, max_value=100))
    def test_property_validation_consistency(self, text: str, max_tokens: int) -> None:
        """Property: Budget validation is consistent with budget application.
        
        **Validates: Requirements FR-4**
        """
        assume(len(text.strip()) > 0)
        
        manager = self.create_test_manager(max_tokens)
        result = manager.apply_budget(text)
        
        # Validation should be consistent with the result
        is_compliant = manager.validate_budget_compliance(result.text)
        assert is_compliant is True, "Applied budget result should always be compliant"
        
        # Original text compliance should match whether trimming was needed
        original_compliant = manager.validate_budget_compliance(text)
        assert original_compliant == (not result.was_trimmed), (
            "Original text compliance should match trimming necessity"
        )


class TestTokenBudgetManagerEdgeProperties:
    """Property-based tests for edge cases and boundary conditions."""

    @given(st.integers(min_value=1, max_value=5))
    def test_property_minimal_budget_handling(self, max_tokens: int) -> None:
        """Property: Handles minimal budgets correctly.
        
        **Validates: Requirements NFR-2**
        """
        # Create manager with minimal budget
        options = ChunkingOptions(
            target_tokens=1,
            max_tokens=max_tokens,
            overlap_tokens=0
        )
        tokenizer = HeuristicTokenizer("test-model")
        manager = TokenBudgetManager(options, tokenizer)
        
        test_text = "This is a test text that is longer than the minimal budget allows."
        result = manager.apply_budget(test_text)
        
        # Should still produce valid result
        assert len(result.text) > 0  # Progress guarantee
        assert result.token_count.count <= manager.effective_max
        assert result.was_trimmed is True  # Should be trimmed for long text

    def test_property_whitespace_text_handling(self) -> None:
        """Property: Handles whitespace-only text appropriately.
        
        **Validates: Requirements NFR-2**
        """
        manager = TokenBudgetManager(
            ChunkingOptions(target_tokens=25, max_tokens=50, overlap_tokens=5),
            HeuristicTokenizer("test-model")
        )
        
        # Test with various whitespace texts
        whitespace_texts = ["   ", "\n\n\n", "\t\t", " \n \t ", "    \n    "]
        
        for text in whitespace_texts:
            result = manager.apply_budget(text)
            
            # Should handle whitespace text without errors
            assert isinstance(result, BudgetResult)
            assert isinstance(result.text, str)
            assert result.token_count.count >= 0


if __name__ == "__main__":
    pytest.main([__file__])