"""
view.py - View and dashboard generation operations.

This module provides use-case functions for generating and refreshing
backlog views and dashboards.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ViewRefreshResult:
    """Result of refreshing views."""
    views_refreshed: List[Path]
    summaries_refreshed: List[Path]
    reports_refreshed: List[Path]


@dataclass
class GenerateViewResult:
    """Result of generating a single view."""
    path: Path
    item_count: int


def refresh_dashboards(
    *,
    product: Optional[str] = None,
    agent: str,
    all_personas: bool = False,
    backlog_root: Optional[Path] = None,
    config_path: Optional[Path] = None,
) -> ViewRefreshResult:
    """
    Refresh all dashboard views.

    Regenerates:
    - Dashboard_PlainMarkdown_Active.md
    - Dashboard_PlainMarkdown_New.md
    - Dashboard_PlainMarkdown_Done.md
    - Summary_<persona>.md (if all_personas=True)
    - Report_<persona>.md (if all_personas=True)

    Args:
        product: Product name (optional, refreshes all if not specified)
        agent: Agent identity for audit logging
        all_personas: Whether to regenerate all persona views
        backlog_root: Root path for backlog
        config_path: Path to config file

    Returns:
        ViewRefreshResult with list of refreshed files

    Raises:
        FileNotFoundError: If backlog not initialized
    """
    # Get scripts directory
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts" / "backlog"
    refresh_script = scripts_dir / "view_refresh_dashboards.py"
    
    if not refresh_script.exists():
        raise FileNotFoundError(f"Script not found: {refresh_script}")
    
    # Build command
    cmd = [
        sys.executable,
        str(refresh_script),
        "--agent", agent,
    ]
    
    if product:
        cmd.extend(["--product", product])
    if all_personas:
        cmd.append("--all-personas")
    if config_path:
        cmd.extend(["--config", str(config_path)])
    
    # Run script
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"Failed to refresh dashboards: {result.stderr or result.stdout}")
    
    # Parse output to collect refreshed files
    views_refreshed = []
    summaries_refreshed = []
    reports_refreshed = []
    
    for line in result.stdout.strip().split("\n"):
        if "Dashboard_PlainMarkdown" in line or "views/" in line:
            # Extract path from lines like "Refreshed: <path>"
            if ":" in line:
                path_str = line.split(":", 1)[1].strip()
                path = Path(path_str)
                if path.exists():
                    views_refreshed.append(path)
        elif "Summary_" in line:
            if ":" in line:
                path_str = line.split(":", 1)[1].strip()
                path = Path(path_str)
                if path.exists():
                    summaries_refreshed.append(path)
        elif "Report_" in line:
            if ":" in line:
                path_str = line.split(":", 1)[1].strip()
                path = Path(path_str)
                if path.exists():
                    reports_refreshed.append(path)
    
    return ViewRefreshResult(
        views_refreshed=views_refreshed,
        summaries_refreshed=summaries_refreshed,
        reports_refreshed=reports_refreshed,
    )


def generate_view(
    title: str,
    output_path: Path,
    *,
    groups: Optional[List[str]] = None,
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> GenerateViewResult:
    """
    Generate a single view file.

    Args:
        title: View title
        output_path: Path for generated view
        groups: State groups to include (e.g., ["New", "InProgress"])
        product: Product name
        backlog_root: Root path for backlog

    Returns:
        GenerateViewResult with generation details

    Raises:
        FileNotFoundError: If backlog not initialized
    """
    # TODO: Implement - currently delegates to view_generate.py
    raise NotImplementedError("generate_view not yet implemented - use view_generate.py")
