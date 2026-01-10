"""
Deprecation utilities for kano-agent-backlog-skill scripts.

Per ADR-0013 Phase 3, all scripts under scripts/backlog/ are deprecated.
Agents should use the unified `scripts/kano` CLI instead.
"""

import sys
import warnings
from pathlib import Path


def warn_deprecated_script(script_name: str, recommended_command: str) -> None:
    """
    Print a deprecation warning for direct script execution.
    
    Args:
        script_name: Name of the deprecated script (e.g., "workitem_create.py")
        recommended_command: Recommended kano CLI command (e.g., "kano item create")
    
    Example:
        warn_deprecated_script("workitem_create.py", "kano item create")
    """
    message = f"""
╭─────────────────────────────────────────────────────────────╮
│ ⚠️  DEPRECATION WARNING                                     │
├─────────────────────────────────────────────────────────────┤
│ Direct script execution is deprecated per ADR-0013.         │
│                                                             │
│ Script: {script_name:<50} │
│                                                             │
│ Please use the unified CLI instead:                         │
│   {recommended_command:<54} │
│                                                             │
│ For help:                                                   │
│   python scripts/kano --help                                │
│                                                             │
│ This script will continue to work but may be removed        │
│ in a future version.                                        │
╰─────────────────────────────────────────────────────────────╯
"""
    print(message, file=sys.stderr)


def get_kano_cli_path() -> Path:
    """
    Get the absolute path to the kano CLI script.
    
    Returns:
        Path to scripts/kano
    """
    # Assuming all scripts are under scripts/backlog/ or scripts/
    script_dir = Path(__file__).parent
    
    # Navigate up to find scripts/kano
    if script_dir.name == "lib":
        # We're in scripts/backlog/lib/
        kano_path = script_dir.parent.parent / "kano"
    elif script_dir.name == "backlog":
        # We're in scripts/backlog/
        kano_path = script_dir.parent / "kano"
    else:
        # Assume we're in scripts/
        kano_path = script_dir / "kano"
    
    return kano_path.resolve()
