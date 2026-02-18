# Token-Aware Overlap Calculation Implementation

## Overview

This document describes the implementation of task 2.4 from the tokenizer-adapters spec: "Implement token-aware overlap calculation". The implementation enhances the chunking system to provide accurate token-based overlap calculation using tokenizer adapters.

## Task Requirements

The task required implementing:

1. **Overlap calculation in token space rather than character space**
2. **Ensure overlap doesn't exceed chunk size**
3. **Handle edge cases (very short chunks, large overlap)**
4. **Validate overlap consistency across chunks**

## Implementation Details

### Enhanced `_calculate_overlap_start` Function

The core improvement is in the `_calculate_overlap_start` function in `chunking.py`:

```python
def _calculate_overlap_start(
    text: str,
    chunk_end: int,
    options: ChunkingOptions,
    tokenizer: "TokenizerAdapter",
    previous_chunk_start: int = 0
) -> int:
```

**Key enhancements:**

1. **Token-space calculation**: Uses the tokenizer adapter to count tokens accurately
2. **Chunk size validation**: Calculates previous chunk size to limit overlap appropriately
3. **Edge case handling**: Special logic for very short chunks (≤2 tokens)
4. **Overlap limiting**: Ensures overlap doesn't exceed half the chunk size
5. **Binary search optimization**: Efficiently finds the optimal overlap position

### Enhanced `chunk_text` Function

Improved the overlap calculation in the original `chunk_text` function:

```python
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
```

### Overlap Consistency Validation

Added a comprehensive validation function:

```python
def validate_overlap_consistency(
    chunks: List[Chunk], 
    options: ChunkingOptions,
    tokenizer: Optional["TokenizerAdapter"] = None
) -> List[str]:
```

This function validates:
- Overlaps don't exceed configured limits
- Overlaps don't exceed chunk sizes
- Adjacent chunks have reasonable overlap
- No chunks are completely contained within overlaps

## Edge Case Handling

### Very Short Chunks
- Chunks with ≤2 tokens get minimal or no overlap
- Ensures forward progress is always maintained
- Prevents overlap from consuming entire chunks

### Large Overlap Configuration
- Overlap is limited to half the chunk size
- Prevents overlap from dominating chunk content
- Maintains meaningful new content in each chunk

### Tokenizer Errors
- Graceful fallback when tokenizer fails
- Maintains system stability
- Logs warnings for debugging

## Testing

### Unit Tests (`test_token_aware_overlap.py`)

Comprehensive test suite covering:
- Basic overlap calculation functionality
- Edge cases (very short chunks, large overlap)
- Different tokenizer types
- Overlap consistency validation
- Error handling

### Property-Based Tests (`test_overlap_properties.py`)

Implements the correctness properties from the spec:

**Property 1.4: Overlap Consistency**
```python
@given(text=st.text(...), target_tokens=st.integers(...), ...)
def test_property_1_4_overlap_consistency(self, ...):
    """Property 1.4: Overlap tokens are correctly applied between adjacent chunks.
    
    **Validates: Requirements US-2, FR-3**
    """
```

Tests validate:
- Overlap is applied between adjacent chunks
- Overlap doesn't exceed configured limits
- Overlap doesn't exceed chunk sizes
- Overall consistency across all chunks

### Integration with Existing Tests

All existing chunking tests continue to pass, ensuring backward compatibility.

## Performance Considerations

### Binary Search Optimization
- Uses binary search to find optimal overlap positions
- Reduces tokenizer calls from O(n) to O(log n)
- Maintains good performance even with large chunks

### Tokenizer Caching
- Reuses tokenizer instances across chunks
- Minimizes initialization overhead
- Supports different tokenizer types efficiently

## Configuration

The overlap calculation respects all existing `ChunkingOptions`:

```python
@dataclass(frozen=True)
class ChunkingOptions:
    target_tokens: int = 256
    max_tokens: int = 512
    overlap_tokens: int = 32        # Used by enhanced overlap calculation
    version: str = "chunk-v1"
    tokenizer_adapter: str = "auto" # Selects tokenizer for overlap calculation
```

## Usage Examples

### Basic Usage with Tokenizer Adapter

```python
from kano_backlog_core.chunking import chunk_text_with_tokenizer, ChunkingOptions
from kano_backlog_core.tokenizer import HeuristicTokenizer

options = ChunkingOptions(
    target_tokens=256,
    max_tokens=512,
    overlap_tokens=50
)
tokenizer = HeuristicTokenizer("gpt-3.5-turbo")

chunks = chunk_text_with_tokenizer("doc-id", text, options, tokenizer)
```

### Validation

```python
from kano_backlog_core.chunking import validate_overlap_consistency

errors = validate_overlap_consistency(chunks, options, tokenizer)
if errors:
    print("Overlap validation issues:", errors)
```

## Benefits

1. **Accurate Token Counting**: Uses actual tokenizer adapters instead of heuristics
2. **Consistent Overlap**: Ensures overlap is meaningful and consistent
3. **Edge Case Handling**: Robust handling of unusual text and configurations
4. **Performance**: Efficient binary search algorithm
5. **Validation**: Comprehensive validation for debugging and quality assurance
6. **Backward Compatibility**: Existing code continues to work unchanged

## Future Enhancements

The implementation provides a solid foundation for future improvements:

1. **Semantic Overlap**: Could be enhanced to consider semantic boundaries
2. **Adaptive Overlap**: Could adjust overlap based on content type
3. **Multi-Model Support**: Already supports different tokenizer adapters
4. **Caching**: Could add token count caching for repeated text segments

## Conclusion

The token-aware overlap calculation implementation successfully addresses all task requirements:

✅ **Overlap calculation in token space** - Uses tokenizer adapters for accurate counting  
✅ **Ensure overlap doesn't exceed chunk size** - Limits overlap to half chunk size  
✅ **Handle edge cases** - Special handling for short chunks and large overlaps  
✅ **Validate overlap consistency** - Comprehensive validation function  

The implementation is thoroughly tested with both unit tests and property-based tests, ensuring reliability and correctness across a wide range of inputs and configurations.