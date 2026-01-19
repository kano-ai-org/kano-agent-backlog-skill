from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .chunking import ChunkingOptions
from .tokenizer import resolve_tokenizer, DEFAULT_MAX_TOKENS
from .embedding import resolve_embedder

@dataclass
class TokenizerConfig:
    adapter: str = "heuristic"
    model: str = "text-embedding-3-small"
    max_tokens: Optional[int] = None

@dataclass
class EmbeddingConfig:
    provider: str = "noop"
    model: str = "noop-embedding"
    dimension: int = 1536
    options: Dict[str, Any] = field(default_factory=dict)

@dataclass
class VectorConfig:
    backend: str = "noop"
    path: str = ".kano/vector"
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
            version=c_data.get("version", "chunk-v1")
        )

        # Tokenizer
        t_data = data.get("tokenizer", {})
        tokenizer = TokenizerConfig(
            adapter=t_data.get("adapter", "heuristic"),
            model=t_data.get("model", "text-embedding-3-small"),
            max_tokens=t_data.get("max_tokens")
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
            backend=v_data.get("backend", "noop"),
            path=v_data.get("path", ".kano/vector"),
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
            resolve_tokenizer(self.tokenizer.adapter, self.tokenizer.model)
        except Exception as e:
            raise ValueError(f"Invalid tokenizer config: {e}")

        # 2. Try to resolve embedder (basic connection check logic could go here, 
        # but factory just checks module existence/config usually)
        # We simulate the config dict that factory expects
        e_config = {
            "provider": self.embedding.provider,
            "model": self.embedding.model,
            "dimension": self.embedding.dimension,
            **self.embedding.options
        }
        try:
            resolve_embedder(e_config)
        except Exception as e:
            raise ValueError(f"Invalid embedding config: {e}")
            
        # 3. Validation logic for Chunking vs Tokenizer budget?
        # Typically max_tokens of chunking should be <= model limit.
        # But we don't have the model object here easily without resolving.
        # Minimal check: overlap < max is already in ChunkingOptions post_init.
