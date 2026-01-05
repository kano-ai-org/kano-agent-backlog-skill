#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from config_loader import (  # noqa: E402
    allowed_roots_for_repo,
    get_config_value,
    load_config_with_defaults,
    resolve_allowed_root,
    validate_config,
)


PRESETS = {
    "new": "state IN ('Proposed','Planned','Ready')",
    "inprogress": "state IN ('InProgress','Review','Blocked')",
    "done": "state IN ('Done','Dropped')",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the rebuildable SQLite backlog index (read-only).")
    parser.add_argument(
        "--backlog-root",
        default="_kano/backlog",
        help="Backlog root path (default: _kano/backlog).",
    )
    parser.add_argument(
        "--config",
        help=(
            "Optional config path override. When omitted, uses KANO_BACKLOG_CONFIG_PATH if set, "
            "otherwise `<backlog-root>/_config/config.json` when present."
        ),
    )
    parser.add_argument(
        "--db-path",
        help=(
            "SQLite DB path override. If omitted, uses config index.path or defaults to "
            "`<backlog-root>/_index/backlog.sqlite3`."
        ),
    )
    parser.add_argument(
        "--preset",
        choices=["new", "inprogress", "done", "recent-updated", "by-tag", "by-parent"],
        help="Preset query (recommended).",
    )
    parser.add_argument("--tag", help="Tag value for --preset by-tag.")
    parser.add_argument("--parent", help="Parent item id for --preset by-parent.")
    parser.add_argument(
        "--sql",
        help="Advanced: custom read-only SQL (SELECT/WITH only, single statement).",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "table"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum rows returned for presets (default: 200).",
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Agent identity running the script (required, used for auditability).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved DB path and exit.",
    )
    return parser.parse_args()


def ensure_under_allowed(path: Path, allowed_roots: List[Path], label: str) -> Path:
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(root) for root in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_config_for_backlog_root(repo_root: Path, backlog_root: Path, cli_config: Optional[str]) -> Optional[str]:
    if cli_config is not None:
        return cli_config
    if os.getenv("KANO_BACKLOG_CONFIG_PATH"):
        return None
    candidate = backlog_root / "_config" / "config.json"
    if candidate.exists():
        return str(candidate)
    return None


def resolve_db_path(repo_root: Path, backlog_root: Path, config: Dict[str, Any], cli_db_path: Optional[str]) -> Path:
    db_path_raw = cli_db_path or get_config_value(config, "index.path")
    if not db_path_raw:
        db_path_raw = str((backlog_root / "_index" / "backlog.sqlite3").resolve())
    db_path = Path(str(db_path_raw))
    if not db_path.is_absolute():
        db_path = (repo_root / db_path).resolve()
    return db_path


def open_readonly(db_path: Path) -> sqlite3.Connection:
    # Prefer URI read-only + immutable to avoid journal/wal writes.
    uri = f"file:{db_path.as_posix()}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA query_only = ON")
    return conn


_SQL_FIRST_TOKEN = re.compile(r"^\\s*(with|select)\\b", re.IGNORECASE)


def assert_select_only(sql: str) -> None:
    if not sql or not sql.strip():
        raise SystemExit("--sql is empty.")
    if ";" in sql.strip().rstrip(";"):
        raise SystemExit("--sql must be a single statement (no ';' separators).")
    if _SQL_FIRST_TOKEN.search(sql) is None:
        raise SystemExit("--sql must start with SELECT or WITH.")


def preset_sql(args: argparse.Namespace) -> Tuple[str, Sequence[Any]]:
    if args.preset in ("new", "inprogress", "done"):
        where = PRESETS[args.preset]
        sql = (
            "SELECT id, type, state, priority, title, source_path, updated "
            "FROM items WHERE "
            + where
            + " ORDER BY "
            + ("updated DESC" if args.preset == "done" else "priority ASC, updated DESC")
            + " LIMIT ?"
        )
        return sql, (args.limit,)

    if args.preset == "recent-updated":
        sql = (
            "SELECT id, type, state, priority, title, source_path, updated "
            "FROM items ORDER BY updated DESC LIMIT ?"
        )
        return sql, (args.limit,)

    if args.preset == "by-tag":
        if not args.tag:
            raise SystemExit("--tag is required for --preset by-tag.")
        sql = (
            "SELECT i.id, i.type, i.state, i.priority, i.title, i.source_path, i.updated "
            "FROM items i JOIN item_tags t ON t.item_id = i.id "
            "WHERE t.tag = ? ORDER BY i.priority ASC, i.updated DESC LIMIT ?"
        )
        return sql, (args.tag, args.limit)

    if args.preset == "by-parent":
        if not args.parent:
            raise SystemExit("--parent is required for --preset by-parent.")
        sql = (
            "SELECT id, type, state, priority, title, source_path, updated "
            "FROM items WHERE parent_id = ? ORDER BY priority ASC, updated DESC LIMIT ?"
        )
        return sql, (args.parent, args.limit)

    raise SystemExit("Provide --preset or --sql.")


def rows_to_dicts(cursor: sqlite3.Cursor, rows: Sequence[Sequence[Any]]) -> List[Dict[str, Any]]:
    columns = [col[0] for col in cursor.description or []]
    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append({columns[i]: row[i] for i in range(len(columns))})
    return out


def print_markdown(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        print("_No results._")
        return
    for row in rows:
        text = f"{row.get('id','')} {row.get('title','')}".strip()
        path = str(row.get("source_path") or "").replace("\\", "/")
        meta = " ".join(
            part
            for part in [
                f"type={row.get('type')}" if row.get("type") else "",
                f"state={row.get('state')}" if row.get("state") else "",
                f"priority={row.get('priority')}" if row.get("priority") else "",
                f"updated={row.get('updated')}" if row.get("updated") else "",
            ]
            if part
        )
        suffix = f" ({meta})" if meta else ""
        if path:
            print(f"- [{text}]({path}){suffix}")
        else:
            print(f"- {text}{suffix}")


def print_table(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        print("No results.")
        return
    cols = list(rows[0].keys())
    widths = {c: max(len(c), *(len(str(r.get(c, ''))) for r in rows)) for c in cols}
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for r in rows:
        print(" | ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def main() -> int:
    args = parse_args()
    _ = args.agent  # required; recorded via command args in audit logs

    repo_root = Path.cwd().resolve()
    allowed_roots = allowed_roots_for_repo(repo_root)

    backlog_root = Path(args.backlog_root)
    if not backlog_root.is_absolute():
        backlog_root = (repo_root / backlog_root).resolve()
    ensure_under_allowed(backlog_root, allowed_roots, "backlog-root")

    config_path = resolve_config_for_backlog_root(repo_root, backlog_root, args.config)
    config = load_config_with_defaults(repo_root=repo_root, config_path=config_path)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    db_path = resolve_db_path(repo_root, backlog_root, config, args.db_path)
    ensure_under_allowed(db_path, allowed_roots, "db-path")

    if args.dry_run:
        print(f"DB path: {db_path}")
        return 0

    if not db_path.exists():
        raise SystemExit(f"DB does not exist: {db_path}\nRun build_sqlite_index.py first.")

    if args.sql and args.preset:
        raise SystemExit("Use either --preset or --sql, not both.")

    if args.sql:
        assert_select_only(args.sql)
        sql = args.sql
        params: Sequence[Any] = ()
    else:
        sql, params = preset_sql(args)

    with open_readonly(db_path) as conn:
        cursor = conn.execute(sql, tuple(params))
        rows = cursor.fetchall()
        rows_dict = rows_to_dicts(cursor, rows)

    if args.format == "json":
        print(json.dumps({"generated_at_utc": now_utc_iso(), "rows": rows_dict}, ensure_ascii=False, indent=2))
        return 0
    if args.format == "table":
        print_table(rows_dict)
        return 0
    print_markdown(rows_dict)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))

