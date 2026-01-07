#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

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
from lib.index import BacklogIndex, BacklogItem  # noqa: E402

VCS_DIR = Path(__file__).resolve().parents[1] / "vcs"
if str(VCS_DIR) not in sys.path:
    sys.path.insert(0, str(VCS_DIR))
import base  # noqa: E402
import git_adapter  # noqa: E402
import perforce_adapter  # noqa: E402
import svn_adapter  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate commit timeline view for backlog items (derived data)."
    )
    parser.add_argument(
        "--backlog-root",
        default="_kano/backlog",
        help="Backlog root path (default: _kano/backlog)",
    )
    parser.add_argument(
        "--state",
        help="Filter by state (e.g., InProgress)",
    )
    parser.add_argument(
        "--since",
        help="Only show commits since this date",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output Markdown file path",
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
        raise SystemExit("No VCS detected (Git/Perforce/SVN).")


def query_item_commits(vcs: base.VCSAdapter, item: BacklogItem, since: str = None) -> List[base.Commit]:
    """Query commits for a single item."""
    # Collect non-empty search patterns
    search_patterns = []
    if item.id:
        search_patterns.append(item.id)
    if item.uid:
        search_patterns.append(item.uid)
    if item.uidshort:
        search_patterns.append(item.uidshort)
    
    all_commits = []
    seen_hashes = set()
    
    for pattern in search_patterns:
        commits = vcs.query_commits(
            ref_pattern=pattern,
            since=since,
            max_count=10,  # Limit per item to avoid explosion
        )
        for commit in commits:
            if commit.hash not in seen_hashes:
                all_commits.append(commit)
                seen_hashes.add(commit.hash)
    
    # Sort by date descending
    all_commits.sort(key=lambda c: c.date, reverse=True)
    return all_commits


def render_view(
    items_with_commits: List[tuple[BacklogItem, List[base.Commit]]],
    state_filter: str,
    backlog_label: str,
) -> str:
    """Render Markdown view."""
    lines = [
        "---",
        "type: View",
        "title: \"Commit Timeline View\"",
        "generated: derived",
        "---",
        "",
        f"# Commit Timeline ({state_filter or 'All'})",
        "",
        "This view shows recent commits for backlog items (derived from VCS, not stored).",
        "",
    ]
    
    if not items_with_commits:
        lines.append("_No items with commits found._")
        return "\n".join(lines) + "\n"
    
    for item, commits in items_with_commits:
        lines.append(f"## {item.id} - {item.title}")
        lines.append(f"**State**: {item.state} | **Priority**: {item.frontmatter.get('priority', 'N/A')}")
        lines.append("")
        
        if not commits:
            lines.append("_No commits found._")
        else:
            latest = commits[0]
            lines.append(f"**Latest commit**: {latest.date} by {latest.author}")
            lines.append("")
            lines.append("Recent commits:")
            lines.append("")
            for commit in commits[:5]:  # Show top 5
                first_line = commit.message.split("\n")[0]
                lines.append(f"- `{commit.hash}` {commit.date} - {first_line}")
        
        lines.append("")
    
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()

    config = load_config_with_defaults(repo_root=repo_root, config_path=args.config)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    backlog_root = Path(args.backlog_root)
    if not backlog_root.is_absolute():
        backlog_root = (repo_root / backlog_root).resolve()

    # Load index
    index = BacklogIndex(backlog_root)
    
    # Filter items by state
    items = []
    for item_list in index.items_by_id.values():
        for item in item_list:
            if args.state and item.state != args.state:
                continue
            items.append(item)
    
    # Get VCS adapter
    vcs = get_vcs_adapter(repo_root)
    
    # Query commits for each item
    items_with_commits = []
    for item in items:
        commits = query_item_commits(vcs, item, since=args.since)
        if commits:  # Only include items with commits
            items_with_commits.append((item, commits))
    
    # Sort by latest commit date
    items_with_commits.sort(key=lambda x: x[1][0].date if x[1] else "", reverse=True)
    
    # Render view
    backlog_label = "_kano/backlog"
    try:
        backlog_label = backlog_root.relative_to(repo_root).as_posix()
    except ValueError:
        pass
    
    output_text = render_view(items_with_commits, args.state, backlog_label)
    
    # Write output
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")
    
    print(f"Generated commit timeline view: {output_path}")
    print(f"Items with commits: {len(items_with_commits)}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
