#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import shutil
import sys
import datetime
from pathlib import Path

# Fix imports
LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from product_args import add_product_arguments  # noqa: E402
from config_loader import get_config_value, load_config_with_defaults, validate_config  # noqa: E402

from lib.index import BacklogIndex
from lib.resolver import resolve_ref

def main() -> int:
    parser = argparse.ArgumentParser(description="Attach a file to a backlog item as an artifact.")
    parser.add_argument("file", help="Path to the file to attach.")
    parser.add_argument("--to", required=True, help="Target backlog item ID/Ref.")
    parser.add_argument("--rename", help="Optional new filename for the artifact.")
    parser.add_argument("--agent", required=True, help="Agent name for worklog.")
    parser.add_argument("--message", help="Optional message for worklog.")
    parser.add_argument("--config", help="Optional config path override.")
    parser.add_argument("--no-refresh", action="store_true", help="Disable automatic dashboard refresh.")
    add_product_arguments(parser)

    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    # Load config for auto-refresh behavior
    config = load_config_with_defaults(repo_root=repo_root, config_path=args.config)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    repo_root = Path.cwd().resolve()
    backlog_root = repo_root / "_kano" / "backlog"
    artifacts_root = backlog_root / "artifacts"
    
    # 1. Validate Source
    source_path = Path(args.file).resolve()
    if not source_path.exists():
        print(f"Error: Source file not found: {source_path}")
        return 1
        
    # 2. Resolve Target Item
    if not backlog_root.exists():
        print(f"Error: Backlog root not found: {backlog_root}")
        return 1
        
    index = BacklogIndex(backlog_root)
    matches = resolve_ref(args.to, index)
    if len(matches) == 0:
        # Fallback: refresh SQLite index then re-resolve
        try:
            scripts_root = Path(__file__).resolve().parents[1]
            build = scripts_root / "indexing" / "build_sqlite_index.py"
            cmd = [sys.executable, str(build), "--backlog-root", str(backlog_root), "--agent", args.agent, "--mode", "rebuild"]
            if args.config:
                cmd.extend(["--config", args.config])
            result = subprocess.run(cmd, text=True, capture_output=True)
            if result.returncode == 0:
                index = BacklogIndex(backlog_root)
                matches = resolve_ref(args.to, index)
        except Exception:
            pass
    
    if len(matches) == 0:
        print(f"Error: Target item '{args.to}' not found.")
        return 1
    if len(matches) > 1:
        print(f"Error: Target item '{args.to}' is ambiguous. Matches: {[m.id for m in matches]}")
        return 1
        
    target_item = matches[0]
    
    # 3. Prepare Artifact Dir
    target_dir = artifacts_root / target_item.id
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 4. Copy File
    dest_name = args.rename or source_path.name
    dest_path = target_dir / dest_name
    
    if dest_path.exists():
        print(f"Warning: Overwriting existing artifact: {dest_path}")
    
    shutil.copy2(source_path, dest_path)
    print(f"Artifact copied to: {dest_path}")
    
    # 5. Update Item Worklog
    # Calculate relative path for Markdown link
    # From item file to artifact
    # Item: _kano/backlog/items/feature/0000/ID.md
    # Artifact: _kano/backlog/artifacts/ID/file.ext
    # Relative: ../../../artifacts/ID/file.ext
    
    import os
    try:
        # Calculate relative path from item file (start) to artifact (dest)
        rel_path = os.path.relpath(dest_path, target_item.path.parent)
        link_path = Path(rel_path).as_posix()
    except Exception:
        # Fallback to repo-relative path if cross-drive or weird
        link_path = "/" + dest_path.relative_to(repo_root).as_posix()

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = args.message or f"Attached artifact: {dest_name}"
    
    log_entry = f"\n{timestamp} [agent={args.agent}] {msg}\n- Artifact: [{dest_name}]({link_path})"
    
    with open(target_item.path, "a", encoding="utf-8") as f:
        f.write(log_entry)
        
    print(f"Updated worklog in: {target_item.path}")
    # Auto-refresh dashboards if enabled
    if not args.no_refresh and bool(get_config_value(config, "views.auto_refresh", True)):
        refresh_script = Path(__file__).resolve().parent / "view_refresh_dashboards.py"
        cmd = [sys.executable, str(refresh_script), "--backlog-root", str(backlog_root), "--agent", args.agent]
        if args.config:
            cmd.extend(["--config", args.config])
        result = subprocess.run(cmd, text=True, capture_output=True)
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or "Failed to refresh dashboards."
            print(err)
    return 0

if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
