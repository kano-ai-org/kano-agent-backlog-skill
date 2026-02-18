"""Tests for token-aware overlap calculation.

This module tests the enhanced overlap calculation functionality that:
1. Works in token space using tokenizer adapters
2. Ensures overlap doesn't exceed chunk size
3. Handles edge cases (very short chunks, large overlap)
4. Validates overlap consistency across chunks
"""

import pytest
from hypothesis import given, strategies as st, assume

from kano_backlog_core.chunking import (
    ChunkingOptions,
    chunk_text,
    chunk_text_with_tokenizer,
    validate_overlap_consistency,
    _calculate_overlap_start,
)
from kano_backlog_core.tokenizer import (
    HeuristicTokenizer,
    TiktokenAdapter,
    HuggingFaceAdapter,
    TokenizerRegistry,
    resolve_tokenizer_with_fallback,
)


class TestTokenAwareOverlapCalculation:
    """Test token-aware overlap calculation functionality."""

    def test_basic_overlap_calculation(self):
        """Test basic overlap calculation with heuristic tokenizer."""
        text = "This is a test document. It has multiple sentences. Each sentence should be handled properly."
        options = ChunkingOptions(target_tokens=10, max_tokens=20, overlap_tokens=5)
        tokenizer = HeuristicTokenizer("test-model")
        
        chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
        
        # Should produce multiple chunks
        assert len(chunks) > 1
        
        # Validate overlap consistency
        errors = validate_overlap_consistency(chunks, options, tokenizer)
        assert not errors, f"Overlap validation errors: {errors}"

    def test_overlap_doesnt_exceed_chunk_size(self):
        """Test that overlap never exceeds the size of the chunk."""
        text = "Short. Text. With. Many. Small. Sentences. For. Testing. Overlap. Behavior."
        options = ChunkingOptions(target_tokens=3, max_tokens=6, overlap_tokens=4)  # Large but valid overlap
        tokenizer = HeuristicTokenizer("test-model")
        
        chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
        
        # Validate that no overlap exceeds chunk size
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i-1]
            curr_chunk = chunks[i]
            
            if curr_chunk.start_char < prev_chunk.end_char:
                # There is overlap
                overlap_text = prev_chunk.text[curr_chunk.start_char - prev_chunk.start_char:]
                overlap_tokens = tokenizer.count_tokens(overlap_text).count
                prev_chunk_tokens = tokenizer.count_tokens(prev_chunk.text).count
                
                # Overlap should not exceed half the previous chunk size
                assert overlap_tokens <= prev_chunk_tokens // 2 + 1, (
                    f"Overlap ({overlap_tokens}) exceeds half of chunk size ({prev_chunk_tokens})"
                )

    def test_very_short_chunks_minimal_overlap(self):
        """Test that very short chunks get minimal or no overlap."""
        text = "A. B. C. D. E."  # Very short chunks
        options = ChunkingOptions(target_tokens=1, max_tokens=2, overlap_tokens=1)  # Valid overlap
        tokenizer = HeuristicTokenizer("test-model")
        
        chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
        
        # Should still produce chunks
        assert len(chunks) > 0
        
        # Validate overlap is reasonable for very short chunks
        errors = validate_overlap_consistency(chunks, options, tokenizer)
        # We expect some validation warnings for very short chunks, but no critical errors
        critical_errors = [e for e in errors if "exceeds" in e and "configured limit" in e]
        assert not critical_errors, f"Critical overlap errors: {critical_errors}"

    def test_large_overlap_configuration(self):
        """Test behavior when overlap_tokens is configured to be very large."""
        text = "This is a longer document with multiple sentences that should be chunked properly even with large overlap configuration. " \
               "It needs to be long enough to force multiple chunks even with large overlap settings. " \
               "Each sentence adds more content to ensure we get multiple chunks for testing purposes."
        options = ChunkingOptions(target_tokens=15, max_tokens=30, overlap_tokens=25)  # Very large but valid overlap
        tokenizer = HeuristicTokenizer("test-model")
        
        chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
        
        # Should still produce multiple chunks with longer text
        assert len(chunks) > 1, f"Expected multiple chunks, got {len(chunks)} chunks"
        
        # Validate that the large overlap is handled gracefully
        errors = validate_overlap_consistency(chunks, options, tokenizer)
        # Should not have critical errors due to overlap limiting
        for error in errors:
            # Large overlaps should be limited, so we shouldn't see configured limit exceeded
            assert "exceeds configured limit" not in error, f"Unexpected error: {error}"

    def test_no_overlap_configuration(self):
        """Test that no overlap works correctly."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        options = ChunkingOptions(target_tokens=5, max_tokens=10, overlap_tokens=0)
        tokenizer = HeuristicTokenizer("test-model")
        
        chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
        
        # Should produce multiple chunks
        assert len(chunks) > 1
        
        # Verify no overlap between chunks
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i-1]
            curr_chunk = chunks[i]
            assert curr_chunk.start_char >= prev_chunk.end_char, (
                f"Unexpected overlap: chunk {i} starts at {curr_chunk.start_char}, "
                f"previous ends at {prev_chunk.end_char}"
            )

    def test_overlap_with_different_tokenizers(self):
        """Test overlap calculation with different tokenizer types."""
        text = "This is a test document for comparing tokenizer behavior with overlap calculation."
        options = ChunkingOptions(target_tokens=10, max_tokens=20, overlap_tokens=5)
        
        tokenizers = [
            HeuristicTokenizer("test-model"),
        ]
        
        # Add TikToken if available
        try:
            tokenizers.append(TiktokenAdapter("gpt-3.5-turbo"))
        except ImportError:
            pass
        
        # Add HuggingFace if available
        try:
            tokenizers.append(HuggingFaceAdapter("sentence-transformers/all-MiniLM-L6-v2"))
        except ImportError:
            pass
        
        results = []
        for tokenizer in tokenizers:
            chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
            errors = validate_overlap_consistency(chunks, options, tokenizer)
            results.append((tokenizer.adapter_id, len(chunks), len(errors)))
        
        # All tokenizers should produce valid results
        for adapter_id, chunk_count, error_count in results:
            assert chunk_count > 0, f"No chunks produced by {adapter_id}"
            # Allow some validation warnings but no critical errors
            assert error_count <= 2, f"Too many validation errors for {adapter_id}: {error_count}"

    def test_overlap_consistency_validation(self):
        """Test the overlap consistency validation function."""
        text = "Test document with multiple sentences for validation testing."
        options = ChunkingOptions(target_tokens=8, max_tokens=15, overlap_tokens=4)
        tokenizer = HeuristicTokenizer("test-model")
        
        chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
        
        # Test validation with tokenizer
        errors_with_tokenizer = validate_overlap_consistency(chunks, options, tokenizer)
        
        # Test validation without tokenizer
        errors_without_tokenizer = validate_overlap_consistency(chunks, options, None)
        
        # Both should complete without exceptions
        assert isinstance(errors_with_tokenizer, list)
        assert isinstance(errors_without_tokenizer, list)
        
        # With tokenizer should provide more detailed validation
        # (though both might have zero errors for well-formed chunks)

    def test_calculate_overlap_start_edge_cases(self):
        """Test the _calculate_overlap_start function with edge cases."""
        text = "Short text for testing."
        tokenizer = HeuristicTokenizer("test-model")
        options = ChunkingOptions(overlap_tokens=5)
        
        # Test with very short text
        result = _calculate_overlap_start(text, len(text), options, tokenizer, 0)
        assert 0 <= result <= len(text)
        
        # Test with zero overlap
        options_no_overlap = ChunkingOptions(overlap_tokens=0)
        result = _calculate_overlap_start(text, len(text), options_no_overlap, tokenizer, 0)
        assert result == len(text)
        
        # Test with overlap larger than text
        options_large_overlap = ChunkingOptions(overlap_tokens=100)
        result = _calculate_overlap_start(text, len(text), options_large_overlap, tokenizer, 0)
        assert 0 <= result <= len(text)


class TestOverlapProperties:
    """Property-based tests for overlap calculation."""

    @given(
        text=st.text(min_size=10, max_size=1000).filter(lambda x: x.strip()),
        target_tokens=st.integers(min_value=5, max_value=50),
        max_tokens=st.integers(min_value=10, max_value=100),
        overlap_tokens=st.integers(min_value=0, max_value=20)
    )
    def test_overlap_never_exceeds_limits(self, text, target_tokens, max_tokens, overlap_tokens):
        """Property: Overlap never exceeds configured limits or chunk sizes."""
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
            
            # Validate overlap consistency
            errors = validate_overlap_consistency(chunks, options, tokenizer)
            
            # Should not have critical errors about exceeding configured limits
            critical_errors = [e for e in errors if "exceeds configured limit" in e]
            assert not critical_errors, f"Critical overlap errors: {critical_errors}"
            
        except Exception as e:
            # Some edge cases might fail, but they should fail gracefully
            assert "tokenizer" in str(e).lower() or "empty" in str(e).lower()

    @given(
        overlap_tokens=st.integers(min_value=1, max_value=15)
    )
    def test_overlap_provides_context_preservation(self, overlap_tokens):
        """Property: Overlap provides meaningful context preservation."""
        # Use a simple, predictable text for this test
        text = "This is sentence one. This is sentence two. This is sentence three. This is sentence four."
        
        options = ChunkingOptions(
            target_tokens=10,
            max_tokens=20,
            overlap_tokens=overlap_tokens
        )
        tokenizer = HeuristicTokenizer("test-model")
        
        chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
        
        if len(chunks) > 1:
            # Check that overlapping chunks share some content
            for i in range(1, len(chunks)):
                prev_chunk = chunks[i-1]
                curr_chunk = chunks[i]
                
                if curr_chunk.start_char < prev_chunk.end_char:
                    # There is overlap - this is the main thing we're testing
                    overlap_start = curr_chunk.start_char
                    overlap_end = prev_chunk.end_char
                    
                    # Basic validation that overlap makes sense
                    assert overlap_start < overlap_end
                    assert overlap_start >= prev_chunk.start_char
                    assert overlap_end <= prev_chunk.end_char

    @given(
        max_tokens=st.integers(min_value=5, max_value=20)
    )
    def test_chunking_always_makes_progress(self, max_tokens):
        """Property: Chunking always makes forward progress regardless of overlap."""
        # Use predictable text that will definitely produce chunks
        text = "Word one. Word two. Word three. Word four. Word five. Word six."
        
        target_tokens = max(1, max_tokens // 2)
        overlap_tokens = max(0, max_tokens - 2)  # Large overlap
        
        options = ChunkingOptions(
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens
        )
        tokenizer = HeuristicTokenizer("test-model")
        
        chunks = chunk_text_with_tokenizer("test-doc", text, options, tokenizer)
        
        # Must produce at least one chunk for non-empty input
        assert len(chunks) >= 1
        
        # Each chunk must make some progress
        if len(chunks) > 1:
            for i in range(1, len(chunks)):
                prev_chunk = chunks[i-1]
                curr_chunk = chunks[i]
                
                # Current chunk must start at or after previous chunk start
                assert curr_chunk.start_char >= prev_chunk.start_char
                
                # Current chunk must have some new content (not be identical)
                assert curr_chunk.end_char > prev_chunk.start_char


if __name__ == "__main__":
    pytest.main([__file__])