"""Vector query operations for similarity search."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import time

from kano_backlog_core.config import ConfigLoader
from kano_backlog_core.embedding import resolve_embedder
from kano_backlog_core.tokenizer import resolve_model_max_tokens
from kano_backlog_core.vector import VectorQueryResult, get_backend

@dataclass
class SearchResult:
    """Result of a vector search query."""
    chunk_id: str
    text: str
    score: float
    source_id: str
    duration_ms: float

def search_similar(
    *,
    query_text: str,
    product: str,
    k: int = 10
) -> List[SearchResult]:
    """
    Search for similar chunks using vector similarity.
    
    Args:
        query_text: Text to search for
        product: Product name
        k: Number of results to return
        
    Returns:
        List of search results sorted by similarity score
    """
    t0 = time.perf_counter()
    
    # Load config
    ctx, effective = ConfigLoader.load_effective_config(
        Path("."),
        product=product
    )
    
    pc = ConfigLoader.validate_pipeline_config(effective)
    
    # Resolve embedding adapter
    embed_cfg = {
        "provider": pc.embedding.provider,
        "model": pc.embedding.model,
        "dimension": pc.embedding.dimension,
    }
    embedder = resolve_embedder(embed_cfg)
    
    # Embed query text
    query_embeddings = embedder.embed_batch([query_text])
    query_vector = query_embeddings[0].vector
    
    # Resolve vector backend
    vec_path = Path(pc.vector.path)
    if not vec_path.is_absolute():
        vec_path = ctx.product_root / vec_path
        
    embedding_space_id = (
        f"emb:{pc.embedding.provider}:{pc.embedding.model}:d{pc.embedding.dimension}"
        f"|tok:{pc.tokenizer.adapter}:{pc.tokenizer.model}:max{pc.tokenizer.max_tokens or resolve_model_max_tokens(pc.tokenizer.model)}"
        f"|chunk:{pc.chunking.version}"
        f"|metric:{pc.vector.metric}"
    )

    vec_cfg = {
        "backend": pc.vector.backend,
        "path": str(vec_path),
        "collection": pc.vector.collection,
        "embedding_space_id": embedding_space_id,
    }
    backend = get_backend(vec_cfg)
    backend.load()
    
    # Query for similar vectors
    results = backend.query(query_vector, k=k)
    
    duration = (time.perf_counter() - t0) * 1000
    
    # Convert to SearchResult
    search_results = []
    for r in results:
        source_id = r.metadata.get("source_id", "unknown")
        search_results.append(SearchResult(
            chunk_id=r.chunk_id,
            text=r.text or "",
            score=r.score,
            source_id=source_id,
            duration_ms=duration
        ))
    
    return search_results
