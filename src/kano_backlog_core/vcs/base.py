"""VCS abstraction base types."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


@dataclass
class VcsMeta:
    """VCS metadata for reproducible builds.

    Keep the model explicit and parse-free:
    - branch: human context (branch/stream/path)
    - revno: human-friendly revision number
    - hash: collision-resistant identifier
    """

    provider: str  # git, p4, svn, none, unknown
    branch: str  # branch, stream, etc. or "unknown"
    revno: str  # git commit-count, svn revision, p4 changelist, etc.
    hash: str  # git commit hash, or derived hash for non-hash providers
    dirty: str = "unknown"  # "true", "false", "unknown"


class VcsAdapter(Protocol):
    """VCS adapter protocol."""
    
    def detect(self, repo_root: Path) -> bool:
        """Check if this VCS is present."""
        ...
    
    def get_metadata(self, repo_root: Path) -> VcsMeta:
        """Get VCS metadata."""
        ...