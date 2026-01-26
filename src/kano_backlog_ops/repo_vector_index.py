"""Vector indexing operations for repo corpus."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import time
import logging
import hashlib
import sqlite3

from kano_backlog_core.config import ConfigLoader, ConfigError
from kano_backlog_core.embedding import resolve_embedder
from kano_backlog_core.tokenizer import resolve_model_max_tokens, resolve_tokenizer
from kano_backlog_core.token_budget import enforce_token_budget
from kano_backlog_core.vector import VectorChunk, get_backend

from .init import _resolve_backlog_root

logger = logging.getLogger(__name__)


def _resolve_sqlite_vector_db_path(
    *,
    vec_path: Path,
    collection: str,
    embedding_space_id: Optional[str],
) -> Path:
    if embedding_space_id:
        digest = hashlib.sha256(embedding_space_id.encode("utf-8")).hexdigest()[:12]
        base_dir = vec_path.parent if vec_path.suffix else vec_path
        return base_dir / f"{collection}.{digest}.sqlite3"

    return vec_path if vec_path.suffix else vec_path / f"{collection}.sqlite3"


@dataclass
class RepoVectorIndexResult:
    files_processed: int
    chunks_generated: int
    chunks_indexed: int
    chunks_skipped: int
    chunks_pruned: int
    duration_ms: float
    backend_type: str


def build_repo_vector_index(
    *,
    project_root: Optional[Path] = None,
    backlog_root: Optional[Path] = None,
    force: bool = False,
    storage_format: str = "binary",
) -> RepoVectorIndexResult:
    """Build vector index for repo corpus."""
    t0 = time.perf_counter()
    
    if project_root is None:
        backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)
        project_root = backlog_root_path.parent.parent
    else:
        project_root = project_root.resolve()
    
    repo_chunks_db_path = project_root / ".cache" / "repo_chunks.sqlite3"
    if not repo_chunks_db_path.exists():
        raise FileNotFoundError(f"Repo chunks DB not found: {repo_chunks_db_path} (run chunks build-repo first)")
    
    try:
        if backlog_root is None:
            backlog_root_path, _ = _resolve_backlog_root(None, create_if_missing=False)
        else:
            backlog_root_path = backlog_root
        
        products_dir = backlog_root_path / "products"
        product_dirs = [p for p in products_dir.iterdir() if p.is_dir()] if products_dir.exists() else []
        
        if product_dirs:
            _, effective = ConfigLoader.load_effective_config(
                product_dirs[0],
                product=product_dirs[0].name,
            )
            pc = ConfigLoader.validate_pipeline_config(effective)
        else:
            raise ConfigError("No products found for config resolution")
    except (ConfigError, FileNotFoundError) as e:
        raise ConfigError(f"Cannot resolve pipeline config: {e}")
    
    tokenizer = resolve_tokenizer(pc.tokenizer.adapter, pc.tokenizer.model)
    
    embed_cfg = {
        "provider": pc.embedding.provider,
        "model": pc.embedding.model,
        "dimension": pc.embedding.dimension,
    }
    embedder = resolve_embedder(embed_cfg)
    
    vec_path = Path(pc.vector.path)
    if not vec_path.is_absolute():
        vec_path = project_root / ".cache" / "vectors"
    
    max_tokens = pc.tokenizer.max_tokens or resolve_model_max_tokens(pc.tokenizer.model)
    
    embedding_space_id = (
        f"corpus:repo"
        f"|emb:{pc.embedding.provider}:{pc.embedding.model}:d{pc.embedding.dimension}"
        f"|tok:{pc.tokenizer.adapter}:{pc.tokenizer.model}:max{max_tokens}"
        f"|chunk:{pc.chunking.version}"
        f"|metric:{pc.vector.metric}"
    )
    
    vec_cfg = {
        "backend": pc.vector.backend,
        "path": str(vec_path),
        "collection": "repo_chunks",
        "embedding_space_id": embedding_space_id,
        "storage_format": storage_format,
    }
    
    sqlite_vec_db_path: Optional[Path] = None
    existing_chunk_ids: set[str] = set()
    
    if pc.vector.backend == "sqlite":
        sqlite_vec_db_path = _resolve_sqlite_vector_db_path(
            vec_path=vec_path,
            collection="repo_chunks",
            embedding_space_id=embedding_space_id,
        )
        
        if sqlite_vec_db_path.exists() and force:
            sqlite_vec_db_path.unlink()
            logger.info(f"Removed existing vector DB: {sqlite_vec_db_path}")
        
        if sqlite_vec_db_path.exists():
            conn = sqlite3.connect(str(sqlite_vec_db_path))
            try:
                cur = conn.cursor()
                try:
                    rows = cur.execute("SELECT chunk_id FROM vectors").fetchall()
                    existing_chunk_ids = {row[0] for row in rows}
                    logger.info(f"Found {len(existing_chunk_ids)} existing vectors")
                except sqlite3.OperationalError:
                    # Table doesn't exist yet (first build or schema mismatch)
                    logger.info("No existing vectors table found, will create fresh")
            finally:
                conn.close()
    
    backend = get_backend(vec_cfg)
    backend.prepare(schema={}, dims=pc.embedding.dimension, metric=pc.vector.metric)
    
    conn = sqlite3.connect(str(repo_chunks_db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        rows = cur.execute(
            """
            SELECT c.chunk_id, c.parent_uid, c.content, i.path
            FROM chunks c
            JOIN items i ON i.uid = c.parent_uid
            ORDER BY c.parent_uid, c.chunk_index
            """
        ).fetchall()
        
        if not rows:
            return RepoVectorIndexResult(
                files_processed=0,
                chunks_generated=0,
                chunks_indexed=0,
                chunks_skipped=0,
                chunks_pruned=0,
                duration_ms=(time.perf_counter() - t0) * 1000,
                backend_type=pc.vector.backend,
            )
        
        chunks_to_index = []
        chunks_skipped = 0
        seen_file_uids = set()
        
        for chunk_id, parent_uid, content, file_path in rows:
            seen_file_uids.add(parent_uid)
            
            if not force and chunk_id in existing_chunk_ids:
                chunks_skipped += 1
                continue
            
            chunks_to_index.append((chunk_id, parent_uid, content, file_path))
        
        if not chunks_to_index:
            logger.info("No new chunks to index")
            return RepoVectorIndexResult(
                files_processed=len(seen_file_uids),
                chunks_generated=len(rows),
                chunks_indexed=0,
                chunks_skipped=chunks_skipped,
                chunks_pruned=0,
                duration_ms=(time.perf_counter() - t0) * 1000,
                backend_type=pc.vector.backend,
            )
        
        chunk_texts = []
        for chunk_id, parent_uid, content, file_path in chunks_to_index:
            budgeted = enforce_token_budget(
                content,
                tokenizer,
                max_tokens=max_tokens
            )
            chunk_texts.append(budgeted.content)
        
        embedding_results = embedder.embed_batch(chunk_texts)
        
        chunks_indexed = 0
        for (chunk_id, parent_uid, content, file_path), embedding_result in zip(chunks_to_index, embedding_results):
            vector_chunk = VectorChunk(
                chunk_id=chunk_id,
                text=content,
                metadata={
                    "source_id": parent_uid,
                    "file_path": file_path,
                    "corpus": "repo",
                    "embedding_provider": pc.embedding.provider,
                    "embedding_model": pc.embedding.model,
                    "embedding_dimension": pc.embedding.dimension,
                },
                vector=embedding_result.vector
            )
            
            backend.upsert(vector_chunk)
            chunks_indexed += 1
        
        backend.persist()
        
        chunks_pruned = 0
        if sqlite_vec_db_path and sqlite_vec_db_path.exists():
            current_chunk_ids = {chunk_id for chunk_id, _, _, _ in rows}
            stale_chunk_ids = existing_chunk_ids - current_chunk_ids
            
            if stale_chunk_ids:
                conn_vec = sqlite3.connect(str(sqlite_vec_db_path))
                try:
                    cur_vec = conn_vec.cursor()
                    for chunk_id in stale_chunk_ids:
                        cur_vec.execute("DELETE FROM vectors WHERE chunk_id = ?", (chunk_id,))
                        chunks_pruned += 1
                    conn_vec.commit()
                    logger.info(f"Pruned {chunks_pruned} stale vectors")
                finally:
                    conn_vec.close()
        
        duration_ms = (time.perf_counter() - t0) * 1000
        
        return RepoVectorIndexResult(
            files_processed=len(seen_file_uids),
            chunks_generated=len(rows),
            chunks_indexed=chunks_indexed,
            chunks_skipped=chunks_skipped,
            chunks_pruned=chunks_pruned,
            duration_ms=duration_ms,
            backend_type=pc.vector.backend,
        )
        
    finally:
        conn.close()
