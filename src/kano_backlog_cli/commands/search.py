"""Search commands.

- query: pure vector similarity search
- hybrid: FTS5 candidates (canonical chunks DB) -> vector rerank

Both commands now support --corpus parameter to select search scope:
- backlog: search backlog items only (default)
- repo: search repository code/docs
- all: search both backlog and repo (future)
"""

from pathlib import Path
from typing import Optional, Literal
import typer
from rich.console import Console
from rich.table import Table

from ..util import ensure_core_on_path

app = typer.Typer(help="Vector similarity search")
console = Console()

@app.command()
def query(
    text: str = typer.Argument(..., help="Query text to search for"),
    product: str = typer.Option(None, "--product", help="Product name (for backlog corpus)"),
    corpus: Literal["backlog", "repo"] = typer.Option("backlog", "--corpus", help="Search corpus: backlog|repo"),
    k: int = typer.Option(10, "--top-k", "-k", help="Number of results to return"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    project_root: Optional[Path] = typer.Option(None, "--project-root", help="Project root (for repo corpus)"),
):
    """Searfor similar content using vector embeddings.
    
    Use --corpus to select search scope:
    - backlog: search backlog items (requires --product)
    - repo: search repository code/docs
    """
    ensure_core_on_path()
    
    if corpus == "backlog":
        from kano_backlog_ops.backlog_vector_query import search_similar
        
        try:
            results = search_similar(
                query_text=text,
                product=product or "kano-agent-backlog-skill",
                k=k,
                backlog_root=backlog_root,
            )
        except Exception as e:
            console.print(f"[red]❌ Search failed:[/red] {e}")
            raise typer.Exit(1)
        
        if not results:
            console.print("[yellow]No results found[/yellow]")
            return
        
        # Display results in a table
        table = Table(title=f"Search Results [backlog] (query: '{text[:50]}...')")
        table.add_column("Rank", style="cyan", width=6)
        table.add_column("Score", style="green", width=8)
        table.add_column("Source", style="magenta", width=15)
        table.add_column("Text", style="white", width=60)
        
        for i, result in enumerate(results, 1):
            score_str = f"{result.score:.4f}"
            text_preview = result.text[:100] + "..." if len(result.text) > 100 else result.text
            table.add_row(
                str(i),
                score_str,
                result.source_id,
                text_preview
            )
        
        console.print(table)
        console.print(f"\n[dim]Search completed in {results[0].duration_ms:.1f}ms[/dim]")
    
    elif corpus == "repo":
        # Repo corpus doesn't have pure vector query yet, show helpful message
        console.print("[yellow]⚠️  Pure vector query not yet implemented for repo corpus.[/yellow]")
        console.print("[dim]Use 'search hybrid --corpus repo' for repo search (FTS + vector rerank)[/dim]")
        raise typer.Exit(1)


@app.command()
def hybrid(
    text: str = typer.Argument(..., help="Query text to search for (also used as FTS MATCH string)"),
    product: str = typer.Option(None, "--product", help="Product name (for backlog corpus)"),
    corpus: Literal["backlog", "repo"] = typer.Option("backlog", "--corpus", help="Search corpus: backlog|repo"),
    k: int = typer.Option(10, "--top-k", "-k", help="Number of results to return"),
    fts_k: int = typer.Option(200, "--fts-k", help="Number of FTS candidates to rerank"),
    snippet_tokens: int = typer.Option(20, "--snippet-tokens", help="FTS snippet token length"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    project_root: Optional[Path] = typer.Option(None, "--project-root", help="Project root (for repo corpus)"),
):
    """Hybrid search: FTS candidates -> vector rerank (with snippet).
    
    Use --corpus to select search scope:
    - backlog: search backlog items (requires --product)
    - repo: search repository code/docs
    """
    ensure_core_on_path()

    if corpus == "backlog":
        from kano_backlog_ops.backlog_vector_query import search_hybrid

        try:
            results = search_hybrid(
                query_text=text,
                product=product or "kano-agent-backlog-skill",
                k=k,
                fts_k=fts_k,
                snippet_tokens=snippet_tokens,
                backlog_root=backlog_root,
            )
        except Exception as e:
            console.print(f"[red]❌ Hybrid search failed:[/red] {e}")
            raise typer.Exit(1)

        if not results:
            console.print("[yellow]No results found[/yellow]")
            return

        table = Table(title=f"Hybrid Search Results [backlog] (query: '{text[:50]}...')")
        table.add_column("Rank", style="cyan", width=6)
        table.add_column("VScore", style="green", width=8)
        table.add_column("BM25", style="green", width=8)
        table.add_column("Item", style="magenta", width=18)
        table.add_column("Section", style="cyan", width=12)
        table.add_column("Snippet", style="white", width=60)

        for i, result in enumerate(results, 1):
            snippet_preview = (
                result.snippet[:100] + "..." if len(result.snippet) > 100 else result.snippet
            )
            item_label = f"{result.item_id}"
            table.add_row(
                str(i),
                f"{result.vector_score:.4f}",
                f"{result.bm25_score:.4f}",
                item_label,
                result.section or "-",
                snippet_preview,
            )

        console.print(table)
        console.print(f"\n[dim]Hybrid search completed in {results[0].duration_ms:.1f}ms[/dim]")
    
    elif corpus == "repo":
        from kano_backlog_ops.repo_vector_query import search_repo_hybrid

        try:
            results = search_repo_hybrid(
                query_text=text,
                project_root=project_root,
                backlog_root=backlog_root,
                k=k,
                fts_candidates=fts_k,
            )
        except Exception as e:
            console.print(f"[red]❌ Hybrid search failed:[/red] {e}")
            raise typer.Exit(1)

        if not results:
            console.print("[yellow]No results found[/yellow]")
            return

        table = Table(title=f"Hybrid Search Results [repo] (query: '{text[:50]}...')")
        table.add_column("Rank", style="cyan", width=6)
        table.add_column("VScore", style="green", width=8)
        table.add_column("BM25", style="green", width=8)
        table.add_column("File", style="magenta", width=30)
        table.add_column("Section", style="cyan", width=12)
        table.add_column("Snippet", style="white", width=50)

        for i, result in enumerate(results, 1):
            snippet_preview = (
                result.snippet[:80] + "..." if len(result.snippet) > 80 else result.snippet
            )
            file_label = result.file_path if len(result.file_path) <= 30 else "..." + result.file_path[-27:]
            table.add_row(
                str(i),
                f"{result.vector_score:.4f}",
                f"{result.bm25_score:.4f}",
                file_label,
                result.section or "-",
                snippet_preview,
            )

        console.print(table)
        console.print(f"\n[dim]Hybrid search completed[/dim]")
