"""Vector query operations for repo corpus similarity search."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import time
import sqlite3

from kano_backlog_core.config import ConfigLoader, ConfigError
from kano_backlog_core.embedding import resolve_embedder
from kano_backlog_core.tokenizer import resolve_model_max_tokens
from kano_backlog_core.vector import get_backend

from .init import _resolve_backlog_root


@dataclass
class RepoHybridSearchResult:
    chunk_id: str
    file_path: str
    file_id: str
    section: Optional[str]
    snippet: str
    content: str
    vector_score: float
    bm25_score: float
    duration_ms: float


def search_repo_hybrid(
    *,
    query_text: str,
    project_root: Optional[Path] = None,
    backlog_root: Optional[Path] = None,
    k: int = 10,
    fts_candidates: int = 200,
) -> List[RepoHybridSearchResult]:
    """Hybrid search over repo corpus: FTS candidates + vector rerank."""
    t0 = time.perf_counter()
    
    if project_root is None:
        backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)
        project_root = backlog_root_path.parent.parent
    else:
        project_root = project_root.resolve()
    
    # Get project name from project root directory
    project_name = project_root.name
    
    backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)
    _, effective = ConfigLoader.load_effective_config(backlog_root_path, product=None)
    cache_dir = ConfigLoader.get_chunks_cache_root(backlog_root_path, effective)
    
    repo_chunks_db_path = cache_dir / f"repo.{project_name}.chunks.v1.db"
    if not repo_chunks_db_path.exists():
        raise FileNotFoundError(f"Repo chunks DB not found: {repo_chunks_db_path}")
    
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
    
    embed_cfg = {
        "provider": pc.embedding.provider,
        "model": pc.embedding.model,
        "dimension": pc.embedding.dimension,
    }
    embedder = resolve_embedder(embed_cfg)
    
    query_embeddings = embedder.embed_batch([query_text])
    query_vector = query_embeddings[0].vector
    
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
    }
    
    conn = sqlite3.connect(str(repo_chunks_db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        fts_rows = cur.execute(
            """
            SELECT
                i.id,
                i.path,
                c.chunk_id,
                c.parent_uid,
                c.section,
                c.content,
                bm25(chunks_fts) AS bm25_score,
                snippet(chunks_fts, 2, '<mark>', '</mark>', '...', 20) AS snippet
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            JOIN items i ON i.uid = c.parent_uid
            WHERE chunks_fts MATCH ?
            ORDER BY bm25_score ASC
            LIMIT ?
            """,
            (query_text, int(fts_candidates)),
        ).fetchall()
        
        if not fts_rows:
            return []
        
        candidate_chunk_ids = [row[2] for row in fts_rows]
        fts_data = {
            row[2]: {
                "file_id": row[0],
                "file_path": row[1],
                "parent_uid": row[3],
                "section": row[4],
                "content": row[5],
                "bm25_score": float(row[6]) if row[6] is not None else 0.0,
                "snippet": row[7] or "",
            }
            for row in fts_rows
        }
        
    finally:
        conn.close()
    
    backend = get_backend(vec_cfg)
    backend.load()
    
    vector_results = backend.query(
        query_vector,
        k=min(k, len(candidate_chunk_ids)),
        filters={"chunk_ids": candidate_chunk_ids},
    )
    
    duration_ms = (time.perf_counter() - t0) * 1000

    # If vectors are missing (or not built for this embedding space), fall back to
    # FTS-only ordering so repo search remains usable.
    if not vector_results:
        results = []
        for chunk_id in candidate_chunk_ids[: int(k)]:
            fts_info = fts_data.get(chunk_id)
            if not fts_info:
                continue
            results.append(
                RepoHybridSearchResult(
                    chunk_id=chunk_id,
                    file_path=fts_info["file_path"],
                    file_id=fts_info["file_id"],
                    section=fts_info["section"],
                    snippet=fts_info["snippet"],
                    content=fts_info["content"],
                    vector_score=0.0,
                    bm25_score=fts_info["bm25_score"],
                    duration_ms=duration_ms,
                )
            )
        return results
    
    results = []
    for vr in vector_results:
        fts_info = fts_data.get(vr.chunk_id)
        if not fts_info:
            continue
        
        results.append(
            RepoHybridSearchResult(
                chunk_id=vr.chunk_id,
                file_path=fts_info["file_path"],
                file_id=fts_info["file_id"],
                section=fts_info["section"],
                snippet=fts_info["snippet"],
                content=fts_info["content"],
                vector_score=vr.score,
                bm25_score=fts_info["bm25_score"],
                duration_ms=duration_ms,
            )
        )
    
    return results
