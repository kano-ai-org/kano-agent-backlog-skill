#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Commit:
    """Represents a VCS commit."""
    hash: str
    author: str
    date: str  # ISO 8601 format
    message: str
    refs: List[str]  # Extracted Refs: values


class VCSAdapter:
    """Abstract base class for VCS adapters."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
    
    def query_commits(
        self,
        ref_pattern: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        author: Optional[str] = None,
        max_count: Optional[int] = None,
    ) -> List[Commit]:
        """Query commits containing the given ref pattern.
        
        Args:
            ref_pattern: Pattern to search in Refs: lines (e.g., "KABSD-TSK-0042" or "019b96cb")
            since: Start date (ISO 8601 or relative like "2 weeks ago")
            until: End date (ISO 8601)
            author: Filter by author
            max_count: Limit number of results
            
        Returns:
            List of Commit objects ordered by date descending (newest first)
        """
        raise NotImplementedError
    
    @staticmethod
    def detect_vcs(repo_root: Path) -> Optional[str]:
        """Detect VCS type from repo structure.
        
        Returns:
            "git", "perforce", "svn", or None if not detected
        """
        if (repo_root / ".git").exists():
            return "git"
        if (repo_root / ".p4config").exists() or (repo_root / "P4CONFIG").exists():
            return "perforce"
        if (repo_root / ".svn").exists():
            return "svn"
        return None
