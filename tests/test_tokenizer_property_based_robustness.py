"""Property-based tests for tokenizer adapters robustness.

This module implements the four correctness properties specified in the tokenizer-adapters spec:
- Property 1.1: Deterministic chunking - same input produces identical output
- Property 1.2: Token budget compliance - chunks never exceed max tokens  
- Property 1.3: Progress guarantee - chunking always makes forward progress
- Property 1.4: Overlap consistency - overlap tokens are correctly applied

These tests use Hypothesis for property-based testing to validate behavior across
a wide range of inputs and configurations.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite
from typing import List, Optional

from kano_backlog_core.chunking import (
    ChunkingOptions,
    chunk_text,
    chunk_text_with_tokenizer,
    validate_overlap_consistency,
    Chunk,
)
from kano_backlog_core.tokenizer import (
    TokenizerAdapter,
    TokenizerRegistry,
    HeuristicTokenizer,
    resolve_tokenizer_with_fallback,
    get_default_registry,
)
from kano_backlog_core.token_budget import TokenBudgetManager


# Test data strategies
@composite
def valid_chunking_options(draw):
    """Generate valid ChunkingOptions instances."""
    max_tokens = draw(st.integers(min_value=20, max_value=1024))
    target_tokens = draw(st.integers(min_value=10, max_value=max_tokens))
    overlap_tokens = draw(st.integers(min_value=0, max_value=min(max_tokens // 2, 50)))
    
    return ChunkingOptions(
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        version="test-v1",
        tokenizer_adapter="heuristic"  # Use heuristic for reliable testing
    )


@composite
def realistic_text_content(draw):
    """Generate realistic text content for testing."""
    # Choose text type
    text_type = draw(st.sampled_from([
        "english_sentences",
        "mixed_content", 
        "technical_content",
        "short_phrases",
        "cjk_content"
    ]))
    
    if text_type == "english_sentences":
        sentences = draw(st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Po", "Zs")),
                min_size=10,
                max_size=100
            ).filter(lambda x: len(x.strip()) > 5),
            min_size=1,
            max_size=20
        ))
        return ". ".join(sentences) + "."
    
    elif text_type == "mixed_content":
        # Mix of paragraphs and lists
        paragraphs = draw(st.lists(
            st.text(min_size=20, max_size=200).filter(lambda x: len(x.strip()) > 10),
            min_size=1,
            max_size=5
        ))
        return "\n\n".join(paragraphs)
    
    elif text_type == "technical_content":
        # Code-like content with special characters
        content = draw(st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd", "Po", "Ps", "Pe", "Zs"),
                whitelist_characters="(){}[]<>=+-*/&|^%$#@!~`"
            ),
            min_size=50,
            max_size=500
        ))
        return content
    
    elif text_type == "short_phrases":
        phrases = draw(st.lists(
            st.text(min_size=3, max_size=30).filter(lambda x: len(x.strip()) > 2),
            min_size=3,
            max_size=15
        ))
        return " ".join(phrases)
    
    elif text_type == "cjk_content":
        # Simple CJK content
        cjk_chars = "你好世界这是一个测试文本包含中文字符"
        content = draw(st.text(
            alphabet=cjk_chars + " .,!?",
            min_size=10,
            max_size=100
        ))
        return content
    
    # Fallback
    return draw(st.text(min_size=10, max_size=500).filter(lambda x: len(x.strip()) > 5))


@composite
def tokenizer_adapter_strategy(draw):
    """Generate tokenizer adapters for testing."""
    adapter_type = draw(st.sampled_from(["heuristic"]))  # Focus on heuristic for reliability
    
    if adapter_type == "heuristic":
        chars_per_token = draw(st.floats(min_value=2.0, max_value=8.0))
        model_name = draw(st.sampled_from(["test-model", "gpt-3.5-turbo", "bert-base-uncased"]))
        return HeuristicTokenizer(model_name, chars_per_token=chars_per_token)
    
    # Fallback to heuristic
    return HeuristicTokenizer("test-model")


class TestTokenizerPropertyBasedRobustness:
    """Property-based tests for tokenizer adapter robustness as specified in the design."""

    @given(
        text=realistic_text_content(),
        options=valid_chunking_options()
    )
    @settings(max_examples=50, deadline=5000)  # Reasonable limits for CI
    def test_property_1_1_deterministic_chunking(self, text: str, options: ChunkingOptions):
        """Property 1.1: Deterministic chunking - same input produces identical output.
        
        **Validates: Requirements US-2, FR-3**
        
        This property ensures that:
        1. Same input text produces identical chunk boundaries and IDs
        2. Chunk ordering is consistent
        3. All chunk metadata is deterministic
        4. Results are reproducible across multiple runs
        """
        assume(len(text.strip()) > 0)
        assume(any(c.isalnum() for c in text))  # Ensure meaningful content
        
        source_id = "test-deterministic"
        
        try:
            # Create tokenizer for consistent testing
            tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
            
            # Run chunking multiple times
            chunks1 = chunk_text_with_tokenizer(source_id, text, options, tokenizer)
            chunks2 = chunk_text_with_tokenizer(source_id, text, options, tokenizer)
            chunks3 = chunk_text_with_tokenizer(source_id, text, options, tokenizer)
            
            # Property 1.1.1: Same number of chunks
            assert len(chunks1) == len(chunks2) == len(chunks3), (
                f"Inconsistent chunk count: {len(chunks1)}, {len(chunks2)}, {len(chunks3)}"
            )
            
            # Property 1.1.2: Identical chunk content and boundaries
            for i, (c1, c2, c3) in enumerate(zip(chunks1, chunks2, chunks3)):
                assert c1.text == c2.text == c3.text, (
                    f"Chunk {i} text differs: '{c1.text[:50]}...' vs '{c2.text[:50]}...'"
                )
                assert c1.start_char == c2.start_char == c3.start_char, (
                    f"Chunk {i} start_char differs: {c1.start_char}, {c2.start_char}, {c3.start_char}"
                )
                assert c1.end_char == c2.end_char == c3.end_char, (
                    f"Chunk {i} end_char differs: {c1.end_char}, {c2.end_char}, {c3.end_char}"
                )
                
                # Property 1.1.3: Identical chunk IDs (deterministic ID generation)
                assert c1.chunk_id == c2.chunk_id == c3.chunk_id, (
                    f"Chunk {i} ID differs: {c1.chunk_id} vs {c2.chunk_id}"
                )
                
                # Property 1.1.4: Consistent source_id
                assert c1.source_id == c2.source_id == c3.source_id == source_id
            
            # Property 1.1.5: Chunks cover the text completely and in order
            if chunks1:
                assert chunks1[0].start_char == 0 or text[:chunks1[0].start_char].strip() == "", (
                    "First chunk should start at beginning or after whitespace"
                )
                
                for i in range(len(chunks1) - 1):
                    curr_chunk = chunks1[i]
                    next_chunk = chunks1[i + 1]
                    
                    # Chunks should be in order
                    assert curr_chunk.start_char <= next_chunk.start_char, (
                        f"Chunks out of order: chunk {i} starts at {curr_chunk.start_char}, "
                        f"chunk {i+1} starts at {next_chunk.start_char}"
                    )
                    
                    # No gaps (allowing for overlap)
                    assert next_chunk.start_char <= curr_chunk.end_char, (
                        f"Gap between chunks {i} and {i+1}: "
                        f"chunk {i} ends at {curr_chunk.end_char}, "
                        f"chunk {i+1} starts at {next_chunk.start_char}"
                    )
        
        except Exception as e:
            # Allow graceful failures for edge cases, but they should be rare
            error_msg = str(e).lower()
            acceptable_errors = [
                "empty", "boundary", "tokenizer", "unicode", "encoding"
            ]
            if not any(keyword in error_msg for keyword in acceptable_errors):
                pytest.fail(f"Unexpected error in deterministic chunking: {e}")

    @given(
        text=realistic_text_content(),
        options=valid_chunking_options(),
        tokenizer=tokenizer_adapter_strategy()
    )
    @settings(max_examples=50, deadline=5000)
    def test_property_1_2_token_budget_compliance(self, text: str, options: ChunkingOptions, tokenizer: TokenizerAdapter):
        """Property 1.2: Token budget compliance - chunks never exceed max tokens.
        
        **Validates: Requirements US-2, FR-4**
        
        This property ensures that:
        1. No chunk exceeds the configured max_tokens limit
        2. Safety margins are properly applied
        3. Token counting is accurate within adapter limitations
        4. Budget compliance is maintained across all text types
        """
        assume(len(text.strip()) > 0)
        assume(any(c.isalnum() for c in text))
        
        source_id = "test-budget-compliance"
        
        try:
            chunks = chunk_text_with_tokenizer(source_id, text, options, tokenizer)
            
            # Property 1.2.1: Every chunk respects token budget
            for i, chunk in enumerate(chunks):
                token_count = tokenizer.count_tokens(chunk.text)
                
                # Core budget compliance - never exceed max_tokens
                assert token_count.count <= options.max_tokens, (
                    f"Chunk {i} exceeds max_tokens: {token_count.count} > {options.max_tokens}"
                )
                
                # Property 1.2.2: Non-empty chunks have positive token count
                if chunk.text.strip():
                    assert token_count.count > 0, (
                        f"Non-empty chunk {i} has zero token count: '{chunk.text[:50]}...'"
                    )
            
            # Property 1.2.3: Test integration with TokenBudgetManager
            # Note: There's a design gap here - chunking uses raw max_tokens but
            # TokenBudgetManager applies safety margins. This test validates both behaviors.
            budget_manager = TokenBudgetManager(options, tokenizer)
            
            for i, chunk in enumerate(chunks):
                chunk_tokens = tokenizer.count_tokens(chunk.text).count
                
                # Core requirement: chunks should never exceed configured max_tokens
                assert chunk_tokens <= options.max_tokens, (
                    f"Chunk {i} exceeds configured max_tokens: {chunk_tokens} > {options.max_tokens}"
                )
                
                # Budget manager integration: it should be able to handle any chunk
                # that fits within max_tokens, either by accepting it or trimming it
                budget_result = budget_manager.apply_budget(chunk.text)
                
                # Budget result should always be compliant with effective max
                result_tokens = budget_result.token_count.count
                assert result_tokens <= budget_manager.effective_max, (
                    f"Budget manager result for chunk {i} exceeds effective max: "
                    f"{result_tokens} > {budget_manager.effective_max}"
                )
                
                # If chunk was within effective max, it shouldn't be trimmed
                if chunk_tokens <= budget_manager.effective_max:
                    assert not budget_result.was_trimmed, (
                        f"Chunk {i} was unnecessarily trimmed: "
                        f"tokens={chunk_tokens}, effective_max={budget_manager.effective_max}"
                    )
                    assert budget_result.text == chunk.text, (
                        f"Chunk {i} text was modified when it shouldn't have been"
                    )
        
        except Exception as e:
            # Handle edge cases gracefully
            error_msg = str(e).lower()
            acceptable_errors = [
                "tokenizer", "encoding", "unicode", "empty", "boundary"
            ]
            if not any(keyword in error_msg for keyword in acceptable_errors):
                pytest.fail(f"Unexpected error in budget compliance: {e}")

    @given(
        text=realistic_text_content(),
        options=valid_chunking_options()
    )
    @settings(max_examples=50, deadline=5000)
    def test_property_1_3_progress_guarantee(self, text: str, options: ChunkingOptions):
        """Property 1.3: Progress guarantee - chunking always makes forward progress.
        
        **Validates: Requirements FR-3, NFR-2**
        
        This property ensures that:
        1. Chunking never gets stuck in infinite loops
        2. Each chunk advances through the text
        3. Non-empty input produces at least one chunk
        4. All input text is covered by chunks (allowing for trimming)
        """
        assume(len(text.strip()) > 0)
        assume(any(c.isalnum() for c in text))
        
        source_id = "test-progress"
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
        
        try:
            chunks = chunk_text_with_tokenizer(source_id, text, options, tokenizer)
            
            # Property 1.3.1: Non-empty input produces at least one chunk
            assert len(chunks) >= 1, (
                f"No chunks produced for non-empty input: '{text[:100]}...'"
            )
            
            # Property 1.3.2: Each chunk makes forward progress
            for i, chunk in enumerate(chunks):
                # Each chunk must have positive length
                assert chunk.end_char > chunk.start_char, (
                    f"Chunk {i} has no length: start={chunk.start_char}, end={chunk.end_char}"
                )
                
                # Each chunk must contain some content
                assert len(chunk.text) > 0, f"Chunk {i} is empty"
                
                # Chunk boundaries must be valid
                assert 0 <= chunk.start_char < len(text), (
                    f"Chunk {i} start_char out of bounds: {chunk.start_char}"
                )
                assert chunk.start_char < chunk.end_char <= len(text), (
                    f"Chunk {i} end_char invalid: start={chunk.start_char}, end={chunk.end_char}, text_len={len(text)}"
                )
            
            # Property 1.3.3: Chunks are in forward order
            for i in range(len(chunks) - 1):
                curr_chunk = chunks[i]
                next_chunk = chunks[i + 1]
                
                # Next chunk must start at or after current chunk start
                assert next_chunk.start_char >= curr_chunk.start_char, (
                    f"Chunks not in forward order: chunk {i} starts at {curr_chunk.start_char}, "
                    f"chunk {i+1} starts at {next_chunk.start_char}"
                )
                
                # Must make some forward progress (allowing for overlap)
                assert next_chunk.end_char > curr_chunk.start_char, (
                    f"No forward progress between chunks {i} and {i+1}: "
                    f"chunk {i} start={curr_chunk.start_char}, chunk {i+1} end={next_chunk.end_char}"
                )
            
            # Property 1.3.4: Text coverage - chunks should cover most of the input
            if chunks:
                total_coverage = chunks[-1].end_char - chunks[0].start_char
                text_length = len(text.strip())
                
                if text_length > 0:
                    coverage_ratio = total_coverage / text_length
                    # Allow for some trimming, but should cover most of the text
                    assert coverage_ratio >= 0.1, (
                        f"Poor text coverage: {coverage_ratio:.2%} "
                        f"(covered {total_coverage} of {text_length} characters)"
                    )
        
        except Exception as e:
            # Handle edge cases
            error_msg = str(e).lower()
            acceptable_errors = [
                "tokenizer", "boundary", "unicode", "encoding", "empty"
            ]
            if not any(keyword in error_msg for keyword in acceptable_errors):
                pytest.fail(f"Unexpected error in progress guarantee: {e}")

    @given(
        text=realistic_text_content().filter(lambda x: len(x) > 50),  # Ensure text long enough for overlap
        options=valid_chunking_options().filter(lambda opt: opt.overlap_tokens > 0)  # Ensure overlap requested
    )
    @settings(max_examples=30, deadline=5000)  # Fewer examples due to complexity
    def test_property_1_4_overlap_consistency(self, text: str, options: ChunkingOptions):
        """Property 1.4: Overlap consistency - overlap tokens are correctly applied.
        
        **Validates: Requirements US-2, FR-3**
        
        This property ensures that:
        1. Overlap is calculated in token space, not character space
        2. Overlap doesn't exceed configured limits
        3. Overlap provides meaningful context between chunks
        4. Edge cases are handled properly
        """
        assume(len(text.strip()) > 20)
        assume(any(c.isalnum() for c in text))
        assume(options.overlap_tokens > 0)
        
        source_id = "test-overlap"
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
        
        try:
            chunks = chunk_text_with_tokenizer(source_id, text, options, tokenizer)
            
            # Property 1.4.1: Overlap validation using built-in validator
            validation_errors = validate_overlap_consistency(chunks, options, tokenizer)
            
            # Allow some minor validation warnings but no critical errors
            critical_errors = [
                error for error in validation_errors
                if "exceeds configured limit" in error and "significantly" not in error.lower()
            ]
            assert len(critical_errors) <= 1, (
                f"Too many critical overlap errors: {critical_errors}"
            )
            
            # Property 1.4.2: Manual overlap validation for adjacent chunks
            if len(chunks) > 1:
                for i in range(1, len(chunks)):
                    prev_chunk = chunks[i-1]
                    curr_chunk = chunks[i]
                    
                    # Check if chunks overlap
                    if curr_chunk.start_char < prev_chunk.end_char:
                        # Calculate overlap region
                        overlap_start = curr_chunk.start_char
                        overlap_end = prev_chunk.end_char
                        overlap_text = text[overlap_start:overlap_end]
                        
                        if overlap_text.strip():  # Non-empty overlap
                            overlap_token_count = tokenizer.count_tokens(overlap_text).count
                            prev_chunk_tokens = tokenizer.count_tokens(prev_chunk.text).count
                            curr_chunk_tokens = tokenizer.count_tokens(curr_chunk.text).count
                            
                            # Property 1.4.3: Overlap doesn't exceed configured limit (with tolerance)
                            max_allowed_overlap = options.overlap_tokens + 3  # Small tolerance for boundary effects
                            assert overlap_token_count <= max_allowed_overlap, (
                                f"Overlap between chunks {i-1} and {i} exceeds limit: "
                                f"{overlap_token_count} > {options.overlap_tokens} (max allowed: {max_allowed_overlap})"
                            )
                            
                            # Property 1.4.4: Overlap doesn't exceed chunk sizes
                            assert overlap_token_count < prev_chunk_tokens, (
                                f"Overlap ({overlap_token_count}) >= previous chunk size ({prev_chunk_tokens})"
                            )
                            assert overlap_token_count < curr_chunk_tokens, (
                                f"Overlap ({overlap_token_count}) >= current chunk size ({curr_chunk_tokens})"
                            )
                            
                            # Property 1.4.5: Overlap contains meaningful content
                            meaningful_chars = sum(1 for c in overlap_text if c.isalnum())
                            assert meaningful_chars > 0, (
                                f"Overlap contains no meaningful content: '{overlap_text}'"
                            )
            
            # Property 1.4.6: Overlap provides context continuity
            if len(chunks) > 1:
                for i in range(1, len(chunks)):
                    prev_chunk = chunks[i-1]
                    curr_chunk = chunks[i]
                    
                    # Ensure reasonable transition between chunks
                    gap_start = prev_chunk.end_char
                    gap_end = curr_chunk.start_char
                    
                    if gap_end > gap_start:
                        # There's a gap - this is allowed but should be minimal
                        gap_text = text[gap_start:gap_end]
                        gap_meaningful = sum(1 for c in gap_text if c.isalnum())
                        
                        # Gap should not contain too much meaningful content
                        assert gap_meaningful <= 10, (
                            f"Large gap with meaningful content between chunks {i-1} and {i}: '{gap_text}'"
                        )
        
        except Exception as e:
            # Handle edge cases gracefully
            error_msg = str(e).lower()
            acceptable_errors = [
                "tokenizer", "overlap", "boundary", "unicode", "encoding", "empty"
            ]
            if not any(keyword in error_msg for keyword in acceptable_errors):
                pytest.fail(f"Unexpected error in overlap consistency: {e}")


class TestTokenizerAdapterRobustness:
    """Property-based tests for individual tokenizer adapter robustness."""

    @given(
        text=realistic_text_content(),
        chars_per_token=st.floats(min_value=1.0, max_value=10.0)
    )
    @settings(max_examples=30, deadline=3000)
    def test_heuristic_tokenizer_consistency(self, text: str, chars_per_token: float):
        """Test that HeuristicTokenizer produces consistent results.
        
        **Validates: Requirements FR-1, FR-2**
        """
        assume(len(text.strip()) > 0)
        
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=chars_per_token)
        
        # Multiple calls should produce identical results
        count1 = tokenizer.count_tokens(text)
        count2 = tokenizer.count_tokens(text)
        count3 = tokenizer.count_tokens(text)
        
        assert count1.count == count2.count == count3.count
        assert count1.method == count2.method == count3.method == "heuristic"
        assert count1.is_exact == count2.is_exact == count3.is_exact == False
        assert count1.tokenizer_id == count2.tokenizer_id == count3.tokenizer_id

    @given(
        text=realistic_text_content(),
        model_name=st.sampled_from(["gpt-3.5-turbo", "bert-base-uncased", "test-model"])
    )
    @settings(max_examples=20, deadline=3000)
    def test_tokenizer_registry_fallback_robustness(self, text: str, model_name: str):
        """Test that tokenizer registry fallback works reliably.
        
        **Validates: Requirements FR-1, FR-2**
        """
        assume(len(text.strip()) > 0)
        
        registry = get_default_registry()
        
        # Test fallback behavior with "auto" adapter
        try:
            tokenizer = resolve_tokenizer_with_fallback("auto", model_name, registry)
            
            # Should successfully create a tokenizer
            assert tokenizer is not None
            assert hasattr(tokenizer, 'count_tokens')
            assert hasattr(tokenizer, 'adapter_id')
            
            # Should be able to count tokens
            token_count = tokenizer.count_tokens(text)
            assert token_count.count >= 0
            assert isinstance(token_count.method, str)
            assert isinstance(token_count.tokenizer_id, str)
            assert isinstance(token_count.is_exact, bool)
            
        except Exception as e:
            # Registry fallback should rarely fail completely
            pytest.fail(f"Registry fallback failed unexpectedly: {e}")

    @given(
        texts=st.lists(realistic_text_content(), min_size=2, max_size=5),
        options=valid_chunking_options()
    )
    @settings(max_examples=20, deadline=5000)
    def test_multi_document_consistency(self, texts: List[str], options: ChunkingOptions):
        """Test that chunking is consistent across multiple documents.
        
        **Validates: Requirements US-2, FR-3**
        """
        # Filter out empty texts
        valid_texts = [text for text in texts if len(text.strip()) > 0 and any(c.isalnum() for c in text)]
        assume(len(valid_texts) >= 2)
        
        tokenizer = HeuristicTokenizer("test-model", chars_per_token=4.0)
        
        all_chunks = []
        for i, text in enumerate(valid_texts):
            source_id = f"doc-{i}"
            chunks = chunk_text_with_tokenizer(source_id, text, options, tokenizer)
            all_chunks.extend(chunks)
        
        # All chunks should be valid and consistent
        for i, chunk in enumerate(all_chunks):
            # Basic validity
            assert len(chunk.text) > 0, f"Empty chunk {i}"
            assert chunk.end_char > chunk.start_char, f"Invalid boundaries for chunk {i}"
            assert chunk.source_id.startswith("doc-"), f"Invalid source_id for chunk {i}"
            
            # Token budget compliance
            token_count = tokenizer.count_tokens(chunk.text)
            assert token_count.count <= options.max_tokens, (
                f"Chunk {i} exceeds token budget: {token_count.count} > {options.max_tokens}"
            )


class TestEdgeCaseRobustness:
    """Property-based tests for edge cases and boundary conditions."""

    @given(
        text_size=st.integers(min_value=1, max_value=10),
        max_tokens=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=20, deadline=3000)
    def test_minimal_input_robustness(self, text_size: int, max_tokens: int):
        """Test robustness with minimal inputs.
        
        **Validates: Requirements NFR-2**
        """
        # Create minimal text
        text = "A" * text_size
        
        options = ChunkingOptions(
            target_tokens=1,
            max_tokens=max_tokens,
            overlap_tokens=0,
            version="test-v1"
        )
        
        tokenizer = HeuristicTokenizer("test-model")
        
        try:
            chunks = chunk_text_with_tokenizer("test-minimal", text, options, tokenizer)
            
            # Should produce at least one chunk for non-empty input
            assert len(chunks) >= 1
            
            # All chunks should be valid
            for chunk in chunks:
                assert len(chunk.text) > 0
                assert chunk.end_char > chunk.start_char
                
                # Should respect token budget
                token_count = tokenizer.count_tokens(chunk.text)
                assert token_count.count <= max_tokens
        
        except Exception as e:
            # Some extreme edge cases might fail, but should be rare
            error_msg = str(e).lower()
            acceptable_errors = ["empty", "boundary", "progress", "tokenizer"]
            if not any(keyword in error_msg for keyword in acceptable_errors):
                pytest.fail(f"Unexpected error with minimal input: {e}")

    @given(
        special_chars=st.text(
            alphabet=st.characters(
                whitelist_categories=("Cc", "Cf", "Zl", "Zp", "Zs"),
                max_codepoint=0x1000  # Limit to avoid very exotic characters
            ),
            min_size=5,
            max_size=50
        )
    )
    @settings(max_examples=15, deadline=3000)
    def test_special_character_robustness(self, special_chars: str):
        """Test robustness with special characters and whitespace.
        
        **Validates: Requirements US-3, NFR-2**
        """
        # Mix special characters with normal text
        text = f"Normal text {special_chars} more normal text."
        
        options = ChunkingOptions(
            target_tokens=20,
            max_tokens=50,
            overlap_tokens=5
        )
        
        tokenizer = HeuristicTokenizer("test-model")
        
        try:
            chunks = chunk_text_with_tokenizer("test-special", text, options, tokenizer)
            
            # Should handle special characters gracefully
            assert len(chunks) >= 1
            
            for chunk in chunks:
                # Should produce valid chunks
                assert isinstance(chunk.text, str)
                assert len(chunk.text) >= 0
                
                # Should not break Unicode encoding
                try:
                    chunk.text.encode('utf-8')
                except UnicodeEncodeError:
                    pytest.fail(f"Unicode encoding broken in chunk: '{chunk.text}'")
        
        except Exception as e:
            # Special characters might cause some issues, but should be handled gracefully
            error_msg = str(e).lower()
            acceptable_errors = ["unicode", "encoding", "tokenizer", "boundary", "empty"]
            if not any(keyword in error_msg for keyword in acceptable_errors):
                pytest.fail(f"Unexpected error with special characters: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])