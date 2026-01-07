#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from product_args import add_product_arguments  # noqa: E402
from config_loader import load_config_with_defaults, validate_config

BACKLOG_DIR = Path(__file__).resolve().parents[1] / "backlog"
if str(BACKLOG_DIR) not in sys.path:
    sys.path.insert(0, str(BACKLOG_DIR))
from lib.index import BacklogIndex  # noqa: E402
from lib.resolver import resolve_ref  # noqa: E402

VCS_DIR = Path(__file__).resolve().parents[1] / "vcs"
if str(VCS_DIR) not in sys.path:
    sys.path.insert(0, str(VCS_DIR))
import base  # noqa: E402
import git_adapter  # noqa: E402
import perforce_adapter  # noqa: E402
import svn_adapter  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query VCS commits referencing a backlog item (derived data, not stored)."
    )
    parser.add_argument("--item", required=True, help="Backlog item ref (id/uid/id@uidshort)")
    parser.add_argument("--since", help="Start date (ISO 8601 or relative like '2 weeks ago')")
    parser.add_argument("--until", help="End date (ISO 8601)")
    parser.add_argument("--author", help="Filter by commit author")
    parser.add_argument("--max-count", type=int, help="Limit number of commits")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument("--config", help="Optional config path override")
    add_product_arguments(parser)
    return parser.parse_args()


def get_vcs_adapter(repo_root: Path) -> base.VCSAdapter:
    """Auto-detect VCS and return appropriate adapter."""
    vcs_type = base.VCSAdapter.detect_vcs(repo_root)
    
    if vcs_type == "git":
        return git_adapter.GitAdapter(repo_root)
    elif vcs_type == "perforce":
        return perforce_adapter.PerforceAdapter(repo_root)
    elif vcs_type == "svn":
        return svn_adapter.SVNAdapter(repo_root)
    else:
        raise SystemExit("No VCS detected (Git/Perforce/SVN). Ensure .git, .p4config, or .svn exists.")


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()

    config = load_config_with_defaults(repo_root=repo_root, config_path=args.config)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    backlog_root = repo_root / "_kano" / "backlog"

    # Resolve item
    index = BacklogIndex(backlog_root)
    matches = resolve_ref(args.item, index)
    if not matches:
        # Try rebuild index then resolve
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

    # Get VCS adapter
    vcs = get_vcs_adapter(repo_root)

    # Query commits using item ID and UID (to catch both formats)
    search_patterns = [item.id, item.uid]
    if item.uidshort:
        search_patterns.append(item.uidshort)

    all_commits = []
    seen_hashes = set()
    
    for pattern in search_patterns:
        commits = vcs.query_commits(
            ref_pattern=pattern,
            since=args.since,
            until=args.until,
            author=args.author,
            max_count=args.max_count,
        )
        # Deduplicate by hash
        for commit in commits:
            if commit.hash not in seen_hashes:
                all_commits.append(commit)
                seen_hashes.add(commit.hash)

    # Sort by date descending (newest first)
    all_commits.sort(key=lambda c: c.date, reverse=True)

    # Apply max_count after deduplication
    if args.max_count:
        all_commits = all_commits[:args.max_count]

    # Output
    if args.format == "json":
        result = {
            "item": item.id,
            "uid": item.uid,
            "title": item.title,
            "commits_found": len(all_commits),
            "commits": [
                {
                    "hash": c.hash,
                    "author": c.author,
                    "date": c.date,
                    "message": c.message,
                    "refs": c.refs,
                }
                for c in all_commits
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # Text format
        if not all_commits:
            print(f"No commits found for {item.id} ({item.title})")
            return 0

        print(f"Commits for {item.id} ({item.title}):")
        print(f"Found: {len(all_commits)} commits\n")
        
        for commit in all_commits:
            print(f"  {commit.hash} - {commit.date} - {commit.author}")
            # Show first line of message
            first_line = commit.message.split("\n")[0]
            print(f"    {first_line}")
            if commit.refs:
                print(f"    Refs: {', '.join(commit.refs)}")
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
