"""Deterministic chunking primitives.

This module provides a small, local-first, dependency-free chunking core that:
- Normalizes text deterministically
- Selects boundaries deterministically (paragraph -> sentence -> hard cut)
- Applies fixed overlap (in tokenizer-agnostic "tokens")
- Produces stable chunk IDs
- Integrates with tokenizer adapters for accurate token counting
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import hashlib
import logging
import re
import unicodedata
from typing import Iterable, List, Optional, Sequence, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .tokenizer import TokenizerAdapter, TokenizerRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkingOptions:
    target_tokens: int = 256
    max_tokens: int = 512
    overlap_tokens: int = 32
    version: str = "chunk-v1"
    tokenizer_adapter: str = "auto"  # New field for tokenizer selection

    def __post_init__(self) -> None:
        if self.target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.target_tokens > self.max_tokens:
            raise ValueError("target_tokens must be <= max_tokens")
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens must be >= 0")
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be < max_tokens")
        if not self.version:
            raise ValueError("version must be non-empty")
        if not self.tokenizer_adapter:
            raise ValueError("tokenizer_adapter must be non-empty")


@dataclass(frozen=True)
class Chunk:
    source_id: str
    start_char: int
    end_char: int
    text: str
    chunk_id: str


_PARA_BREAK_RE = re.compile(r"\n{2,}")
_SENT_END_RE = re.compile(r"(?:[.!?]+|[。！？]+)(?=\s|$)")


def normalize_text(text: str) -> str:
    """Enhanced text normalization with comprehensive Unicode and whitespace handling.
    
    This function implements the text normalization pipeline specified in the design:
    1. Unicode NFC normalization for consistent character representation
    2. Comprehensive newline normalization (CRLF, CR -> LF)
    3. Whitespace normalization (trailing spaces, multiple spaces)
    4. Control character handling for robust text processing
    
    Args:
        text: Raw input text to normalize
        
    Returns:
        Normalized text with consistent Unicode, newlines, and whitespace
    """
    if not text:
        return ""
    
    # Step 1: Unicode NFC normalization for consistent character representation
    # This ensures that composed characters (é) and decomposed characters (e + ´) 
    # are represented consistently, which is crucial for deterministic chunking
    normalized = unicodedata.normalize("NFC", text)
    
    # Step 2: Comprehensive newline normalization
    # Convert all newline variants to Unix-style LF for consistency
    normalized = normalized.replace("\r\n", "\n")  # Windows CRLF -> LF
    normalized = normalized.replace("\r", "\n")    # Mac CR -> LF
    
    # Step 3: Enhanced whitespace normalization
    # Remove trailing whitespace from lines (but preserve intentional line breaks)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    
    # Normalize multiple consecutive spaces to single spaces (but preserve intentional formatting)
    # This is conservative - only collapse excessive spaces, not all multiple spaces
    normalized = re.sub(r"[ \t]{4,}", "   ", normalized)  # 4+ spaces -> 3 spaces (preserve some formatting)
    
    # Step 4: Control character handling
    # Remove or normalize problematic control characters while preserving essential ones
    # Keep: \n (newline), \t (tab), and printable characters
    # Remove: other control characters that can cause issues
    normalized = "".join(
        char for char in normalized 
        if char == "\n" or char == "\t" or not unicodedata.category(char).startswith("C")
        or unicodedata.category(char) in ("Cf",)  # Keep format characters like zero-width space
    )
    
    # Step 5: Final cleanup
    # Remove trailing whitespace from the entire text while preserving internal structure
    # Only remove trailing spaces and tabs, but preserve trailing newlines if they're significant
    normalized = re.sub(r"[ \t]+$", "", normalized)
    
    return normalized


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF  # CJK Ext A
        or 0x4E00 <= code <= 0x9FFF  # CJK Unified
        or 0x3040 <= code <= 0x30FF  # Hiragana/Katakana
        or 0xAC00 <= code <= 0xD7AF  # Hangul
    )


def token_spans(text: str) -> List[Tuple[int, int]]:
    """Return deterministic token spans for tokenizer-agnostic chunking.

    This intentionally avoids external tokenizer dependencies:
    - ASCII/Latin: groups alnum + underscore
    - CJK: treats each CJK character as a token
    - Punctuation: each punctuation mark is a token
    """
    spans: List[Tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue

        if _is_cjk(ch):
            spans.append((i, i + 1))
            i += 1
            continue

        if ch.isalnum() or ch == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            spans.append((i, j))
            i = j
            continue

        spans.append((i, i + 1))
        i += 1

    return spans


def _boundary_token_indexes(boundary_chars: Iterable[int], spans: Sequence[Tuple[int, int]]) -> List[int]:
    ends = [e for _, e in spans]
    token_indexes: Set[int] = set()
    for c in boundary_chars:
        idx = bisect_right(ends, c)
        token_indexes.add(idx)
    return sorted(token_indexes)


def _paragraph_boundary_chars(text: str) -> List[int]:
    """Enhanced paragraph boundary detection with improved patterns.
    
    Detects paragraph boundaries using multiple patterns:
    1. Double newlines (traditional paragraph breaks)
    2. Markdown-style headers (# ## ###)
    3. List item boundaries (-, *, +, numbered lists)
    4. Block quote boundaries (>)
    
    Args:
        text: Normalized text to analyze
        
    Returns:
        List of character positions where paragraph boundaries occur
    """
    boundaries: List[int] = []
    
    # Pattern 1: Traditional double newlines (most common)
    for match in _PARA_BREAK_RE.finditer(text):
        boundaries.append(match.start())
    
    # Pattern 2: Markdown headers (start of line with #)
    header_pattern = re.compile(r"^#{1,6}\s", re.MULTILINE)
    for match in header_pattern.finditer(text):
        if match.start() > 0:  # Don't add boundary at start of text
            boundaries.append(match.start())
    
    # Pattern 3: List items (start of line with list markers)
    list_pattern = re.compile(r"^(?:[-*+]|\d+\.)\s", re.MULTILINE)
    for match in list_pattern.finditer(text):
        if match.start() > 0:
            boundaries.append(match.start())
    
    # Pattern 4: Block quotes (start of line with >)
    quote_pattern = re.compile(r"^>\s", re.MULTILINE)
    for match in quote_pattern.finditer(text):
        if match.start() > 0:
            boundaries.append(match.start())
    
    # Always add end of text as a boundary
    boundaries.append(len(text))
    
    # Remove duplicates and sort
    boundaries = sorted(set(boundaries))
    
    return boundaries


def _sentence_boundary_chars(text: str) -> List[int]:
    """Enhanced sentence boundary detection with improved patterns.
    
    Detects sentence boundaries using multiple patterns:
    1. Traditional sentence endings (. ! ?)
    2. CJK sentence endings (。！？)
    3. Abbreviation handling (avoid breaking on Dr. Mr. etc.)
    4. Quote and parenthesis handling
    
    Args:
        text: Normalized text to analyze
        
    Returns:
        List of character positions where sentence boundaries occur
    """
    boundaries: List[int] = []
    
    # Enhanced sentence ending pattern with better context awareness
    # For CJK text, we don't require whitespace after punctuation
    sentence_pattern = re.compile(
        r"(?:[.!?]+|[\u3002\uFF01\uFF1F]+)"  # Sentence ending punctuation
        r"(?=\s|$|[\"'\uFF09\u3011\u3009\u300B\u300D\u300F]|[^\w\s]|[\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF])"  # Followed by whitespace, end, quotes, or CJK chars
    )
    
    # Common abbreviations that shouldn't trigger sentence breaks
    abbreviations = {
        "Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", "Sr.", "Jr.", 
        "Inc.", "Ltd.", "Corp.", "Co.", "etc.", "vs.", "e.g.", "i.e.",
        "U.S.", "U.K.", "U.N.", "Ph.D.", "M.D.", "B.A.", "M.A."
    }
    
    for match in sentence_pattern.finditer(text):
        end_pos = match.end()
        
        # Check if this might be an abbreviation
        # Look backwards to see if we're in a known abbreviation
        is_abbreviation = False
        start_check = max(0, match.start() - 10)  # Check up to 10 chars back
        context = text[start_check:end_pos]
        
        for abbrev in abbreviations:
            if context.endswith(abbrev):
                is_abbreviation = True
                break
        
        if not is_abbreviation:
            boundaries.append(end_pos)
    
    # Always add end of text as a boundary
    boundaries.append(len(text))
    
    # Remove duplicates and sort
    boundaries = sorted(set(boundaries))
    
    return boundaries


def _pick_boundary(
    *,
    boundaries: Sequence[int],
    start_token: int,
    preferred_end: int,
    max_end: int,
) -> Optional[int]:
    """Enhanced boundary selection with improved hierarchy and scoring.
    
    Selects the best boundary position using a sophisticated scoring system:
    1. Prefer boundaries close to the target size
    2. Avoid boundaries that are too close to the start
    3. Prefer boundaries that don't create very small remaining chunks
    4. Use distance-based scoring for optimal selection
    
    Args:
        boundaries: Available boundary positions (in token space)
        start_token: Starting token position for the chunk
        preferred_end: Preferred ending token position (target size)
        max_end: Maximum allowed ending token position (hard limit)
        
    Returns:
        Best boundary position, or None if no suitable boundary found
    """
    # Filter boundaries to valid range
    valid_boundaries = [
        b for b in boundaries 
        if start_token + 1 <= b <= max_end  # Must make progress and stay within limits
    ]
    
    if not valid_boundaries:
        return None
    
    # If we only have one valid boundary, use it
    if len(valid_boundaries) == 1:
        return valid_boundaries[0]
    
    # Score each boundary based on multiple criteria
    best_boundary = None
    best_score = float('-inf')
    
    for boundary in valid_boundaries:
        score = 0.0
        
        # Criterion 1: Distance from preferred end (closer is better)
        distance_from_preferred = abs(boundary - preferred_end)
        max_distance = max_end - start_token
        if max_distance > 0:
            distance_score = 1.0 - (distance_from_preferred / max_distance)
            score += distance_score * 3.0  # Weight: 3.0
        
        # Criterion 2: Avoid boundaries too close to start (minimum chunk size)
        min_chunk_size = max(1, (max_end - start_token) // 10)  # At least 10% of max chunk
        if boundary - start_token >= min_chunk_size:
            score += 2.0  # Weight: 2.0
        else:
            score -= 1.0  # Penalty for very small chunks
        
        # Criterion 3: Prefer boundaries that don't leave tiny remainders
        # (This helps avoid creating very small final chunks)
        remaining_tokens = max_end - boundary
        if remaining_tokens == 0:  # Perfect fit
            score += 1.0
        elif remaining_tokens < min_chunk_size:  # Would create tiny remainder
            score -= 0.5
        
        # Criterion 4: Prefer boundaries closer to preferred size over max size
        if boundary <= preferred_end:
            score += 0.5  # Slight bonus for staying within preferred size
        
        # Update best boundary if this one scores higher
        if score > best_score:
            best_score = score
            best_boundary = boundary
    
    return best_boundary


def build_chunk_id(
    *, source_id: str, version: str, start_char: int, end_char: int, span_text: str
) -> str:
    """Build a deterministic chunk ID for a given span with enhanced stability.
    
    The chunk ID is designed to be:
    1. Deterministic - same input always produces same ID
    2. Stable - minor text changes don't affect unrelated chunks
    3. Unique - different chunks have different IDs
    4. Versioned - includes version for schema evolution
    5. Traceable - includes source and position information
    
    Format: {source_id}:{version}:{start_char}:{end_char}:{content_hash}
    
    Args:
        source_id: Stable identifier for the source document
        version: Chunking version for schema evolution
        start_char: Starting character position in source text
        end_char: Ending character position in source text
        span_text: The actual text content of the chunk
        
    Returns:
        Deterministic chunk ID string
    """
    # Normalize the span text for consistent hashing
    # This ensures minor whitespace differences don't change the ID
    normalized_span = span_text.strip()
    
    # Create a stable hash of the content
    # Use both position and content to ensure uniqueness
    hash_input = f"{source_id}\n{version}\n{start_char}\n{end_char}\n{normalized_span}"
    content_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    
    # Use first 16 characters of hash for reasonable ID length while maintaining uniqueness
    short_hash = content_hash[:16]
    
    # Build the final ID with clear structure
    chunk_id = f"{source_id}:{version}:{start_char}:{end_char}:{short_hash}"
    
    return chunk_id


def validate_overlap_consistency(
    chunks: List[Chunk], 
    options: ChunkingOptions,
    tokenizer: Optional["TokenizerAdapter"] = None
) -> List[str]:
    """Validate overlap consistency across chunks.
    
    This function checks that:
    1. Overlaps don't exceed the configured overlap_tokens limit
    2. Overlaps don't exceed chunk sizes
    3. Adjacent chunks have reasonable overlap
    4. No chunks are completely contained within overlaps
    
    Args:
        chunks: List of chunks to validate
        options: Chunking options used to create the chunks
        tokenizer: Optional tokenizer for accurate token counting
        
    Returns:
        List of validation error messages (empty if all validations pass)
    """
    errors = []
    
    if len(chunks) <= 1:
        return errors  # No overlap to validate with single chunk
    
    for i in range(1, len(chunks)):
        prev_chunk = chunks[i-1]
        curr_chunk = chunks[i]
        
        # Check if chunks overlap
        if curr_chunk.start_char >= prev_chunk.end_char:
            # No overlap - this is valid but worth noting
            continue
        
        # Calculate overlap region
        overlap_start = curr_chunk.start_char
        overlap_end = prev_chunk.end_char
        overlap_text = prev_chunk.text[overlap_start - prev_chunk.start_char:]
        
        if not overlap_text.strip():
            # Empty overlap - skip validation
            continue
        
        # Validate overlap size if tokenizer is available
        if tokenizer:
            try:
                overlap_token_count = tokenizer.count_tokens(overlap_text).count
                
                # Check if overlap exceeds configured limit
                if overlap_token_count > options.overlap_tokens:
                    errors.append(
                        f"Chunk {i}: Overlap ({overlap_token_count} tokens) exceeds "
                        f"configured limit ({options.overlap_tokens} tokens)"
                    )
                
                # Check if overlap is too large relative to chunk size
                prev_chunk_tokens = tokenizer.count_tokens(prev_chunk.text).count
                if overlap_token_count > prev_chunk_tokens // 2:
                    errors.append(
                        f"Chunk {i}: Overlap ({overlap_token_count} tokens) exceeds "
                        f"half of previous chunk size ({prev_chunk_tokens} tokens)"
                    )
                
                # Check if current chunk is too small compared to overlap
                curr_chunk_tokens = tokenizer.count_tokens(curr_chunk.text).count
                if overlap_token_count >= curr_chunk_tokens:
                    errors.append(
                        f"Chunk {i}: Overlap ({overlap_token_count} tokens) is larger than "
                        f"or equal to current chunk ({curr_chunk_tokens} tokens)"
                    )
                    
            except Exception as e:
                errors.append(f"Chunk {i}: Failed to validate overlap with tokenizer: {e}")
        
        # Character-based validation (always performed)
        overlap_chars = len(overlap_text)
        prev_chunk_chars = len(prev_chunk.text)
        curr_chunk_chars = len(curr_chunk.text)
        
        # Check for excessive character overlap
        if overlap_chars > prev_chunk_chars * 0.8:  # More than 80% overlap
            errors.append(
                f"Chunk {i}: Character overlap ({overlap_chars}) is more than 80% "
                f"of previous chunk ({prev_chunk_chars} chars)"
            )
        
        if overlap_chars >= curr_chunk_chars:
            errors.append(
                f"Chunk {i}: Character overlap ({overlap_chars}) is larger than "
                f"or equal to current chunk ({curr_chunk_chars} chars)"
            )
    
    return errors


def chunk_text(source_id: str, text: str, options: ChunkingOptions) -> List[Chunk]:
    """Chunk text into deterministic spans with stable IDs and enhanced boundary detection.

    This function implements the enhanced chunking algorithm with:
    1. Comprehensive text normalization (Unicode NFC, whitespace, newlines)
    2. Hierarchical boundary detection (paragraph → sentence → hard cut)
    3. Improved boundary selection with scoring
    4. Stable chunk ID generation with version tracking

    Args:
        source_id: Stable identifier for the source document.
        text: Raw input text.
        options: Chunking options (size, overlap, version).

    Returns:
        Deterministic list of chunks ordered by increasing start_char.
        
    Raises:
        ValueError: If source_id is empty or options are invalid.
    """
    if not source_id:
        raise ValueError("source_id must be non-empty")

    # Step 1: Enhanced text normalization
    normalized = normalize_text(text)
    if not normalized:
        return []  # Empty text produces no chunks

    # Step 2: Generate token spans for tokenizer-agnostic chunking
    spans = token_spans(normalized)
    if not spans:
        return []

    # Step 3: Enhanced boundary detection with hierarchy
    para_boundaries = _boundary_token_indexes(_paragraph_boundary_chars(normalized), spans)
    sent_boundaries = _boundary_token_indexes(_sentence_boundary_chars(normalized), spans)

    chunks: List[Chunk] = []
    start_token = 0
    total_tokens = len(spans)

    # Step 4: Iterative chunking with enhanced boundary selection
    while start_token < total_tokens:
        max_end = min(start_token + options.max_tokens, total_tokens)
        preferred_end = min(start_token + options.target_tokens, max_end)

        # Try paragraph boundaries first (highest priority)
        end_token = _pick_boundary(
            boundaries=para_boundaries,
            start_token=start_token,
            preferred_end=preferred_end,
            max_end=max_end,
        )
        
        # Fall back to sentence boundaries if no good paragraph boundary
        if end_token is None:
            end_token = _pick_boundary(
                boundaries=sent_boundaries,
                start_token=start_token,
                preferred_end=preferred_end,
                max_end=max_end,
            )
        
        # Hard cut if no good boundary found (last resort)
        if end_token is None:
            end_token = max_end

        # Ensure progress (never create empty chunks)
        if end_token <= start_token:
            end_token = min(start_token + 1, total_tokens)

        # Step 5: Create chunk with enhanced metadata
        start_char = spans[start_token][0]
        end_char = spans[end_token - 1][1]
        span_text = normalized[start_char:end_char]
        
        chunk = Chunk(
            source_id=source_id,
            start_char=start_char,
            end_char=end_char,
            text=span_text,
            chunk_id=build_chunk_id(
                source_id=source_id,
                version=options.version,
                start_char=start_char,
                end_char=end_char,
                span_text=span_text,
            ),
        )
        chunks.append(chunk)

        # Step 6: Calculate next start position with enhanced overlap handling
        if end_token >= total_tokens:
            break

        chunk_len = end_token - start_token
        
        # Enhanced overlap calculation that respects token boundaries and chunk sizes
        if options.overlap_tokens <= 0:
            # No overlap requested
            start_token = end_token
        elif chunk_len <= options.overlap_tokens:
            # Chunk is smaller than or equal to overlap - use minimal overlap
            overlap_amount = max(0, chunk_len - 1)  # Leave at least 1 token of new content
            start_token = max(end_token - overlap_amount, start_token + 1)
        elif chunk_len <= 2:
            # Very small chunk - no overlap to ensure progress
            start_token = end_token
        else:
            # Normal case: apply overlap but limit to half the chunk size
            max_overlap = min(options.overlap_tokens, chunk_len // 2)
            start_token = end_token - max_overlap

    return chunks


def chunk_text_with_tokenizer(
    source_id: str, 
    text: str, 
    options: ChunkingOptions,
    tokenizer: Optional["TokenizerAdapter"] = None,
    registry: Optional["TokenizerRegistry"] = None,
    model_name: str = "default-model"
) -> List[Chunk]:
    """Enhanced chunking function that uses tokenizer adapters for accurate token counting.
    
    This function integrates with the tokenizer adapter system to provide more accurate
    token-aware chunking while maintaining backward compatibility with the existing API.
    
    Args:
        source_id: Stable identifier for the source document.
        text: Raw input text.
        options: Chunking options including tokenizer adapter selection.
        tokenizer: Optional pre-configured tokenizer adapter. If None, will resolve
                  from options.tokenizer_adapter using the registry.
        registry: Optional tokenizer registry. If None, uses default registry.
        model_name: Model name for tokenizer resolution when tokenizer is None.
        
    Returns:
        Deterministic list of chunks ordered by increasing start_char.
        
    Raises:
        ValueError: If source_id is empty or tokenizer cannot be resolved.
        RuntimeError: If no tokenizer adapter is available.
    """
    if not source_id:
        raise ValueError("source_id must be non-empty")

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    
    # Resolve tokenizer if not provided
    if tokenizer is None:
        try:
            # Import here to avoid circular imports
            from .tokenizer import resolve_tokenizer_with_fallback, get_default_registry
            
            if registry is None:
                registry = get_default_registry()
            
            tokenizer = resolve_tokenizer_with_fallback(
                adapter_name=options.tokenizer_adapter,
                model_name=model_name,
                registry=registry
            )
            
            # Log telemetry for adapter usage
            logger.info(
                "tokenizer_adapter_resolved",
                extra={
                    "adapter_name": options.tokenizer_adapter,
                    "resolved_adapter": tokenizer.adapter_id,
                    "model_name": model_name,
                    "source_id": source_id
                }
            )
            
        except Exception as e:
            logger.warning(f"Failed to resolve tokenizer adapter '{options.tokenizer_adapter}': {e}")
            # Fallback to original chunking method for backward compatibility
            logger.info("Falling back to heuristic token-span chunking")
            return chunk_text(source_id, text, options)
    
    # Use the enhanced chunking with tokenizer adapter
    return _chunk_text_with_adapter(source_id, text, options, tokenizer)


def _chunk_text_with_adapter(
    source_id: str,
    text: str, 
    options: ChunkingOptions,
    tokenizer: "TokenizerAdapter"
) -> List[Chunk]:
    """Internal function that performs tokenizer-aware chunking.
    
    This function uses the tokenizer adapter to make more accurate token-based
    decisions while maintaining the same deterministic boundary selection logic.
    """
    if not text:
        return []
    
    normalized = normalize_text(text)
    if not normalized.strip():
        return []
    
    # Get paragraph and sentence boundaries in character space
    para_boundaries = _paragraph_boundary_chars(normalized)
    sent_boundaries = _sentence_boundary_chars(normalized)
    
    chunks: List[Chunk] = []
    current_pos = 0
    text_len = len(normalized)
    
    while current_pos < text_len:
        # Find the optimal chunk end position using tokenizer feedback
        chunk_end = _find_optimal_chunk_end(
            text=normalized,
            start_pos=current_pos,
            options=options,
            tokenizer=tokenizer,
            para_boundaries=para_boundaries,
            sent_boundaries=sent_boundaries
        )
        
        if chunk_end <= current_pos:
            # Ensure progress - take at least one character
            chunk_end = min(current_pos + 1, text_len)
        
        # Extract chunk text
        chunk_text = normalized[current_pos:chunk_end]
        
        # Create chunk with stable ID
        chunk = Chunk(
            source_id=source_id,
            start_char=current_pos,
            end_char=chunk_end,
            text=chunk_text,
            chunk_id=build_chunk_id(
                source_id=source_id,
                version=options.version,
                start_char=current_pos,
                end_char=chunk_end,
                span_text=chunk_text,
            ),
        )
        chunks.append(chunk)
        
        if chunk_end >= text_len:
            break
        
        # Calculate next start position with enhanced token-aware overlap
        next_start = _calculate_overlap_start(
            text=normalized,
            chunk_end=chunk_end,
            options=options,
            tokenizer=tokenizer,
            previous_chunk_start=current_pos  # Pass the current chunk start for validation
        )
        
        current_pos = max(next_start, current_pos + 1)  # Ensure progress
    
    return chunks


def _find_optimal_chunk_end(
    text: str,
    start_pos: int,
    options: ChunkingOptions,
    tokenizer: "TokenizerAdapter",
    para_boundaries: List[int],
    sent_boundaries: List[int]
) -> int:
    """Find the optimal end position for a chunk using tokenizer feedback.
    
    This function uses binary search with tokenizer feedback to find the largest
    chunk that fits within the token budget while respecting boundary preferences.
    """
    text_len = len(text)
    
    # Binary search for the maximum text that fits within max_tokens
    left = start_pos + 1
    right = min(start_pos + (options.max_tokens * 10), text_len)  # Rough upper bound
    
    best_end = left
    
    while left <= right:
        mid = (left + right) // 2
        candidate_text = text[start_pos:mid]
        
        try:
            token_count = tokenizer.count_tokens(candidate_text)
            
            if token_count.count <= options.max_tokens:
                best_end = mid
                left = mid + 1
            else:
                right = mid - 1
                
        except Exception as e:
            logger.warning(f"Tokenizer failed for text segment: {e}")
            # Fallback to character-based estimation
            right = mid - 1
    
    # Now find the best boundary within the token budget
    return _find_best_boundary(
        text=text,
        start_pos=start_pos,
        max_end=best_end,
        target_tokens=options.target_tokens,
        tokenizer=tokenizer,
        para_boundaries=para_boundaries,
        sent_boundaries=sent_boundaries
    )


def _find_best_boundary(
    text: str,
    start_pos: int,
    max_end: int,
    target_tokens: int,
    tokenizer: "TokenizerAdapter",
    para_boundaries: List[int],
    sent_boundaries: List[int]
) -> int:
    """Find the best boundary position within the token budget."""
    
    # Try to find a boundary near the target token count
    target_end = _find_position_for_target_tokens(
        text, start_pos, target_tokens, tokenizer, max_end
    )
    
    # Look for paragraph boundaries first
    para_end = _find_nearest_boundary(para_boundaries, target_end, start_pos + 1, max_end)
    if para_end is not None:
        return para_end
    
    # Fall back to sentence boundaries
    sent_end = _find_nearest_boundary(sent_boundaries, target_end, start_pos + 1, max_end)
    if sent_end is not None:
        return sent_end
    
    # No good boundary found, use the maximum allowed position
    return max_end


def _find_position_for_target_tokens(
    text: str,
    start_pos: int,
    target_tokens: int,
    tokenizer: "TokenizerAdapter",
    max_end: int
) -> int:
    """Find the position that approximately matches the target token count."""
    
    left = start_pos + 1
    right = max_end
    best_pos = left
    
    while left <= right:
        mid = (left + right) // 2
        candidate_text = text[start_pos:mid]
        
        try:
            token_count = tokenizer.count_tokens(candidate_text)
            
            if token_count.count <= target_tokens:
                best_pos = mid
                left = mid + 1
            else:
                right = mid - 1
                
        except Exception:
            # Fallback on tokenizer error
            right = mid - 1
    
    return best_pos


def _find_nearest_boundary(
    boundaries: List[int],
    target_pos: int,
    min_pos: int,
    max_pos: int
) -> Optional[int]:
    """Find the nearest boundary to the target position within the allowed range."""
    
    # Filter boundaries to the allowed range
    valid_boundaries = [b for b in boundaries if min_pos <= b <= max_pos]
    
    if not valid_boundaries:
        return None
    
    # Find the boundary closest to target_pos
    best_boundary = valid_boundaries[0]
    best_distance = abs(best_boundary - target_pos)
    
    for boundary in valid_boundaries[1:]:
        distance = abs(boundary - target_pos)
        if distance < best_distance:
            best_boundary = boundary
            best_distance = distance
    
    return best_boundary


def _calculate_overlap_start(
    text: str,
    chunk_end: int,
    options: ChunkingOptions,
    tokenizer: "TokenizerAdapter",
    previous_chunk_start: int = 0
) -> int:
    """Calculate the start position for the next chunk considering token-aware overlap.
    
    Enhanced overlap calculation that:
    1. Works in token space using the tokenizer adapter
    2. Ensures overlap doesn't exceed chunk size
    3. Handles edge cases (very short chunks, large overlap)
    4. Validates overlap consistency
    
    Args:
        text: The normalized text being chunked
        chunk_end: End position of the current chunk
        options: Chunking options including overlap_tokens
        tokenizer: Tokenizer adapter for accurate token counting
        previous_chunk_start: Start position of the previous chunk (for validation)
        
    Returns:
        Start position for the next chunk that provides optimal overlap
    """
    if options.overlap_tokens <= 0:
        return chunk_end
    
    # Calculate the size of the previous chunk in tokens for validation
    previous_chunk_text = text[previous_chunk_start:chunk_end]
    try:
        previous_chunk_tokens = tokenizer.count_tokens(previous_chunk_text).count
    except Exception as e:
        logger.warning(f"Failed to count tokens for previous chunk: {e}")
        # Fallback to no overlap on tokenizer error
        return chunk_end
    
    # Edge case: If the previous chunk is very small, limit overlap
    if previous_chunk_tokens <= 2:
        # For very small chunks, use minimal or no overlap
        max_overlap_tokens = max(0, previous_chunk_tokens - 1)
        effective_overlap_tokens = min(options.overlap_tokens, max_overlap_tokens)
        logger.debug(f"Very small chunk ({previous_chunk_tokens} tokens), limiting overlap to {effective_overlap_tokens}")
    else:
        # Ensure overlap doesn't exceed half the chunk size to maintain meaningful content
        max_overlap_tokens = min(options.overlap_tokens, previous_chunk_tokens // 2)
        effective_overlap_tokens = max_overlap_tokens
    
    # If no effective overlap, return chunk_end
    if effective_overlap_tokens <= 0:
        return chunk_end
    
    # Binary search to find the position that gives us the desired overlap
    left = max(0, previous_chunk_start)  # Don't go before the previous chunk start
    right = chunk_end - 1
    best_start = chunk_end  # No overlap by default
    best_token_count = 0
    
    # Ensure we have a valid search range
    if left >= right:
        return chunk_end
    
    while left <= right:
        mid = (left + right) // 2
        overlap_text = text[mid:chunk_end]
        
        # Skip empty overlap text
        if not overlap_text.strip():
            left = mid + 1
            continue
        
        try:
            token_count = tokenizer.count_tokens(overlap_text).count
            
            if token_count <= effective_overlap_tokens:
                # This overlap size is acceptable
                best_start = mid
                best_token_count = token_count
                right = mid - 1  # Try to get more overlap
            else:
                # Too much overlap, reduce it
                left = mid + 1
                
        except Exception as e:
            logger.debug(f"Tokenizer error during overlap calculation: {e}")
            # On tokenizer error, try reducing overlap
            left = mid + 1
    
    # Validate the overlap result
    if best_start < chunk_end:
        final_overlap_text = text[best_start:chunk_end]
        if final_overlap_text.strip():  # Only log if there's actual content
            logger.debug(
                f"Calculated overlap: {best_token_count} tokens "
                f"(requested: {effective_overlap_tokens}, max: {max_overlap_tokens})"
            )
    
    return best_start
