"""Vector indexing operations for backlog items."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import time
import logging

from kano_backlog_core.config import ConfigLoader
from kano_backlog_core.canonical import CanonicalStore
from kano_backlog_core.chunking import chunk_text
from kano_backlog_core.tokenizer import resolve_model_max_tokens, resolve_tokenizer
from kano_backlog_core.token_budget import enforce_token_budget
from kano_backlog_core.embedding import resolve_embedder
from kano_backlog_core.vector import VectorChunk, get_backend

logger = logging.getLogger(__name__)

@dataclass
class VectorIndexResult:
    """Result of vector indexing operation."""
    items_processed: int
    chunks_generated: int
    chunks_indexed: int
    duration_ms: float
    backend_type: str

def build_vector_index(
    *,
    product: str,
    backlog_root: Optional[Path] = None,
    force: bool = False
) -> VectorIndexResult:
    """Build vector index for a product."""
    t0 = time.perf_counter()
    
    # Load config
    ctx, effective = ConfigLoader.load_effective_config(
        Path("."),
        product=product
    )
    
    pc = ConfigLoader.validate_pipeline_config(effective)
    
    # Resolve components
    tokenizer = resolve_tokenizer(pc.tokenizer.adapter, pc.tokenizer.model)
    
    embed_cfg = {
        "provider": pc.embedding.provider,
        "model": pc.embedding.model,
        "dimension": pc.embedding.dimension,
    }
    embedder = resolve_embedder(embed_cfg)
    
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
    backend.prepare(schema={}, dims=pc.embedding.dimension, metric=pc.vector.metric)
    
    # Process items
    store = CanonicalStore(ctx.product_root)
    items_processed = 0
    chunks_generated = 0
    chunks_indexed = 0
    
    current_batch = []
    BATCH_SIZE = 16
    
    def flush_batch():
        nonlocal current_batch, chunks_indexed
        if not current_batch:
            return
        texts = [c.text for c in current_batch]
        embeddings = embedder.embed_batch(texts)
        for i, res in enumerate(embeddings):
            chunk = current_batch[i]
            chunk.vector = res.vector
            backend.upsert(chunk)
            chunks_indexed += 1
        current_batch = []

    for path in store.list_items():
        try:
            item = store.read(path)
            items_processed += 1
            
            text_to_chunk = f"{item.title}"
            if item.body:
                text_to_chunk += f"\n\n{item.body}"
            
            raw_chunks = chunk_text(
                source_id=item.id,
                text=text_to_chunk,
                options=pc.chunking,
            )

            for rc in raw_chunks:
                max_tokens = pc.tokenizer.max_tokens or resolve_model_max_tokens(
                    pc.tokenizer.model
                )
                budget_res = enforce_token_budget(rc.text, tokenizer, max_tokens=max_tokens)

                vc = VectorChunk(
                    chunk_id=rc.chunk_id,
                    text=budget_res.content,
                    metadata={
                        "source_id": item.id,
                        "start_char": rc.start_char,
                        "end_char": rc.end_char,
                        "trimmed": budget_res.trimmed,
                        "token_count": budget_res.token_count.count,
                        "token_count_method": budget_res.token_count.method,
                        "tokenizer_id": budget_res.token_count.tokenizer_id,
                        "is_exact": budget_res.token_count.is_exact,
                        "target_budget": budget_res.target_budget,
                        "safety_margin": budget_res.safety_margin,
                        "max_tokens": max_tokens,
                    },
                )

                current_batch.append(vc)
                chunks_generated += 1

                if len(current_batch) >= BATCH_SIZE:
                    flush_batch()
                    
        except Exception as e:
            logger.warning(f"Failed to process {path}: {e}")
            continue

    flush_batch()
    backend.persist()
    
    duration = (time.perf_counter() - t0) * 1000
    return VectorIndexResult(
        items_processed=items_processed,
        chunks_generated=chunks_generated,
        chunks_indexed=chunks_indexed,
        duration_ms=duration,
        backend_type=pc.vector.backend
    )
