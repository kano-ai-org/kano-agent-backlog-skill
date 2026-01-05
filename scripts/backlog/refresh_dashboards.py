#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh generated Markdown dashboards (optionally using SQLite index)."
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
        "--agent",
        required=True,
        help="Agent identity running the script (required, used for auditability).",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "files", "sqlite"],
        default="auto",
        help="Dashboard data source (default: auto).",
    )
    parser.add_argument(
        "--refresh-index",
        choices=["auto", "skip", "rebuild", "incremental"],
        default="auto",
        help="Whether to refresh the SQLite index before rendering (default: auto).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing.",
    )
    return parser.parse_args()


def ensure_under_allowed(path: Path, allowed_roots: List[Path], label: str) -> Path:
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(root) for root in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def resolve_config_for_backlog_root(backlog_root: Path, cli_config: Optional[str]) -> Optional[str]:
    if cli_config is not None:
        return cli_config
    if os.getenv("KANO_BACKLOG_CONFIG_PATH"):
        return None
    candidate = backlog_root / "_config" / "config.json"
    if candidate.exists():
        return str(candidate)
    return None


def run_cmd(cmd: List[str], dry_run: bool) -> None:
    if dry_run:
        print("[DRY] " + " ".join(cmd))
        return
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"Command failed: {' '.join(cmd)}")


def main() -> int:
    args = parse_args()
    agent = args.agent

    repo_root = Path.cwd().resolve()
    allowed_roots = allowed_roots_for_repo(repo_root)

    backlog_root = Path(args.backlog_root)
    if not backlog_root.is_absolute():
        backlog_root = (repo_root / backlog_root).resolve()
    root = ensure_under_allowed(backlog_root, allowed_roots, "backlog-root")

    config_path = resolve_config_for_backlog_root(backlog_root, args.config)
    config = load_config_with_defaults(repo_root=repo_root, config_path=config_path)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    index_enabled = bool(get_config_value(config, "index.enabled", False))
    backend = str(get_config_value(config, "index.backend") or "sqlite").strip().lower()

    refresh = args.refresh_index
    if refresh == "auto":
        refresh = "incremental" if index_enabled and backend == "sqlite" else "skip"

    python = sys.executable
    scripts_root = Path(__file__).resolve().parents[1]

    if refresh != "skip":
        if backend != "sqlite":
            print(f"Skip index refresh: backend={backend} (only sqlite supported).")
        else:
            build = scripts_root / "indexing" / "build_sqlite_index.py"
            cmd = [python, str(build), "--backlog-root", str(backlog_root), "--agent", agent, "--mode", refresh]
            if args.config:
                cmd.extend(["--config", args.config])
            run_cmd(cmd, args.dry_run)

    generate = scripts_root / "backlog" / "generate_view.py"
    items_root = backlog_root / "items"
    views_root = backlog_root / "views"

    dashboards = [
        ("New,InProgress", "InProgress Work", views_root / "Dashboard_PlainMarkdown_Active.md"),
        ("New", "New Work", views_root / "Dashboard_PlainMarkdown_New.md"),
        ("Done", "Done Work", views_root / "Dashboard_PlainMarkdown_Done.md"),
    ]

    for groups, title, output in dashboards:
        cmd = [
            python,
            str(generate),
            "--source",
            args.source,
            "--items-root",
            str(items_root),
            "--backlog-root",
            str(backlog_root),
            "--output",
            str(output),
            "--groups",
            groups,
            "--title",
            title,
        ]
        if args.config:
            cmd.extend(["--config", args.config])
        run_cmd(cmd, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))

