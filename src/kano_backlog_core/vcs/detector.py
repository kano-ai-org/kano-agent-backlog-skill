"""VCS detection and metadata utilities."""

from pathlib import Path
from typing import Optional
from .base import VcsMeta
from .git_adapter import GitAdapter
from .null_adapter import NullAdapter


def detect_vcs_metadata(repo_root: Optional[Path] = None) -> VcsMeta:
    """Detect VCS and return metadata."""
    if repo_root is None:
        repo_root = Path.cwd()
    
    # Try adapters in order
    adapters = [GitAdapter(), NullAdapter()]
    
    for adapter in adapters:
        if adapter.detect(repo_root):
            return adapter.get_metadata(repo_root)
    
    # Fallback (should never reach here due to NullAdapter)
    return VcsMeta(
        provider="unknown",
        revision="unknown", 
        ref="unknown",
        dirty="unknown"
    )


def format_vcs_metadata(meta: VcsMeta, mode: str = "min") -> str:
    """Format VCS metadata as HTML comment block."""
    if mode == "none":
        return ""
    
    lines = ["<!-- kano:build"]
    # KABSD-FTR-0039: fixed schema + field order for reproducible docs.
    lines.append(f"vcs.provider: {meta.provider}")
    lines.append(f"vcs.branch: {meta.branch}")
    lines.append(f"vcs.revno: {meta.revno}")
    lines.append(f"vcs.hash: {meta.hash}")
    lines.append(f"vcs.dirty: {meta.dirty}")
    
    if mode == "full":
        # Reserved for future expansions; keep stable output for now.
        pass
    
    lines.append("-->")
    return "\n".join(lines)
