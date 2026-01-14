"""Null VCS adapter for environments without VCS."""

from pathlib import Path
from .base import VcsAdapter, VcsMeta


class NullAdapter:
    """Null VCS adapter for no VCS environments."""
    
    def detect(self, repo_root: Path) -> bool:
        """Always available as fallback."""
        return True
    
    def get_metadata(self, repo_root: Path) -> VcsMeta:
        """Return unknown metadata."""
        return VcsMeta(
            provider="none",
            branch="unknown",
            revno="unknown",
            hash="unknown",
            dirty="unknown"
        )