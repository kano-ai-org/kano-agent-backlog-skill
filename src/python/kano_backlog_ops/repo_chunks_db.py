"""repo_chunks_db.py - Repo corpus chunks SQLite DB (FTS5) operations.

This module builds a rebuildable workspace-level SQLite database that indexes
repository files (docs + code) using the canonical schema (ADR-0012).

Source of truth: workspace files (*.md, *.py, *.toml, *.json by default).
Excludes: .git, .cache, *.sqlite3, .env, node_modules, __pycache__, etc.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kano_backlog_core.chunking import chunk_text_with_tokenizer, ChunkingOptions
from kano_backlog_core.config import ConfigError, ConfigLoader
from kano_backlog_core.schema import load_canonical_schema
from kano_backlog_core.tokenizer import resolve_tokenizer

from .init import _resolve_backlog_root

# Conditional import for UUIDv7
if sys.version_info >= (3, 12):
    from uuid import uuid7  # type: ignore
else:
    from uuid6 import uuid7  # type: ignore


DEFAULT_INCLUDE_PATTERNS = [
    "*.md",
    "*.py",
    "*.toml",
    "*.json",
    "*.txt",
    "*.yaml",
    "*.yml",
]

DEFAULT_EXCLUDE_PATTERNS = [
    ".git",
    ".cache",
    "*.sqlite3",
    ".env",
    ".env.*",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "venv",
    ".venv",
    "dist",
    "build",
    "*.egg-info",
    ".DS_Store",
    "Thumbs.db",
]

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


@dataclass
class RepoChunksDbBuildResult:
    db_path: Path
    files_indexed: int
    chunks_indexed: int
    build_time_ms: float


@dataclass
class RepoChunkSearchRow:
    file_path: str
    file_id: str
    chunk_id: str
    parent_uid: str
    section: Optional[str]
    content: str
    score: float


def _should_exclude(path: Path, project_root: Path, exclude_patterns: list[str]) -> bool:
    """Check if path should be excluded based on patterns."""
    try:
        rel_path = path.relative_to(project_root)
    except ValueError:
        return True
    
    rel_str = rel_path.as_posix()
    
    for pattern in exclude_patterns:
        if "/" not in pattern and not pattern.startswith("*"):
            if pattern in rel_path.parts:
                return True
        elif path.match(pattern) or any(parent.match(pattern) for parent in path.parents):
            return True
        elif rel_str.startswith(pattern.rstrip("/")):
            return True
    
    return False


def _scan_repo_files(
    project_root: Path,
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> list[tuple[Path, float]]:
    """Scan workspace for files matching include patterns, excluding excluded paths."""
    results: list[tuple[Path, float]] = []
    
    for pattern in include_patterns:
        for file_path in project_root.rglob(pattern):
            if not file_path.is_file():
                continue
            
            if _should_exclude(file_path, project_root, exclude_patterns):
                continue
            
            try:
                size = os.path.getsize(file_path)
                if size > MAX_FILE_SIZE_BYTES or size == 0:
                    continue
            except OSError:
                continue
            
            try:
                mtime = os.stat(file_path).st_mtime
            except OSError:
                continue
            
            results.append((file_path, mtime))
    
    seen = set()
    unique_results = []
    for path, mtime in results:
        if path not in seen:
            seen.add(path)
            unique_results.append((path, mtime))
    
    return unique_results


def _map_file_to_item(file_path: Path, project_root: Path, mtime: float) -> object:
    """Map a file to a canonical item-like object."""
    try:
        rel_path = file_path.relative_to(project_root)
    except ValueError:
        rel_path = file_path
    
    file_id = f"FILE:{rel_path.as_posix()}"
    file_uid = str(uuid7())
    file_title = file_path.name
    file_ext = file_path.suffix.lstrip(".")
    
    lang_map = {
        "py": "python",
        "md": "markdown",
        "toml": "toml",
        "json": "json",
        "yaml": "yaml",
        "yml": "yaml",
        "txt": "text",
    }
    file_lang = lang_map.get(file_ext, file_ext)
    
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        content = ""
    
    class FileItem:
        def __init__(self):
            self.uid = file_uid
            self.id = file_id
            self.type = type("ItemType", (), {"value": "File"})()
            self.state = type("ItemState", (), {"value": "Active"})()
            self.title = file_title
            self.priority = "P3"
            self.parent = None
            self.owner = "system"
            self.area = "repo"
            self.iteration = "n/a"
            self.tags = [file_lang]
            self.created = ""
            self.updated = ""
            self.content = content
            self.file_path = rel_path.as_posix()
            self.file_ext = file_ext
            self.file_lang = file_lang
    
    return FileItem()


def build_repo_chunks_db(
    *,
    project_root: Optional[Path] = None,
    backlog_root: Optional[Path] = None,
    include_patterns: Optional[list[str]] = None,
    exclude_patterns: Optional[list[str]] = None,
    force: bool = False,
) -> RepoChunksDbBuildResult:
    """Build the repo corpus chunks DB for workspace files."""
    
    t0 = time.perf_counter()
    
    if project_root is None:
        if backlog_root is not None:
            project_root = backlog_root.resolve().parent.parent
        else:
            project_root = Path.cwd().resolve()
    else:
        project_root = project_root.resolve()
    
    if not project_root.exists():
        raise FileNotFoundError(f"Project root not found: {project_root}")
    
    if include_patterns is None:
        include_patterns = DEFAULT_INCLUDE_PATTERNS
    if exclude_patterns is None:
        exclude_patterns = DEFAULT_EXCLUDE_PATTERNS
    
    # Get project name from project root directory
    project_name = project_root.name
    
    def _resolve_repo_cache_dir() -> Path:
        """Resolve repo corpus cache directory.

        Repo corpus indexing should work even when the backlog is not initialized
        yet (or when no project config exists). We prefer project config
        `[shared.cache].root` when available, otherwise default to
        `<project_root>/.kano/cache/backlog`.
        """
        default_dir = project_root / ".kano" / "cache" / "backlog"
        try:
            from kano_backlog_core.project_config import ProjectConfigLoader

            project_cfg = ProjectConfigLoader.load_project_config_optional(project_root)
            shared = project_cfg.shared if project_cfg else None
            if isinstance(shared, dict):
                cache = shared.get("cache")
                if isinstance(cache, dict):
                    root = cache.get("root")
                    if isinstance(root, str) and root.strip():
                        candidate = Path(root.strip())
                        return (candidate if candidate.is_absolute() else (project_root / candidate)).resolve()
        except Exception:
            pass
        return default_dir

    cache_dir = _resolve_repo_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / f"repo.{project_name}.chunks.v1.db"
    
    if db_path.exists() and not force:
        raise FileExistsError(f"Repo chunks DB already exists: {db_path} (use force to rebuild)")
    
    if db_path.exists():
        db_path.unlink()
    
    try:
        backlog_root_path: Optional[Path] = None
        if backlog_root is not None:
            backlog_root_path = backlog_root.resolve()
        else:
            candidate = project_root / "_kano" / "backlog"
            if candidate.exists():
                backlog_root_path = candidate

        products_dir = (backlog_root_path / "products") if backlog_root_path else None
        product_dirs = [p for p in products_dir.iterdir() if p.is_dir()] if (products_dir and products_dir.exists()) else []
        
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
    
    file_items = _scan_repo_files(project_root, include_patterns, exclude_patterns)
    
    loaded: list[tuple[Path, object, float]] = []
    for file_path, mtime in file_items:
        item = _map_file_to_item(file_path, project_root, mtime)
        loaded.append((file_path, item, mtime))
    
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        cur.executescript(load_canonical_schema())
        
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("chunking_version", str(chunking_options.version)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("chunking_target_tokens", str(chunking_options.target_tokens)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("chunking_max_tokens", str(chunking_options.max_tokens)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("chunking_overlap_tokens", str(chunking_options.overlap_tokens)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("tokenizer_adapter", str(tokenizer_adapter)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("tokenizer_model", str(tokenizer_model)),
        )
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
            ("corpus_type", "repo"),
        )
        
        item_rows = []
        for file_path, item, mtime in loaded:
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
            
            item_rows.append(
                {
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
                }
            )
        
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
        
        chunk_rows = []
        for _, item, _ in loaded:
            content = getattr(item, "content", "")
            if not content or not content.strip():
                continue
            
            raw_chunks = chunk_text_with_tokenizer(
                source_id=item.uid,
                text=content,
                options=chunking_options,
                tokenizer=tokenizer,
                model_name=tokenizer_model,
            )
            
            chunk_index = 0
            for rc in raw_chunks:
                chunk_content = rc.text.strip()
                if not chunk_content:
                    continue
                
                chunk_rows.append(
                    {
                        "chunk_id": rc.chunk_id,
                        "parent_uid": item.uid,
                        "chunk_index": chunk_index,
                        "content": chunk_content,
                        "section": "content",
                        "embedding": None,
                    }
                )
                chunk_index += 1
        
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
        
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return RepoChunksDbBuildResult(
            db_path=db_path,
            files_indexed=len(item_rows),
            chunks_indexed=len(chunk_rows),
            build_time_ms=elapsed_ms,
        )
    finally:
        conn.close()


def query_repo_chunks_fts(
    *,
    project_root: Optional[Path] = None,
    backlog_root: Optional[Path] = None,
    query: str,
    k: int = 10,
) -> list[RepoChunkSearchRow]:
    """Keyword search over repo corpus chunks_fts."""
    
    if project_root is None:
        if backlog_root is not None:
            project_root = backlog_root.resolve().parent.parent
        else:
            project_root = Path.cwd().resolve()
    else:
        project_root = project_root.resolve()
    
    # Get project name from project root directory
    project_name = project_root.name
    
    def _resolve_repo_cache_dir() -> Path:
        default_dir = project_root / ".kano" / "cache" / "backlog"
        try:
            from kano_backlog_core.project_config import ProjectConfigLoader

            project_cfg = ProjectConfigLoader.load_project_config_optional(project_root)
            shared = project_cfg.shared if project_cfg else None
            if isinstance(shared, dict):
                cache = shared.get("cache")
                if isinstance(cache, dict):
                    root = cache.get("root")
                    if isinstance(root, str) and root.strip():
                        candidate = Path(root.strip())
                        return (candidate if candidate.is_absolute() else (project_root / candidate)).resolve()
        except Exception:
            pass
        return default_dir

    cache_dir = _resolve_repo_cache_dir()
    
    db_path = cache_dir / f"repo.{project_name}.chunks.v1.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Repo chunks DB not found: {db_path} (run build first)")
    
    if not query.strip():
        return []
    
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        # FTS5 bm25(): lower is better. Convert to higher-is-better score.
        rows = cur.execute(
            """
            SELECT
                i.id,
                i.path,
                c.chunk_id,
                c.parent_uid,
                c.section,
                c.content,
                bm25(chunks_fts) AS bm25_score
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            JOIN items i ON i.uid = c.parent_uid
            WHERE chunks_fts MATCH ?
            ORDER BY bm25_score ASC
            LIMIT ?
            """,
            (query, int(k)),
        ).fetchall()
        
        out: list[RepoChunkSearchRow] = []
        for (
            file_id,
            file_path,
            chunk_id,
            parent_uid,
            section,
            content,
            bm25_score,
        ) in rows:
            score = -float(bm25_score) if bm25_score is not None else 0.0
            out.append(
                RepoChunkSearchRow(
                    file_path=file_path,
                    file_id=file_id,
                    chunk_id=chunk_id,
                    parent_uid=parent_uid,
                    section=section,
                    content=content,
                    score=score,
                )
            )
        
        return out
    finally:
        conn.close()
