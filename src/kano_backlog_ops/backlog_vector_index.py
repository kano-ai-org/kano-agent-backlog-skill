"""Vector indexing operations for backlog items."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import time
import logging
import hashlib
import sqlite3
import os

from kano_backlog_core.config import ConfigLoader
from kano_backlog_core.canonical import CanonicalStore
from kano_backlog_core.chunking import chunk_text, chunk_text_with_tokenizer, ChunkingOptions
from kano_backlog_core.tokenizer import resolve_model_max_tokens, resolve_tokenizer
from kano_backlog_core.token_budget import enforce_token_budget, budget_chunks
from kano_backlog_core.embedding import resolve_embedder
from kano_backlog_core.vector import VectorChunk, get_backend
from kano_backlog_core.vector.sqlite_backend import SQLiteVectorBackend
from kano_backlog_core.pipeline_config import PipelineConfig

logger = logging.getLogger(__name__)


def _resolve_sqlite_vector_db_path(
    *,
    vec_path: Path,
    collection: str,
    embedding_space_id: Optional[str],
    product: str,
) -> Path:
    # Keep naming consistent with kano_backlog_core.vector.sqlite_backend.SQLiteVectorBackend
    # so that `--force` can reliably delete the DB it will actually use.
    base_dir = vec_path.parent if vec_path.suffix else vec_path

    if embedding_space_id:
        components = {}
        for segment in embedding_space_id.split('|'):
            if ':' in segment:
                key, value = segment.split(':', 1)
                components[key] = value
        
        emb_parts = components.get('emb', '').split(':')
        if len(emb_parts) >= 3:
            emb_type = emb_parts[0]
            emb_dim = emb_parts[-1]
            emb_short = f"{emb_type}-{emb_dim}"
        else:
            emb_short = "unknown"
        
        digest = hashlib.sha256(embedding_space_id.encode("utf-8")).hexdigest()[:8]
        
        base_dir = vec_path.parent if vec_path.suffix else vec_path
        return base_dir / f"backlog.{product}.vectors.{emb_short}.{digest}.db"

    return vec_path if vec_path.suffix else vec_path / f"backlog.{product}.vectors.db"

        digest = hashlib.sha256(embedding_space_id.encode("utf-8")).hexdigest()[:8]
        return base_dir / f"vectors.{corpus}.{emb_short}.{digest}.db"

    # No embedding space isolation: fallback to a stable per-collection DB name.
    return vec_path if vec_path.suffix else base_dir / f"vectors.{collection}.db"


def _chunks_db_is_stale(*, product_root: Path, chunks_db_path: Path) -> bool:
    if not chunks_db_path.exists():
        return True

    try:
        db_mtime = chunks_db_path.stat().st_mtime
    except OSError:
        return True

    items_root = product_root / "items"
    if not items_root.exists():
        return False

    latest_item_mtime = db_mtime
    for p in items_root.rglob("*.md"):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > latest_item_mtime:
            latest_item_mtime = m

    return latest_item_mtime > db_mtime

@dataclass
class VectorIndexResult:
    """Result of vector indexing operation."""
    items_processed: int
    chunks_generated: int
    chunks_indexed: int
    duration_ms: float
    backend_type: str

@dataclass
class IndexResult:
    """Result of indexing a single document."""
    chunks_count: int
    tokens_total: int
    duration_ms: float
    backend_type: str
    embedding_provider: str
    chunks_trimmed: int = 0


def index_document(
    source_id: str,
    text: str,
    config: PipelineConfig,
    *,
    product_root: Optional[Path] = None
) -> IndexResult:
    """Index a single document through the complete embedding pipeline.
    
    Args:
        source_id: Unique identifier for the document
        text: Raw text content to index
        config: Pipeline configuration with chunking, tokenizer, embedding, vector settings
        product_root: Product root directory for resolving relative paths
        
    Returns:
        IndexResult with telemetry data
        
    Raises:
        ValueError: If source_id is empty or config is invalid
        Exception: If any pipeline component fails
    """
    if not source_id:
        raise ValueError("source_id must be non-empty")
    
    if not text:
        # Handle empty text gracefully
        return IndexResult(
            chunks_count=0,
            tokens_total=0,
            duration_ms=0.0,
            backend_type=config.vector.backend,
            embedding_provider=config.embedding.provider,
            chunks_trimmed=0
        )
    
    t0 = time.perf_counter()
    
    try:
        # 1. Resolve components from config
        tokenizer = resolve_tokenizer(config.tokenizer.adapter, config.tokenizer.model)
        
        embed_cfg = {
            "provider": config.embedding.provider,
            "model": config.embedding.model,
            "dimension": config.embedding.dimension,
            **config.embedding.options
        }
        embedder = resolve_embedder(embed_cfg)
        
        # Create embedding space ID for backend isolation
        max_tokens = config.tokenizer.max_tokens or resolve_model_max_tokens(config.tokenizer.model)
        embedding_space_id = (
            f"emb:{config.embedding.provider}:{config.embedding.model}:d{config.embedding.dimension}"
            f"|tok:{config.tokenizer.adapter}:{config.tokenizer.model}:max{max_tokens}"
            f"|chunk:{config.chunking.version}"
            f"|metric:{config.vector.metric}"
        )
        
        # Resolve vector path
        vec_path = Path(config.vector.path)
        if not vec_path.is_absolute() and product_root:
            vec_path = product_root / vec_path
        
        vec_cfg = {
            "backend": config.vector.backend,
            "path": str(vec_path),
            "collection": config.vector.collection,
            "embedding_space_id": embedding_space_id,
            **config.vector.options
        }
        backend = get_backend(vec_cfg)
        backend.prepare(schema={}, dims=config.embedding.dimension, metric=config.vector.metric)
        
        # 2. Chunk the text using enhanced chunking with tokenizer integration
        # Use the new chunk_text_with_tokenizer for better accuracy
        raw_chunks = chunk_text_with_tokenizer(
            source_id=source_id,
            text=text,
            options=config.chunking,
            tokenizer=tokenizer,
            model_name=config.tokenizer.model
        )
        
        if not raw_chunks:
            return IndexResult(
                chunks_count=0,
                tokens_total=0,
                duration_ms=(time.perf_counter() - t0) * 1000,
                backend_type=config.vector.backend,
                embedding_provider=config.embedding.provider,
                chunks_trimmed=0
            )
        
        # 3. Apply token budgeting to each chunk
        budgeted_chunks = []
        for chunk in raw_chunks:
            budgeted = enforce_token_budget(
                chunk.text,
                tokenizer,
                max_tokens=max_tokens
            )
            budgeted_chunks.append(budgeted)
        
        # 4. Prepare chunks for embedding
        chunk_texts = [budgeted.content for budgeted in budgeted_chunks]
        
        # 5. Generate embeddings
        embedding_results = embedder.embed_batch(chunk_texts)
        
        # 6. Create VectorChunk objects and upsert to backend
        chunks_indexed = 0
        tokens_total = 0
        chunks_trimmed = 0
        
        for i, (raw_chunk, budgeted, embedding_result) in enumerate(zip(raw_chunks, budgeted_chunks, embedding_results)):
            tokens_total += budgeted.token_count.count
            if budgeted.trimmed:
                chunks_trimmed += 1
                
            vector_chunk = VectorChunk(
                chunk_id=raw_chunk.chunk_id,
                text=budgeted.content,
                metadata={
                    "source_id": source_id,
                    "start_char": raw_chunk.start_char,
                    "end_char": raw_chunk.end_char,
                    "trimmed": budgeted.trimmed,
                    "token_count": budgeted.token_count.count,
                    "token_count_method": budgeted.token_count.method,
                    "tokenizer_id": budgeted.token_count.tokenizer_id,
                    "is_exact": budgeted.token_count.is_exact,
                    "target_budget": budgeted.target_budget,
                    "safety_margin": budgeted.safety_margin,
                    "embedding_provider": config.embedding.provider,
                    "embedding_model": config.embedding.model,
                    "embedding_dimension": config.embedding.dimension,
                    "chunking_method": "tokenizer_aware",  # New telemetry field
                    "tokenizer_adapter": config.chunking.tokenizer_adapter,  # New telemetry field
                },
                vector=embedding_result.vector
            )
            
            backend.upsert(vector_chunk)
            chunks_indexed += 1
        
        # 6. Persist changes
        backend.persist()
        
        duration_ms = (time.perf_counter() - t0) * 1000
        
        return IndexResult(
            chunks_count=chunks_indexed,
            tokens_total=tokens_total,
            duration_ms=duration_ms,
            backend_type=config.vector.backend,
            embedding_provider=config.embedding.provider,
            chunks_trimmed=chunks_trimmed
        )
        
    except Exception as e:
        logger.error(f"Failed to index document {source_id}: {e}")
        raise

def build_vector_index(
    *,
    product: str,
    backlog_root: Optional[Path] = None,
    force: bool = False,
    cache_root: Optional[Path] = None
) -> VectorIndexResult:
    """Build vector index for a product."""
    t0 = time.perf_counter()
    
    # Load config
    resource_path = backlog_root or Path(".")
    ctx, effective = ConfigLoader.load_effective_config(
        resource_path,
        product=product
    )
    
    pc = ConfigLoader.validate_pipeline_config(effective)
    
    if not pc.vector.enabled:
        logger.info(f"Vector generation disabled for product '{product}' (vector.enabled=false)")
        return VectorIndexResult(
            items_processed=0,
            chunks_generated=0,
            chunks_indexed=0,
            duration_ms=(time.perf_counter() - t0) * 1000,
            backend_type=pc.vector.backend
        )
    
    # Resolve components
    tokenizer = resolve_tokenizer(pc.tokenizer.adapter, pc.tokenizer.model)
    
    embed_cfg = {
        "provider": pc.embedding.provider,
        "model": pc.embedding.model,
        "dimension": pc.embedding.dimension,
        **pc.embedding.options,
    }
    embedder = resolve_embedder(embed_cfg)
    
    if cache_root:
        vec_path = Path(cache_root)
    else:
        vec_path = ConfigLoader.get_chunks_cache_root(ctx.backlog_root, effective)
        
    embedding_space_id = (
        f"corpus:backlog"
        f"|emb:{pc.embedding.provider}:{pc.embedding.model}:d{pc.embedding.dimension}"
        f"|tok:{pc.tokenizer.adapter}:{pc.tokenizer.model}:max{pc.tokenizer.max_tokens or resolve_model_max_tokens(pc.tokenizer.model)}"
        f"|chunk:{pc.chunking.version}"
        f"|metric:{pc.vector.metric}"
    )

    sqlite_vec_db_path: Optional[Path] = None
    if pc.vector.backend == "sqlite":
        sqlite_vec_db_path = _resolve_sqlite_vector_db_path(
            vec_path=vec_path,
            collection=pc.vector.collection,
            embedding_space_id=embedding_space_id,
            product=product,
        )

        if force and sqlite_vec_db_path.exists():
            sqlite_vec_db_path.unlink()
    
    vec_cfg = {
        "backend": pc.vector.backend,
        "path": str(sqlite_vec_db_path) if sqlite_vec_db_path else str(vec_path),
        "collection": pc.vector.collection,
        "embedding_space_id": embedding_space_id,
    }
    existing_chunk_ids: set[str] = set()

    backend = get_backend(vec_cfg)
    backend.prepare(schema={}, dims=pc.embedding.dimension, metric=pc.vector.metric)

    if isinstance(backend, SQLiteVectorBackend) and (not force):
        try:
            existing_chunk_ids = set(backend.list_chunk_ids())
        except Exception:
            existing_chunk_ids = set()

    # Ensure canonical chunks DB exists and is fresh (single chunk contract).
    if cache_root:
        cache_dir = Path(cache_root)
    else:
        real_backlog_root = ctx.project_root / "_kano" / "backlog"
        cache_dir = ConfigLoader.get_chunks_cache_root(real_backlog_root, effective)
    
    chunks_db_path = cache_dir / f"backlog.{product}.chunks.v1.db"
    if force or _chunks_db_is_stale(product_root=ctx.product_root, chunks_db_path=chunks_db_path):
        from kano_backlog_ops.backlog_chunks_db import build_chunks_db

        real_backlog_root = ctx.project_root / "_kano" / "backlog"
        build_chunks_db(product=product, backlog_root=real_backlog_root, force=True, cache_root=cache_root)

        # Use the project config that resolved ctx (important when the backlog data
        # lives in another repo and that repo's project config does not define this product).
        project_config_file = ctx.project_root / ".kano" / "backlog_config.toml"
        build_chunks_db(
            product=product,
            backlog_root=ops_backlog_root,
            force=True,
            cache_root=cache_root,
            custom_config_file=project_config_file if project_config_file.exists() else None,
        )

    if not chunks_db_path.exists():
        raise FileNotFoundError(f"Chunks DB not found: {chunks_db_path}")

    max_tokens = pc.tokenizer.max_tokens or resolve_model_max_tokens(pc.tokenizer.model)

    items_processed = 0
    chunks_generated = 0
    chunks_indexed = 0
    seen_parent_uids: set[str] = set()

    current_batch: list[VectorChunk] = []
    BATCH_SIZE = 16

    def flush_batch() -> None:
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

    conn = sqlite3.connect(str(chunks_db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.execute(
            """
            SELECT
                c.chunk_id,
                c.content,
                c.section,
                c.chunk_index,
                c.parent_uid,
                i.id,
                i.path
            FROM chunks c
            JOIN items i ON i.uid = c.parent_uid
            ORDER BY i.id, c.chunk_index
            """
        )

        canonical_chunk_ids: set[str] = set()

        for chunk_id, content, section, chunk_index, parent_uid, item_id, item_path in cursor:
            chunk_id_str = str(chunk_id)
            canonical_chunk_ids.add(chunk_id_str)

            if parent_uid not in seen_parent_uids:
                seen_parent_uids.add(parent_uid)
                items_processed += 1

            if not isinstance(content, str) or not content.strip():
                continue

            # Skip re-embedding when the vector DB already has this chunk_id.
            if existing_chunk_ids and chunk_id_str in existing_chunk_ids:
                continue

            budget_res = enforce_token_budget(content, tokenizer, max_tokens=max_tokens)

            vc = VectorChunk(
                chunk_id=chunk_id_str,
                text=budget_res.content,
                metadata={
                    # Primary UX fields
                    "source_id": str(item_id),
                    "product": product,
                    # Canonical alignment fields
                    "parent_uid": str(parent_uid),
                    "item_uid": str(parent_uid),
                    "item_path": str(item_path),
                    "section": str(section) if section is not None else None,
                    "chunk_index": int(chunk_index),
                    # Budget telemetry
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

        # Prune stale chunk rows (only for sqlite backend) so chunk_ids track the
        # canonical chunk contract.
        if isinstance(backend, SQLiteVectorBackend):
            backend.prune_to_chunk_ids(list(canonical_chunk_ids))

    finally:
        conn.close()

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
