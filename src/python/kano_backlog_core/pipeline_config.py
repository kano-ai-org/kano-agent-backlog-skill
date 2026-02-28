from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .chunking import ChunkingOptions
from .tokenizer import resolve_tokenizer, get_default_registry, DEFAULT_MAX_TOKENS
from .tokenizer_config import TokenizerConfig as ComprehensiveTokenizerConfig, load_tokenizer_config
from .embedding import resolve_embedder

@dataclass
class TokenizerConfig:
    """Legacy tokenizer configuration for backward compatibility.
    
    This class is maintained for backward compatibility with existing code.
    New code should use the comprehensive TokenizerConfig from tokenizer_config module.
    """
    adapter: str = "auto"  # Changed default to "auto" for fallback chain
    model: str = "text-embedding-3-small"
    max_tokens: Optional[int] = None
    fallback_chain: Optional[List[str]] = None  # Optional custom fallback chain
    options: Dict[str, Any] = field(default_factory=dict)  # Adapter-specific options
    
    def to_comprehensive_config(self) -> ComprehensiveTokenizerConfig:
        """Convert to comprehensive tokenizer configuration."""
        config_dict = {
            "adapter": self.adapter,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "options": self.options
        }
        
        if self.fallback_chain:
            config_dict["fallback_chain"] = self.fallback_chain
        
        return load_tokenizer_config(config_dict=config_dict)

@dataclass
class EmbeddingConfig:
    provider: str = "noop"
    model: str = "noop-embedding"
    dimension: int = 1536
    options: Dict[str, Any] = field(default_factory=dict)

@dataclass
class VectorConfig:
    enabled: bool = False
    backend: str = "sqlite"
    collection: str = "backlog"
    metric: str = "cosine"
    options: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PipelineConfig:
    chunking: ChunkingOptions
    tokenizer: TokenizerConfig
    embedding: EmbeddingConfig
    vector: VectorConfig

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        """Parse and validate pipeline config from raw dictionary."""
        
        # Chunking
        c_data = data.get("chunking", {})
        chunking = ChunkingOptions(
            target_tokens=c_data.get("target_tokens", 256),
            max_tokens=c_data.get("max_tokens", 512),
            overlap_tokens=c_data.get("overlap_tokens", 32),
            version=c_data.get("version", "chunk-v1"),
            tokenizer_adapter=c_data.get("tokenizer_adapter", "auto")
        )

        # Tokenizer
        t_data = data.get("tokenizer", {})
        tokenizer = TokenizerConfig(
            adapter=t_data.get("adapter", "auto"),
            model=t_data.get("model", "text-embedding-3-small"),
            max_tokens=t_data.get("max_tokens"),
            fallback_chain=t_data.get("fallback_chain"),
            options=t_data.get("options", {})
        )

        # Embedding
        e_data = data.get("embedding", {})
        embedding = EmbeddingConfig(
            provider=e_data.get("provider", "noop"),
            model=e_data.get("model", "noop-embedding"),
            dimension=e_data.get("dimension", 1536),
            options=e_data.get("options", {})
        )

        # Vector
        v_data = data.get("vector", {})
        vector = VectorConfig(
            enabled=v_data.get("enabled", False),
            backend=v_data.get("backend", "sqlite"),
            collection=v_data.get("collection", "backlog"),
            metric=v_data.get("metric", "cosine"),
            options=v_data.get("options", {})
        )

        return cls(
            chunking=chunking,
            tokenizer=tokenizer,
            embedding=embedding,
            vector=vector
        )

    def validate(self) -> None:
        """Validate configuration consistency."""
        # 1. Try to resolve tokenizer to ensure adapter exists
        try:
            # Use comprehensive configuration for validation
            comprehensive_config = self.tokenizer.to_comprehensive_config()
            comprehensive_config.validate()
            
            registry = get_default_registry()
            
            # Set custom fallback chain if provided
            if comprehensive_config.fallback_chain:
                registry.set_fallback_chain(comprehensive_config.fallback_chain)
            
            # Try to resolve the tokenizer
            resolve_tokenizer(
                comprehensive_config.adapter, 
                comprehensive_config.model,
                max_tokens=comprehensive_config.max_tokens,
                registry=registry
            )
        except Exception as e:
            raise ValueError(f"Invalid tokenizer config: {e}")

        # 2. Try to resolve embedder (basic connection check logic could go here, 
        # but factory just checks module existence/config usually)
        # We simulate the config dict that factory expects
        e_config = {
            "provider": self.embedding.provider,
            "model": self.embedding.model,
            "dimension": self.embedding.dimension,
            **self.embedding.options,
        }
        try:
            resolve_embedder(e_config)
        except Exception as e:
            raise ValueError(f"Invalid embedding config: {e}")
            
        # 3. Validation logic for Chunking vs Tokenizer budget?
        # Typically max_tokens of chunking should be <= model limit.
        # But we don't have the model object here easily without resolving.
        # Minimal check: overlap < max is already in ChunkingOptions post_init.
