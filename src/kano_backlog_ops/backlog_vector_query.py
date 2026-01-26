"""Vector query operations for similarity search.

This module supports:
- Pure vector similarity search over the vector backend
- Hybrid search: FTS5 candidate retrieval from canonical chunks DB + vector rerank
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import time

from kano_backlog_core.config import ConfigLoader
from kano_backlog_core.embedding import resolve_embedder
from kano_backlog_core.tokenizer import resolve_model_max_tokens
from kano_backlog_core.vector import VectorQueryResult, get_backend

from .backlog_chunks_db import ChunkFtsCandidate, query_chunks_fts_candidates

@dataclass
class SearchResult:
    """Result of a vector search query."""
    chunk_id: str
    text: str
    score: float
    source_id: str
    duration_ms: float


@dataclass
class HybridSearchResult:
    chunk_id: str
    item_id: str
    item_title: str
    item_path: str
    section: Optional[str]
    snippet: str
    vector_score: float
    bm25_score: float
    duration_ms: float

def search_similar(
    *,
    query_text: str,
    product: str,
    k: int = 10,
    backlog_root: Optional[Path] = None
) -> List[SearchResult]:
    """
    Search for similar chunks using vector similarity.
    
    Args:
        query_text: Text to search for
        product: Product name
        k: Number of results to return
        backlog_root: Optional backlog root path
        
    Returns:
        List of search results sorted by similarity score
    """
    t0 = time.perf_counter()
    
    # Load config
    resource_path = backlog_root or Path(".")
    ctx, effective = ConfigLoader.load_effective_config(
        resource_path,
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


def search_hybrid(
    *,
    query_text: str,
    product: str,
    k: int = 10,
    fts_k: int = 200,
    snippet_tokens: int = 20,
    backlog_root: Optional[Path] = None,
) -> List[HybridSearchResult]:
    """Hybrid search: FTS candidate retrieval -> vector rerank.

    Args:
        query_text: Query text (also used as FTS MATCH string).
        product: Product name.
        k: Number of results to return.
        fts_k: Number of FTS candidates to consider.
        snippet_tokens: Token count for FTS snippet().
        backlog_root: Optional backlog root path.

    Returns:
        Ranked hybrid results.
    """

    t0 = time.perf_counter()

    resource_path = backlog_root or Path(".")
    ctx, effective = ConfigLoader.load_effective_config(resource_path, product=product)
    pc = ConfigLoader.validate_pipeline_config(effective)

    # FTS candidate retrieval from canonical chunks DB
    candidates = query_chunks_fts_candidates(
        product=product,
        backlog_root=ctx.backlog_root,
        query=query_text,
        k=fts_k,
        snippet_tokens=snippet_tokens,
    )
    if not candidates:
        return []

    candidate_by_chunk_id: Dict[str, ChunkFtsCandidate] = {
        str(c.chunk_id): c for c in candidates
    }
    candidate_chunk_ids = list(candidate_by_chunk_id.keys())

    # Embed query
    embed_cfg = {
        "provider": pc.embedding.provider,
        "model": pc.embedding.model,
        "dimension": pc.embedding.dimension,
    }
    embedder = resolve_embedder(embed_cfg)
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

    # Rerank within candidate set.
    vec_results: List[VectorQueryResult] = backend.query(
        query_vector,
        k=min(len(candidate_chunk_ids), int(fts_k)),
        filters={"chunk_ids": candidate_chunk_ids},
    )

    duration_ms = (time.perf_counter() - t0) * 1000

    merged: List[HybridSearchResult] = []
    for r in vec_results:
        cand = candidate_by_chunk_id.get(str(r.chunk_id))
        if not cand:
            continue
        merged.append(
            HybridSearchResult(
                chunk_id=str(r.chunk_id),
                item_id=str(cand.item_id),
                item_title=str(cand.item_title),
                item_path=str(cand.item_path),
                section=cand.section,
                snippet=str(cand.snippet),
                vector_score=float(r.score),
                bm25_score=float(cand.bm25_score),
                duration_ms=duration_ms,
            )
        )

    # Primary sort: vector score (desc). Tie-break: bm25 (asc).
    merged.sort(key=lambda x: (-x.vector_score, x.bm25_score))
    return merged[: int(k)]
