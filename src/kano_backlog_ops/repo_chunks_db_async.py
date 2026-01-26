"""repo_chunks_db_async.py - Async version of repo chunks DB builder with progress tracking.

This module provides an optimized, async version of the repo chunks DB builder that:
1. Uses ThreadPoolExecutor for parallel file processing
2. Implements batch writing to SQLite for better performance
3. Provides progress tracking via status file
4. Supports cancellation and resumption
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from uuid import uuid4

from kano_backlog_core.chunking import chunk_text_with_tokenizer, ChunkingOptions
from kano_backlog_core.config import ConfigError, ConfigLoader
from kano_backlog_core.schema import load_canonical_schema
from kano_backlog_core.tokenizer import resolve_tokenizer

from .init import _resolve_backlog_root
from .repo_chunks_db import (
    DEFAULT_INCLUDE_PATTERNS,
    DEFAULT_EXCLUDE_PATTERNS,
    RepoChunksDbBuildResult,
    _scan_repo_files,
    _map_file_to_item,
)

# Conditional import for UUIDv7
if sys.version_info >= (3, 12):
    from uuid import uuid7  # type: ignore
else:
    from uuid6 import uuid7  # type: ignore


@dataclass
class BuildProgress:
    """Progress tracking for repo chunks DB build."""
    task_id: str
    status: str  # running | completed | failed | cancelled
    total_files: int
    processed_files: int
    total_chunks: int
    start_time: str
    last_update: str
    current_file: Optional[str] = None
    error_message: Optional[str] = None
    
    @property
    def percentage(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100.0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> BuildProgress:
        return cls(**data)


def _get_status_file_path(project_root: Path) -> Path:
    """Get the path to the build status file."""
    cache_dir = project_root / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "repo_build_status.json"


def get_build_progress(project_root: Optional[Path] = None) -> Optional[BuildProgress]:
    """Get the current build progress status.
    
    Args:
        project_root: Project root directory
        
    Returns:
        BuildProgress if a build is in progress or recently completed, None otherwise
    """
    if project_root is None:
        backlog_root_path, _ = _resolve_backlog_root(None, create_if_missing=False)
        project_root = backlog_root_path.parent.parent
    else:
        project_root = project_root.resolve()
    
    status_file = _get_status_file_path(project_root)
    if not status_file.exists():
        return None
    
    try:
        data = json.loads(status_file.read_text(encoding="utf-8"))
        return BuildProgress.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _update_progress(
    status_file: Path,
    progress: BuildProgress,
) -> None:
    """Update the progress status file."""
    progress.last_update = datetime.now().isoformat()
    status_file.write_text(json.dumps(progress.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _process_file_batch(
    file_items: list[tuple[Path, float]],
    project_root: Path,
    chunking_options: ChunkingOptions,
    tokenizer,
    tokenizer_model: str,
) -> tuple[list[dict], list[dict]]:
    """Process a batch of files and return item rows and chunk rows.
    
    This function is designed to be called in parallel by ThreadPoolExecutor.
    """
    item_rows = []
    chunk_rows = []
    
    for file_path, mtime in file_items:
        try:
            item = _map_file_to_item(file_path, project_root, mtime)
            
            try:
                rel_path = file_path.relative_to(project_root).as_posix()
            except ValueError:
                rel_path = str(file_path)
            
            frontmatter_dict = {
                "uid": item.uid,
      "id": item.id,
                "type": item.type.value,
                "state": item.state.value,
                "title": item.title,
                "priority": item.priority,
                "parent": None,
                "parent_uid": None,
                "owner": item.owner,
                "area": item.area,
                "iteration": item.iteration,
                "tags": item.tags or [],
                "created": item.created,
                "updated": item.updated,
                "file_path": item.file_path,
                "file_ext": item.file_ext,
                "file_lang": item.file_lang,
            }
            
            item_rows.append({
                "uid": item.uid,
                "id": item.id,
                "type": item.type.value,
                "state": item.state.value,
                "title": item.title,
                "path": rel_path,
                "mtime": mtime,
                "content_hash": None,
                "frontmatter": json.dumps(frontmatter_dict, ensure_ascii=False),
                "created": item.created,
                "updated": item.updated,
                "priority": item.priority,
                "parent_uid": None,
                "owner": item.owner,
                "area": item.area,
                "iteration": item.iteration,
                "tags": json.dumps(item.tags or [], ensure_ascii=False),
            })
            
            content = getattr(item, "content", "")
            if content and content.strip():
                raw_chunks = chunk_text_with_tokenizer(
                    source_id=item.uid,
                    text=content,
                    options=chunking_options,
                    tokenizer=tokenizer,
                    model_name=tokenizer_model,
                )
                
                for chunk_index, rc in enumerate(raw_chunks):
                    chunk_content = rc.text.strip()
                    if chunk_content:
                        chunk_rows.append({
                            "chunk_id": rc.chunk_id,
                            "parent_uid": item.uid,
                            "chunk_index": chunk_index,
                            "content": chunk_content,
                            "section": "content",
                            "embedding": None,
                        })
        except Exception:
            # Skip files that fail to process
            continue
    
    return item_rows, chunk_rows


def build_repo_chunks_db_async(
    *,
    project_root: Optional[Path] = None,
    backlog_root: Optional[Path] = None,
    include_patterns: Optional[list[str]] = None,
    exclude_patterns: Optional[list[str]] = None,
    force: bool = False,
    max_workers: int = 4,
    batch_size: int = 50,
    progress_callback: Optional[Callable[[BuildProgress], None]] = None,
) -> RepoChunksDbBuildResult:
    """Build the repo corpus chunks DB with async processing and progress tracking.
    
    Args:
        project_root: Project root directory
        backlog_root: Backlog root directory
        include_patterns: File patterns to include
        exclude_patterns: File patterns to exclude
        force: Force rebuild if DB exists
        max_workers: Number of parallel workers (default: 4)
        batch_size: Number of files to process per batch (default: 50)
        progress_callback: Optional callback function to receive progress updates
        
    Returns:
        RepoChunksDbBuildResult with build statistics
    """
    t0 = time.perf_counter()
    
    # Resolve paths
    if project_root is None:
        backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)
        project_root = backlog_root_path.parent.parent
    else:
        project_root = project_root.resolve()
    
    if not project_root.exists():
        raise FileNotFoundError(f"Project root not found: {project_root}")
    
    if include_patterns is None:
        include_patterns = DEFAULT_INCLUDE_PATTERNS
    if exclude_patterns is None:
        exclude_patterns = DEFAULT_EXCLUDE_PATTERNS
    
    cache_dir = project_root / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / "repo_chunks.sqlite3"
    status_file = _get_status_file_path(project_root)
    
    if db_path.exists() and not force:
        raise FileExistsError(f"Repo chunks DB already exists: {db_path} (use force to rebuild)")
    
    if db_path.exists():
        db_path.unlink()
    
    # Load config
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
            chunking_options = pc.chunking
            tokenizer_model = pc.tokenizer.model
            tokenizer_adapter = pc.tokenizer.adapter
            tokenizer = resolve_tokenizer(pc.tokenizer.adapter, pc.tokenizer.model)
        else:
            raise ConfigError("No products found")
    except (ConfigError, FileNotFoundError):
        chunking_options = ChunkingOptions(tokenizer_adapter="heuristic")
        tokenizer_model = "default-model"
        tokenizer_adapter = "heuristic"
        tokenizer = resolve_tokenizer("heuristic", tokenizer_model)
    
    # Scan files
    file_items = _scan_repo_files(project_root, include_patterns, exclude_patterns)
    total_files = len(file_items)
    
    # Initialize progress tracking
    progress = BuildProgress(
        task_id=str(uuid4()),
        status="running",
        total_files=total_files,
        processed_files=0,
        total_chunks=0,
        start_time=datetime.now().isoformat(),
        last_update=datetime.now().isoformat(),
    )
    _update_progress(status_file, progress)
    
    if progress_callback:
        progress_callback(progress)
    
    # Initialize database
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        cur.executescript(load_canonical_schema())
        
        # Insert schema metadata
        cur.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("chunking_version", str(chunking_options.version)))
        cur.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("chunking_target_tokens", str(chunking_options.target_tokens)))
        cur.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("chunking_max_tokens", str(chunking_options.max_tokens)))
        cur.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("chunking_overlap_tokens", str(chunking_options.overlap_tokens)))
        cur.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("tokenizer_adapter", str(tokenizer_adapter)))
        cur.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("tokenizer_model", str(tokenizer_model)))
        cur.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)", ("corpus_type", "repo"))
        conn.commit()
        
        # Process files in parallel batches
        all_item_rows = []
        all_chunk_rows = []
        
        # Split files into batches
        batches = [file_items[i:i + batch_size] for i in range(0, len(file_items), batch_size)]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all batches
            future_to_batch = {
                executor.submit(
                    _process_file_batch,
                    batch,
                    project_root,
                    chunking_options,
                    tokenizer,
                    tokenizer_model,
                ): batch
                for batch in batches
            }
            
            # Process completed batches
            for future in as_completed(future_to_batch):
                batch = future_to_batch[future]
                try:
                    item_rows, chunk_rows = future.result()
                    
                    # Write to database immediately (batch write)
                    if item_rows:
                        cur.executemany(
                            """
                            INSERT INTO items (
                                uid, id, type, state, title, path, mtime, content_hash, frontmatter,
                                created, updated, priority, parent_uid, owner, area, iteration, tags
                            ) VALUES (
                                :uid, :id, :type, :state, :title, :path, :mtime, :content_hash, :frontmatter,
                                :created, :updated, :priority, :parent_uid, :owner, :area, :iteration, :tags
                            )
                            """,
                            item_rows,
                        )
                    
                    if chunk_rows:
                        cur.executemany(
                            """
                            INSERT INTO chunks (
                                chunk_id, parent_uid, chunk_index, content, section, embedding
                            ) VALUES (
                                :chunk_id, :parent_uid, :chunk_index, :content, :section, :embedding
                            )
                            """,
                            chunk_rows,
                        )
                    
                    conn.commit()
                    
                    all_item_rows.extend(item_rows)
                    all_chunk_rows.extend(chunk_rows)
                    progress.processed_files += len(batch)
                    progress.total_chunks = len(all_chunk_rows)
                    progress.current_file = batch[-1][0].name if batch else None
                    _update_progress(status_file, progress)
                    
                    if progress_callback:
                        progress_callback(progress)
                    
                except Exception as e:
                    progress.error_message = str(e)
                    _update_progress(status_file, progress)
                    continue
        
        progress.status = "completed"
        progress.current_file = None
        _update_progress(status_file, progress)
        
        if progress_callback:
            progress_callback(progress)
        
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return RepoChunksDbBuildResult(
            db_path=db_path,
            files_indexed=len(all_item_rows),
            chunks_indexed=len(all_chunk_rows),
            build_time_ms=elapsed_ms,
        )
    
    except Exception as e:
        progress.status = "failed"
        progress.error_message = str(e)
        _update_progress(status_file, progress)
        raise
    
    finally:
        conn.close()
