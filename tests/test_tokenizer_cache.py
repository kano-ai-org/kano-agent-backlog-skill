"""Tests for token count caching functionality."""

import pytest
import time
from unittest.mock import Mock, patch

# Import TokenCount from the main tokenizer module to avoid circular imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kano_backlog_core.tokenizer import TokenCount
from kano_backlog_core.tokenizer_cache import (
    TokenCountCache,
    CachingTokenizerAdapter,
    CacheStats,
    get_global_cache,
    clear_global_cache
)


class TestTokenCountCache:
    """Test cases for TokenCountCache."""
    
    def test_cache_initialization(self):
        """Test cache initialization with default parameters."""
        cache = TokenCountCache()
        
        assert cache.max_size == 1000
        assert cache.ttl_seconds is None
        
        stats = cache.get_stats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.cache_size == 0
        assert stats.max_size == 1000
    
    def test_cache_initialization_with_params(self):
        """Test cache initialization with custom parameters."""
        cache = TokenCountCache(max_size=500, ttl_seconds=3600)
        
        assert cache.max_size == 500
        assert cache.ttl_seconds == 3600
        
        stats = cache.get_stats()
        assert stats.max_size == 500
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        cache = TokenCountCache()
        
        key1 = cache._generate_cache_key("hello world", "heuristic", "test-model")
        key2 = cache._generate_cache_key("hello world", "heuristic", "test-model")
        key3 = cache._generate_cache_key("hello world", "tiktoken", "test-model")
        key4 = cache._generate_cache_key("different text", "heuristic", "test-model")
        
        # Same inputs should generate same key
        assert key1 == key2
        
        # Different adapter should generate different key
        assert key1 != key3
        
        # Different text should generate different key
        assert key1 != key4
    
    def test_cache_put_and_get(self):
        """Test basic cache put and get operations."""
        cache = TokenCountCache()
        
        token_count = TokenCount(
            count=10,
            method="heuristic",
            tokenizer_id="test",
            is_exact=False
        )
        
        # Cache miss initially
        result = cache.get("hello world", "heuristic", "test-model")
        assert result is None
        
        stats = cache.get_stats()
        assert stats.misses == 1
        assert stats.hits == 0
        
        # Put in cache
        cache.put("hello world", "heuristic", "test-model", token_count)
        
        # Cache hit now
        result = cache.get("hello world", "heuristic", "test-model")
        assert result is not None
        assert result.count == 10
        assert result.method == "heuristic"
        
        stats = cache.get_stats()
        assert stats.hits == 1
        assert stats.misses == 1
        assert stats.cache_size == 1
    
    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = TokenCountCache(max_size=2)
        
        token_count1 = TokenCount(count=10, method="test", tokenizer_id="test1", is_exact=False)
        token_count2 = TokenCount(count=20, method="test", tokenizer_id="test2", is_exact=False)
        token_count3 = TokenCount(count=30, method="test", tokenizer_id="test3", is_exact=False)
        
        # Fill cache to capacity
        cache.put("text1", "adapter", "model", token_count1)
        cache.put("text2", "adapter", "model", token_count2)
        
        assert cache.get_stats().cache_size == 2
        
        # Add third item, should evict first
        cache.put("text3", "adapter", "model", token_count3)
        
        stats = cache.get_stats()
        assert stats.cache_size == 2
        assert stats.evictions == 1
        
        # First item should be evicted
        assert cache.get("text1", "adapter", "model") is None
        assert cache.get("text2", "adapter", "model") is not None
        assert cache.get("text3", "adapter", "model") is not None
    
    def test_cache_ttl_expiration(self):
        """Test TTL-based cache expiration."""
        cache = TokenCountCache(ttl_seconds=0.1)  # 100ms TTL
        
        token_count = TokenCount(count=10, method="test", tokenizer_id="test", is_exact=False)
        
        # Put in cache
        cache.put("hello", "adapter", "model", token_count)
        
        # Should be available immediately
        result = cache.get("hello", "adapter", "model")
        assert result is not None
        
        # Wait for expiration
        time.sleep(0.15)
        
        # Should be expired now
        result = cache.get("hello", "adapter", "model")
        assert result is None
        
        stats = cache.get_stats()
        assert stats.evictions == 1
    
    def test_cache_clear(self):
        """Test cache clearing."""
        cache = TokenCountCache()
        
        token_count = TokenCount(count=10, method="test", tokenizer_id="test", is_exact=False)
        
        # Add some entries
        cache.put("text1", "adapter", "model", token_count)
        cache.put("text2", "adapter", "model", token_count)
        
        assert cache.get_stats().cache_size == 2
        
        # Clear cache
        cache.clear()
        
        stats = cache.get_stats()
        assert stats.cache_size == 0
        assert stats.evictions == 2
    
    def test_cache_resize(self):
        """Test cache resizing."""
        cache = TokenCountCache(max_size=3)
        
        token_count = TokenCount(count=10, method="test", tokenizer_id="test", is_exact=False)
        
        # Fill cache
        cache.put("text1", "adapter", "model", token_count)
        cache.put("text2", "adapter", "model", token_count)
        cache.put("text3", "adapter", "model", token_count)
        
        assert cache.get_stats().cache_size == 3
        
        # Resize to smaller
        cache.resize(2)
        
        stats = cache.get_stats()
        assert stats.cache_size == 2
        assert stats.max_size == 2
        assert stats.evictions == 1
    
    def test_cache_invalidate_adapter(self):
        """Test invalidating cache entries by adapter."""
        cache = TokenCountCache()
        
        token_count = TokenCount(count=10, method="test", tokenizer_id="test", is_exact=False)
        
        # Add entries for different adapters
        cache.put("text1", "adapter1", "model", token_count)
        cache.put("text2", "adapter2", "model", token_count)
        cache.put("text3", "adapter1", "model", token_count)
        
        assert cache.get_stats().cache_size == 3
        
        # Invalidate adapter1 entries
        invalidated = cache.invalidate_adapter("adapter1")
        
        assert invalidated == 2
        assert cache.get_stats().cache_size == 1
        
        # Only adapter2 entry should remain
        assert cache.get("text1", "adapter1", "model") is None
        assert cache.get("text2", "adapter2", "model") is not None
        assert cache.get("text3", "adapter1", "model") is None


class TestCachingTokenizerAdapter:
    """Test cases for CachingTokenizerAdapter."""
    
    def test_caching_adapter_initialization(self):
        """Test caching adapter initialization."""
        mock_adapter = Mock()
        mock_adapter.adapter_id = "test"
        mock_adapter.model_name = "test-model"
        
        cache = TokenCountCache()
        caching_adapter = CachingTokenizerAdapter(mock_adapter, cache)
        
        assert caching_adapter.adapter_id == "cached_test"
        assert caching_adapter.model_name == "test-model"
    
    def test_caching_adapter_count_tokens_cache_miss(self):
        """Test token counting with cache miss."""
        mock_adapter = Mock()
        mock_adapter.adapter_id = "test"
        mock_adapter.model_name = "test-model"
        
        token_count = TokenCount(count=10, method="test", tokenizer_id="test", is_exact=False)
        mock_adapter.count_tokens.return_value = token_count
        
        cache = TokenCountCache()
        caching_adapter = CachingTokenizerAdapter(mock_adapter, cache)
        
        # First call should be cache miss
        result = caching_adapter.count_tokens("hello world")
        
        assert result.count == 10
        mock_adapter.count_tokens.assert_called_once_with("hello world")
        
        stats = caching_adapter.get_cache_stats()
        assert stats.misses == 1
        assert stats.hits == 0
        assert stats.cache_size == 1
    
    def test_caching_adapter_count_tokens_cache_hit(self):
        """Test token counting with cache hit."""
        mock_adapter = Mock()
        mock_adapter.adapter_id = "test"
        mock_adapter.model_name = "test-model"
        
        token_count = TokenCount(count=10, method="test", tokenizer_id="test", is_exact=False)
        mock_adapter.count_tokens.return_value = token_count
        
        cache = TokenCountCache()
        caching_adapter = CachingTokenizerAdapter(mock_adapter, cache)
        
        # First call - cache miss
        result1 = caching_adapter.count_tokens("hello world")
        assert result1.count == 10
        
        # Second call - cache hit
        result2 = caching_adapter.count_tokens("hello world")
        assert result2.count == 10
        
        # Mock should only be called once
        mock_adapter.count_tokens.assert_called_once_with("hello world")
        
        stats = caching_adapter.get_cache_stats()
        assert stats.hits == 1
        assert stats.misses == 1
        assert stats.cache_size == 1
    
    def test_caching_adapter_empty_text_not_cached(self):
        """Test that empty text is not cached."""
        mock_adapter = Mock()
        mock_adapter.adapter_id = "test"
        mock_adapter.model_name = "test-model"
        
        token_count = TokenCount(count=0, method="test", tokenizer_id="test", is_exact=False)
        mock_adapter.count_tokens.return_value = token_count
        
        cache = TokenCountCache()
        caching_adapter = CachingTokenizerAdapter(mock_adapter, cache)
        
        # Call with empty text
        result = caching_adapter.count_tokens("")
        
        assert result.count == 0
        mock_adapter.count_tokens.assert_called_once_with("")
        
        # Cache should be empty
        stats = caching_adapter.get_cache_stats()
        assert stats.cache_size == 0
    
    def test_caching_adapter_negative_count_not_cached(self):
        """Test that negative token counts are not cached."""
        mock_adapter = Mock()
        mock_adapter.adapter_id = "test"
        mock_adapter.model_name = "test-model"
        
        token_count = TokenCount(count=-1, method="test", tokenizer_id="test", is_exact=False)
        mock_adapter.count_tokens.return_value = token_count
        
        cache = TokenCountCache()
        caching_adapter = CachingTokenizerAdapter(mock_adapter, cache)
        
        # Call with text that returns negative count
        result = caching_adapter.count_tokens("error text")
        
        assert result.count == -1
        
        # Cache should be empty
        stats = caching_adapter.get_cache_stats()
        assert stats.cache_size == 0


class TestGlobalCache:
    """Test cases for global cache functionality."""
    
    def test_get_global_cache(self):
        """Test getting global cache instance."""
        # Clear any existing global cache
        clear_global_cache()
        
        cache1 = get_global_cache(max_size=500)
        cache2 = get_global_cache(max_size=1000)  # Should be ignored
        
        # Should return same instance
        assert cache1 is cache2
        assert cache1.max_size == 500  # First call parameters used
    
    def test_clear_global_cache(self):
        """Test clearing global cache."""
        cache = get_global_cache()
        
        token_count = TokenCount(count=10, method="test", tokenizer_id="test", is_exact=False)
        cache.put("test", "adapter", "model", token_count)
        
        assert cache.get_stats().cache_size == 1
        
        clear_global_cache()
        
        assert cache.get_stats().cache_size == 0


if __name__ == "__main__":
    pytest.main([__file__])