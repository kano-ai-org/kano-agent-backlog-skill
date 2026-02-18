# Context Graph (Derived) and Graph-assisted retrieval

This project is **file-first**: Markdown work items and ADRs are the canonical source of truth.

A **Context Graph** is a *derived* representation of how those artifacts relate, designed to help agents retrieve and assemble the right context *without prompt bloat*.

## What we mean by "Context Graph"

A Context Graph is a directed, typed graph:

- **Nodes**: artifacts (WorkItem, ADR, Worklog entry, chunks, code files, commits)
- **Edges**: explicit relationships (parent, decision_ref, relates, blocks, blocked_by, mentions, etc.)

This is a **weak graph first** approach:

- v1 uses *only explicit, structured relationships* already present in frontmatter or known file conventions
- no LLM-based entity extraction
- no server/MCP requirement (local-first)

## Why it matters (vs vector-only RAG)

Vector/FTS retrieval finds "similar" text, but can miss:

- the parent chain (task -> story -> feature -> epic)
- the ADR that explains the decision
- the blockers/depends chain

Graph-assisted retrieval uses vector/FTS to find **seed nodes**, then expands along known edges to pull in the *load-bearing neighbors*.

## Minimal Graph-assisted retrieval flow

1. **Seed retrieval**
   - FTS/embeddings return top-N chunks/nodes (seed set)
2. **Graph expansion**
   - expand via allowlisted edge types
   - limit traversal depth (k-hop) and fanout
3. **Re-rank**
   - prioritize ADR decision sections and item title/acceptance
   - downweight noisy worklog-only matches
4. **Context packing**
   - assemble "seed + neighbors" into a compact, traceable context pack

## Suggested node / edge model (v1)

**Node types** (initial):

- `work_item`
- `adr`
- `chunk` (optional, for embedding/fts indexing)

**Edge types** (initial):

- `parent` (child -> parent)
- `decision_ref` (work_item -> adr)
- `relates` (work_item -> work_item)
- `blocks` / `blocked_by`

## Storage (derived)

Two equivalent ways to store the derived graph:

- **Reuse the SQLite index**: materialize edges into a `links`-like table and query it for traversal
- **Sidecar JSONL**: `graph_nodes.jsonl` + `graph_edges.jsonl` under `<backlog-root>/_index/`

Either way:

- graph artifacts must be safe to delete
- the build must be repeatable from canonical Markdown (or from the SQLite index derived from Markdown)

## Configuration knobs

Recommended config keys (names indicative; see product ADR for final schema):

- `retrieval.mode`: `file_scan | sqlite | hybrid`
- `retrieval.graph.enabled`: boolean
- `retrieval.graph.k_hop`: int
- `retrieval.graph.edge_allowlist`: list
- `retrieval.weights`: doctype/section/state weights

## References

- Product ADR (planned): Graph-assisted retrieval with a derived Context Graph
- `references/indexing.md` for the derived indexing layer
