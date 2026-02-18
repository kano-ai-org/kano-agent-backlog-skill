"""Real-world document processing integration tests.

This module provides integration tests using realistic document types and scenarios
that users would encounter in production environments. These tests validate the
complete tokenizer-chunking pipeline with actual document formats and content.

Test scenarios include:
- Markdown documents with various formatting
- Code documentation and technical content
- Mixed-language documentation
- Large structured documents
- Real backlog item processing
"""

import pytest
from typing import List, Dict, Any, Optional
from pathlib import Path
import tempfile

from kano_backlog_core.tokenizer import (
    HeuristicTokenizer,
    TokenizerRegistry,
)
from kano_backlog_core.chunking import (
    ChunkingOptions,
    Chunk,
    chunk_text_with_tokenizer,
    normalize_text,
    validate_overlap_consistency,
)
from kano_backlog_core.token_budget import (
    budget_chunks,
    TokenBudgetPolicy,
)


class TestMarkdownDocumentProcessing:
    """Test processing of Markdown documents with various formatting elements."""

    def test_technical_documentation_processing(self):
        """Test processing of technical documentation with code blocks and formatting."""
        source_id = "tech-doc-test"
        markdown_content = '''# API Documentation

This document describes the REST API for the tokenizer service.

## Overview

The tokenizer service provides accurate token counting for various model providers.
It supports multiple adapters including:

- **Heuristic Adapter**: Fast approximation using character ratios
- **TikToken Adapter**: Exact tokenization for OpenAI models  
- **HuggingFace Adapter**: Support for transformer models

## Authentication

All API requests require authentication using an API key:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \\
     https://api.example.com/tokenize
```

### API Key Management

API keys can be managed through the dashboard:

1. Navigate to the API Keys section
2. Click "Generate New Key"
3. Copy the key and store it securely
4. Use the key in your requests

## Endpoints

### POST /tokenize

Tokenize text using the specified adapter.

**Request Body:**
```json
{
  "text": "Text to tokenize",
  "adapter": "heuristic",
  "model": "text-embedding-3-small"
}
```

**Response:**
```json
{
  "token_count": 42,
  "method": "heuristic",
  "tokenizer_id": "heuristic:text-embedding-3-small:chars_4.0",
  "is_exact": false
}
```

### GET /adapters

List available tokenizer adapters.

**Response:**
```json
{
  "adapters": [
    {
      "name": "heuristic",
      "description": "Fast character-based approximation",
      "available": true
    },
    {
      "name": "tiktoken", 
      "description": "OpenAI's exact tokenizer",
      "available": true
    }
  ]
}
```

## Error Handling

The API returns standard HTTP status codes:

| Code | Description |
|------|-------------|
| 200  | Success |
| 400  | Bad Request |
| 401  | Unauthorized |
| 429  | Rate Limited |
| 500  | Server Error |

### Error Response Format

```json
{
  "error": {
    "code": "INVALID_ADAPTER",
    "message": "The specified adapter is not available",
    "details": {
      "adapter": "nonexistent",
      "available_adapters": ["heuristic", "tiktoken"]
    }
  }
}
```

## Rate Limits

API requests are rate limited:

- **Free tier**: 100 requests per hour
- **Pro tier**: 1,000 requests per hour  
- **Enterprise**: Custom limits

Rate limit headers are included in responses:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## SDKs and Libraries

Official SDKs are available for:

- Python: `pip install tokenizer-client`
- JavaScript: `npm install @tokenizer/client`
- Go: `go get github.com/tokenizer/go-client`

### Python Example

```python
from tokenizer_client import TokenizerClient

client = TokenizerClient(api_key="your-key")
result = client.tokenize(
    text="Hello world",
    adapter="heuristic",
    model="text-embedding-3-small"
)
print(f"Token count: {result.token_count}")
```

## Support

For support and questions:

- Documentation: https://docs.tokenizer.example.com
- GitHub Issues: https://github.com/tokenizer/issues
- Email: support@tokenizer.example.com
- Discord: https://discord.gg/tokenizer
'''
        
        options = ChunkingOptions(
            target_tokens=200,
            max_tokens=400,
            overlap_tokens=40,
            version="tech-doc-v1",
            tokenizer_adapter="heuristic"
        )
        
        tokenizer = HeuristicTokenizer("tech-doc-model", chars_per_token=4.0)
        
        chunks = chunk_text_with_tokenizer(source_id, markdown_content, options, tokenizer)
        
        # Validate technical documentation processing
        assert len(chunks) >= 3, "Technical documentation should produce multiple chunks"
        
        # Verify chunks respect boundaries and maintain readability
        for i, chunk in enumerate(chunks):
            # Verify basic chunk properties
            assert chunk.source_id == source_id
            assert len(chunk.text) > 0
            assert chunk.chunk_id.startswith(f"{source_id}:{options.version}:")
            
            # Verify token budget compliance
            token_count = tokenizer.count_tokens(chunk.text)
            assert token_count.count <= options.max_tokens, \
                f"Chunk {i} exceeds token budget: {token_count.count} > {options.max_tokens}"
            
            # Verify chunk contains meaningful content (not just whitespace/formatting)
            meaningful_content = chunk.text.strip()
            assert len(meaningful_content) > 10, f"Chunk {i} lacks meaningful content"
        
        # Verify overlap consistency
        overlap_errors = validate_overlap_consistency(chunks, options, tokenizer)
        assert not overlap_errors, f"Overlap validation errors: {overlap_errors}"
        
        # Note: The chunking core does not guarantee fence-balanced code blocks.
        # Code fences may legitimately span chunks when token budgets require it.

    def test_mixed_content_documentation(self):
        """Test processing of documentation with mixed content types."""
        source_id = "mixed-content-doc"
        mixed_content = '''# Multi-Language Development Guide

This guide covers development practices for international applications.

## English Content

Standard development practices apply for English content. Use clear, concise language
and follow established documentation patterns.

### Code Examples

```javascript
// English comments in code
function processText(input) {
    return input.toLowerCase().trim();
}
```

## 中文内容 (Chinese Content)

中文文档需要特殊处理。每个汉字通常被视为一个标记。

### 代码示例

```python
# 中文注释
def 处理文本(输入):
    """处理中文文本的函数"""
    return 输入.strip()
```

## 日本語コンテンツ (Japanese Content)

日本語の文書処理では、ひらがな、カタカナ、漢字の混在に注意が必要です。

### コード例

```java
// 日本語のコメント
public class テキスト処理 {
    public String 正規化(String 入力) {
        return 入力.trim();
    }
}
```

## Mixed Language Examples

Real-world applications often contain mixed languages:

```yaml
# Configuration with mixed languages
app:
  name: "MyApp"
  title_en: "My Application"
  title_zh: "我的应用程序"
  title_ja: "私のアプリケーション"
  
  messages:
    welcome_en: "Welcome to our application!"
    welcome_zh: "欢迎使用我们的应用程序！"
    welcome_ja: "私たちのアプリケーションへようこそ！"
```

## Best Practices

### Internationalization (i18n)

1. **Text Extraction**: Extract all user-facing text
2. **Unicode Handling**: Properly handle Unicode normalization
3. **RTL Support**: Consider right-to-left languages
4. **Font Support**: Ensure fonts support all required scripts

### Tokenization Considerations

Different languages have different tokenization patterns:

- **English**: Word-based tokenization works well
- **Chinese**: Character-based tokenization is common
- **Japanese**: Mixed approach with morphological analysis
- **Arabic**: RTL text with complex script rules

### Testing Strategies

```python
def test_multilingual_processing():
    test_cases = [
        ("Hello world", "en"),
        ("你好世界", "zh"),
        ("こんにちは世界", "ja"),
        ("مرحبا بالعالم", "ar"),
    ]
    
    for text, lang in test_cases:
        result = process_text(text, language=lang)
        assert result is not None
        assert len(result) > 0
```

## Conclusion

Proper handling of multilingual content requires careful consideration of:

- Character encoding and normalization
- Tokenization strategies per language
- Cultural and linguistic conventions
- Testing across different scripts and languages

For more information, see the [Unicode Standard](https://unicode.org/standard/standard.html).
'''
        
        options = ChunkingOptions(
            target_tokens=150,
            max_tokens=300,
            overlap_tokens=30,
            version="mixed-content-v1",
            tokenizer_adapter="heuristic"
        )
        
        tokenizer = HeuristicTokenizer("mixed-content-model", chars_per_token=3.5)  # Better for mixed content
        
        chunks = chunk_text_with_tokenizer(source_id, mixed_content, options, tokenizer)
        
        # Validate mixed content processing
        assert len(chunks) >= 4, "Mixed content document should produce multiple chunks"
        
        # Analyze script distribution across chunks
        script_stats = {"latin": 0, "cjk": 0, "mixed": 0}
        
        for chunk in chunks:
            # Count different script types
            latin_chars = sum(1 for c in chunk.text if c.isascii() and c.isalpha())
            cjk_chars = sum(1 for c in chunk.text if 
                          '\u4e00' <= c <= '\u9fff' or  # Chinese
                          '\u3040' <= c <= '\u30ff' or  # Japanese
                          '\uac00' <= c <= '\ud7af')    # Korean
            
            if latin_chars > 0 and cjk_chars > 0:
                script_stats["mixed"] += 1
            elif cjk_chars > 0:
                script_stats["cjk"] += 1
            elif latin_chars > 0:
                script_stats["latin"] += 1
            
            # Verify token budget compliance
            token_count = tokenizer.count_tokens(chunk.text)
            assert token_count.count <= options.max_tokens
            
            # Verify chunk quality
            assert len(chunk.text.strip()) > 0
        
        # Should have processed different script types
        total_script_chunks = sum(script_stats.values())
        assert total_script_chunks > 0, "Should have processed text with identifiable scripts"


class TestBacklogItemProcessing:
    """Test processing of actual backlog items with realistic content."""

    def test_epic_item_processing(self):
        """Test processing of a large epic backlog item."""
        source_id = "EPIC-001"
        epic_content = '''---
id: PROJ-EPIC-001
uid: 12345678-90ab-cdef-1234-567890abcdef
type: Epic
state: InProgress
title: Implement Advanced Search and Analytics Platform
priority: P1
parent: null
owner: product-team
area: search
iteration: Q2-2024
tags: [search, analytics, machine-learning, performance]
created: '2024-01-15'
updated: '2024-01-23'
---

# Context

Our current search functionality is limited to basic text matching and lacks the sophisticated
analytics capabilities that our users need. Customer feedback indicates that:

1. **Search Quality Issues**: Users struggle to find relevant content due to limited ranking algorithms
2. **No Analytics**: Product managers lack insights into search patterns and user behavior  
3. **Performance Problems**: Search becomes slow with large datasets (>100k items)
4. **Limited Personalization**: No ability to customize search results based on user preferences

Market research shows that competitors offer advanced search with:
- Semantic search using vector embeddings
- Real-time analytics dashboards
- Machine learning-powered recommendations
- Sub-second response times even for complex queries

## Business Impact

Current limitations are affecting key metrics:
- **User Satisfaction**: Search satisfaction score is 2.3/5 (target: 4.0/5)
- **Task Completion**: 35% of users abandon searches without finding what they need
- **Support Load**: 40% of support tickets are related to "can't find" issues
- **Revenue Impact**: Estimated $2M annual loss due to poor search experience

# Goal

Implement a comprehensive search and analytics platform that provides:

1. **Advanced Search Capabilities**
   - Semantic search using vector embeddings
   - Faceted search with dynamic filters
   - Auto-complete and query suggestions
   - Typo tolerance and fuzzy matching

2. **Real-time Analytics**
   - Search query analytics and trending
   - User behavior tracking and insights
   - Performance monitoring and alerting
   - A/B testing framework for search improvements

3. **Machine Learning Integration**
   - Personalized search results
   - Content recommendations
   - Query intent classification
   - Automated relevance tuning

4. **Performance and Scalability**
   - Sub-second response times for 99% of queries
   - Support for 10M+ documents
   - Horizontal scaling capabilities
   - Efficient indexing and caching

# Approach

## Phase 1: Foundation (Months 1-2)
- Set up vector database infrastructure (Pinecone/Weaviate)
- Implement basic semantic search with embeddings
- Create search API with standardized interfaces
- Build basic analytics data pipeline

## Phase 2: Advanced Features (Months 3-4)
- Add faceted search and dynamic filtering
- Implement auto-complete and suggestions
- Build real-time analytics dashboard
- Add A/B testing framework

## Phase 3: ML Integration (Months 5-6)
- Implement personalization algorithms
- Add content recommendation engine
- Build query intent classification
- Create automated relevance tuning

## Phase 4: Optimization (Months 7-8)
- Performance optimization and caching
- Advanced analytics and reporting
- Mobile and API optimizations
- Documentation and training

## Technical Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Search API    │    │  Analytics API  │    │   Admin API     │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
          ┌─────────────────────────────────────────────┐
          │            Search Engine Core               │
          │  ┌─────────────┐  ┌─────────────────────┐   │
          │  │   Vector    │  │    Traditional      │   │
          │  │   Search    │  │    Text Search      │   │
          │  └─────────────┘  └─────────────────────┘   │
          └─────────────────────────────────────────────┘
                                 │
          ┌─────────────────────────────────────────────┐
          │              Data Layer                     │
          │  ┌─────────────┐  ┌─────────────────────┐   │
          │  │   Vector    │  │    Document         │   │
          │  │  Database   │  │    Database         │   │
          │  └─────────────┘  └─────────────────────┘   │
          └─────────────────────────────────────────────┘
```

# Acceptance Criteria

## Functional Requirements

### Search Quality
- [ ] Semantic search returns relevant results for natural language queries
- [ ] Faceted search allows filtering by multiple dimensions simultaneously
- [ ] Auto-complete provides relevant suggestions within 100ms
- [ ] Typo tolerance handles common misspellings (edit distance ≤ 2)
- [ ] Search results include relevance scores and ranking explanations

### Analytics and Insights
- [ ] Real-time dashboard shows search metrics with <5 second latency
- [ ] Query analytics track search patterns, popular terms, and zero-result queries
- [ ] User behavior analytics show click-through rates and session patterns
- [ ] A/B testing framework supports search algorithm experiments
- [ ] Automated alerts notify of performance degradation or anomalies

### Performance and Scalability
- [ ] 99% of search queries complete within 500ms
- [ ] System handles 10,000 concurrent users without degradation
- [ ] Indexing processes 1M documents within 1 hour
- [ ] System maintains 99.9% uptime with proper failover
- [ ] Memory usage scales linearly with document count

### Machine Learning
- [ ] Personalization improves click-through rates by 25%
- [ ] Recommendations achieve 15% engagement rate
- [ ] Query intent classification accuracy >90%
- [ ] Automated relevance tuning improves search quality scores

## Non-Functional Requirements

### Security
- [ ] All search queries are logged and auditable
- [ ] Personal data in search results respects privacy settings
- [ ] API endpoints require proper authentication and authorization
- [ ] Search analytics data is anonymized and GDPR compliant

### Monitoring and Observability
- [ ] Comprehensive metrics for search performance and quality
- [ ] Distributed tracing for complex search operations
- [ ] Error tracking and alerting for system issues
- [ ] Capacity planning metrics and forecasting

### Documentation and Training
- [ ] API documentation with examples and SDKs
- [ ] User guides for search features and analytics
- [ ] Operational runbooks for system maintenance
- [ ] Training materials for support and product teams

# Risks / Dependencies

## High Risk
- **Vector Database Selection**: Choice between Pinecone, Weaviate, or self-hosted affects architecture
  - *Mitigation*: Prototype with multiple options, create abstraction layer
- **ML Model Performance**: Embedding models may not work well with domain-specific content
  - *Mitigation*: Plan for fine-tuning, have fallback to traditional search
- **Data Migration**: Moving existing search index without downtime is complex
  - *Mitigation*: Implement dual-write pattern, gradual migration strategy

## Medium Risk
- **Third-party Dependencies**: Reliance on external services for embeddings and analytics
  - *Mitigation*: Have backup providers, consider self-hosted alternatives
- **Performance at Scale**: Unknown performance characteristics with large datasets
  - *Mitigation*: Load testing, performance benchmarking, gradual rollout
- **User Adoption**: Users may resist changes to familiar search interface
  - *Mitigation*: Gradual rollout, user feedback, training and documentation

## Dependencies
- **Infrastructure Team**: Need support for new database deployments
- **Data Team**: Require data pipeline for analytics and ML features  
- **Security Team**: Need review of new data handling and privacy implications
- **Product Team**: Ongoing collaboration for feature prioritization and UX design

# Worklog

2024-01-15 10:00 [agent=product-manager] [model=gpt-4] Created epic based on user research and competitive analysis.
2024-01-16 14:30 [agent=tech-lead] [model=claude-3] Added technical architecture and implementation approach.
2024-01-17 09:15 [agent=product-manager] [model=gpt-4] Refined acceptance criteria based on stakeholder feedback.
2024-01-18 16:45 [agent=security-lead] [model=claude-3] Added security and compliance requirements.
2024-01-19 11:20 [agent=data-engineer] [model=gpt-4] Reviewed data pipeline requirements and dependencies.
2024-01-20 13:00 [agent=product-manager] [model=gpt-4] Updated timeline based on resource availability.
2024-01-21 10:30 [agent=ux-designer] [model=claude-3] Added user experience considerations and design requirements.
2024-01-22 15:15 [agent=tech-lead] [model=gpt-4] Detailed technical risks and mitigation strategies.
2024-01-23 09:45 [agent=product-manager] [model=claude-3] Final review and approval for development kickoff.
'''
        
        options = ChunkingOptions(
            target_tokens=300,
            max_tokens=600,
            overlap_tokens=60,
            version="backlog-v1",
            tokenizer_adapter="heuristic"
        )
        
        tokenizer = HeuristicTokenizer("backlog-model", chars_per_token=4.0)
        
        chunks = chunk_text_with_tokenizer(source_id, epic_content, options, tokenizer)
        
        # Validate epic processing
        assert len(chunks) >= 5, "Large epic should produce multiple chunks"
        
        # Verify frontmatter is handled correctly
        first_chunk = chunks[0]
        assert "---" in first_chunk.text, "First chunk should contain frontmatter"
        
        # Verify sections are chunked appropriately
        section_headers = ["# Context", "# Goal", "# Approach", "# Acceptance Criteria", "# Risks / Dependencies"]
        found_sections = set()
        
        for chunk in chunks:
            for header in section_headers:
                if header in chunk.text:
                    found_sections.add(header)
            
            # Verify token budget compliance
            token_count = tokenizer.count_tokens(chunk.text)
            assert token_count.count <= options.max_tokens
            
            # Verify chunk quality
            assert len(chunk.text.strip()) > 0
        
        # Should have found major sections
        assert len(found_sections) >= 3, f"Should find major sections, found: {found_sections}"

    def test_task_item_processing(self):
        """Test processing of a typical task backlog item."""
        source_id = "TASK-042"
        task_content = '''---
id: PROJ-TSK-042
uid: abcdef12-3456-7890-abcd-ef1234567890
type: Task
state: Ready
title: Implement token budget validation for chunking pipeline
priority: P2
parent: PROJ-FTR-015
owner: backend-dev
area: tokenization
iteration: sprint-23
tags: [tokenization, validation, testing]
created: '2024-01-20'
updated: '2024-01-23'
---

# Context

The current chunking pipeline lacks proper token budget validation, which can lead to:

1. **Budget Overruns**: Chunks may exceed the configured max_tokens limit
2. **Inconsistent Behavior**: Different tokenizer adapters may handle budgets differently  
3. **Poor Error Handling**: No clear feedback when budget constraints cannot be met
4. **Testing Gaps**: Insufficient test coverage for budget edge cases

This task is part of the larger tokenizer adapters feature (PROJ-FTR-015) and specifically
addresses the token budget management component identified in the design review.

## Current State

The existing implementation has basic budget checking but lacks:
- Comprehensive validation across all adapter types
- Proper error messages for budget violations
- Edge case handling (very small budgets, large overlaps)
- Integration tests for budget compliance

## User Impact

Without proper budget validation:
- Embedding operations may fail due to token limit violations
- Users get unclear error messages when budgets are misconfigured
- Inconsistent behavior across different tokenizer adapters
- Difficult to debug budget-related issues in production

# Goal

Implement comprehensive token budget validation that:

1. **Validates Budget Compliance**: Ensures all chunks respect configured token limits
2. **Provides Clear Feedback**: Returns meaningful error messages for budget violations
3. **Handles Edge Cases**: Gracefully manages extreme budget configurations
4. **Maintains Consistency**: Works identically across all tokenizer adapters
5. **Supports Testing**: Enables thorough testing of budget scenarios

## Success Metrics

- Zero budget overruns in production (100% compliance)
- Clear error messages for all budget violation scenarios
- Comprehensive test coverage (>95%) for budget validation
- Consistent behavior across all tokenizer adapters

# Approach

## Implementation Strategy

### Phase 1: Core Validation Logic
1. Create `TokenBudgetValidator` class with comprehensive validation rules
2. Implement budget compliance checking for all chunk operations
3. Add proper error handling with descriptive messages
4. Integrate with existing `TokenBudgetManager`

### Phase 2: Adapter Integration
1. Update all tokenizer adapters to use budget validation
2. Ensure consistent behavior across heuristic, tiktoken, and huggingface adapters
3. Add adapter-specific validation where needed
4. Test integration with chunking pipeline

### Phase 3: Edge Case Handling
1. Handle very small token budgets (< 10 tokens)
2. Manage large overlap configurations
3. Deal with empty or minimal text inputs
4. Provide graceful degradation for impossible budgets

### Phase 4: Testing and Documentation
1. Create comprehensive test suite for all budget scenarios
2. Add integration tests with real tokenizer adapters
3. Update documentation with budget validation examples
4. Add troubleshooting guide for common budget issues

## Technical Design

```python
class TokenBudgetValidator:
    def __init__(self, options: ChunkingOptions, tokenizer: TokenizerAdapter):
        self.options = options
        self.tokenizer = tokenizer
        self.safety_margin = self._calculate_safety_margin()
    
    def validate_chunk_budget(self, chunk_text: str) -> BudgetValidationResult:
        """Validate that chunk respects token budget."""
        token_count = self.tokenizer.count_tokens(chunk_text)
        
        if token_count.count > self.options.max_tokens:
            return BudgetValidationResult(
                valid=False,
                error_code="BUDGET_EXCEEDED",
                message=f"Chunk has {token_count.count} tokens, exceeds limit of {self.options.max_tokens}",
                suggested_action="Reduce chunk size or increase max_tokens"
            )
        
        return BudgetValidationResult(valid=True)
    
    def validate_configuration(self) -> ConfigValidationResult:
        """Validate that chunking configuration is reasonable."""
        # Implementation details...
```

## Error Handling Strategy

Define clear error codes and messages:

- `BUDGET_EXCEEDED`: Chunk exceeds max_tokens limit
- `INVALID_CONFIGURATION`: Chunking options are invalid
- `OVERLAP_TOO_LARGE`: Overlap exceeds chunk size
- `BUDGET_TOO_SMALL`: Budget too small for meaningful chunks
- `TOKENIZER_ERROR`: Tokenizer failed during validation

# Acceptance Criteria

## Functional Requirements

### Budget Validation
- [ ] All chunks are validated against max_tokens limit before creation
- [ ] Budget violations return clear error messages with specific details
- [ ] Validation works consistently across all tokenizer adapters
- [ ] Edge cases (small budgets, large overlaps) are handled gracefully
- [ ] Safety margins are properly applied and validated

### Error Handling
- [ ] Specific error codes for different types of budget violations
- [ ] Error messages include current values, limits, and suggested actions
- [ ] Validation failures don't crash the chunking pipeline
- [ ] Fallback behavior when strict validation cannot be met
- [ ] Proper logging of budget validation events

### Integration
- [ ] Budget validation integrates seamlessly with existing chunking pipeline
- [ ] No performance degradation from validation overhead
- [ ] Validation can be disabled for testing/debugging purposes
- [ ] Works with all existing tokenizer adapter configurations
- [ ] Maintains backward compatibility with existing code

## Testing Requirements

### Unit Tests
- [ ] Test budget validation with various token limits
- [ ] Test error message generation for different violation types
- [ ] Test edge cases (zero budgets, negative values, extreme overlaps)
- [ ] Test validation with different tokenizer adapters
- [ ] Test configuration validation logic

### Integration Tests
- [ ] Test budget validation in complete chunking pipeline
- [ ] Test with real documents and various configurations
- [ ] Test performance impact of validation
- [ ] Test error propagation through the system
- [ ] Test fallback behavior when validation fails

### Property-Based Tests
- [ ] **Property 1**: Budget validation never allows chunks exceeding max_tokens
- [ ] **Property 2**: Valid configurations always pass validation
- [ ] **Property 3**: Error messages are always non-empty for failures
- [ ] **Property 4**: Validation is deterministic for same inputs

## Performance Requirements

- [ ] Budget validation adds <10ms overhead per chunk
- [ ] Memory usage increases by <5% due to validation
- [ ] Validation scales linearly with chunk size
- [ ] No significant impact on overall chunking performance
- [ ] Validation can be batched for multiple chunks

# Risks / Dependencies

## Technical Risks

- **Performance Impact**: Validation might slow down chunking pipeline
  - *Mitigation*: Optimize validation logic, add performance benchmarks
- **Tokenizer Inconsistencies**: Different adapters might have different validation needs
  - *Mitigation*: Create adapter-specific validation where needed
- **Edge Case Complexity**: Handling all edge cases might be complex
  - *Mitigation*: Start with common cases, add edge cases iteratively

## Dependencies

- **TokenBudgetManager**: Need to integrate with existing budget management
- **Tokenizer Adapters**: All adapters must support validation requirements
- **Chunking Pipeline**: Changes must not break existing functionality
- **Test Infrastructure**: Need comprehensive test setup for validation scenarios

# Worklog

2024-01-20 14:00 [agent=backend-dev] [model=claude-3] Created task based on design review feedback.
2024-01-21 09:30 [agent=tech-lead] [model=gpt-4] Added technical design and implementation approach.
2024-01-21 16:15 [agent=backend-dev] [model=claude-3] Detailed acceptance criteria and testing requirements.
2024-01-22 10:45 [agent=qa-engineer] [model=gpt-4] Added property-based testing requirements.
2024-01-22 14:20 [agent=backend-dev] [model=claude-3] Refined error handling strategy and edge cases.
2024-01-23 11:00 [agent=tech-lead] [model=gpt-4] Final review and approval for implementation.
'''
        
        options = ChunkingOptions(
            target_tokens=200,
            max_tokens=400,
            overlap_tokens=40,
            version="task-v1",
            tokenizer_adapter="heuristic"
        )
        
        tokenizer = HeuristicTokenizer("task-model", chars_per_token=4.0)
        
        chunks = chunk_text_with_tokenizer(source_id, task_content, options, tokenizer)
        
        # Validate task processing
        assert len(chunks) >= 3, "Task item should produce multiple chunks"
        
        # Verify key sections are present
        key_sections = ["# Context", "# Goal", "# Approach", "# Acceptance Criteria"]
        found_sections = set()
        
        for chunk in chunks:
            for section in key_sections:
                if section in chunk.text:
                    found_sections.add(section)
            
            # Verify token budget compliance
            token_count = tokenizer.count_tokens(chunk.text)
            assert token_count.count <= options.max_tokens
            
            # Verify chunk structure
            assert chunk.source_id == source_id
            assert len(chunk.text.strip()) > 0
        
        # Should find major sections
        assert len(found_sections) >= 2, f"Should find major sections, found: {found_sections}"


class TestLargeStructuredDocuments:
    """Test processing of large structured documents with complex formatting."""

    def test_comprehensive_specification_document(self):
        """Test processing of a large specification document with multiple sections."""
        source_id = "SPEC-DOC-001"
        spec_content = '''# Tokenizer Adapters Feature Specification

## 1. Executive Summary

This specification defines the requirements and design for implementing tokenizer adapters
that provide accurate token counting for different model providers to support reliable
chunking, cost estimation, and token budget management.

### 1.1 Background

Current limitations in token counting accuracy affect:
- Chunking reliability and consistency
- Cost estimation for API usage
- Token budget management across different models
- Integration with various model providers

### 1.2 Objectives

Primary objectives for this feature:
1. Accurate token counting across model providers
2. Reliable chunking with deterministic boundaries
3. Comprehensive error handling and fallback mechanisms
4. Extensible architecture for future model support

## 2. Requirements Analysis

### 2.1 Functional Requirements

#### 2.1.1 Tokenizer Adapter Interface
- Standard interface for token counting operations
- Support for model-specific max token limits
- Metadata about tokenization method and accuracy
- Graceful handling of unsupported models

#### 2.1.2 Adapter Implementations
- **Heuristic Adapter**: Fast approximation using character ratios
- **TikToken Adapter**: OpenAI's exact tokenizer for GPT models
- **HuggingFace Adapter**: Support for transformer models
- **Extensible Framework**: Easy addition of new adapters

#### 2.1.3 Integration Requirements
- Seamless integration with existing chunking pipeline
- Backward compatibility with current implementations
- Configuration-driven adapter selection
- Runtime adapter switching capabilities

### 2.2 Non-Functional Requirements

#### 2.2.1 Performance Requirements
- Tokenization: <100ms for 10KB documents
- Memory usage: Linear scaling with document size
- Startup time: <2s including dependency loading
- Concurrent processing: Support 100+ simultaneous requests

#### 2.2.2 Reliability Requirements
- Deterministic output for identical inputs
- Graceful error handling for malformed text
- Fallback mechanisms when dependencies unavailable
- 99.9% uptime for tokenization services

#### 2.2.3 Maintainability Requirements
- Modular architecture for easy extension
- Comprehensive logging and telemetry
- Clear separation of concerns
- Well-documented APIs and configuration

## 3. Technical Architecture

### 3.1 System Overview

The tokenizer adapter system consists of:
- **Adapter Registry**: Central registry for adapter management
- **Adapter Implementations**: Specific tokenizer implementations
- **Configuration System**: TOML-based configuration management
- **Error Handling**: Comprehensive error recovery mechanisms

### 3.2 Component Design

#### 3.2.1 TokenizerAdapter Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class TokenCount:
    count: int
    method: str
    tokenizer_id: str
    is_exact: bool
    model_max_tokens: Optional[int] = None

class TokenizerAdapter(ABC):
    @abstractmethod
    def count_tokens(self, text: str) -> TokenCount:
        pass
    
    @abstractmethod
    def get_max_tokens(self, model_name: str) -> int:
        pass
    
    @property
    @abstractmethod
    def adapter_id(self) -> str:
        pass
```

#### 3.2.2 Registry Architecture

```python
class TokenizerRegistry:
    def __init__(self):
        self._adapters = {}
        self._fallback_chain = ["tiktoken", "huggingface", "heuristic"]
    
    def register(self, name: str, adapter_class: type, **kwargs):
        self._adapters[name] = (adapter_class, kwargs)
    
    def resolve(self, adapter_name: Optional[str] = None) -> TokenizerAdapter:
        # Implementation with fallback logic
        pass
```

### 3.3 Data Flow

1. **Configuration Loading**: Load adapter preferences from config
2. **Adapter Resolution**: Resolve requested adapter with fallbacks
3. **Text Processing**: Process text through selected adapter
4. **Result Validation**: Validate token counts and metadata
5. **Error Handling**: Handle failures with graceful degradation

## 4. Implementation Plan

### 4.1 Phase 1: Core Infrastructure (Weeks 1-2)
- Implement base TokenizerAdapter interface
- Create TokenizerRegistry with fallback logic
- Add basic configuration system
- Implement heuristic adapter as baseline

### 4.2 Phase 2: Adapter Implementations (Weeks 3-4)
- Implement TikToken adapter with OpenAI integration
- Add HuggingFace adapter for transformer models
- Create comprehensive error handling system
- Add dependency management and graceful fallbacks

### 4.3 Phase 3: Integration and Testing (Weeks 5-6)
- Integrate adapters with chunking pipeline
- Implement comprehensive test suite
- Add performance benchmarks and optimization
- Create documentation and examples

### 4.4 Phase 4: Advanced Features (Weeks 7-8)
- Add configuration migration tools
- Implement telemetry and monitoring
- Create CLI tools for adapter management
- Add advanced error recovery mechanisms

## 5. Testing Strategy

### 5.1 Unit Testing
- Test each adapter implementation independently
- Mock external dependencies for reliable testing
- Test error conditions and edge cases
- Validate configuration parsing and validation

### 5.2 Integration Testing
- End-to-end document processing tests
- Multi-language text processing validation
- Token budget compliance verification
- Deterministic behavior validation

### 5.3 Performance Testing
- Tokenization performance across different text sizes
- Memory usage profiling for large documents
- Concurrent processing load testing
- Comparison benchmarks between adapter types

### 5.4 Property-Based Testing
- **Property 1**: Deterministic chunking for identical inputs
- **Property 2**: Token budget compliance across all adapters
- **Property 3**: Progress guarantee in chunking operations
- **Property 4**: Overlap consistency between adjacent chunks

## 6. Configuration Management

### 6.1 Configuration Format

```toml
[tokenizer]
adapter = "auto"
model = "text-embedding-3-small"
max_tokens = 8192
fallback_chain = ["tiktoken", "huggingface", "heuristic"]

[tokenizer.heuristic]
chars_per_token = 4.0

[tokenizer.tiktoken]
encoding = "cl100k_base"

[tokenizer.huggingface]
model_name = "sentence-transformers/all-MiniLM-L6-v2"
use_fast = true
trust_remote_code = false
```

### 6.2 Environment Overrides

```bash
export KANO_TOKENIZER_ADAPTER=heuristic
export KANO_TOKENIZER_MODEL=text-embedding-3-large
export KANO_TOKENIZER_MAX_TOKENS=8192
```

## 7. Error Handling and Recovery

### 7.1 Error Categories
- **Dependency Errors**: Missing optional packages
- **Configuration Errors**: Invalid settings or parameters
- **Runtime Errors**: Tokenization failures or timeouts
- **Resource Errors**: Memory or performance constraints

### 7.2 Recovery Strategies
- **Graceful Degradation**: Fall back to simpler adapters
- **Retry Logic**: Automatic retry with exponential backoff
- **Circuit Breaker**: Prevent cascade failures
- **User Notification**: Clear error messages and guidance

## 8. Monitoring and Observability

### 8.1 Metrics Collection
- Tokenization performance and accuracy
- Adapter usage statistics and success rates
- Error rates and failure patterns
- Resource utilization and capacity planning

### 8.2 Logging Strategy
- Structured logging with correlation IDs
- Performance metrics and timing data
- Error context and stack traces
- Configuration and environment information

## 9. Security Considerations

### 9.1 Input Validation
- Text sanitization and size limits
- Configuration parameter validation
- Dependency version checking
- Resource consumption monitoring

### 9.2 Data Privacy
- No persistent storage of processed text
- Anonymized telemetry and metrics
- Secure handling of API keys and credentials
- Compliance with data protection regulations

## 10. Documentation Requirements

### 10.1 User Documentation
- Getting started guide with examples
- Configuration reference and best practices
- Troubleshooting guide for common issues
- Performance tuning recommendations

### 10.2 Developer Documentation
- API reference with detailed examples
- Architecture overview and design decisions
- Extension guide for custom adapters
- Testing and debugging procedures

## 11. Success Criteria

### 11.1 Functional Success
- All tokenizer adapters work correctly with their backends
- Chunking produces deterministic, budget-compliant results
- Graceful fallback when optional dependencies unavailable
- Comprehensive test coverage (>90% for core functionality)

### 11.2 Performance Success
- Tokenization performance meets targets across all adapters
- Memory usage scales linearly with document size
- No significant performance regression from existing implementation
- Acceptable startup time with optional dependencies

### 11.3 Quality Success
- Token count accuracy within 5% of actual model tokenizers
- Zero budget overruns in production usage
- Clear error messages and diagnostic information
- Comprehensive documentation and examples

## Appendices

### Appendix A: Model Token Limits

| Model | Max Tokens | Encoding |
|-------|------------|----------|
| text-embedding-ada-002 | 8192 | cl100k_base |
| text-embedding-3-small | 8192 | cl100k_base |
| text-embedding-3-large | 8192 | cl100k_base |
| gpt-3.5-turbo | 4096 | cl100k_base |
| gpt-4 | 8192 | cl100k_base |
| gpt-4-turbo | 128000 | cl100k_base |

### Appendix B: Performance Benchmarks

Target performance metrics:
- 1KB document: <10ms tokenization
- 10KB document: <100ms tokenization
- 100KB document: <1s tokenization
- Memory usage: <2x document size
- Concurrent requests: 100+ simultaneous

### Appendix C: Error Code Reference

| Code | Description | Recovery Action |
|------|-------------|-----------------|
| TOK001 | Adapter not available | Try fallback adapter |
| TOK002 | Dependency missing | Install required package |
| TOK003 | Configuration invalid | Check config format |
| TOK004 | Tokenization failed | Retry with different adapter |
| TOK005 | Budget exceeded | Reduce chunk size |
'''
        
        options = ChunkingOptions(
            target_tokens=400,
            max_tokens=800,
            overlap_tokens=80,
            version="spec-v1",
            tokenizer_adapter="heuristic"
        )
        
        tokenizer = HeuristicTokenizer("spec-model", chars_per_token=4.0)
        
        chunks = chunk_text_with_tokenizer(source_id, spec_content, options, tokenizer)
        
        # Validate large document processing
        assert len(chunks) >= 8, "Large specification should produce many chunks"
        
        # Verify major sections are captured
        major_sections = [
            "## 1. Executive Summary",
            "## 2. Requirements Analysis", 
            "## 3. Technical Architecture",
            "## 4. Implementation Plan",
            "## 5. Testing Strategy"
        ]
        
        found_sections = set()
        for chunk in chunks:
            for section in major_sections:
                if section in chunk.text:
                    found_sections.add(section)
            
            # Verify token budget compliance
            token_count = tokenizer.count_tokens(chunk.text)
            assert token_count.count <= options.max_tokens, \
                f"Chunk exceeds budget: {token_count.count} > {options.max_tokens}"
            
            # Verify chunk quality
            assert len(chunk.text.strip()) > 50, "Chunks should have substantial content"
        
        # Should find most major sections
        assert len(found_sections) >= 3, f"Should find major sections, found: {found_sections}"
        
        # Verify overlap consistency
        overlap_errors = validate_overlap_consistency(chunks, options, tokenizer)
        assert not overlap_errors, f"Overlap validation errors: {overlap_errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
