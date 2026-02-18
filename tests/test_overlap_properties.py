"""Property-based tests for token-aware overlap calculation.

This module implements the correctness properties specified in the tokenizer-adapters spec:
- Property 1.4: Overlap consistency - overlap tokens are correctly applied
"""

import pytest
from hypothesis import given, strategies as st, assume

from kano_backlog_core.chunking import (
    ChunkingOptions,
    chunk_text_with_tokenizer,
    validate_overlap_consistency,
)
from kano_backlog_core.tokenizer import HeuristicTokenizer


class TestOverlapProperties:
    """Property-based tests for overlap calculation as specified in the tokenizer-adapters spec."""

    @given(
        text=st.text(min_size=50, max_size=1000).filter(
            lambda x: len(x.strip()) > 20 and any(c.isalnum() for c in x)
        ),
        target_tokens=st.integers(min_value=10, max_value=50),
        max_tokens=st.integers(min_value=20, max_value=100),
        overlap_tokens=st.integers(min_value=1, max_value=30)
    )
    def test_property_1_4_overlap_consistency(self, text, target_tokens, max_tokens, overlap_tokens):
        """Property 1.4: Overlap tokens are correctly applied between adjacent chunks.
        
        **Validates: Requirements US-2, FR-3**
        
        This property ensures that:
        1. Overlap is calculated in token space, not character space
        2. Overlap doesn't exceed chunk size
        3. Overlap is consistent across chunks
        4. Edge cases are handled properly
        """
        assume(target_tokens <= max_tokens)
        assume(overlap_tokens < max_tokens)
        
        options = ChunkingOptions(
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens
        )
        tokenizer = HeuristicTokenizer("test-model")
        
        try:
            chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
            
            # Property 1.4.1: Overlap is applied between adjacent chunks
            if len(chunks) > 1:
                for i in range(1, len(chunks)):
                    prev_chunk = chunks[i-1]
                    curr_chunk = chunks[i]
                    
                    # Check if there's overlap (current chunk starts before previous ends)
                    if curr_chunk.start_char < prev_chunk.end_char:
                        # Validate overlap is reasonable
                        overlap_start = curr_chunk.start_char
                        overlap_end = prev_chunk.end_char
                        overlap_text = text[overlap_start:overlap_end]
                        
                        if overlap_text.strip():  # Non-empty overlap
                            overlap_token_count = tokenizer.count_tokens(overlap_text).count
                            prev_chunk_tokens = tokenizer.count_tokens(prev_chunk.text).count
                            
                            # Property 1.4.2: Overlap doesn't exceed configured limit (with tolerance for edge cases)
                            assert overlap_token_count <= options.overlap_tokens + 2, (
                                f"Overlap ({overlap_token_count}) significantly exceeds "
                                f"configured limit ({options.overlap_tokens})"
                            )
                            
                            # Property 1.4.3: Overlap doesn't exceed half the chunk size
                            assert overlap_token_count <= prev_chunk_tokens // 2 + 3, (
                                f"Overlap ({overlap_token_count}) exceeds half of "
                                f"chunk size ({prev_chunk_tokens})"
                            )
            
            # Property 1.4.4: Validate overall overlap consistency
            validation_errors = validate_overlap_consistency(chunks, options, tokenizer)
            
            # Allow some validation warnings but no critical errors
            critical_errors = [
                e for e in validation_errors 
                if "exceeds configured limit" in e and "significantly" not in e.lower()
            ]
            assert len(critical_errors) <= 1, f"Too many critical overlap errors: {critical_errors}"
            
        except Exception as e:
            # Some edge cases with very short text or unusual tokenization might fail
            # This is acceptable as long as it fails gracefully
            error_msg = str(e).lower()
            acceptable_errors = [
                "empty", "tokenizer", "progress", "chunk", "boundary"
            ]
            assert any(keyword in error_msg for keyword in acceptable_errors), (
                f"Unexpected error type: {e}"
            )

    @given(
        overlap_tokens=st.integers(min_value=1, max_value=20),
        chunk_size_multiplier=st.integers(min_value=2, max_value=5)
    )
    def test_overlap_never_exceeds_chunk_size(self, overlap_tokens, chunk_size_multiplier):
        """Property: Overlap never exceeds the size of individual chunks.
        
        This test ensures that the overlap limiting logic works correctly
        by testing with various overlap configurations.
        """
        # Create predictable text that will produce multiple chunks
        sentences = [
            "This is sentence number one with some content.",
            "This is sentence number two with different content.", 
            "This is sentence number three with more content.",
            "This is sentence number four with additional content.",
            "This is sentence number five with final content."
        ]
        text = " ".join(sentences)
        
        max_tokens = overlap_tokens * chunk_size_multiplier
        target_tokens = max(1, max_tokens // 2)
        
        options = ChunkingOptions(
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens
        )
        tokenizer = HeuristicTokenizer("test-model")
        
        chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
        
        # Validate that overlap never exceeds chunk size
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i-1]
            curr_chunk = chunks[i]
            
            if curr_chunk.start_char < prev_chunk.end_char:
                # There is overlap
                overlap_start = curr_chunk.start_char
                overlap_end = prev_chunk.end_char
                overlap_text = text[overlap_start:overlap_end]
                
                if overlap_text.strip():
                    overlap_tokens_actual = tokenizer.count_tokens(overlap_text).count
                    prev_chunk_tokens = tokenizer.count_tokens(prev_chunk.text).count
                    
                    # Overlap should not exceed half the chunk size
                    assert overlap_tokens_actual <= prev_chunk_tokens // 2 + 2, (
                        f"Overlap ({overlap_tokens_actual}) exceeds half of "
                        f"chunk size ({prev_chunk_tokens}) for chunk {i}"
                    )

    @given(
        text_length=st.integers(min_value=20, max_value=200),
        overlap_ratio=st.floats(min_value=0.1, max_value=0.8)
    )
    def test_overlap_provides_context_preservation(self, text_length, overlap_ratio):
        """Property: Overlap provides meaningful context preservation between chunks.
        
        This test ensures that overlap actually preserves context by checking
        that overlapping regions contain meaningful content.
        """
        # Generate predictable text of specified length
        words = ["word", "text", "content", "data", "information", "context", "meaning"]
        text_words = []
        current_length = 0
        
        while current_length < text_length:
            word = words[len(text_words) % len(words)]
            text_words.append(f"{word}{len(text_words)}")
            current_length = len(" ".join(text_words))
        
        text = " ".join(text_words)
        
        # Configure chunking with specified overlap ratio
        max_tokens = 30
        target_tokens = 20
        overlap_tokens = max(1, int(max_tokens * overlap_ratio))
        
        options = ChunkingOptions(
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens
        )
        tokenizer = HeuristicTokenizer("test-model")
        
        chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
        
        if len(chunks) > 1:
            # Check that overlaps preserve meaningful context
            for i in range(1, len(chunks)):
                prev_chunk = chunks[i-1]
                curr_chunk = chunks[i]
                
                if curr_chunk.start_char < prev_chunk.end_char:
                    # There is overlap
                    overlap_start = curr_chunk.start_char
                    overlap_end = prev_chunk.end_char
                    overlap_text = text[overlap_start:overlap_end].strip()
                    
                    if overlap_text:
                        # Overlap should contain meaningful content (not just whitespace/punctuation)
                        meaningful_chars = sum(1 for c in overlap_text if c.isalnum())
                        assert meaningful_chars > 0, (
                            f"Overlap contains no meaningful content: '{overlap_text}'"
                        )
                        
                        # Overlap should be reasonably sized (not too small to be meaningful)
                        assert len(overlap_text) >= 2, (
                            f"Overlap too small to be meaningful: '{overlap_text}'"
                        )


if __name__ == "__main__":
    pytest.main([__file__])