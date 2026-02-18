"""Tests for enhanced text normalization and boundary detection (Task 2.3).

This module tests the enhancements made to text normalization and boundary detection
as specified in the tokenizer-adapters design document.
"""

import pytest
import unicodedata
from kano_backlog_core.chunking import (
    normalize_text,
    _paragraph_boundary_chars,
    _sentence_boundary_chars,
    _pick_boundary,
    build_chunk_id,
    chunk_text,
    ChunkingOptions,
)


class TestEnhancedTextNormalization:
    """Test suite for enhanced text normalization."""

    def test_unicode_nfc_normalization(self) -> None:
        """Test Unicode NFC normalization handles composed/decomposed characters."""
        # Test composed vs decomposed characters (é vs e + ´)
        composed = "café"  # é as single character
        decomposed = "cafe\u0301"  # e + combining acute accent
        
        # Both should normalize to the same result
        normalized_composed = normalize_text(composed)
        normalized_decomposed = normalize_text(decomposed)
        
        assert normalized_composed == normalized_decomposed
        assert unicodedata.normalize("NFC", composed) == normalized_composed

    def test_comprehensive_newline_normalization(self) -> None:
        """Test comprehensive newline normalization handles all variants."""
        test_cases = [
            ("line1\r\nline2", "line1\nline2"),  # Windows CRLF
            ("line1\rline2", "line1\nline2"),    # Mac CR
            ("line1\nline2", "line1\nline2"),    # Unix LF (unchanged)
            ("line1\r\n\rline2\nline3", "line1\n\nline2\nline3"),  # Mixed
        ]
        
        for input_text, expected in test_cases:
            result = normalize_text(input_text)
            assert result == expected

    def test_whitespace_normalization(self) -> None:
        """Test enhanced whitespace normalization."""
        test_cases = [
            ("line1   \nline2", "line1\nline2"),  # Trailing spaces before newline
            ("line1\t\t\nline2", "line1\nline2"),  # Trailing tabs before newline
            ("line1    line2", "line1   line2"),  # 4+ spaces -> 3 spaces
            ("line1     line2", "line1   line2"),  # 5+ spaces -> 3 spaces
            ("line1  line2", "line1  line2"),     # 2 spaces unchanged
            ("line1\t\t\t\tline2", "line1   line2"),  # 4+ tabs -> 3 spaces
        ]
        
        for input_text, expected in test_cases:
            result = normalize_text(input_text)
            assert result == expected

    def test_control_character_handling(self) -> None:
        """Test control character handling preserves essential characters."""
        # Test that essential control characters are preserved
        text_with_controls = "line1\nline2\tindented"
        result = normalize_text(text_with_controls)
        assert "\n" in result  # Newlines preserved
        assert "\t" in result  # Tabs preserved
        
        # Test that problematic control characters are removed
        text_with_bad_controls = "line1\x00line2\x01line3"  # NULL and SOH
        result = normalize_text(text_with_bad_controls)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "line1line2line3" == result

    def test_final_cleanup_trailing_whitespace(self) -> None:
        """Test final cleanup removes trailing whitespace."""
        test_cases = [
            ("text   ", "text"),
            ("text\n\n  ", "text\n\n"),  # Should preserve internal newlines, remove trailing spaces
            ("text\t\t", "text"),
            ("  text  ", "  text"),  # Leading whitespace preserved, trailing removed
        ]
        
        for input_text, expected in test_cases:
            result = normalize_text(input_text)
            assert result == expected, f"Input: {repr(input_text)}, Expected: {repr(expected)}, Got: {repr(result)}"

    def test_empty_text_handling(self) -> None:
        """Test normalization handles empty and whitespace-only text."""
        assert normalize_text("") == ""
        assert normalize_text("   ") == ""
        assert normalize_text("\n\n\n") == "\n\n\n"  # Newlines are preserved
        assert normalize_text("\t\t\t") == ""

    def test_complex_unicode_text(self) -> None:
        """Test normalization with complex Unicode text."""
        # Mix of different Unicode categories
        complex_text = "Hello 世界! Café naïve résumé 🌟"
        result = normalize_text(complex_text)
        
        # Should preserve all visible characters
        assert "Hello" in result
        assert "世界" in result
        assert "Café" in result
        assert "naïve" in result
        assert "résumé" in result
        assert "🌟" in result


class TestEnhancedBoundaryDetection:
    """Test suite for enhanced boundary detection."""

    def test_paragraph_boundary_traditional(self) -> None:
        """Test traditional paragraph boundary detection."""
        text = "Paragraph 1.\n\nParagraph 2.\n\n\nParagraph 3."
        boundaries = _paragraph_boundary_chars(text)
        
        # Should detect double newlines - boundaries are at the start of the newline sequence
        assert 12 in boundaries  # After "Paragraph 1." at start of "\n\n"
        assert 26 in boundaries  # After "Paragraph 2." at start of "\n\n\n"
        assert len(text) in boundaries  # End of text

    def test_paragraph_boundary_markdown_headers(self) -> None:
        """Test paragraph boundary detection with Markdown headers."""
        text = "# Header 1\nContent 1\n## Header 2\nContent 2\n### Header 3"
        boundaries = _paragraph_boundary_chars(text)
        
        # Should detect header starts (except at beginning)
        header2_pos = text.find("## Header 2")
        header3_pos = text.find("### Header 3")
        
        assert header2_pos in boundaries
        assert header3_pos in boundaries
        assert len(text) in boundaries

    def test_paragraph_boundary_list_items(self) -> None:
        """Test paragraph boundary detection with list items."""
        text = "Text before\n- Item 1\n- Item 2\n* Item 3\n+ Item 4\n1. Numbered"
        boundaries = _paragraph_boundary_chars(text)
        
        # Should detect list item starts
        item1_pos = text.find("- Item 1")
        item2_pos = text.find("- Item 2")
        item3_pos = text.find("* Item 3")
        item4_pos = text.find("+ Item 4")
        numbered_pos = text.find("1. Numbered")
        
        assert item1_pos in boundaries
        assert item2_pos in boundaries
        assert item3_pos in boundaries
        assert item4_pos in boundaries
        assert numbered_pos in boundaries

    def test_paragraph_boundary_block_quotes(self) -> None:
        """Test paragraph boundary detection with block quotes."""
        text = "Regular text\n> Quote 1\n> Quote 2\nRegular again"
        boundaries = _paragraph_boundary_chars(text)
        
        # Should detect quote starts
        quote1_pos = text.find("> Quote 1")
        quote2_pos = text.find("> Quote 2")
        
        assert quote1_pos in boundaries
        assert quote2_pos in boundaries

    def test_sentence_boundary_traditional(self) -> None:
        """Test traditional sentence boundary detection."""
        text = "First sentence. Second sentence! Third sentence? Fourth."
        boundaries = _sentence_boundary_chars(text)
        
        # Should detect sentence endings
        assert 15 in boundaries  # After "First sentence."
        assert 32 in boundaries  # After "Second sentence!"
        assert 48 in boundaries  # After "Third sentence?" (corrected position)
        assert len(text) in boundaries

    def test_sentence_boundary_cjk(self) -> None:
        """Test sentence boundary detection with CJK punctuation."""
        text = "中文句子。另一个句子！第三个句子？"
        boundaries = _sentence_boundary_chars(text)
        
        # Should detect CJK sentence endings
        assert 5 in boundaries   # After first sentence (中文句子。)
        assert 11 in boundaries  # After second sentence (另一个句子！)
        assert 17 in boundaries  # After third sentence (第三个句子？) and end of text

    def test_sentence_boundary_abbreviation_handling(self) -> None:
        """Test sentence boundary detection avoids breaking on abbreviations."""
        text = "Dr. Smith went to the U.S. yesterday. He met Prof. Johnson."
        boundaries = _sentence_boundary_chars(text)
        
        # Should not break on "Dr." or "U.S." or "Prof."
        # Should only break after "yesterday." and at end
        yesterday_pos = text.find("yesterday.") + len("yesterday.")
        
        assert yesterday_pos in boundaries
        assert len(text) in boundaries
        
        # Should not have boundaries at abbreviations
        dr_pos = text.find("Dr.") + 3
        us_pos = text.find("U.S.") + 4
        prof_pos = text.find("Prof.") + 5
        
        assert dr_pos not in boundaries
        assert us_pos not in boundaries
        assert prof_pos not in boundaries

    def test_sentence_boundary_quotes_handling(self) -> None:
        """Test sentence boundary detection with quotes."""
        text = 'He said "Hello world." Then he left.'
        boundaries = _sentence_boundary_chars(text)
        
        # Should detect sentence end after quote
        # The boundary is after the period, not after the quote
        period_pos = text.find('Hello world.') + len('Hello world.')
        
        assert period_pos in boundaries  # After "Hello world."
        assert len(text) in boundaries


class TestEnhancedBoundarySelection:
    """Test suite for enhanced boundary selection."""

    def test_boundary_selection_scoring(self) -> None:
        """Test boundary selection uses scoring for optimal selection."""
        boundaries = [10, 20, 30, 40, 50]
        
        # Test preferring boundaries close to target
        result = _pick_boundary(
            boundaries=boundaries,
            start_token=0,
            preferred_end=25,
            max_end=50
        )
        # Should pick 20 or 30 (closest to 25)
        assert result in [20, 30]

    def test_boundary_selection_minimum_chunk_size(self) -> None:
        """Test boundary selection avoids very small chunks."""
        boundaries = [2, 10, 20, 30]
        
        # With start_token=0, boundary at 2 creates very small chunk
        result = _pick_boundary(
            boundaries=boundaries,
            start_token=0,
            preferred_end=15,
            max_end=30
        )
        # Should prefer larger chunks
        assert result >= 10

    def test_boundary_selection_no_valid_boundaries(self) -> None:
        """Test boundary selection returns None when no valid boundaries."""
        boundaries = [5, 10]
        
        result = _pick_boundary(
            boundaries=boundaries,
            start_token=15,  # All boundaries are before start
            preferred_end=20,
            max_end=25
        )
        assert result is None

    def test_boundary_selection_single_boundary(self) -> None:
        """Test boundary selection with single valid boundary."""
        boundaries = [10, 15, 30]  # Only 15 is in valid range
        
        result = _pick_boundary(
            boundaries=boundaries,
            start_token=12,
            preferred_end=20,
            max_end=25
        )
        assert result == 15


class TestEnhancedChunkIdGeneration:
    """Test suite for enhanced chunk ID generation."""

    def test_chunk_id_deterministic(self) -> None:
        """Test chunk ID generation is deterministic."""
        chunk_id1 = build_chunk_id(
            source_id="test_doc",
            version="v1",
            start_char=0,
            end_char=10,
            span_text="Hello test"
        )
        
        chunk_id2 = build_chunk_id(
            source_id="test_doc",
            version="v1",
            start_char=0,
            end_char=10,
            span_text="Hello test"
        )
        
        assert chunk_id1 == chunk_id2

    def test_chunk_id_unique_for_different_content(self) -> None:
        """Test chunk IDs are unique for different content."""
        chunk_id1 = build_chunk_id(
            source_id="test_doc",
            version="v1",
            start_char=0,
            end_char=10,
            span_text="Hello test"
        )
        
        chunk_id2 = build_chunk_id(
            source_id="test_doc",
            version="v1",
            start_char=0,
            end_char=10,
            span_text="Different text"
        )
        
        assert chunk_id1 != chunk_id2

    def test_chunk_id_format(self) -> None:
        """Test chunk ID has expected format."""
        chunk_id = build_chunk_id(
            source_id="test_doc",
            version="v1",
            start_char=0,
            end_char=10,
            span_text="Hello test"
        )
        
        # Format: {source_id}:{version}:{start_char}:{end_char}:{hash}
        parts = chunk_id.split(":")
        assert len(parts) == 5
        assert parts[0] == "test_doc"
        assert parts[1] == "v1"
        assert parts[2] == "0"
        assert parts[3] == "10"
        assert len(parts[4]) == 16  # 16-character hash

    def test_chunk_id_whitespace_normalization(self) -> None:
        """Test chunk ID normalizes whitespace in content."""
        chunk_id1 = build_chunk_id(
            source_id="test_doc",
            version="v1",
            start_char=0,
            end_char=10,
            span_text="  Hello test  "
        )
        
        chunk_id2 = build_chunk_id(
            source_id="test_doc",
            version="v1",
            start_char=0,
            end_char=10,
            span_text="Hello test"
        )
        
        # Should be the same due to whitespace normalization
        assert chunk_id1 == chunk_id2


class TestIntegratedEnhancements:
    """Integration tests for all enhancements working together."""

    def test_enhanced_chunking_with_markdown(self) -> None:
        """Test enhanced chunking handles Markdown content properly."""
        markdown_text = """# Introduction

This is the introduction paragraph.

## Section 1

Content for section 1 with multiple sentences. This is another sentence.

- List item 1
- List item 2
- List item 3

## Section 2

> This is a block quote.
> It continues here.

Final paragraph."""

        options = ChunkingOptions(target_tokens=20, max_tokens=40, overlap_tokens=5)  # Smaller chunks
        chunks = chunk_text("markdown_doc", markdown_text, options)
        
        # Should create multiple chunks with good boundaries
        assert len(chunks) > 1
        
        # Each chunk should have valid content
        for chunk in chunks:
            assert len(chunk.text.strip()) > 0
            assert chunk.chunk_id.startswith("markdown_doc:")
            assert chunk.source_id == "markdown_doc"

    def test_enhanced_chunking_with_mixed_content(self) -> None:
        """Test enhanced chunking with mixed ASCII/CJK content."""
        mixed_text = """English paragraph with normal text.

中文段落包含中文内容。这是另一个中文句子。

Mixed paragraph with English and 中文 content together. This tests boundary detection.

Final English paragraph."""

        options = ChunkingOptions(target_tokens=30, max_tokens=60)
        chunks = chunk_text("mixed_doc", mixed_text, options)
        
        # Should handle mixed content properly
        assert len(chunks) > 1
        
        # Verify chunk IDs are stable and unique
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        assert len(chunk_ids) == len(set(chunk_ids))  # All unique

    def test_enhanced_chunking_deterministic(self) -> None:
        """Test enhanced chunking produces deterministic results."""
        text = """This is a test document with multiple paragraphs.

Each paragraph should be handled consistently.

The chunking algorithm should produce the same results every time."""

        options = ChunkingOptions(target_tokens=20, max_tokens=40)
        
        chunks1 = chunk_text("test_doc", text, options)
        chunks2 = chunk_text("test_doc", text, options)
        
        # Should be identical
        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1.chunk_id == c2.chunk_id
            assert c1.text == c2.text
            assert c1.start_char == c2.start_char
            assert c1.end_char == c2.end_char

    def test_enhanced_chunking_with_unicode_normalization(self) -> None:
        """Test enhanced chunking with Unicode normalization."""
        # Text with composed and decomposed characters
        text_composed = "Café naïve résumé"
        text_decomposed = "Cafe\u0301 nai\u0308ve re\u0301sume\u0301"
        
        options = ChunkingOptions(target_tokens=10, max_tokens=20, overlap_tokens=5)  # Fixed overlap
        
        chunks_composed = chunk_text("doc1", text_composed, options)
        chunks_decomposed = chunk_text("doc2", text_decomposed, options)
        
        # Should produce similar chunking patterns (same normalized content)
        assert len(chunks_composed) == len(chunks_decomposed)
        
        # Normalized text should be the same
        for c1, c2 in zip(chunks_composed, chunks_decomposed):
            # The actual text content should be normalized to the same form
            assert unicodedata.normalize("NFC", c1.text) == unicodedata.normalize("NFC", c2.text)


if __name__ == "__main__":
    pytest.main([__file__])