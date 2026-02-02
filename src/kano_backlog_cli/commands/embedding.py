"""CLI commands for embedding pipeline operations."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import typer

from kano_backlog_cli.util import ensure_core_on_path

app = typer.Typer(help="Embedding pipeline operations")


@app.command("build")
def build_index(
    file_path: Optional[Path] = typer.Argument(None, help="File path to index (optional for full product index)"),
    text: Optional[str] = typer.Option(None, "--text", help="Raw text to index instead of file"),
    source_id: Optional[str] = typer.Option(None, "--source-id", help="Source ID for text input (required with --text)"),
    product: str = typer.Option("kano-agent-backlog-skill", "--product", help="Product name"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    cache_root: Optional[Path] = typer.Option(None, "--cache-root", help="Cache root directory (overrides config)"),
    force: bool = typer.Option(False, "--force", help="Force rebuild of existing index"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
    # Tokenizer configuration options
    tokenizer_adapter: Optional[str] = typer.Option(None, "--tokenizer-adapter", help="Tokenizer adapter (auto, heuristic, tiktoken, huggingface)"),
    tokenizer_model: Optional[str] = typer.Option(None, "--tokenizer-model", help="Override tokenizer model name"),
    tokenizer_max_tokens: Optional[int] = typer.Option(None, "--tokenizer-max-tokens", help="Override max tokens for tokenizer"),
    tokenizer_config: Optional[Path] = typer.Option(None, "--tokenizer-config", help="Path to tokenizer configuration file"),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Profile (path or shorthand; path-first, fallback to .kano/backlog_config)",
    ),
):
    """Build embedding index for files or full product."""
    ensure_core_on_path()
    
    if text and not source_id:
        raise typer.BadParameter("--source-id is required when using --text")
    
    if file_path and text:
        raise typer.BadParameter("Use either file path or --text, not both")
    
    # Apply tokenizer configuration overrides if provided
    tokenizer_overrides = {}
    if tokenizer_adapter:
        tokenizer_overrides["adapter"] = tokenizer_adapter
    if tokenizer_model:
        tokenizer_overrides["model"] = tokenizer_model
    if tokenizer_max_tokens:
        tokenizer_overrides["max_tokens"] = tokenizer_max_tokens
    
    if text:
        # Index single text input
        from kano_backlog_core.config import ConfigLoader
        from kano_backlog_ops.backlog_vector_index import index_document
        
        # Load config
        ctx, effective = ConfigLoader.load_effective_config(
            Path("."),
            product=product,
            profile=profile,
        )
        pc = ConfigLoader.validate_pipeline_config(effective)
        
        # Apply tokenizer overrides to pipeline config
        if tokenizer_overrides:
            # Create a copy of the tokenizer config and apply overrides
            tokenizer_config_dict = pc.tokenizer.__dict__.copy()
            tokenizer_config_dict.update(tokenizer_overrides)
            
            # Update the pipeline config with new tokenizer settings
            from kano_backlog_core.pipeline_config import TokenizerConfig
            pc.tokenizer = TokenizerConfig(**tokenizer_config_dict)
        
        # Load custom tokenizer config if provided
        if tokenizer_config:
            from kano_backlog_core.tokenizer_config import load_tokenizer_config
            custom_config = load_tokenizer_config(config_path=tokenizer_config)
            
            # Apply custom config to pipeline config
            pc.tokenizer.adapter = custom_config.adapter
            pc.tokenizer.model = custom_config.model
            if custom_config.max_tokens:
                pc.tokenizer.max_tokens = custom_config.max_tokens
            pc.tokenizer.fallback_chain = custom_config.fallback_chain
            pc.tokenizer.options = custom_config.options
        
        # Index the text
        if source_id is None:
            raise typer.BadParameter("--source-id is required when using --text")
        sid: str = source_id
        result = index_document(sid, text, pc, product_root=ctx.product_root)
        
        if output_format == "json":
            payload = {
                "source_id": source_id,
                "chunks_count": result.chunks_count,
                "tokens_total": result.tokens_total,
                "duration_ms": result.duration_ms,
                "backend_type": result.backend_type,
                "embedding_provider": result.embedding_provider,
                "chunks_trimmed": result.chunks_trimmed,
                "tokenizer_adapter": pc.tokenizer.adapter,
                "tokenizer_model": pc.tokenizer.model,
            }
            typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
            return
        
        typer.echo(f"# Index Document: {source_id}")
        typer.echo(f"- chunks_count: {result.chunks_count}")
        typer.echo(f"- tokens_total: {result.tokens_total}")
        typer.echo(f"- duration_ms: {result.duration_ms:.2f}")
        typer.echo(f"- backend_type: {result.backend_type}")
        typer.echo(f"- embedding_provider: {result.embedding_provider}")
        typer.echo(f"- tokenizer_adapter: {pc.tokenizer.adapter}")
        typer.echo(f"- tokenizer_model: {pc.tokenizer.model}")
        if result.chunks_trimmed > 0:
            typer.echo(f"- chunks_trimmed: {result.chunks_trimmed}")
        
    elif file_path:
        # Index single file
        from kano_backlog_core.config import ConfigLoader
        from kano_backlog_ops.backlog_vector_index import index_document
        
        if not file_path.exists():
            raise typer.BadParameter(f"File not found: {file_path}")
        
        # Load config
        ctx, effective = ConfigLoader.load_effective_config(
            Path("."),
            product=product,
            profile=profile,
        )
        pc = ConfigLoader.validate_pipeline_config(effective)
        
        # Apply tokenizer overrides to pipeline config
        if tokenizer_overrides:
            # Create a copy of the tokenizer config and apply overrides
            tokenizer_config_dict = pc.tokenizer.__dict__.copy()
            tokenizer_config_dict.update(tokenizer_overrides)
            
            # Update the pipeline config with new tokenizer settings
            from kano_backlog_core.pipeline_config import TokenizerConfig
            pc.tokenizer = TokenizerConfig(**tokenizer_config_dict)
        
        # Load custom tokenizer config if provided
        if tokenizer_config:
            from kano_backlog_core.tokenizer_config import load_tokenizer_config
            custom_config = load_tokenizer_config(config_path=tokenizer_config)
            
            # Apply custom config to pipeline config
            pc.tokenizer.adapter = custom_config.adapter
            pc.tokenizer.model = custom_config.model
            if custom_config.max_tokens:
                pc.tokenizer.max_tokens = custom_config.max_tokens
            pc.tokenizer.fallback_chain = custom_config.fallback_chain
            pc.tokenizer.options = custom_config.options
        
        # Read file content
        try:
            text_content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            raise typer.BadParameter(f"Failed to read file {file_path}: {e}")
        
        # Use file path as source_id
        source_id = str(file_path)
        
        # Index the file
        result = index_document(source_id, text_content, pc, product_root=ctx.project_root)
        
        if output_format == "json":
            payload = {
                "file_path": str(file_path),
                "source_id": source_id,
                "chunks_count": result.chunks_count,
                "tokens_total": result.tokens_total,
                "duration_ms": result.duration_ms,
                "backend_type": result.backend_type,
                "embedding_provider": result.embedding_provider,
                "chunks_trimmed": result.chunks_trimmed,
                "tokenizer_adapter": pc.tokenizer.adapter,
                "tokenizer_model": pc.tokenizer.model,
            }
            typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
            return
        
        typer.echo(f"# Index File: {file_path}")
        typer.echo(f"- source_id: {source_id}")
        typer.echo(f"- chunks_count: {result.chunks_count}")
        typer.echo(f"- tokens_total: {result.tokens_total}")
        typer.echo(f"- duration_ms: {result.duration_ms:.2f}")
        typer.echo(f"- backend_type: {result.backend_type}")
        typer.echo(f"- embedding_provider: {result.embedding_provider}")
        typer.echo(f"- tokenizer_adapter: {pc.tokenizer.adapter}")
        typer.echo(f"- tokenizer_model: {pc.tokenizer.model}")
        if result.chunks_trimmed > 0:
            typer.echo(f"- chunks_trimmed: {result.chunks_trimmed}")
        
    else:
        from kano_backlog_core.config import ConfigLoader
        from kano_backlog_ops.backlog_vector_index import build_vector_index
        
        ctx, effective = ConfigLoader.load_effective_config(
            Path("."),
            product=product,
            profile=profile,
        )
        pc = ConfigLoader.validate_pipeline_config(effective)
        
        if not pc.vector.enabled:
            typer.echo(f"⚠️  Vector generation is disabled for product '{product}'", err=True)
            typer.echo(f"   Set 'enabled = true' in [vector] section of config to enable.", err=True)
            typer.echo(f"   Config location: _kano/backlog/products/{product}/_config/config.toml", err=True)
            raise typer.Exit(0)
        
        if tokenizer_overrides or tokenizer_config:
            typer.echo("⚠️  Tokenizer overrides not yet supported for full product index builds.", err=True)
            typer.echo("   Use file-specific or text-specific indexing for custom tokenizer settings.", err=True)
        
        result = build_vector_index(
            product=product,
            backlog_root=backlog_root,
            force=force,
            cache_root=cache_root
        )
        
        if output_format == "json":
            payload = {
                "product": product,
                "items_processed": result.items_processed,
                "chunks_generated": result.chunks_generated,
                "chunks_indexed": result.chunks_indexed,
                "duration_ms": result.duration_ms,
                "backend_type": result.backend_type,
            }
            typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
            return
        
        typer.echo(f"# Build Vector Index: {product}")
        typer.echo(f"- items_processed: {result.items_processed}")
        typer.echo(f"- chunks_generated: {result.chunks_generated}")
        typer.echo(f"- chunks_indexed: {result.chunks_indexed}")
        typer.echo(f"- duration_ms: {result.duration_ms:.2f}")
        typer.echo(f"- backend_type: {result.backend_type}")


@app.command("query")
def query_index(
    query_text: str = typer.Argument(..., help="Query text to search for"),
    k: int = typer.Option(5, "--k", help="Number of results to return"),
    product: str = typer.Option("kano-agent-backlog-skill", "--product", help="Product name"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
    # Tokenizer configuration options
    tokenizer_adapter: Optional[str] = typer.Option(None, "--tokenizer-adapter", help="Tokenizer adapter (auto, heuristic, tiktoken, huggingface)"),
    tokenizer_model: Optional[str] = typer.Option(None, "--tokenizer-model", help="Override tokenizer model name"),
    tokenizer_config: Optional[Path] = typer.Option(None, "--tokenizer-config", help="Path to tokenizer configuration file"),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Profile (path or shorthand; path-first, fallback to .kano/backlog_config)",
    ),
):
    """Query the embedding index for similar content."""
    ensure_core_on_path()
    
    from kano_backlog_core.config import ConfigLoader
    from kano_backlog_core.embedding import resolve_embedder
    from kano_backlog_core.vector import get_backend
    from kano_backlog_core.tokenizer import resolve_model_max_tokens
    
    # Load config
    ctx, effective = ConfigLoader.load_effective_config(
        Path("."),
        product=product,
        profile=profile,
    )
    pc = ConfigLoader.validate_pipeline_config(effective)
    
    # Apply tokenizer overrides if provided
    if tokenizer_adapter:
        pc.tokenizer.adapter = tokenizer_adapter
    if tokenizer_model:
        pc.tokenizer.model = tokenizer_model
    
    # Load custom tokenizer config if provided
    if tokenizer_config:
        from kano_backlog_core.tokenizer_config import load_tokenizer_config
        custom_config = load_tokenizer_config(config_path=tokenizer_config)
        
        # Apply custom config to pipeline config
        pc.tokenizer.adapter = custom_config.adapter
        pc.tokenizer.model = custom_config.model
        if custom_config.max_tokens:
            pc.tokenizer.max_tokens = custom_config.max_tokens
        pc.tokenizer.fallback_chain = custom_config.fallback_chain
        pc.tokenizer.options = custom_config.options
    
    # Resolve embedder
    embed_cfg = {
        "provider": pc.embedding.provider,
        "model": pc.embedding.model,
        "dimension": pc.embedding.dimension,
        **pc.embedding.options
    }
    embedder = resolve_embedder(embed_cfg)
    
    # Create embedding space ID for backend isolation
    max_tokens = pc.tokenizer.max_tokens or resolve_model_max_tokens(pc.tokenizer.model)
    embedding_space_id = (
        f"emb:{pc.embedding.provider}:{pc.embedding.model}:d{pc.embedding.dimension}"
        f"|tok:{pc.tokenizer.adapter}:{pc.tokenizer.model}:max{max_tokens}"
        f"|chunk:{pc.chunking.version}"
        f"|metric:{pc.vector.metric}"
    )
    
    # Resolve vector backend
    vec_path = Path(pc.vector.path)
    if not vec_path.is_absolute():
        vec_path = ctx.product_root / vec_path
        
    vec_cfg = {
        "backend": pc.vector.backend,
        "path": str(vec_path),
        "collection": pc.vector.collection,
        "embedding_space_id": embedding_space_id,
        **pc.vector.options
    }
    backend = get_backend(vec_cfg)
    backend.load()  # Load existing index
    
    try:
        # Embed the query
        t0 = time.perf_counter()
        query_results = embedder.embed_batch([query_text])
        query_vector = query_results[0].vector
        
        # Search the index
        search_results = backend.query(query_vector, k=k)
        query_duration_ms = (time.perf_counter() - t0) * 1000
        
        if output_format == "json":
            payload = {
                "query": query_text,
                "k": k,
                "duration_ms": query_duration_ms,
                "tokenizer_adapter": pc.tokenizer.adapter,
                "tokenizer_model": pc.tokenizer.model,
                "results": [
                    {
                        "chunk_id": result.chunk_id,
                        "text": result.text,
                        "score": result.score,
                        "metadata": result.metadata,
                    }
                    for result in search_results
                ]
            }
            typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
            return
        
        typer.echo(f"# Query Results: '{query_text}'")
        typer.echo(f"- k: {k}")
        typer.echo(f"- duration_ms: {query_duration_ms:.2f}")
        typer.echo(f"- results_count: {len(search_results)}")
        typer.echo(f"- tokenizer_adapter: {pc.tokenizer.adapter}")
        typer.echo(f"- tokenizer_model: {pc.tokenizer.model}")
        typer.echo()
        
        for i, result in enumerate(search_results, 1):
            preview: str = result.text or ""
            typer.echo(f"## Result {i} (score: {result.score:.4f})")
            typer.echo(f"- chunk_id: {result.chunk_id}")
            typer.echo(f"- source_id: {result.metadata.get('source_id', 'unknown')}")
            typer.echo(f"- text: {preview[:200]}{'...' if len(preview) > 200 else ''}")
            typer.echo()
            
    except Exception as e:
        typer.echo(f"Error querying index: {e}", err=True)
        raise typer.Exit(1)


@app.command("status")
def index_status(
    product: str = typer.Option("kano-agent-backlog-skill", "--product", help="Product name"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Profile (path or shorthand; path-first, fallback to .kano/backlog_config)",
    ),
):
    """Show embedding index status and metadata."""
    ensure_core_on_path()
    
    from kano_backlog_core.config import ConfigLoader
    from kano_backlog_core.vector import get_backend
    from kano_backlog_core.tokenizer import resolve_model_max_tokens
    
    # Load config
    ctx, effective = ConfigLoader.load_effective_config(
        Path("."),
        product=product,
        profile=profile,
    )
    pc = ConfigLoader.validate_pipeline_config(effective)
    
    # Create embedding space ID for backend isolation
    max_tokens = pc.tokenizer.max_tokens or resolve_model_max_tokens(pc.tokenizer.model)
    embedding_space_id = (
        f"emb:{pc.embedding.provider}:{pc.embedding.model}:d{pc.embedding.dimension}"
        f"|tok:{pc.tokenizer.adapter}:{pc.tokenizer.model}:max{max_tokens}"
        f"|chunk:{pc.chunking.version}"
        f"|metric:{pc.vector.metric}"
    )
    
    # Resolve vector backend
    vec_path = Path(pc.vector.path)
    if not vec_path.is_absolute():
        vec_path = ctx.product_root / vec_path
        
    vec_cfg = {
        "backend": pc.vector.backend,
        "path": str(vec_path),
        "collection": pc.vector.collection,
        "embedding_space_id": embedding_space_id,
        **pc.vector.options
    }
    backend = get_backend(vec_cfg)
    backend.load()  # Load existing index
    
    try:
        stats: dict[str, object] = {}
        
        if output_format == "json":
            payload = {
                "product": product,
                "backend_type": pc.vector.backend,
                "index_path": str(vec_path),
                "collection": pc.vector.collection,
                "embedding_space_id": embedding_space_id,
                "embedding_provider": pc.embedding.provider,
                "embedding_model": pc.embedding.model,
                "embedding_dimension": pc.embedding.dimension,
                "vector_metric": pc.vector.metric,
                "stats": stats,
            }
            typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
            return
        
        typer.echo(f"# Embedding Index Status: {product}")
        typer.echo(f"- backend_type: {pc.vector.backend}")
        typer.echo(f"- index_path: {vec_path}")
        typer.echo(f"- collection: {pc.vector.collection}")
        typer.echo(f"- embedding_space_id: {embedding_space_id}")
        typer.echo()
        typer.echo("## Configuration")
        typer.echo(f"- embedding_provider: {pc.embedding.provider}")
        typer.echo(f"- embedding_model: {pc.embedding.model}")
        typer.echo(f"- embedding_dimension: {pc.embedding.dimension}")
        typer.echo(f"- vector_metric: {pc.vector.metric}")
        typer.echo(f"- tokenizer_adapter: {pc.tokenizer.adapter}")
        typer.echo(f"- tokenizer_model: {pc.tokenizer.model}")
        typer.echo(f"- max_tokens: {max_tokens}")
        typer.echo()
        typer.echo("## Statistics")
        for key, value in stats.items():
            typer.echo(f"- {key}: {value}")
            
        # Show tokenizer adapter status
        try:
            from kano_backlog_core.tokenizer import get_default_registry
            registry = get_default_registry()
            adapter_status = registry.get_adapter_status_with_dependencies()
            
            typer.echo()
            typer.echo("## Tokenizer Adapter Status")
            for adapter_name, info in adapter_status.items():
                status_emoji = "✅" if info["available"] else "❌"
                typer.echo(f"- {status_emoji} {adapter_name}: {'Available' if info['available'] else 'Not available'}")
                if not info["available"] and info.get("error"):
                    typer.echo(f"  Error: {info['error']}")
        except Exception as e:
            typer.echo(f"- tokenizer_status_error: {e}")
            
    except Exception as e:
        typer.echo(f"Error getting index status: {e}", err=True)
        raise typer.Exit(1)
