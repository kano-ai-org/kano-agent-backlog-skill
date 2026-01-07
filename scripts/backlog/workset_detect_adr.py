#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

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
    parser = argparse.ArgumentParser(
        description="Scan workset notes for Decision: markers and suggest ADR creation."
    )
    parser.add_argument("--item", required=True, help="Backlog item ref (id/uid/id@uidshort)")
    parser.add_argument(
        "--cache-root",
        default="_kano/backlog/sandboxes/.cache",
        help="Cache root (default: _kano/backlog/sandboxes/.cache)",
    )
    parser.add_argument("--config", help="Optional config path override")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    add_product_arguments(parser)
    return parser.parse_args()


def ensure_under_allowed(path: Path, allowed_roots: list[Path], label: str) -> Path:
    from config_loader import resolve_allowed_root
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(r) for r in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def extract_decisions(notes_path: Path) -> List[Tuple[int, str]]:
    """Extract lines containing Decision: markers with line numbers."""
    if not notes_path.exists():
        return []
    
    decisions = []
    pattern = re.compile(r"(?i)decision\s*:", re.IGNORECASE)
    
    for line_num, line in enumerate(notes_path.read_text(encoding="utf-8").splitlines(), start=1):
        if pattern.search(line):
            decisions.append((line_num, line.strip()))
    
    return decisions


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
            cmd = [sys.executable, str(build), "--backlog-root", str(backlog_root), "--agent", "system", "--mode", "rebuild"]
            result = __import__("subprocess").run(cmd, text=True, capture_output=True)
            if result.returncode == 0:
                index = BacklogIndex(backlog_root)
                matches = resolve_ref(args.item, index)
        except Exception:
            pass
    if len(matches) != 1:
        raise SystemExit(f"Ambiguous or missing item: {args.item} (matches={len(matches)})")
    item = matches[0]

    cache_root = Path(args.cache_root)
    if not cache_root.is_absolute():
        cache_root = (repo_root / cache_root).resolve()
    ensure_under_allowed(cache_root, allowed_roots, "cache-root")

    ws_dir = cache_root / item.uid
    notes_path = ws_dir / "notes.md"

    decisions = extract_decisions(notes_path)

    if args.format == "json":
        import json
        result = {
            "item": item.id,
            "uid": item.uid,
            "workset": str(ws_dir.relative_to(repo_root)),
            "decisions_detected": len(decisions),
            "lines": [{"line": ln, "text": txt} for ln, txt in decisions],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # Text format
        if not decisions:
            print(f"No Decision: markers found in {notes_path.relative_to(repo_root)}")
            return 0
        
        print(f"Decision markers detected ({len(decisions)}):")
        print(f"Item: {item.id} ({item.title})")
        print(f"Workset: {ws_dir.relative_to(repo_root)}")
        print()
        for line_num, text in decisions:
            print(f"  Line {line_num}: {text}")
        print()
        print("Suggestions:")
        print(f"  - Review notes.md and extract decision rationale")
        print(f"  - Create ADR: python skills/kano-agent-backlog-skill/scripts/backlog/adr_init.py --for {item.uid} --agent <agent>")
        print(f"  - Link ADR back to item frontmatter (decisions: list)")

    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
