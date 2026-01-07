#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import datetime
from pathlib import Path

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from product_args import add_product_arguments  # noqa: E402
from config_loader import (
    allowed_roots_for_repo,
    load_config_with_defaults,
    validate_config,
)

BACKLOG_DIR = Path(__file__).resolve().parents[1] / "backlog"
if str(BACKLOG_DIR) not in sys.path:
    sys.path.insert(0, str(BACKLOG_DIR))
from lib.index import BacklogIndex  # noqa: E402
from lib.resolver import resolve_ref  # noqa: E402

PLAN_TEMPLATE = """# Plan Checklist\n\n- Define scope & constraints\n- Identify deliverables\n- List tasks & owners\n- Risks & mitigations\n- Verification steps\n"""

NOTES_TEMPLATE = """# Notes\n\n- Observations\n- Questions\n- Decisions (mark with 'Decision:' to promote)\n"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize local workset cache for a backlog item.")
    parser.add_argument("--item", required=True, help="Backlog item ref (id/uid/id@uidshort)")
    parser.add_argument("--agent", required=True, help="Agent name for worklog")
    parser.add_argument(
        "--cache-root",
        default="_kano/backlog/sandboxes/.cache",
        help="Cache root (default: _kano/backlog/sandboxes/.cache)",
    )
    parser.add_argument("--config", help="Optional config path override")
    add_product_arguments(parser)
    return parser.parse_args()


def ensure_under_allowed(path: Path, allowed_roots: list[Path], label: str) -> Path:
    from config_loader import resolve_allowed_root
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(r) for r in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()

    config = load_config_with_defaults(repo_root=repo_root, config_path=args.config)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    backlog_root = repo_root / "_kano" / "backlog"
    allowed_roots = allowed_roots_for_repo(repo_root)

    # Resolve item
    index = BacklogIndex(backlog_root)
    matches = resolve_ref(args.item, index)
    if not matches:
        # Try rebuild index then resolve
        try:
            build = Path(__file__).resolve().parents[1] / "indexing" / "build_sqlite_index.py"
            cmd = [sys.executable, str(build), "--backlog-root", str(backlog_root), "--agent", args.agent, "--mode", "rebuild"]
            result = __import__("subprocess").run(cmd, text=True, capture_output=True)
            if result.returncode == 0:
                index = BacklogIndex(backlog_root)
                matches = resolve_ref(args.item, index)
        except Exception:
            pass
    if len(matches) != 1:
        raise SystemExit(f"Ambiguous or missing item: {args.item} (matches={len(matches)})")
    item = matches[0]

    # Prepare cache path
    cache_root = Path(args.cache_root)
    if not cache_root.is_absolute():
        cache_root = (repo_root / cache_root).resolve()
    ensure_under_allowed(cache_root, allowed_roots, "cache-root")

    ws_dir = cache_root / item.uid
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "deliverables").mkdir(parents=True, exist_ok=True)

    # Seed templates
    (ws_dir / "plan.md").write_text(PLAN_TEMPLATE, encoding="utf-8")
    (ws_dir / "notes.md").write_text(NOTES_TEMPLATE, encoding="utf-8")
    meta = {
        "uid": item.uid,
        "id": item.id,
        "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "agent": args.agent,
    }
    import json
    (ws_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Append worklog to item
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    message = f"Workset initialized: {ws_dir.relative_to(repo_root).as_posix()}"
    with open(item.path, "a", encoding="utf-8") as f:
        f.write(f"\n{timestamp} [agent={args.agent}] {message}\n")

    print(f"Initialized workset: {ws_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
