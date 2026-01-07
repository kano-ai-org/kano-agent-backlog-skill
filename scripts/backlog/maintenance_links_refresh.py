#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run link autofix -> index rebuild -> dashboard refresh (product-aware)."
    )
    parser.add_argument("--backlog-root", default="_kano/backlog", help="Backlog root (default: _kano/backlog)")
    parser.add_argument("--product", default=None, help="Product name (optional; forwarded to refresh)")
    parser.add_argument("--db-path", default=None, help="SQLite index path override (optional)")
    parser.add_argument("--agent", default="copilot", help="Agent name for audit/log (default: copilot)")
    parser.add_argument("--dry-run-fix", action="store_true", help="Run autofix in dry-run mode only")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    backlog_root = (repo_root / args.backlog_root).resolve()
    if not backlog_root.exists():
        raise SystemExit(f"Backlog root not found: {backlog_root}")

    py = sys.executable

    # 1) Autofix links (relates/blocks/blocked_by)
    fix_script = repo_root / "skills" / "kano-agent-backlog-skill" / "scripts" / "backlog" / "link_disambiguation_fix.py"
    fix_cmd = [py, str(fix_script), "--backlog-root", str(args.backlog_root)]
    if args.dry_run_fix:
        fix_cmd.append("--dry-run")
    print("[1/3] link autofix:", " ".join(fix_cmd))
    run(fix_cmd)

    # 2) Rebuild index
    index_script = repo_root / "skills" / "kano-agent-backlog-skill" / "scripts" / "indexing" / "build_sqlite_index.py"
    idx_cmd = [py, str(index_script), "--agent", args.agent, "--mode", "rebuild", "--backlog-root", str(args.backlog_root)]
    if args.db_path:
        idx_cmd.extend(["--db-path", args.db_path])
    print("[2/3] index rebuild:", " ".join(idx_cmd))
    run(idx_cmd)

    # 3) Refresh dashboards
    refresh_script = repo_root / "skills" / "kano-agent-backlog-skill" / "scripts" / "backlog" / "view_refresh_dashboards.py"
    ref_cmd = [py, str(refresh_script), "--agent", args.agent, "--backlog-root", str(args.backlog_root)]
    if args.product:
        ref_cmd.extend(["--product", args.product])
    print("[3/3] dashboard refresh:", " ".join(ref_cmd))
    run(ref_cmd)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
