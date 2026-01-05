#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
    "new": ("New Work", "state IN ('Proposed','Planned','Ready')"),
    "inprogress": ("InProgress Work", "state IN ('InProgress','Review','Blocked')"),
    "done": ("Done Work", "state IN ('Done','Dropped')"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a Markdown dashboard view from the SQLite backlog index."
    )
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
        choices=["new", "inprogress", "done"],
        required=True,
        help="Dashboard preset to render (required).",
    )
    parser.add_argument(
        "--output",
        help=(
            "Output markdown file path. Default: `<backlog-root>/views/Dashboard_DBIndex_<Preset>.md`."
        ),
    )
    parser.add_argument(
        "--title",
        help="Optional title override (default derived from preset).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum rows included (default: 500).",
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Agent identity running the script (required, used for auditability).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned output path and exit.",
    )
    return parser.parse_args()


def ensure_under_allowed(path: Path, allowed_roots: List[Path], label: str) -> Path:
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(root) for root in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def now_local_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


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
    uri = f"file:{db_path.as_posix()}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA query_only = ON")
    return conn


def preset_query(preset: str) -> Tuple[str, Sequence[Any]]:
    _, where = PRESETS[preset]
    sql = (
        "SELECT id, type, state, priority, title, source_path, updated "
        "FROM items WHERE "
        + where
        + " ORDER BY "
        + "CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 99 END, "
        + "updated DESC, id ASC LIMIT ?"
    )
    return sql, ()


def main() -> int:
    args = parse_args()
    _ = args.agent  # required; recorded via command args in audit logs

    repo_root = Path.cwd().resolve()
    allowed_roots = allowed_roots_for_repo(repo_root)

    backlog_root = Path(args.backlog_root)
    if not backlog_root.is_absolute():
        backlog_root = (repo_root / backlog_root).resolve()
    root = ensure_under_allowed(backlog_root, allowed_roots, "backlog-root")

    config_path = resolve_config_for_backlog_root(repo_root, backlog_root, args.config)
    config = load_config_with_defaults(repo_root=repo_root, config_path=config_path)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    db_path = resolve_db_path(repo_root, backlog_root, config, args.db_path)
    ensure_under_allowed(db_path, allowed_roots, "db-path")

    title_default, _ = PRESETS[args.preset]
    title = args.title or title_default

    output_name = {
        "new": "Dashboard_DBIndex_New.md",
        "inprogress": "Dashboard_DBIndex_InProgress.md",
        "done": "Dashboard_DBIndex_Done.md",
    }[args.preset]
    output_path = Path(args.output) if args.output else (backlog_root / "views" / output_name)
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()
    output_root = ensure_under_allowed(output_path, allowed_roots, "output")
    if output_root != root:
        raise SystemExit("output must share the same root as backlog-root.")

    if args.dry_run:
        print(f"Output: {output_path}")
        print(f"DB: {db_path}")
        return 0

    if not db_path.exists():
        raise SystemExit(f"DB does not exist: {db_path}\nRun build_sqlite_index.py first.")

    sql, params = preset_query(args.preset)
    with open_readonly(db_path) as conn:
        rows = conn.execute(sql, (args.limit,)).fetchall()

    out: List[str] = []
    out.append(f"# {title}")
    out.append("")
    out.append(f"Generated: {now_local_stamp()}")
    out.append(f"Source: SQLite index (`{db_path.as_posix()}`)")
    out.append(f"Preset: `{args.preset}`")
    out.append("")

    if not rows:
        out.append("_No items._")
        out.append("")
    else:
        for item_id, item_type, state, priority, title_text, source_path, updated in rows:
            text = f"{item_id} {title_text}".strip()
            meta = " ".join(
                part
                for part in [
                    f"type={item_type}" if item_type else "",
                    f"state={state}" if state else "",
                    f"priority={priority}" if priority else "",
                    f"updated={updated}" if updated else "",
                ]
                if part
            )
            suffix = f" ({meta})" if meta else ""
            rel = str(source_path or "").replace("\\", "/")
            if rel:
                out.append(f"- [{text}]({rel}){suffix}")
            else:
                out.append(f"- {text}{suffix}")
        out.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
