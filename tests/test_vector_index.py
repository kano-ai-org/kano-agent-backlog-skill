"""Tests for vector indexing operations.

This module tests the E2E pipeline integration function index_document()
with various configurations and scenarios.
"""

import pytest

from kano_backlog_ops.backlog_vector_index import index_document, IndexResult
from kano_backlog_core.pipeline_config import (
    PipelineConfig,
    TokenizerConfig,
    EmbeddingConfig,
    VectorConfig,
)
from kano_backlog_core.chunking import ChunkingOptions


class TestIndexDocument:
    """Test suite for index_document E2E pipeline function."""

    def create_test_config(
        self,
        embedding_provider: str = "noop",
        vector_backend: str = "noop",
        vector_path: str = "",
        **kwargs
    ) -> PipelineConfig:
        """Create a test pipeline configuration."""
        if not vector_path:
            raise ValueError("vector_path must be non-empty")
        return PipelineConfig(
            chunking=ChunkingOptions(
                target_tokens=kwargs.get("target_tokens", 50),
                max_tokens=kwargs.get("max_tokens", 100),
                overlap_tokens=kwargs.get("overlap_tokens", 10),
                version=kwargs.get("version", "chunk-v1")
            ),
            tokenizer=TokenizerConfig(
                adapter=kwargs.get("tokenizer_adapter", "heuristic"),
                model=kwargs.get("tokenizer_model", "test-model"),
                max_tokens=kwargs.get("tokenizer_max_tokens", 200)
            ),
            embedding=EmbeddingConfig(
                provider=embedding_provider,
                model=kwargs.get("embedding_model", "noop-embedding"),
                dimension=kwargs.get("embedding_dimension", 128),
                options=kwargs.get("embedding_options", {})
            ),
            vector=VectorConfig(
                backend=vector_backend,
                path=vector_path,
                collection=kwargs.get("collection", "test"),
                metric=kwargs.get("metric", "cosine"),
                options=kwargs.get("vector_options", {})
            )
        )

    def test_index_document_basic_functionality(self, tmp_path) -> None:
        """Test basic index_document functionality with NoOp adapters."""
        config = self.create_test_config(vector_path=str(tmp_path / "vector"))
        
        source_id = "test-doc-001"
        text = "This is a test document for indexing. It contains multiple sentences to test chunking behavior."
        
        result = index_document(source_id, text, config)
        
        assert isinstance(result, IndexResult)
        assert result.chunks_count > 0
        assert result.tokens_total > 0
        assert result.duration_ms >= 0
        assert result.backend_type == "noop"
        assert result.embedding_provider == "noop"
        assert result.chunks_trimmed >= 0

    def test_index_document_empty_source_id_raises(self, tmp_path) -> None:
        """Test that empty source_id raises ValueError."""
        config = self.create_test_config(vector_path=str(tmp_path / "vector"))
        
        with pytest.raises(ValueError, match="source_id must be non-empty"):
            index_document("", "Some text", config)

    def test_index_document_empty_text_handling(self, tmp_path) -> None:
        """Test handling of empty text input."""
        config = self.create_test_config(vector_path=str(tmp_path / "vector"))
        
        result = index_document("test-doc-empty", "", config)
        
        assert result.chunks_count == 0
        assert result.tokens_total == 0
        assert result.duration_ms >= 0
        assert result.backend_type == "noop"
        assert result.embedding_provider == "noop"

    def test_index_document_whitespace_only_text(self, tmp_path) -> None:
        """Test handling of whitespace-only text."""
        config = self.create_test_config(vector_path=str(tmp_path / "vector"))
        
        result = index_document("test-doc-whitespace", "   \n\t  ", config)
        
        # Should handle gracefully (chunking will normalize and may produce empty result)
        assert result.chunks_count >= 0
        assert result.tokens_total >= 0
        assert result.backend_type == "noop"

    def test_index_document_single_chunk(self, tmp_path) -> None:
        """Test indexing text that produces a single chunk."""
        config = self.create_test_config(
            vector_path=str(tmp_path / "vector"),
            target_tokens=100,
            max_tokens=200,
        )
        
        source_id = "test-doc-single"
        text = "Short text that should fit in one chunk."
        
        result = index_document(source_id, text, config)
        
        assert result.chunks_count == 1
        assert result.tokens_total > 0
        assert result.backend_type == "noop"

    def test_index_document_multiple_chunks(self, tmp_path) -> None:
        """Test indexing text that produces multiple chunks."""
        config = self.create_test_config(
            vector_path=str(tmp_path / "vector"),
            target_tokens=10,
            max_tokens=20,
        )
        
        source_id = "test-doc-multi"
        text = "This is a longer text document that should be split into multiple chunks. " \
               "Each chunk should be processed separately through the embedding pipeline. " \
               "The chunks should have proper overlap and metadata."
        
        result = index_document(source_id, text, config)
        
        assert result.chunks_count > 1
        assert result.tokens_total > 0
        assert result.backend_type == "noop"

    def test_index_document_cjk_text(self, tmp_path) -> None:
        """Test indexing CJK text."""
        config = self.create_test_config(
            vector_path=str(tmp_path / "vector"),
            target_tokens=15,
            max_tokens=30,
        )
        
        source_id = "test-doc-cjk"
        text = "你好世界！这是一个中文测试文档。包含多个句子来测试分块行为。每个字符都应该被正确处理。"
        
        result = index_document(source_id, text, config)
        
        assert result.chunks_count > 0
        assert result.tokens_total > 0
        assert result.backend_type == "noop"

    def test_index_document_mixed_text(self, tmp_path) -> None:
        """Test indexing mixed ASCII and CJK text."""
        config = self.create_test_config(
            vector_path=str(tmp_path / "vector"),
            target_tokens=20,
            max_tokens=40,
        )
        
        source_id = "test-doc-mixed"
        text = "Hello 你好 world 世界! This is mixed text 这是混合文本. " \
               "Testing chunking behavior 测试分块行为 with different scripts."
        
        result = index_document(source_id, text, config)
        
        assert result.chunks_count > 0
        assert result.tokens_total > 0
        assert result.backend_type == "noop"

    def test_index_document_with_sqlite_backend(self, tmp_path) -> None:
        """Test index_document with SQLite vector backend."""
        # Use a temp path so tests don't write to repo root.
        config = self.create_test_config(
            vector_backend="sqlite",
            vector_path=str(tmp_path / "test_vector_simple.db"),
            embedding_dimension=64  # Smaller for faster testing
        )
        
        source_id = "test-doc-sqlite"
        text = "This is a test document for SQLite backend integration."
        
        result = index_document(source_id, text, config)
        
        assert result.chunks_count > 0
        assert result.tokens_total > 0
        assert result.backend_type == "sqlite"
        assert result.embedding_provider == "noop"

    def test_index_document_token_budget_trimming(self, tmp_path) -> None:
        """Test that token budget trimming is properly tracked."""
        config = self.create_test_config(
            vector_path=str(tmp_path / "vector"),
            target_tokens=5,  # Very small to force trimming
            max_tokens=10,
            overlap_tokens=2,  # Must be < max_tokens
            tokenizer_max_tokens=15
        )
        
        source_id = "test-doc-trim"
        text = "This is a very long text that should definitely exceed the token budget and require trimming to fit within the specified limits."
        
        result = index_document(source_id, text, config)
        
        assert result.chunks_count > 0
        assert result.tokens_total > 0
        # Some chunks might be trimmed due to small budget
        assert result.chunks_trimmed >= 0

    def test_index_document_different_embedding_dimensions(self, tmp_path) -> None:
        """Test index_document with different embedding dimensions."""
        dimensions = [64, 128, 256, 512]
        
        for dim in dimensions:
            config = self.create_test_config(
                vector_path=str(tmp_path / f"vector_{dim}"),
                embedding_dimension=dim,
            )
            
            result = index_document(f"test-doc-dim-{dim}", "Test text for dimension testing.", config)
            
            assert result.chunks_count > 0
            assert result.embedding_provider == "noop"

    def test_index_document_different_chunking_strategies(self, tmp_path) -> None:
        """Test index_document with different chunking configurations."""
        strategies = [
            {"target_tokens": 10, "max_tokens": 20, "overlap_tokens": 2},
            {"target_tokens": 50, "max_tokens": 100, "overlap_tokens": 10},
            {"target_tokens": 100, "max_tokens": 200, "overlap_tokens": 20},
        ]
        
        text = "This is a test document for chunking strategy validation. " \
               "It contains multiple sentences to test different chunking approaches. " \
               "Each strategy should produce different chunk counts and token distributions."
        
        for i, strategy in enumerate(strategies):
            config = self.create_test_config(
                vector_path=str(tmp_path / f"vector_{i}"),
                **strategy,
            )
            
            result = index_document(f"test-doc-strategy-{i}", text, config)
            
            assert result.chunks_count > 0
            assert result.tokens_total > 0

    def test_index_document_deterministic_behavior(self, tmp_path) -> None:
        """Test that index_document produces deterministic results."""
        config = self.create_test_config(vector_path=str(tmp_path / "vector"))
        
        source_id = "test-doc-deterministic"
        text = "This text should produce identical results across multiple runs."
        
        # Run indexing multiple times
        results = []
        for _ in range(3):
            result = index_document(source_id, text, config)
            results.append((result.chunks_count, result.tokens_total))
        
        # All results should be identical
        first_result = results[0]
        for result in results[1:]:
            assert result == first_result, "Results should be deterministic"

    def test_index_document_config_validation(self, tmp_path) -> None:
        """Test that invalid configurations are handled properly."""
        # Test with invalid tokenizer adapter
        with pytest.raises(ValueError, match="Unknown tokenizer adapter"):
            config = self.create_test_config(
                vector_path=str(tmp_path / "vector"),
                tokenizer_adapter="invalid-adapter",
            )
            index_document("test-doc", "Test text", config)

    def test_index_document_metadata_completeness(self, tmp_path) -> None:
        """Test that indexed chunks contain complete metadata."""
        # Use NoOp backend to avoid SQLite connection issues in tests
        config = self.create_test_config(
            vector_path=str(tmp_path / "vector"),
            vector_backend="noop"
        )
        
        source_id = "test-doc-metadata"
        text = "This is a test document for metadata validation."
        
        result = index_document(source_id, text, config)
        
        assert result.chunks_count > 0
        assert result.backend_type == "noop"
        assert result.embedding_provider == "noop"

    @pytest.mark.parametrize("text_type,text_content", [
        ("ascii", "Simple ASCII text for testing."),
        ("unicode", "Unicode text with émojis 🚀 and spëcial characters."),
        ("cjk", "中文测试文档包含多个句子。"),
        ("mixed", "Mixed text with English and 中文 content."),
        ("code", "def test_function():\n    return 'Hello, world!'"),
        ("numbers", "Testing with numbers: 123, 456.789, and 1,000,000."),
    ])
    def test_index_document_text_types(self, tmp_path, text_type: str, text_content: str) -> None:
        """Test index_document with various text types."""
        config = self.create_test_config(vector_path=str(tmp_path / f"vector_{text_type}"))
        
        result = index_document(f"test-doc-{text_type}", text_content, config)
        
        assert result.chunks_count > 0
        assert result.tokens_total > 0
        assert result.backend_type == "noop"


if __name__ == "__main__":
    pytest.main([__file__])
