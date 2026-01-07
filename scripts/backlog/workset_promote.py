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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote workset deliverables and decisions back to canonical.")
    parser.add_argument("--item", required=True, help="Backlog item ref (id/uid/id@uidshort)")
    parser.add_argument("--agent", required=True, help="Agent name for worklog")
    parser.add_argument(
        "--cache-root",
        default="_kano/backlog/sandboxes/.cache",
        help="Cache root (default: _kano/backlog/sandboxes/.cache)",
    )
    parser.add_argument("--config", help="Optional config path override")
    parser.add_argument("--dry-run", action="store_true", help="Preview promotion actions")
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

    # Locate workset deliverables
    cache_root = Path(args.cache_root)
    if not cache_root.is_absolute():
        cache_root = (repo_root / cache_root).resolve()
    ensure_under_allowed(cache_root, allowed_roots, "cache-root")

    ws_dir = cache_root / item.uid
    deliver_dir = ws_dir / "deliverables"
    if not deliver_dir.exists():
        print(f"No deliverables folder: {deliver_dir}")
        return 0

    # Attach each file as artifact and log promotion
    python = sys.executable
    attach = Path(__file__).resolve().parent / "workitem_attach_artifact.py"
    promoted = []
    for f in deliver_dir.rglob("*"):
        if f.is_file():
            if args.dry_run:
                print(f"[DRY] promote {f}")
                promoted.append(f)
                continue
            cmd = [python, str(attach), str(f), "--to", item.id, "--agent", args.agent]
            if args.config:
                cmd.extend(["--config", args.config])
            result = __import__("subprocess").run(cmd, text=True, capture_output=True)
            if result.returncode != 0:
                print(result.stderr.strip() or result.stdout.strip() or f"Attach failed: {f}")
            else:
                promoted.append(f)

    # Append summary Worklog
    if promoted and not args.dry_run:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"Promoted deliverables ({len(promoted)}):"] + [f"- {p.relative_to(repo_root).as_posix()}" for p in promoted]
        with open(item.path, "a", encoding="utf-8") as f:
            f.write("\n" + timestamp + f" [agent={args.agent}] " + lines[0] + "\n" + "\n".join(lines[1:]) + "\n")
        print(f"Promoted {len(promoted)} deliverables.")
    else:
        print("No deliverables to promote.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
