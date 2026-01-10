#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from config_loader import get_config_value, load_config_with_defaults, validate_config  # noqa: E402
from context import find_platform_root, get_product_root, get_sandbox_root_or_none, resolve_product_name  # noqa: E402
from product_args import add_product_arguments, get_product_and_sandbox_flags  # noqa: E402


STATE_GROUPS = {
    "Proposed": "New",
    "Planned": "New",
    "Ready": "New",
    "New": "New",
    "InProgress": "InProgress",
    "Review": "InProgress",
    "Blocked": "InProgress",
    "Done": "Done",
    "Dropped": "Done",
}

PERSONAS = {"developer", "pm", "qa"}


@dataclass(frozen=True)
class ItemRow:
    product: str
    id: str
    type: str
    title: str
    state: str
    priority: str
    updated: str
    source_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic persona-aware project status report (Markdown)."
    )
    parser.add_argument(
        "--source",
        choices=["auto", "files", "sqlite"],
        default="auto",
        help="Data source (default: auto; prefer sqlite when index.enabled=true and DB exists).",
    )
    parser.add_argument(
        "--items-root",
        default="_kano/backlog/items",
        help="Backlog items root (default: _kano/backlog/items).",
    )
    parser.add_argument(
        "--backlog-root",
        help="Backlog root path override (default: parent of --items-root).",
    )
    parser.add_argument(
        "--config",
        help="Optional config path override (default: KANO_BACKLOG_CONFIG_PATH or <backlog-root>/_config/config.json).",
    )
    parser.add_argument(
        "--db-path",
        help="SQLite DB path override (default: config index.path or <backlog-root>/_index/backlog.sqlite3).",
    )
    parser.add_argument(
        "--persona",
        help="Persona (developer|pm|qa). Defaults to config mode.persona, then developer.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output markdown file path.",
    )
    parser.add_argument(
        "--products",
        action="append",
        help="Comma-separated product names to aggregate (repeatable).",
    )
    parser.add_argument(
        "--all-products",
        action="store_true",
        help="Aggregate across all products under the platform root.",
    )
    add_product_arguments(parser)
    return parser.parse_args()


def normalize_persona(raw: Optional[str]) -> str:
    if not raw:
        return "developer"
    value = raw.strip().lower()
    return value if value in PERSONAS else "developer"


def parse_products_values(values: Optional[List[str]]) -> List[str]:
    if not values:
        return []
    products: List[str] = []
    for raw in values:
        if not raw:
            continue
        for part in raw.split(","):
            name = part.strip()
            if name:
                products.append(name)
    deduped: List[str] = []
    seen: set[str] = set()
    for name in products:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


def list_all_products(platform_root: Path) -> List[str]:
    products_dir = platform_root / "products"
    if not products_dir.exists():
        return []
    names: List[str] = []
    for entry in sorted(products_dir.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            names.append(entry.name)
    return names


def resolve_config_for_backlog_root(repo_root: Path, backlog_root: Path, cli_config: Optional[str]) -> Optional[str]:
    if cli_config is not None:
        return cli_config
    if os.getenv("KANO_BACKLOG_CONFIG_PATH"):
        return None
    candidate = backlog_root / "_config" / "config.json"
    if candidate.exists():
        return str(candidate)
    return None


def resolve_db_path(repo_root: Path, backlog_root: Path, config: Dict[str, object], cli_db_path: Optional[str]) -> Path:
    db_path_raw = cli_db_path or get_config_value(config, "index.path")
    if not db_path_raw:
        db_path_raw = str((backlog_root / "_index" / "backlog.sqlite3").resolve())
    db_path = Path(str(db_path_raw))
    if not db_path.is_absolute():
        db_path = (repo_root / db_path).resolve()
    return db_path


def is_legacy_plural_product_items_path(path: Path) -> bool:
    parts = list(path.as_posix().split("/"))
    try:
        items_idx = parts.index("items")
    except ValueError:
        return False
    if "products" not in parts:
        return False
    if items_idx + 1 >= len(parts):
        return False
    next_dir = parts[items_idx + 1]
    legacy_plural = {"epics", "features", "tasks", "userstories", "bugs"}
    return next_dir in legacy_plural


def _strip_quotes(raw: str) -> str:
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", "\""):
        return v[1:-1]
    return v


def _parse_frontmatter_quick(path: Path) -> Tuple[Dict[str, str], str]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}, content
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content
    data: Dict[str, str] = {}
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        data[key.strip()] = _strip_quotes(raw)
    if end is None:
        return data, content
    body = "\n".join(lines[end + 1 :])
    return data, body


def _parse_date(value: str) -> Optional[dt.date]:
    v = (value or "").strip()
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _priority_rank(p: str) -> int:
    p = (p or "").strip().upper()
    if p.startswith("P") and p[1:].isdigit():
        return int(p[1:])
    return 9


def _extract_section(body: str, heading: str) -> List[str]:
    target = heading.strip().lower()
    lines = body.splitlines()
    start = None
    start_level = None
    for i, line in enumerate(lines):
        s = line.strip()
        if not s.startswith("#"):
            continue
        hashes = len(s) - len(s.lstrip("#"))
        title = s.lstrip("#").strip().lower()
        if title == target:
            start = i + 1
            start_level = hashes
            break
    if start is None or start_level is None:
        return []
    out: List[str] = []
    for line in lines[start:]:
        s = line.strip()
        if s.startswith("#"):
            level = len(s) - len(s.lstrip("#"))
            if level <= start_level:
                break
        if not s:
            continue
        out.append(line.rstrip())
    # Keep it bounded.
    return out[:30]


def _extract_acceptance_snippet(repo_root: Path, item: ItemRow) -> List[str]:
    if not item.source_path:
        return []
    rel = Path(item.source_path.replace("\\", "/"))
    path = (repo_root / rel).resolve()
    if not path.exists():
        return []
    _, body = _parse_frontmatter_quick(path)
    return _extract_section(body, "Acceptance Criteria")


def iter_items_from_files(repo_root: Path, items_root: Path, product_name: str) -> Iterable[ItemRow]:
    for path in items_root.rglob("*.md"):
        if is_legacy_plural_product_items_path(path):
            continue
        if path.name == "README.md" or path.name.endswith(".index.md"):
            continue
        data, _body = _parse_frontmatter_quick(path)
        item_id = str(data.get("id", "")).strip()
        item_type = str(data.get("type", "")).strip()
        state = str(data.get("state", "")).strip()
        title = str(data.get("title", "")).strip()
        priority = str(data.get("priority", "P2")).strip() or "P2"
        updated = str(data.get("updated", "")).strip()
        if not item_id or not item_type or not state:
            continue
        source_path = str(path.relative_to(repo_root).as_posix()) if repo_root in path.parents else path.as_posix()
        yield ItemRow(
            product=product_name,
            id=item_id,
            type=item_type,
            title=title or item_id,
            state=state,
            priority=priority,
            updated=updated,
            source_path=source_path,
        )


def iter_items_from_sqlite(db_path: Path, default_product: str) -> Iterable[ItemRow]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT COALESCE(product, ''), id, type, title, COALESCE(state, ''), "
            "COALESCE(priority, 'P2'), COALESCE(updated, ''), COALESCE(source_path, '') "
            "FROM items"
        ).fetchall()
        for r in rows:
            product_name, item_id, item_type, title, state, priority, updated, source_path = r
            if not item_id or not item_type or not state:
                continue
            yield ItemRow(
                product=str(product_name) if product_name else default_product,
                id=str(item_id),
                type=str(item_type),
                title=str(title) if title else str(item_id),
                state=str(state),
                priority=str(priority) if priority else "P2",
                updated=str(updated) if updated else "",
                source_path=str(source_path) if source_path else "",
            )
    finally:
        conn.close()


def select_items(
    rows: Sequence[ItemRow],
    *,
    states: Sequence[str],
    types: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
    sort: str = "priority_then_updated",
) -> List[ItemRow]:
    wanted_states = {s for s in states}
    wanted_types = {t for t in types} if types else None
    selected = []
    for r in rows:
        if r.state not in wanted_states:
            continue
        if wanted_types is not None and r.type not in wanted_types:
            continue
        selected.append(r)
    if sort == "updated_desc":
        selected.sort(key=lambda x: (x.updated or ""), reverse=True)
    else:
        selected.sort(key=lambda x: (_priority_rank(x.priority), x.updated or "", x.id))
    if limit is not None:
        return selected[:limit]
    return selected


def render_bullets(rows: Sequence[ItemRow], *, limit: int) -> List[str]:
    lines: List[str] = []
    if not rows:
        return ["- (none)"]
    for r in rows[:limit]:
        prefix = f"[{r.product}] " if r.product else ""
        lines.append(f"- {prefix}`{r.id}` [{r.type}] ({r.state}, {r.priority}) {r.title}")
    if len(rows) > limit:
        lines.append(f"- …and {len(rows) - limit} more")
    return lines


def render_report(repo_root: Path, *, persona: str, rows: Sequence[ItemRow], source_label: str, products_label: str) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: List[str] = []
    lines.append(f"# Project Status Report ({persona})")
    lines.append("")
    lines.append(f"- Generated: {now}")
    lines.append(f"- Source: `{source_label}`")
    lines.append(products_label)
    lines.append("")

    counts_by_group: Dict[str, int] = {"New": 0, "InProgress": 0, "Done": 0}
    counts_by_state: Dict[str, int] = {}
    for r in rows:
        group = STATE_GROUPS.get(r.state, "New")
        counts_by_group[group] = counts_by_group.get(group, 0) + 1
        counts_by_state[r.state] = counts_by_state.get(r.state, 0) + 1

    lines.append("## Snapshot")
    lines.append("")
    lines.append(f"- New: **{counts_by_group.get('New', 0)}** (Proposed/Planned/Ready)")
    lines.append(f"- InProgress: **{counts_by_group.get('InProgress', 0)}** (InProgress/Blocked/Review)")
    lines.append(f"- Done: **{counts_by_group.get('Done', 0)}** (Done/Dropped)")
    lines.append("")

    today = dt.datetime.now(dt.timezone.utc).date()
    stale_cutoff = today - dt.timedelta(days=7)

    in_progress_all = select_items(rows, states=["InProgress", "Blocked", "Review"], limit=None)
    ready_all = select_items(rows, states=["Ready"], limit=None)
    blocked_all = select_items(rows, states=["Blocked"], limit=None)

    def is_stale(item: ItemRow) -> bool:
        d = _parse_date(item.updated)
        return bool(d and d < stale_cutoff)

    stale_in_progress = [r for r in in_progress_all if is_stale(r)]
    high_priority_new = [r for r in select_items(rows, states=["Proposed", "Planned", "Ready"], limit=None) if _priority_rank(r.priority) <= 1]

    if persona == "developer":
        lines.append("## What to focus on (developer)")
        lines.append("")
        lines.append("### Continue (InProgress/Blocked/Review)")
        lines += render_bullets(select_items(rows, states=["InProgress", "Blocked", "Review"], types=["Task", "Bug"], limit=10), limit=10)
        lines.append("")
        lines.append("### Next (Ready)")
        lines += render_bullets(select_items(rows, states=["Ready"], types=["Task", "Bug"], limit=10), limit=10)
        lines.append("")
        if blocked_all:
            lines.append("### Blockers")
            lines += render_bullets(blocked_all[:10], limit=10)
            lines.append("")
        recent_done = select_items(rows, states=["Done"], types=["Task", "Bug"], limit=10, sort="updated_desc")
        lines.append("### Recently completed (sanity check)")
        lines += render_bullets(recent_done, limit=10)
        lines.append("")

    elif persona == "pm":
        lines.append("## Executive view (pm)")
        lines.append("")
        active_scope = select_items(rows, states=["InProgress", "Blocked", "Review", "Ready", "Planned"], types=["Epic", "Feature"], limit=10)
        proposed_scope = select_items(rows, states=["Proposed"], types=["Epic", "Feature"], limit=10)
        lines.append("### Active Epics / Features")
        lines += render_bullets(active_scope, limit=10)
        lines.append("")
        lines.append("### New proposals (Epics / Features)")
        lines += render_bullets(proposed_scope, limit=10)
        lines.append("")

        lines.append("### Risks (derived)")
        lines.append("")
        lines.append(f"- Blocked items: **{len(blocked_all)}**")
        lines.append(f"- Stale in-progress (no update in 7d): **{len(stale_in_progress)}**")
        lines.append(f"- High priority in New (P0/P1): **{len(high_priority_new)}**")
        lines.append("")
        if stale_in_progress:
            lines.append("### Stale work (check ownership / unblock)")
            lines += render_bullets(stale_in_progress[:10], limit=10)
            lines.append("")

    else:  # qa
        lines.append("## Verification view (qa)")
        lines.append("")
        review_queue = select_items(rows, states=["Review"], limit=15)
        open_bugs = select_items(rows, states=["Proposed", "Planned", "Ready", "InProgress", "Blocked", "Review"], types=["Bug"], limit=15)
        lines.append("### Review queue (needs verification)")
        lines += render_bullets(review_queue, limit=15)
        lines.append("")
        lines.append("### Bugs to triage")
        lines += render_bullets(open_bugs, limit=15)
        lines.append("")

        recent_done = select_items(rows, states=["Done"], types=["Task", "Bug", "Feature"], limit=None, sort="updated_desc")
        recent_done = [r for r in recent_done if _parse_date(r.updated) and _parse_date(r.updated) >= stale_cutoff][:10]
        lines.append("### Recently done (suggested regression check)")
        lines += render_bullets(recent_done, limit=10)
        lines.append("")

        lines.append("### Suggested test notes (best-effort)")
        lines.append("")
        targets = (review_queue + recent_done)[:5]
        if not targets:
            lines.append("- (none)")
        for item in targets:
            ac = _extract_acceptance_snippet(repo_root, item)
            prefix = f"[{item.product}] " if item.product else ""
            lines.append(f"- {prefix}`{item.id}`: {item.title}")
            if ac:
                for line in ac[:8]:
                    lines.append(f"  - {line.strip()}")
            else:
                lines.append("  - (No Acceptance Criteria section found; verify expected behavior + run relevant tests.)")
        lines.append("")

    lines.append("## How to refresh")
    lines.append("")
    lines.append("Use `view_refresh_dashboards.py` to regenerate dashboards and persona outputs.")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()

    products = parse_products_values(getattr(args, "products", None))
    if getattr(args, "all_products", False):
        if products:
            raise SystemExit("--products and --all-products cannot be used together.")
        products = list_all_products(find_platform_root(repo_root))

    product_name, use_sandbox = get_product_and_sandbox_flags(args)
    if product_name and products:
        raise SystemExit("Use either --product or --products/--all-products, not both.")

    def collect_for_root(backlog_root: Path, display_product: str) -> Tuple[List[ItemRow], str, Dict[str, object]]:
        config_path = resolve_config_for_backlog_root(repo_root, backlog_root, args.config)
        config = load_config_with_defaults(repo_root=repo_root, config_path=config_path, product_name=display_product or None)
        errors = validate_config(config)
        if errors:
            raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

        db_path = resolve_db_path(repo_root, backlog_root, config, args.db_path)
        index_enabled = bool(get_config_value(config, "index.enabled", False))

        if args.source == "sqlite":
            use_sqlite = True
        elif args.source == "files":
            use_sqlite = False
        else:
            use_sqlite = bool(index_enabled and db_path.exists())

        if use_sqlite:
            rows = list(iter_items_from_sqlite(db_path, display_product))
            source_label = f"sqlite:{db_path.relative_to(repo_root) if repo_root in db_path.parents else db_path}"
            return rows, source_label, config

        items_root = backlog_root / "items"
        rows = list(iter_items_from_files(repo_root, items_root, product_name=display_product or ""))
        source_label = f"files:{items_root.relative_to(repo_root) if repo_root in items_root.parents else items_root}"
        return rows, source_label, config

    all_rows: List[ItemRow] = []
    sources: List[str] = []
    persona_from_config: Optional[str] = None

    if products:
        platform_root = find_platform_root(repo_root)
        for name in products:
            root = (
                (get_sandbox_root_or_none(name, platform_root) or (platform_root / "sandboxes" / name))
                if use_sandbox
                else get_product_root(name, platform_root)
            )
            rows, source_label, cfg = collect_for_root(root, name)
            all_rows.extend(rows)
            sources.append(f"{name}:{source_label}")
            if persona_from_config is None:
                persona_from_config = str(get_config_value(cfg, "mode.persona") or "")
    else:
        backlog_root = Path(args.backlog_root) if args.backlog_root else Path(args.items_root).parent
        if not backlog_root.is_absolute():
            backlog_root = (repo_root / backlog_root).resolve()

        if product_name and (args.backlog_root is None or str(args.backlog_root).strip() == "_kano/backlog"):
            platform_root = find_platform_root(repo_root)
            resolved = resolve_product_name(product_name, platform_root=platform_root)
            backlog_root = (
                (get_sandbox_root_or_none(resolved, platform_root) or (platform_root / "sandboxes" / resolved))
                if use_sandbox
                else get_product_root(resolved, platform_root)
            )
            product_name = resolved

        rows, source_label, cfg = collect_for_root(backlog_root, product_name or "")
        all_rows = rows
        sources = [source_label]
        persona_from_config = str(get_config_value(cfg, "mode.persona") or "")

    persona = normalize_persona(args.persona or persona_from_config)
    source_label = ", ".join(sources)

    output = Path(args.output)
    if not output.is_absolute():
        output = (repo_root / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if products:
        products_label = f"- Products: {', '.join(f'`{p}`' for p in products)}"
    elif product_name:
        products_label = f"- Product: `{product_name}`"
    else:
        products_label = "- Product: `(unknown)`"

    content = render_report(
        repo_root,
        persona=persona,
        rows=all_rows,
        source_label=source_label,
        products_label=products_label,
    )
    output.write_text(content, encoding="utf-8")
    print(f"Wrote: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
