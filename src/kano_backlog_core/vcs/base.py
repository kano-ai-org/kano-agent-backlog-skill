"""VCS abstraction base types."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


@dataclass
class VcsMeta:
    """VCS metadata for reproducible builds."""
    provider: str  # git, p4, svn, none, unknown
    revision: str = "unknown"  # commit hash, changelist, etc. or "unknown"
    ref: str = "unknown"  # branch, stream, etc. or "unknown"
    label: Optional[str] = None  # tag, describe, etc.
    dirty: str = "unknown"  # "true", "false", "unknown"
    # Compatibility fields for ops.vcs V2 metadata.
    branch: Optional[str] = None
    revno: Optional[str] = None
    hash: Optional[str] = None

    def __post_init__(self) -> None:
        if self.branch and self.ref in ("", "unknown"):
            self.ref = self.branch
        if self.hash and self.revision in ("", "unknown"):
            self.revision = self.hash
        elif self.revno and self.revision in ("", "unknown"):
            self.revision = self.revno

        if self.branch is None:
            self.branch = self.ref
        if self.hash is None:
            self.hash = self.revision
        if self.revno is None:
            self.revno = "unknown"


class VcsAdapter(Protocol):
    """VCS adapter protocol."""
    
    def detect(self, repo_root: Path) -> bool:
        """Check if this VCS is present."""
        ...
    
    def get_metadata(self, repo_root: Path) -> VcsMeta:
        """Get VCS metadata."""
        ...
