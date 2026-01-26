"""CLI commands for canonical chunks DB (FTS5) operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from kano_backlog_cli.util import ensure_core_on_path


app = typer.Typer(help="Canonical chunks SQLite DB (FTS5) operations")


@app.command("build")
def build_chunks(
    product: str = typer.Option("kano-agent-backlog-skill", "--product", help="Product name"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    force: bool = typer.Option(False, "--force", help="Force rebuild if DB exists"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Build per-product canonical chunks DB (items/chunks/chunks_fts)."""
    ensure_core_on_path()

    from kano_backlog_ops.backlog_chunks_db import build_chunks_db

    result = build_chunks_db(product=product, backlog_root=backlog_root, force=force)

    if output_format == "json":
        payload = {
            "product": product,
            "db_path": str(result.db_path),
            "items_indexed": result.items_indexed,
            "chunks_indexed": result.chunks_indexed,
            "build_time_ms": result.build_time_ms,
        }
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Build Chunks DB: {product}")
    typer.echo(f"- db_path: {result.db_path}")
    typer.echo(f"- items_indexed: {result.items_indexed}")
    typer.echo(f"- chunks_indexed: {result.chunks_indexed}")
    typer.echo(f"- build_time_ms: {result.build_time_ms:.2f}")


@app.command("query")
def query_chunks(
    query: str = typer.Argument(..., help="FTS query (SQLite MATCH syntax)"),
    product: str = typer.Option("kano-agent-backlog-skill", "--product", help="Product name"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    k: int = typer.Option(10, "--k", help="Number of results to return"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Keyword search over canonical chunks_fts."""
    ensure_core_on_path()

    from kano_backlog_ops.backlog_chunks_db import query_chunks_fts

    results = query_chunks_fts(product=product, backlog_root=backlog_root, query=query, k=k)

    if output_format == "json":
        payload = {
            "product": product,
            "query": query,
            "k": k,
            "results": [
                {
                    "item_id": r.item_id,
                    "item_title": r.item_title,
                    "item_path": r.item_path,
                    "chunk_id": r.chunk_id,
                    "parent_uid": r.parent_uid,
                    "section": r.section,
                    "content": r.content,
                    "score": r.score,
                }
                for r in results
            ],
        }
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Chunks Search: {product}")
    typer.echo(f"- query: {query}")
    typer.echo(f"- k: {k}")
    typer.echo(f"- results_count: {len(results)}")
    typer.echo()

    for i, r in enumerate(results, 1):
        preview = r.content[:200] + ("..." if len(r.content) > 200 else "")
        typer.echo(f"## Result {i} (score: {r.score:.4f})")
        typer.echo(f"- item: {r.item_id} ({r.item_title})")
        typer.echo(f"- path: {r.item_path}")
        typer.echo(f"- section: {r.section or 'unknown'}")
        typer.echo(f"- chunk_id: {r.chunk_id}")
        typer.echo(f"- text: {preview}")
        typer.echo()


@app.command("build-repo")
def build_repo_chunks(
    project_root: Optional[Path] = typer.Option(None, "--project-root", help="Project root (auto-detected if not specified)"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    include: Optional[list[str]] = typer.Option(None, "--include", help="Include patterns (e.g., *.md *.py)"),
    exclude: Optional[list[str]] = typer.Option(None, "--exclude", help="Exclude patterns (e.g., .git node_modules)"),
    force: bool = typer.Option(False, "--force", help="Force rebuild if DB exists"),
    sync: bool = typer.Option(False, "--sync", help="Use synchronous build (slower, for debugging)"),
    max_workers: int = typer.Option(4, "--max-workers", help="Number of parallel workers (async mode only)"),
    batch_size: int = typer.Option(50, "--batch-size", help="Batch size for database writes (async mode only)"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Build repo corpus chunks DB (docs + code). Uses async by default for better performance."""
    ensure_core_on_path()

    if sync:
        from kano_backlog_ops.repo_chunks_db import build_repo_chunks_db
        result = build_repo_chunks_db(
            project_root=project_root,
            backlog_root=backlog_root,
            include_patterns=include,
            exclude_patterns=exclude,
            force=force,
        )
    else:
        from kano_backlog_ops.repo_chunks_db_async import build_repo_chunks_db_async
        result = build_repo_chunks_db_async(
            project_root=project_root,
            backlog_root=backlog_root,
            include_patterns=include,
            exclude_patterns=exclude,
            force=force,
            max_workers=max_workers,
            batch_size=batch_size,
        )

    if output_format == "json":
        payload = {
            "db_path": str(result.db_path),
            "files_indexed": result.files_indexed,
            "chunks_indexed": result.chunks_indexed,
            "build_time_ms": result.build_time_ms,
        }
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Build Repo Chunks DB")
    typer.echo(f"- db_path: {result.db_path}")
    typer.echo(f"- files_indexed: {result.files_indexed}")
    typer.echo(f"- chunks_indexed: {result.chunks_indexed}")
    typer.echo(f"- build_time_ms: {result.build_time_ms:.2f}")


@app.command("query-repo")
def query_repo_chunks(
    query: str = typer.Argument(..., help="FTS query (SQLite MATCH syntax)"),
    project_root: Optional[Path] = typer.Option(None, "--project-root", help="Project root (auto-detected if not specified)"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    k: int = typer.Option(10, "--k", help="Number of results to return"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Keyword search over repo corpus chunks_fts."""
    ensure_core_on_path()

    from kano_backlog_ops.repo_chunks_db import query_repo_chunks_fts

    results = query_repo_chunks_fts(
        project_root=project_root,
        backlog_root=backlog_root,
        query=query,
        k=k,
    )

    if output_format == "json":
        payload = {
            "query": query,
            "k": k,
            "results": [
                {
                    "file_path": r.file_path,
                    "file_id": r.file_id,
                    "chunk_id": r.chunk_id,
                    "parent_uid": r.parent_uid,
                    "section": r.section,
                    "content": r.content,
                    "score": r.score,
                }
                for r in results
            ],
        }
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Repo Chunks Search")
    typer.echo(f"- query: {query}")
    typer.echo(f"- k: {k}")
    typer.echo(f"- results_count: {len(results)}")
    typer.echo()

    for i, r in enumerate(results, 1):
        preview = r.content[:200] + ("..." if len(r.content) > 200 else "")
        typer.echo(f"## Result {i} (score: {r.score:.4f})")
        typer.echo(f"- file: {r.file_path}")
        typer.echo(f"- file_id: {r.file_id}")
        typer.echo(f"- section: {r.section or 'unknown'}")
        typer.echo(f"- chunk_id: {r.chunk_id}")
        typer.echo(f"- text: {preview}")
        typer.echo()


@app.command("build-repo-vectors")
def build_repo_vectors(
    project_root: Optional[Path] = typer.Option(None, "--project-root", help="Project root (auto-detected if not specified)"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    force: bool = typer.Option(False, "--force", help="Force rebuild (clear existing vectors)"),
    storage_format: str = typer.Option("binary", "--storage-format", help="Vector storage format: binary (default, 80% smaller) | json (debug-friendly)"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Build vector index for repo corpus."""
    ensure_core_on_path()

    from kano_backlog_ops.repo_vector_index import build_repo_vector_index

    result = build_repo_vector_index(
        project_root=project_root,
        backlog_root=backlog_root,
        force=force,
        storage_format=storage_format,
    )

    if output_format == "json":
        payload = {
            "files_processed": result.files_processed,
            "chunks_generated": result.chunks_generated,
            "chunks_indexed": result.chunks_indexed,
            "chunks_skipped": result.chunks_skipped,
            "chunks_pruned": result.chunks_pruned,
            "duration_ms": result.duration_ms,
            "backend_type": result.backend_type,
        }
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Build Repo Vector Index")
    typer.echo(f"- files_processed: {result.files_processed}")
    typer.echo(f"- chunks_generated: {result.chunks_generated}")
    typer.echo(f"- chunks_indexed: {result.chunks_indexed}")
    typer.echo(f"- chunks_skipped: {result.chunks_skipped}")
    typer.echo(f"- chunks_pruned: {result.chunks_pruned}")
    typer.echo(f"- duration_ms: {result.duration_ms:.2f}")
    typer.echo(f"- backend_type: {result.backend_type}")


@app.command("build-status")
def check_build_status(
    project_root: Optional[Path] = typer.Option(None, "--project-root", help="Project root (auto-detected if not specified)"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Check repo chunks DB build progress."""
    ensure_core_on_path()
    
    from kano_backlog_ops.repo_chunks_db_async import get_build_progress
    
    progress = get_build_progress(project_root)
    
    if progress is None:
        if output_format == "json":
            typer.echo(json.dumps({"status": "no_build_in_progress"}, ensure_ascii=True, indent=2))
        else:
            typer.echo("No build in progress or recently completed.")
        return
    
    if output_format == "json":
        typer.echo(json.dumps(progress.to_dict(), ensure_ascii=True, indent=2))
        return
    
    typer.echo(f"# Repo Chunks DB Build Status")
    typer.echo(f"- task_id: {progress.task_id}")
    typer.echo(f"- status: {progress.status}")
    typer.echo(f"- progress: {progress.processed_files}/{progress.total_files} files ({progress.percentage:.1f}%)")
    typer.echo(f"- chunks: {progress.total_chunks}")
    typer.echo(f"- start_time: {progress.start_time}")
    typer.echo(f"- last_update: {progress.last_update}")
    if progress.current_file:
        typer.echo(f"- current_file: {progress.current_file}")
    
    if progress.error_message:
        typer.echo(f"- error: {progress.error_message}")
