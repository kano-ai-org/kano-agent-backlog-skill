from __future__ import annotations
from typing import Optional, Union
from pathlib import Path
import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Deterministic benchmark harness")


@app.command()
def run(
    product: str = typer.Option("kano-agent-backlog-skill", "--product", help="Product name"),
    agent: str = typer.Option(..., "--agent", help="Agent id (for topic overrides)"),
    corpus: Path = typer.Option(
        Path("skills/kano-agent-backlog-skill/tests/fixtures/benchmark_corpus.json"),
        "--corpus",
        help="Path to benchmark corpus JSON",
    ),
    queries: Path = typer.Option(
        Path("skills/kano-agent-backlog-skill/tests/fixtures/benchmark_queries.json"),
        "--queries",
        help="Path to benchmark queries JSON",
    ),
    out_dir: Optional[Path] = typer.Option(None, "--out", help="Output directory (default: product artifacts)")
    ,
    mode: str = typer.Option(
        "chunk-only",
        "--mode",
        help="chunk-only|embed|embed+vector",
    ),
    top_k: int = typer.Option(5, "--top-k", help="Top-k for vector sanity queries"),
):
    ensure_core_on_path()

    from kano_backlog_ops.benchmark_embeddings import BenchmarkHarnessOptions, run_benchmark

    include_embedding = mode in {"embed", "embed+vector"}
    include_vector = mode == "embed+vector"

    options = BenchmarkHarnessOptions(
        include_embedding=include_embedding,
        include_vector=include_vector,
        top_k=top_k,
        output_dir=out_dir,
    )

    report, paths = run_benchmark(
        product=product,
        agent=agent,
        corpus_path=corpus,
        queries_path=queries,
        options=options,
    )

    typer.echo(f"OK: wrote {paths.report_json}")
    typer.echo(f"OK: wrote {paths.report_md}")
