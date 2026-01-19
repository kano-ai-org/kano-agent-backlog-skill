from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kano_backlog_core.chunking import ChunkingOptions, chunk_text
from kano_backlog_core.config import ConfigLoader
from kano_backlog_core.token_budget import enforce_token_budget
from kano_backlog_core.tokenizer import HeuristicTokenizer, TokenCount, resolve_model_max_tokens, resolve_tokenizer
from kano_backlog_core.embedding import resolve_embedder
from kano_backlog_core.vector import VectorChunk, get_backend


def _dumps_deterministic(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BenchmarkDocument:
    source_id: str
    language: str
    text: str


@dataclass(frozen=True)
class BenchmarkQuery:
    query_id: str
    text: str
    expected_source_ids: Optional[List[str]] = None


@dataclass(frozen=True)
class BenchmarkHarnessOptions:
    include_embedding: bool = True
    include_vector: bool = False
    top_k: int = 5
    round_decimals: int = 4
    output_dir: Optional[Path] = None
    attach_item_id: Optional[str] = None


@dataclass(frozen=True)
class BenchmarkRunPaths:
    run_dir: Path
    report_json: Path
    report_md: Path


def load_benchmark_corpus(corpus_path: Path) -> List[BenchmarkDocument]:
    raw = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    docs: List[BenchmarkDocument] = []
    for d in raw:
        docs.append(
            BenchmarkDocument(
                source_id=str(d["source_id"]).strip(),
                language=str(d.get("language", "unknown")).strip(),
                text=str(d.get("text", "")),
            )
        )
    docs.sort(key=lambda x: x.source_id)
    return docs


def load_benchmark_queries(queries_path: Path) -> List[BenchmarkQuery]:
    raw = json.loads(Path(queries_path).read_text(encoding="utf-8"))
    queries: List[BenchmarkQuery] = []
    for q in raw:
        expected = q.get("expected_source_ids")
        expected_list = [str(s) for s in expected] if isinstance(expected, list) else None
        if expected_list is not None:
            expected_list.sort()
        queries.append(
            BenchmarkQuery(
                query_id=str(q["query_id"]).strip(),
                text=str(q.get("text", "")),
                expected_source_ids=expected_list,
            )
        )
    queries.sort(key=lambda x: x.query_id)
    return queries


def fingerprint_corpus_and_queries(
    corpus: List[BenchmarkDocument], queries: List[BenchmarkQuery]
) -> str:
    payload = {
        "corpus": [asdict(d) for d in corpus],
        "queries": [asdict(q) for q in queries],
    }
    return _sha256_hex(_dumps_deterministic(payload))


def _round_float(value: float, ndigits: int) -> float:
    return float(round(value, ndigits))


def run_benchmark(
    *,
    product: str,
    agent: str,
    corpus_path: Path,
    queries_path: Path,
    options: BenchmarkHarnessOptions,
) -> Tuple[Dict[str, Any], BenchmarkRunPaths]:
    ctx, effective = ConfigLoader.load_effective_config(Path("."), product=product, agent=agent)
    pc = ConfigLoader.validate_pipeline_config(effective)

    corpus = load_benchmark_corpus(corpus_path)
    queries = load_benchmark_queries(queries_path)

    corpus_fingerprint = fingerprint_corpus_and_queries(corpus, queries)

    output_dir = options.output_dir
    if output_dir is None:
        # Default under product artifacts, deterministic path keyed by corpus fingerprint.
        output_dir = ctx.product_root / "artifacts" / "KABSD-TSK-0261" / "runs" / corpus_fingerprint[:12]

    run_dir = Path(output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = resolve_tokenizer(pc.tokenizer.adapter, pc.tokenizer.model, max_tokens=pc.tokenizer.max_tokens)
    heuristic_tok = HeuristicTokenizer(model_name=pc.tokenizer.model)

    max_tokens = pc.tokenizer.max_tokens or resolve_model_max_tokens(pc.tokenizer.model)

    # Chunk/token metrics
    doc_metrics: List[Dict[str, Any]] = []
    chunks_for_embedding: List[Tuple[str, str, str]] = []  # (chunk_id, source_id, text)

    for doc in corpus:
        chunks = chunk_text(source_id=doc.source_id, text=doc.text, options=pc.chunking)
        trimmed_count = 0
        token_counts_exactish: List[int] = []
        token_counts_heur: List[int] = []

        for c in chunks:
            before = tokenizer.count_tokens(c.text)
            after = enforce_token_budget(c.text, tokenizer, max_tokens=max_tokens)
            token_counts_exactish.append(after.token_count.count)
            token_counts_heur.append(heuristic_tok.count_tokens(c.text).count)
            if after.trimmed:
                trimmed_count += 1
            chunks_for_embedding.append((c.chunk_id, doc.source_id, after.content))

        total_tokens = sum(token_counts_exactish)
        total_heur = sum(token_counts_heur)
        inflation = (float(total_tokens) / float(total_heur)) if total_heur else 0.0

        doc_metrics.append(
            {
                "source_id": doc.source_id,
                "language": doc.language,
                "chunks": len(chunks),
                "trimmed_chunks": trimmed_count,
                "token_total": total_tokens,
                "token_total_heuristic": total_heur,
                "inflation_ratio": _round_float(inflation, options.round_decimals),
            }
        )

    doc_metrics.sort(key=lambda m: (m["language"], m["source_id"]))

    include_embedding = bool(options.include_embedding)
    include_vector = bool(options.include_vector)

    embedding_summary: Dict[str, Any] = {"ran": False}
    vector_summary: Dict[str, Any] = {"ran": False}

    embedded_vectors: Dict[str, List[float]] = {}
    if include_embedding:
        embed_cfg = {
            "provider": pc.embedding.provider,
            "model": pc.embedding.model,
            "dimension": pc.embedding.dimension,
        }
        embedder = resolve_embedder(embed_cfg)

        # Deterministic batch order
        chunks_for_embedding.sort(key=lambda x: x[0])
        texts = [t for _, _, t in chunks_for_embedding]

        t0 = __import__("time").perf_counter()
        results = embedder.embed_batch(texts)
        duration_ms = (__import__("time").perf_counter() - t0) * 1000

        for i, (chunk_id, _source_id, _t) in enumerate(chunks_for_embedding):
            embedded_vectors[chunk_id] = results[i].vector

        per_item_ms = duration_ms / max(1, len(results))
        embedding_summary = {
            "ran": True,
            "provider": pc.embedding.provider,
            "model": pc.embedding.model,
            "dimension": pc.embedding.dimension,
            "items": len(results),
            "latency_ms_per_item": _round_float(per_item_ms, options.round_decimals),
        }

    if include_vector:
        embedding_space_id = (
            f"emb:{pc.embedding.provider}:{pc.embedding.model}:d{pc.embedding.dimension}"
            f"|tok:{pc.tokenizer.adapter}:{pc.tokenizer.model}:max{max_tokens}"
            f"|chunk:{pc.chunking.version}"
            f"|metric:{pc.vector.metric}"
        )

        vec_cfg = {
            "backend": pc.vector.backend,
            "path": str(run_dir / "vector"),
            "collection": pc.vector.collection,
            "embedding_space_id": embedding_space_id,
        }
        backend = get_backend(vec_cfg)
        backend.prepare(schema={}, dims=pc.embedding.dimension, metric=pc.vector.metric)

        # Index vectors
        chunks_for_embedding.sort(key=lambda x: x[0])
        indexed = 0
        for chunk_id, source_id, text in chunks_for_embedding:
            vec = embedded_vectors.get(chunk_id)
            if vec is None:
                continue
            backend.upsert(
                VectorChunk(
                    chunk_id=chunk_id,
                    text=text,
                    metadata={"source_id": source_id},
                    vector=vec,
                )
            )
            indexed += 1
        backend.persist()

        # Sanity queries
        query_pass = 0
        query_total = 0
        for q in queries:
            query_total += 1
            q_vec_res = resolve_embedder(
                {
                    "provider": pc.embedding.provider,
                    "model": pc.embedding.model,
                    "dimension": pc.embedding.dimension,
                }
            ).embed_batch([q.text])
            q_vec = q_vec_res[0].vector
            res = backend.query(q_vec, k=options.top_k)
            got_source_ids = sorted({r.metadata.get("source_id", "") for r in res if r.metadata})

            expected = q.expected_source_ids or []
            if expected and any(sid in got_source_ids for sid in expected):
                query_pass += 1

        vector_summary = {
            "ran": True,
            "backend": pc.vector.backend,
            "metric": pc.vector.metric,
            "indexed_chunks": indexed,
            "queries": query_total,
            "queries_with_expected_hit": query_pass,
        }

    report: Dict[str, Any] = {
        "schema_version": "1.0",
        "product": product,
        "agent": agent,
        "corpus_fingerprint": corpus_fingerprint,
        "effective_config": effective,
        "pipeline": {
            "chunking": {
                "target_tokens": pc.chunking.target_tokens,
                "max_tokens": pc.chunking.max_tokens,
                "overlap_tokens": pc.chunking.overlap_tokens,
                "version": pc.chunking.version,
            },
            "tokenizer": {
                "adapter": pc.tokenizer.adapter,
                "model": pc.tokenizer.model,
                "max_tokens": max_tokens,
            },
            "embedding": {
                "provider": pc.embedding.provider,
                "model": pc.embedding.model,
                "dimension": pc.embedding.dimension,
            },
            "vector": {
                "backend": pc.vector.backend,
                "metric": pc.vector.metric,
                "collection": pc.vector.collection,
            },
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "metrics": {
            "documents": len(corpus),
            "doc_metrics": doc_metrics,
            "embedding": embedding_summary,
            "vector": vector_summary,
        },
    }

    report_json = run_dir / "report.json"
    report_md = run_dir / "report.md"

    report_json.write_text(_dumps_deterministic(report) + "\n", encoding="utf-8")

    report_md.write_text(
        _render_report_md(report),
        encoding="utf-8",
    )

    return report, BenchmarkRunPaths(run_dir=run_dir, report_json=report_json, report_md=report_md)


def _render_report_md(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Benchmark Report")
    lines.append("")
    lines.append(f"- Product: {report['product']}")
    lines.append(f"- Agent: {report['agent']}")
    lines.append(f"- Corpus fingerprint: {report['corpus_fingerprint']}")
    lines.append("")

    pipeline = report["pipeline"]
    lines.append("## Pipeline")
    lines.append("")
    lines.append(_dumps_deterministic(pipeline))
    lines.append("")

    metrics = report["metrics"]
    lines.append("## Document Metrics")
    lines.append("")
    for m in metrics["doc_metrics"]:
        lines.append(
            f"- {m['language']} {m['source_id']}: chunks={m['chunks']} trimmed={m['trimmed_chunks']} tokens={m['token_total']} inflation={m['inflation_ratio']}"
        )

    lines.append("")
    lines.append("## Embedding")
    lines.append("")
    emb = metrics["embedding"]
    if not emb.get("ran"):
        lines.append("Not run")
    else:
        lines.append(_dumps_deterministic(emb))

    lines.append("")
    lines.append("## Vector")
    lines.append("")
    vec = metrics["vector"]
    if not vec.get("ran"):
        lines.append("Not run")
    else:
        lines.append(_dumps_deterministic(vec))

    lines.append("")
    return "\n".join(lines) + "\n"
