# kano_backlog_webview (C++ Drogon)

Local-only backlog visualization service for Backboard.

Backboard is the product-facing local review UI. KOB Webview is the technical
name for this native service, its binary, routes, and Docker wrapper.

Design contracts:

- [`docs/design/backboard-information-architecture.md`](../../../../../docs/design/backboard-information-architecture.md)
- [`docs/design/backboard-review-inbox-model.md`](../../../../../docs/design/backboard-review-inbox-model.md)
- [`docs/design/backboard-partial-ui-boundary.md`](../../../../../docs/design/backboard-partial-ui-boundary.md)
- [`docs/design/webview-technology-boundary.md`](../../../../../docs/design/webview-technology-boundary.md)

## Scope (MVP)

- Read canonical markdown backlog files under `_kano/backlog/products/*/items/`
- Default to an all-products view, with explicit single-product and multi-product filters.
- Expose item metadata needed for review scans: product, type, state, source kind, UID, and topic membership when a topic manifest references the item.
- Read-mostly APIs:
  - `GET /healthz`
  - `GET /api/products`
  - `GET /api/items?product=all|<name>[&products=a,b][&q=...][&state=Ready,Doing][&type=task,feature][&assignee=alias-a,alias-b][&reviewer=alias-a,alias-b][&assignment_case=missing_assignee,...][&limit=200][&offset=0]`
  - `GET /api/items/<id>?product=all|<name>[&products=a,b]`
  - `GET /api/tree?product=all|<name>[&products=a,b][&q=...][&state=...][&type=...][&limit=...]`
  - `GET /api/kanban?product=all|<name>[&products=a,b][&q=...][&state=...][&type=...][&limit=...]`
  - `GET /api/refresh[?product=all|<name>][&products=a,b]`
  - `GET /api/review/done-detector?product=all|<name>[&products=a,b][&q=...][&state=...][&type=...]`
  - `GET /api/review/evidence-quality?product=all|<name>[&products=a,b][&q=...][&state=...][&type=...]`
  - `GET /api/review/handoff-readiness?product=all|<name>[&products=a,b][&q=...][&state=...][&type=...]`
  - `GET /api/review/context-recovery?area=...&product=all|<name>[&products=a,b][&q=...][&state=...][&type=...]`
  - `GET /api/review/graph?product=all|<name>[&products=a,b][&item=<id>][&root_product=<name>][&mode=dependency|structure|cycles|related|product_memory][&graph_isolation=fade|hide][&max_depth=2][&max_children_per_node=25][&max_total_nodes=80|&node_limit=80][&max_total_edges=120|&edge_limit=120]`
  - `GET /api/review/graph/expand?product=all|<name>[&products=a,b]&item=<id>[&root_product=<name>]&expansion=inbound|outbound|children|related[&q=...][&state=...][&type=...][&max_children_per_node=25][&max_total_nodes=80][&max_total_edges=120]`
  - `GET /api/review/feature-evolution?product=<name>&feature_id=<id>`
  - `GET /api/review/roadmap?product=all|<name>[&products=a,b]`
  - `GET /api/review/decision-radar?product=all|<name>[&products=a,b]`
  - `POST /api/review/decision/draft`
  - `POST /api/review/decision/draft/discard`
  - `POST /api/review/decision/submit`
- Server-rendered partials:
  - `GET /partials/tree?...`
  - `GET /partials/kanban?...`
  - `GET /partials/review?...`
  - `GET /partials/handoff-readiness?...`
  - `GET /partials/roadmap?...`
  - `GET /partials/decision-radar?...`
  - `GET /partials/context?...`
  - `GET /partials/filters?...`
  - `GET /partials/item/<id>?product=all|<name>`
- First-party UI runtime:
  - `GET /assets/kob-ui.js`
  - `GET /graph?tab=graph[&product=<name>][&item=<id>][&root_product=<name>][&mode=dependency][&graph_isolation=fade|hide][&max_depth=2][&max_children_per_node=25][&max_total_nodes=80][&max_total_edges=120]`
- UI: Backboard Review Inbox, Agent Handoff Readiness, product map, flow,
  context, dependencies, agent runs, and command preview at `/`

### Assignment query contract

Backboard's list, tree, flow, and review queries accept three read-only
assignment filters:

- `assignee` is a comma-separated list of repo-visible assignee aliases.
- `reviewer` is a comma-separated list of repo-visible reviewer aliases.
- `assignment_case` is a comma-separated list containing any of
  `missing_assignee`, `missing_bug_reviewer`, `assigned_to_koa`, and
  `needs_review_by_koa`.

Alias matching is case-insensitive exact matching; it is not a substring or
display-name search. Values within the assignee dimension are ORed, values
within the reviewer dimension are ORed, and selected assignment cases are ORed.
Active dimensions are ANDed across assignee, reviewer, and assignment-case
filters, and they remain ANDed with the existing product, state, type, and text
filters.

Assignment filtering uses materialized-only values from the native assignment
contract. It does not recompute defaults in the browser. `missing_assignee`
matches an item whose materialized assignee is empty. `missing_bug_reviewer`
matches only Bug items whose materialized reviewer is empty; an unassigned
reviewer on a non-Bug is not a missing-Bug-reviewer match. `assigned_to_koa`
matches the materialized `koa` assignee alias, while `needs_review_by_koa`
matches the materialized `koa` or `reviewer-koa` reviewer alias. Pseudo-records are
excluded from assignment matching rather than being treated as unassigned
items.

Cards and Product Map rows display the materialized assignee and reviewer.
Inherited values are labeled `Inherited from product default`, with the exact
native `owner_source` or `reviewer_source` retained in accessible/title text.
Missing assignees display `Unassigned`; missing Bug reviewers display
`Bug reviewer Missing`; other absent reviewers display `Not assigned`.

The assignment controls round-trip `assignee`, `reviewer`, and
`assignment_case` through the page URL. Clearing assignment filters removes all
three keys without disturbing unrelated query state. These filters are not
forwarded by the graph-only `graphQueryString`, so assignment filtering cannot
broaden or otherwise change the bounded item-rooted graph contract.

Stale-assigned policy is deferred: this read-only UI neither mutates assignment
nor adds special stale-assigned filtering, dispatch, approval, or automatic
reassignment behavior.

The full-page Dependencies canvas is item-rooted and bounded by query caps. The
default graph page shell keeps the mode selector/help visible, but when no
`item` root is present it renders a scaffold-only prompt instead of fetching or
rendering a global all-node graph by default.

When an item root exists, the normal Backboard UI sends a graph-only bounded all-product scan
(`product=all`, `limit=1000`, `offset=0`) only to resolve qualified cross-product dependencies.
It does not forward list filters such as search, state, type, topic, selected products, or list
offsets. The response remains item-rooted and bounded by depth, child, node, and edge caps, and
does not render a global graph.

The graph toolbar also keeps the root-focused isolation contract local and
bounded: reviewers can change `max_depth`, switch between fade or hide for
unrelated nodes, select a graph node without changing the root, and use Reset
scope to restore the incoming root (or clear back to the scaffold when no
incoming root exists). Selection opens a compact side panel. Re-rooting is an
explicit `Set root` action rather than an activation side effect.
Hidden or faded nodes and edges always stay diagnosable through the graph summary
and diagnostics cards; Backboard does not silently drop unrelated blockers from
review context.

### Graph node inspector

Mouse click, Enter, and Space select a graph node and open a compact inspector
without reloading or changing the item-rooted graph query. The panel renders
ID, title, type, state, parent, blockers, blocked items, related refs, and
missing or invalid refs. It paints immediately from the bounded graph payload,
then uses the existing exact `GET /api/items/<id>?product=<product>` route to
fill relationship metadata. Only the compact fields are retained in client
state; raw Markdown content and paths are not copied into the inspector.

Resolved product-qualified items expose explicit Open detail, Set root,
Isolate node, Expand inbound, Expand outbound, Hide node, and Pin node actions.
Missing and topic nodes remain inspectable, while unsupported detail, root, and
expansion actions are visibly disabled. Escape or Close dismisses the panel.

Isolate node changes only the client-side neighborhood focus and is reversible;
it does not change the root URL or fetch an unbounded graph. Inbound and
outbound actions reuse the existing one-hop expansion endpoint and its caps.
Pin and hide are reversible in-memory view state. A pinned node remains visible
through hide isolation and must be unpinned before manual hiding.
A manually hidden node leaves an explicit diagnostic with its retained
dependency-edge count and a Restore action, so hiding never erases blocker
evidence silently.
Inspector, pin, manual-hide, and local-isolate state are excluded from URLs,
saved graph queries, `localStorage`, and `sessionStorage`,
and are cleared with the base graph.

The canvas and inspector use a two-column desktop layout, collapse to one
column at tablet width, and make action buttons single-column at narrow width.
SVG nodes expose button semantics, accessible labels and selection state; panel
actions use native buttons and visible focus treatment.

The same bounded item-rooted graph data now has client-side viewport controls:
zoom out, zoom in, fit all, fit focused subgraph, and reset view. The SVG graph
canvas supports pointer drag panning, mouse-wheel zoom centered on the pointer,
button zoom controls, and focused keyboard shortcuts (`+`/`=`, `-`, `0`, and
arrow-key pan) without changing the bounded query itself. Reset view only
changes the client-side pan/zoom state; it does not change root scope, depth,
isolation mode, URL query state, or fetched graph data.

### One-hop graph expansion overlays

`GET /api/review/graph/expand` returns a read-only delta with schema
`kob.backboard.graph_expansion.v1`. The required `expansion` parameter accepts
exactly four kinds. `inbound` finds blockers and emits blocker-to-anchor edges.
`outbound` finds blocked items and emits anchor-to-blocked edges. `children`
reverse-scans recorded parent refs and emits parent-to-child edges. `related`
treats `relates` as non-directional for discovery, so a one-sided declaration
from either endpoint can place the recorded relation in the delta. Every kind
is fixed at depth one. The route does not accept `max_depth`.

Requests select scope with `product` or comma-separated `products`, identify
the anchor with `item`, and can disambiguate it with `root_product`. Optional
`q`, comma-separated `state`, and comma-separated `type` values filter both the
anchor and neighbors. `max_children_per_node`, `max_total_nodes`, and
`max_total_edges` bound the delta, and each cap is limited to 1,000. The
response echoes the selected products, active query fields, and
`effective_caps`, alongside the resolved `root`, `nodes`, `edges`,
`missing_nodes`, `invalid_refs`, `diagnostics`, count fields, and truncation
flags.

A missing or unknown `expansion` value is a request error and returns HTTP 400
with `graph_expand.expansion_required` or `graph_expand.expansion_invalid`.
Root resolution failures are diagnostic deltas, not transport errors. A
missing `item`, unknown root, ambiguous bare ID, filtered root, or qualified
root outside the selected product scope returns HTTP 200 with an empty delta
and a precise `graph_expand_root_*` diagnostic. Filtered or out-of-scope
neighbors are also omitted with diagnostics rather than widening the request.

Expansion performs a deterministic scan of at most 20,000 primary records in
the selected product scope. If the bound is reached, `scan_truncated` and
`truncated` are true and `graph_expand_scan_truncated` states that completeness
is not claimed. Roots or refs not observed before that stop use bounded-scan
diagnostics instead of being claimed missing.

Server cap application reserves the anchor first, then admits one-hop nodes in
canonical key order within the child and total-node caps. Edges are ordered by
`from`, `to`, `kind`, and `source`, deduplicated, and admitted only when both
endpoints are visible. Missing valid refs and invalid refs remain explicit;
`hidden_node_count` and `hidden_edge_count` report cap losses, and no dangling
edge is returned. Equivalent requests serialize identically, so repeating the
same expansion is idempotent.

In Backboard, expansion is an overlay on the already loaded base graph. The
normal base graph still does not inherit list filters. For each expansion, the
client starts from that stored all-product scope and its graph caps, explicitly
synchronizes the current `q`, selected `state`, and selected `type` filters,
then changes `item`, `root_product`, and `expansion` without reloading the base
graph. Isolation mode and viewport pan/zoom are preserved. Generation and
request sequence guards ignore stale responses, while a failed repeat leaves
the last successful overlay visible.

Composition admits all base nodes and edges first, then overlays in first-click
order. Overlay nodes are sorted and deduplicated by canonical product and item
key. Edges are sorted and deduplicated by normalized endpoints and kind, with
`relates` treated as a non-directional pair. Client node and edge caps still
apply, and edges with dropped endpoints are rejected. The overlay diagnostics
report source, admitted, deduplicated, client-dropped, missing, and server
truncation counts.

Overlay state exists only in memory for the current base graph. It is excluded
from URL state, saved graph queries, workspace records, `localStorage`, and
`sessionStorage`, and is cleared when the base graph scope or workspace
changes. Blocker chain, cycle audit, hierarchy summary, and graph mode claims
remain base-only derived summaries. They are not recomputed from overlay nodes
or edges.

### Saved graph queries

The Focus Graph toolbar can save, list, load, and update browser-local queries.
Each record is versioned safe bounded query metadata: a product-qualified item
root, explicit graph mode, product/state/type/edge-type/direction fields, depth,
node/edge/child caps, and the isolation display option. Backboard keeps at most
50 normalized records and rejects malformed, path-like, unqualified, or
over-limit fields.

Saved records never include private paths or raw graph dumps, and they do not
write canonical backlog data. Loading restores the bounded root, mode, caps,
depth, and display option, then uses the normal item-rooted API. A missing root
therefore degrades to the existing empty/error diagnostics instead of widening
scope or fetching a global graph.

Dependency mode is dependency-only by default: its bounded item-rooted response
may include a native `blocker_chain` object with `root_item`,
`edge_direction_note`, `upstream_blockers`, `downstream_blocked_items`,
`root_blockers`, `jump_targets`, `ranking_basis`, branch counts, and bounded
summary counts/caps. Backboard renders Root blockers, Upstream blockers,
Downstream impact, and Branch evidence before the SVG canvas when that object is
present. Root ordering is explainable bounded review order: visible bounded
impact, shorter path, then stable ID. It is not business priority.

In explicit dependency mode (`mode=dependency`), the graph contains only
`blocks` and `blocked_by` edges and emits `blocker_chain` when the requested
root is unambiguous. An omitted mode preserves legacy broad context for the
internal Focus Graph summary. If duplicate products share a bare root ID and
`root_product` is omitted, the response emits `graph_root_ambiguous` and no
`blocker_chain`; callers provide `root_product=<name>` to disambiguate that
item-rooted graph request.

In explicit structure mode (`mode=structure`), the response adds a bounded
`hierarchy_summary` object derived only from recorded parent refs. Item-rooted
responses expose the direct parent, ancestors nearest-parent first, and a nested
child tree. Topic-rooted responses expose the acyclic visible roots for matching
topic items. Every tree node reports total, visible, and hidden child counts;
the summary echoes depth, child, node, and edge caps plus truncation and gap
counts. Missing, invalid, or cyclic parent evidence is shown as a gap rather
than inferred. Backboard renders the tree with native `<details>` elements so
the structure remains DOM-readable and supports collapse/expand without a
canvas dependency. Structure mode uses parent edges only and does not imply execution order.

In explicit cycles mode (`mode=cycles`), Backboard shows a cycle audit before
the SVG. It reports strongly connected dependency groups from the visible bounded dependency graph,
using only `blocks` and `blocked_by` execution edges. Each group can contain
multiple simple loops, so its count is not a simple-loop or backlog-global count.
The audit presents sorted members, normalized offending edges in blocker-to-blocked
direction, involved-product and cross-product facts, visible dependency node and
edge counts, and the applied graph caps. member jump actions re-root the existing
bounded graph using each member's product-qualified target; they do not fetch a
global graph. A truncated graph warns that the bounded audit may be incomplete
without claiming hidden group counts. The exact empty state is `No dependency cycles found.`
Cycles mode has no `blocker_chain`.

This cycle audit remains bounded, item-rooted, and local: Backboard has no
global graph support. It does not enumerate simple loops or claim
cycles outside the visible bounded dependency graph.

Branch truncation is bounded and diagnosable: parallel and truncated branch
counts, hidden node and edge counts, invalid references, visible dependency edge
counts, and the returned query caps remain visible rather than being inferred.
Jump actions only re-root the existing bounded graph query; they do not request
a global graph. Hierarchy, relates, topic, and product-memory views require
explicit modes (`structure`, `related`, or `product_memory`) rather than being
mixed into dependency mode. Backboard has no global graph support or framework
scope.

`kob-ui.js` is intentionally small and first-party. It owns partial fetch/swap,
delegated partial links, filter debounce support, URL query-state helpers, and
bounded error rendering without npm or a frontend build step.

## Embedded asset layout

The Backboard root shell remains embedded in the native binary to avoid runtime
static-file lookup and Docker packaging drift.

- `assets/index_html.hpp` composes the `/` HTML shell and stitches the embedded
  CSS and page app JavaScript into one response body.
- `assets/backboard_css.hpp` holds the first-party CSS used by the root shell.
- `assets/backboard_app_js.hpp` holds the inline page application JavaScript for
  the root shell.
- `assets/backboard_graph_inspector_js.hpp` holds the bounded graph-node
  inspector, explicit actions, and ephemeral pin/hide diagnostics.
- `assets/kob_ui_js.hpp` holds the first-party `/assets/kob-ui.js` runtime.

## Security Defaults

- Binds to `127.0.0.1` only
- Product path constrained to configured products root
- Mutation endpoints are limited to local KOB review-decision drafts/submissions;
  confirmed target-state actions call existing KOB transition policy and never
  start agents or dispatch work.

## Build (Linux)

```bash
cmake --preset linux-ninja-gcc
cmake --build --preset build-linux
./build/linux-ninja-gcc/apps/kano_backlog_webview/kano_backlog_webview
```

or

```bash
./scripts/build/build_linux_gcc.sh
```

## Build (Windows, Ninja + MSVC)

Use the C++ convention skill guidance to pin MSVC toolset before CMake if needed.

```bat
cmake --preset windows-ninja-msvc
cmake --build --preset build-windows
build\windows-ninja-msvc\apps\kano_backlog_webview\Debug\kano_backlog_webview.exe
```

or

```bat
scripts\build\build_win_ninja_msvc.bat
```

## Runtime Configuration

- Backlog products root:
  - default: `_kano/backlog/products`
  - env: `KANO_BACKLOG_PRODUCTS_ROOT`
  - arg: `--backlog-root <path>`
- Port:
  - default: `8787`
  - env: `KANO_WEBVIEW_PORT`
  - arg: `--port <number>`
- Bind host:
  - default: `127.0.0.1`
  - env: `KANO_WEBVIEW_HOST`
  - arg: `--host <address>`

## Docker Compose

From the repository root:

```bash
pixi run webview-docker
```

The Docker path binds the webview to `0.0.0.0` inside the container, publishes
it on host port `8799`, mounts `../_kano/backlog` read-only at
`/workspace/_kano/backlog`, and uses Docker's `unless-stopped` restart policy.
