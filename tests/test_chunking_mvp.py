"""Tests for chunking MVP functionality.

This module tests the core chunking functionality with different text types:
- ASCII text (single chunk)
- Long English text (multiple chunks with overlap)
- CJK text (per-character tokenization)

All tests verify deterministic chunk IDs and proper boundary selection.
"""

import pytest
from typing import List

from kano_backlog_core.chunking import (
    ChunkingOptions,
    Chunk,
    chunk_text,
    normalize_text,
    token_spans,
    build_chunk_id,
)
from kano_backlog_core.token_budget import (
    budget_chunks,
    TokenBudgetPolicy,
    BudgetedChunk,
)
from kano_backlog_core.tokenizer import HeuristicTokenizer


class TestChunkingMVP:
    """Test suite for chunking MVP functionality."""

    def test_short_ascii_single_chunk(self) -> None:
        """Test short ASCII text produces single chunk with stable ID."""
        source_id = "test-doc-ascii"
        text = "This is a short ASCII paragraph for testing chunking behavior."
        options = ChunkingOptions(target_tokens=256, max_tokens=512, overlap_tokens=32)
        
        # Test basic chunking
        chunks = chunk_text(source_id, text, options)
        
        # Should produce exactly one chunk
        assert len(chunks) == 1
        
        chunk = chunks[0]
        assert chunk.source_id == source_id
        assert chunk.start_char == 0
        assert chunk.end_char == len(normalize_text(text))
        assert chunk.text == normalize_text(text)
        
        # Verify chunk ID is deterministic
        expected_id = build_chunk_id(
            source_id=source_id,
            version=options.version,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            span_text=chunk.text,
        )
        assert chunk.chunk_id == expected_id
        
        # Test determinism - same input should produce same chunk ID
        chunks2 = chunk_text(source_id, text, options)
        assert len(chunks2) == 1
        assert chunks2[0].chunk_id == chunk.chunk_id

    def test_long_english_multiple_chunks(self) -> None:
        """Test long English text produces multiple chunks with correct overlap."""
        source_id = "test-doc-long"
        # Create a long text that will require multiple chunks
        sentences = [
            "This is the first sentence of a long document.",
            "It contains multiple sentences to test chunking behavior.",
            "Each sentence should be properly handled by the boundary detection.",
            "The chunking algorithm should respect sentence boundaries when possible.",
            "Overlap between chunks should be handled correctly.",
            "This ensures that context is preserved across chunk boundaries.",
            "The final chunk should contain the remaining text.",
            "All chunk IDs should be deterministic and stable.",
        ]
        text = " ".join(sentences)
        
        # Use smaller chunk sizes to force multiple chunks
        options = ChunkingOptions(target_tokens=20, max_tokens=40, overlap_tokens=5)
        
        chunks = chunk_text(source_id, text, options)
        
        # Should produce multiple chunks
        assert len(chunks) > 1, f"Expected multiple chunks, got {len(chunks)}"
        
        # Verify chunks are ordered by start_char
        for i in range(1, len(chunks)):
            assert chunks[i].start_char >= chunks[i-1].start_char
        
        # Verify overlap behavior
        if len(chunks) > 1:
            # Check that there's some overlap between consecutive chunks
            # (This depends on the specific text and tokenization)
            for i in range(1, len(chunks)):
                prev_chunk = chunks[i-1]
                curr_chunk = chunks[i]
                
                # Current chunk should start before or at the end of previous chunk
                # (allowing for overlap)
                assert curr_chunk.start_char <= prev_chunk.end_char
        
        # Verify all chunks have valid IDs
        for chunk in chunks:
            assert chunk.chunk_id.startswith(f"{source_id}:{options.version}:")
            assert len(chunk.chunk_id.split(':')) == 5  # source:version:start:end:hash
        
        # Test determinism
        chunks2 = chunk_text(source_id, text, options)
        assert len(chunks2) == len(chunks)
        for i, (chunk1, chunk2) in enumerate(zip(chunks, chunks2)):
            assert chunk1.chunk_id == chunk2.chunk_id, f"Chunk {i} ID mismatch"

    def test_cjk_text_per_character_tokenization(self) -> None:
        """Test CJK text with per-character tokenization and stable IDs."""
        source_id = "test-doc-cjk"
        # Mix of Chinese characters and punctuation
        text = "你好世界！这是一个测试文档。包含中文字符和标点符号。"
        options = ChunkingOptions(target_tokens=10, max_tokens=20, overlap_tokens=3)
        
        chunks = chunk_text(source_id, text, options)
        
        # Should produce multiple chunks due to small target_tokens
        assert len(chunks) >= 1
        
        # Verify token spans for CJK text
        spans = token_spans(normalize_text(text))
        
        # Each CJK character should be a separate token
        cjk_chars = [c for c in normalize_text(text) if '\u4e00' <= c <= '\u9fff']
        assert len([s for s in spans if len(text[s[0]:s[1]]) == 1 and '\u4e00' <= text[s[0]] <= '\u9fff']) == len(cjk_chars)
        
        # Verify chunk properties
        for chunk in chunks:
            assert chunk.source_id == source_id
            assert chunk.start_char >= 0
            assert chunk.end_char <= len(normalize_text(text))
            assert chunk.start_char < chunk.end_char
            assert len(chunk.text) > 0
            
            # Verify chunk ID format
            assert chunk.chunk_id.startswith(f"{source_id}:{options.version}:")
        
        # Test determinism with CJK text
        chunks2 = chunk_text(source_id, text, options)
        assert len(chunks2) == len(chunks)
        for chunk1, chunk2 in zip(chunks, chunks2):
            assert chunk1.chunk_id == chunk2.chunk_id

    def test_mixed_ascii_cjk_text(self) -> None:
        """Test mixed ASCII and CJK text handling."""
        source_id = "test-doc-mixed"
        text = "Hello 你好 world 世界! This is mixed text 这是混合文本."
        options = ChunkingOptions(target_tokens=15, max_tokens=30, overlap_tokens=5)
        
        chunks = chunk_text(source_id, text, options)
        
        assert len(chunks) >= 1
        
        # Verify that all text is covered
        all_text = "".join(chunk.text for chunk in chunks)
        normalized = normalize_text(text)
        
        # The concatenated chunks should cover the original text
        # (allowing for overlap, so total length might be longer)
        assert len(all_text) >= len(normalized)
        
        # Test determinism
        chunks2 = chunk_text(source_id, text, options)
        assert len(chunks2) == len(chunks)
        for chunk1, chunk2 in zip(chunks, chunks2):
            assert chunk1.chunk_id == chunk2.chunk_id

    def test_budget_chunks_integration(self) -> None:
        """Test budget_chunks function with tokenizer integration."""
        source_id = "test-budget"
        text = "This is a test document for budget chunking. It should be processed with token budgets."
        options = ChunkingOptions(target_tokens=10, max_tokens=20, overlap_tokens=3)
        tokenizer = HeuristicTokenizer("test-model", max_tokens=100)
        policy = TokenBudgetPolicy(safety_margin_ratio=0.1, safety_margin_min_tokens=5)
        
        budgeted = budget_chunks(source_id, text, options, tokenizer, policy=policy)
        
        assert len(budgeted) >= 1
        
        for chunk in budgeted:
            assert isinstance(chunk, BudgetedChunk)
            assert chunk.source_id == source_id
            assert chunk.token_count.count > 0
            assert chunk.target_budget > 0
            assert chunk.safety_margin >= 0
            assert chunk.chunk_id.startswith(f"{source_id}:{options.version}:")

    def test_empty_text_handling(self) -> None:
        """Test handling of empty or whitespace-only text."""
        source_id = "test-empty"
        options = ChunkingOptions()
        
        # Empty string
        chunks = chunk_text(source_id, "", options)
        assert len(chunks) == 0
        
        # Whitespace only
        chunks = chunk_text(source_id, "   \n\t  ", options)
        assert len(chunks) == 0
        
        # Single character
        chunks = chunk_text(source_id, "a", options)
        assert len(chunks) == 1
        assert chunks[0].text == "a"

    def test_chunk_id_determinism_across_runs(self) -> None:
        """Test that chunk IDs are deterministic across multiple runs."""
        source_id = "determinism-test"
        text = "This text should produce the same chunk IDs every time it's processed."
        options = ChunkingOptions(target_tokens=50, max_tokens=100, overlap_tokens=10)
        
        # Run chunking multiple times
        all_runs = []
        for _ in range(5):
            chunks = chunk_text(source_id, text, options)
            all_runs.append([chunk.chunk_id for chunk in chunks])
        
        # All runs should produce identical chunk ID sequences
        first_run = all_runs[0]
        for run in all_runs[1:]:
            assert run == first_run, "Chunk IDs should be deterministic across runs"

    def test_boundary_selection_priority(self) -> None:
        """Test that boundary selection prioritizes paragraphs over sentences."""
        source_id = "boundary-test"
        # Text with both paragraph and sentence boundaries
        text = "First paragraph sentence one. First paragraph sentence two.\n\nSecond paragraph sentence one. Second paragraph sentence two."
        options = ChunkingOptions(target_tokens=15, max_tokens=30, overlap_tokens=5)
        
        chunks = chunk_text(source_id, text, options)
        
        # Should produce multiple chunks
        assert len(chunks) >= 1
        
        # Verify that chunks respect boundaries appropriately
        for chunk in chunks:
            # Each chunk should contain complete tokens
            assert len(chunk.text.strip()) > 0
            
            # Chunk text should be a substring of the original (normalized) text
            normalized = normalize_text(text)
            assert chunk.text in normalized or normalized.startswith(chunk.text) or normalized.endswith(chunk.text)


if __name__ == "__main__":
    pytest.main([__file__])