"""Search command for vector similarity queries."""

from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from ..util import ensure_core_on_path

app = typer.Typer(help="Vector similarity search")
console = Console()

@app.command()
def query(
    text: str = typer.Argument(..., help="Query text to search for"),
    product: str = typer.Option(None, "--product", help="Product name"),
    k: int = typer.Option(10, "--top-k", "-k", help="Number of results to return"),
):
    """Search for similar content using vector embeddings."""
    ensure_core_on_path()
    from kano_backlog_ops.vector_query import search_similar
    
    try:
        results = search_similar(
            query_text=text,
            product=product or "kano-agent-backlog-skill",
            k=k
        )
    except Exception as e:
        console.print(f"[red]❌ Search failed:[/red] {e}")
        raise typer.Exit(1)
    
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return
    
    # Display results in a table
    table = Table(title=f"Search Results (query: '{text[:50]}...')")
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
