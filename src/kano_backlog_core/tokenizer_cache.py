"""Token count caching system for improved performance.

This module provides LRU caching for tokenization results to avoid repeated
expensive tokenization operations on the same text content.

Features:
- LRU cache with configurable size limits
- Cache invalidation strategies
- Performance metrics and monitoring
- Thread-safe operations
- Memory-efficient cache keys using text hashing
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple, Union
from collections import OrderedDict

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""
    
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_requests: int = 0
    cache_size: int = 0
    max_size: int = 0
    hit_rate: float = 0.0
    memory_usage_bytes: int = 0
    
    def update_hit_rate(self) -> None:
        """Update the hit rate based on current hits and total requests."""
        if self.total_requests > 0:
            self.hit_rate = self.hits / self.total_requests
        else:
            self.hit_rate = 0.0


@dataclass
class CacheEntry:
    """Cache entry containing tokenization result and metadata."""
    
    token_count: Any  # Will be TokenCount, but avoid circular import
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    text_length: int = 0
    
    def touch(self) -> None:
        """Update access timestamp and count."""
        self.timestamp = time.time()
        self.access_count += 1


class TokenCountCache:
    """Thread-safe LRU cache for token count results."""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: Optional[float] = None):
        """Initialize token count cache.
        
        Args:
            max_size: Maximum number of entries to cache
            ttl_seconds: Time-to-live for cache entries (None for no expiration)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats(max_size=max_size)
        
        logger.debug(f"Initialized TokenCountCache with max_size={max_size}, ttl={ttl_seconds}")
    
    def _generate_cache_key(self, text: str, adapter_id: str, model_name: str) -> str:
        """Generate a cache key for the given text and adapter configuration.
        
        Args:
            text: Input text to tokenize
            adapter_id: Tokenizer adapter identifier
            model_name: Model name
            
        Returns:
            Cache key string
        """
        # Use SHA-256 hash for memory efficiency with long texts
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
        return f"{adapter_id}:{model_name}:{text_hash}:{len(text)}"
    
    def get(self, text: str, adapter_id: str, model_name: str) -> Optional[Any]:
        """Get cached token count result.
        
        Args:
            text: Input text
            adapter_id: Tokenizer adapter identifier
            model_name: Model name
            
        Returns:
            Cached TokenCount if available, None otherwise
        """
        cache_key = self._generate_cache_key(text, adapter_id, model_name)
        
        with self._lock:
            self._stats.total_requests += 1
            
            if cache_key not in self._cache:
                self._stats.misses += 1
                self._stats.update_hit_rate()
                return None
            
            entry = self._cache[cache_key]
            
            # Check TTL expiration
            if self.ttl_seconds and (time.time() - entry.timestamp) > self.ttl_seconds:
                del self._cache[cache_key]
                self._stats.misses += 1
                self._stats.evictions += 1
                self._stats.cache_size = len(self._cache)
                self._stats.update_hit_rate()
                logger.debug(f"Cache entry expired for key: {cache_key}")
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(cache_key)
            entry.touch()
            
            self._stats.hits += 1
            self._stats.update_hit_rate()
            
            logger.debug(f"Cache hit for key: {cache_key}")
            return entry.token_count
    
    def put(self, text: str, adapter_id: str, model_name: str, token_count: Any) -> None:
        """Store token count result in cache.
        
        Args:
            text: Input text
            adapter_id: Tokenizer adapter identifier
            model_name: Model name
            token_count: TokenCount result to cache
        """
        cache_key = self._generate_cache_key(text, adapter_id, model_name)
        
        with self._lock:
            # Create cache entry
            entry = CacheEntry(
                token_count=token_count,
                text_length=len(text)
            )
            
            # Add to cache
            self._cache[cache_key] = entry
            
            # Enforce size limit (LRU eviction)
            while len(self._cache) > self.max_size:
                oldest_key, _ = self._cache.popitem(last=False)
                self._stats.evictions += 1
                logger.debug(f"Evicted cache entry: {oldest_key}")
            
            self._stats.cache_size = len(self._cache)
            logger.debug(f"Cached result for key: {cache_key}")
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            evicted_count = len(self._cache)
            self._cache.clear()
            self._stats.evictions += evicted_count
            self._stats.cache_size = 0
            logger.info(f"Cleared cache, evicted {evicted_count} entries")
    
    def get_stats(self) -> CacheStats:
        """Get current cache statistics.
        
        Returns:
            CacheStats object with current metrics
        """
        with self._lock:
            # Update memory usage estimate
            memory_usage = 0
            for entry in self._cache.values():
                # Rough estimate: TokenCount object + metadata
                memory_usage += (
                    len(entry.token_count.tokenizer_id) * 2 +  # Unicode string
                    len(entry.token_count.method) * 2 +
                    64 +  # Other fields and overhead
                    entry.text_length * 2  # Original text length estimate
                )
            
            self._stats.memory_usage_bytes = memory_usage
            self._stats.cache_size = len(self._cache)
            
            # Return a copy to avoid concurrent modification
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                total_requests=self._stats.total_requests,
                cache_size=self._stats.cache_size,
                max_size=self._stats.max_size,
                hit_rate=self._stats.hit_rate,
                memory_usage_bytes=self._stats.memory_usage_bytes
            )
    
    def resize(self, new_max_size: int) -> None:
        """Resize the cache to a new maximum size.
        
        Args:
            new_max_size: New maximum cache size
        """
        with self._lock:
            old_size = self.max_size
            self.max_size = new_max_size
            self._stats.max_size = new_max_size
            
            # Evict entries if new size is smaller
            while len(self._cache) > new_max_size:
                oldest_key, _ = self._cache.popitem(last=False)
                self._stats.evictions += 1
            
            self._stats.cache_size = len(self._cache)
            logger.info(f"Resized cache from {old_size} to {new_max_size}")
    
    def invalidate_adapter(self, adapter_id: str) -> int:
        """Invalidate all cache entries for a specific adapter.
        
        Args:
            adapter_id: Adapter identifier to invalidate
            
        Returns:
            Number of entries invalidated
        """
        with self._lock:
            keys_to_remove = [
                key for key in self._cache.keys() 
                if key.startswith(f"{adapter_id}:")
            ]
            
            for key in keys_to_remove:
                del self._cache[key]
                self._stats.evictions += 1
            
            self._stats.cache_size = len(self._cache)
            logger.info(f"Invalidated {len(keys_to_remove)} entries for adapter: {adapter_id}")
            return len(keys_to_remove)
    
    def invalidate_model(self, model_name: str) -> int:
        """Invalidate all cache entries for a specific model.
        
        Args:
            model_name: Model name to invalidate
            
        Returns:
            Number of entries invalidated
        """
        with self._lock:
            keys_to_remove = [
                key for key in self._cache.keys() 
                if f":{model_name}:" in key
            ]
            
            for key in keys_to_remove:
                del self._cache[key]
                self._stats.evictions += 1
            
            self._stats.cache_size = len(self._cache)
            logger.info(f"Invalidated {len(keys_to_remove)} entries for model: {model_name}")
            return len(keys_to_remove)


class CachingTokenizerAdapter:
    """Wrapper that adds caching to any tokenizer adapter."""
    
    def __init__(self, wrapped_adapter, cache: Optional[TokenCountCache] = None):
        """Initialize caching tokenizer adapter.
        
        Args:
            wrapped_adapter: The tokenizer adapter to wrap
            cache: Optional cache instance (creates default if None)
        """
        self._wrapped_adapter = wrapped_adapter
        self._cache = cache or TokenCountCache()
        
        logger.debug(f"Wrapped {wrapped_adapter.adapter_id} adapter with caching")
    
    @property
    def adapter_id(self) -> str:
        """Unique identifier for this adapter."""
        return f"cached_{self._wrapped_adapter.adapter_id}"
    
    @property
    def model_name(self) -> str:
        """Return the model name for this adapter."""
        return self._wrapped_adapter.model_name
    
    def count_tokens(self, text: str) -> Any:
        """Count tokens with caching support."""
        if not text:
            # Don't cache empty strings
            return self._wrapped_adapter.count_tokens(text)
        
        # Try cache first
        cached_result = self._cache.get(
            text, 
            self._wrapped_adapter.adapter_id, 
            self._wrapped_adapter.model_name
        )
        
        if cached_result is not None:
            return cached_result
        
        # Cache miss - compute and store result
        result = self._wrapped_adapter.count_tokens(text)
        
        # Only cache successful results
        if result.count >= 0:
            self._cache.put(
                text, 
                self._wrapped_adapter.adapter_id, 
                self._wrapped_adapter.model_name, 
                result
            )
        
        return result
    
    def max_tokens(self) -> int:
        """Return the max token budget for the model."""
        return self._wrapped_adapter.max_tokens()
    
    def get_cache_stats(self) -> CacheStats:
        """Get cache performance statistics."""
        return self._cache.get_stats()
    
    def clear_cache(self) -> None:
        """Clear the cache."""
        self._cache.clear()
    
    def __getattr__(self, name):
        """Delegate attribute access to wrapped adapter."""
        return getattr(self._wrapped_adapter, name)


# Global cache instance
_global_cache: Optional[TokenCountCache] = None
_cache_lock = threading.Lock()


def get_global_cache(max_size: int = 1000, ttl_seconds: Optional[float] = None) -> TokenCountCache:
    """Get or create the global token count cache.
    
    Args:
        max_size: Maximum cache size (only used for initial creation)
        ttl_seconds: Cache TTL (only used for initial creation)
        
    Returns:
        Global TokenCountCache instance
    """
    global _global_cache
    
    with _cache_lock:
        if _global_cache is None:
            _global_cache = TokenCountCache(max_size=max_size, ttl_seconds=ttl_seconds)
            logger.info(f"Created global token count cache with max_size={max_size}")
        
        return _global_cache


def clear_global_cache() -> None:
    """Clear the global cache."""
    global _global_cache
    
    with _cache_lock:
        if _global_cache is not None:
            _global_cache.clear()


def get_global_cache_stats() -> Optional[CacheStats]:
    """Get global cache statistics.
    
    Returns:
        CacheStats if global cache exists, None otherwise
    """
    global _global_cache
    
    with _cache_lock:
        if _global_cache is not None:
            return _global_cache.get_stats()
        return None