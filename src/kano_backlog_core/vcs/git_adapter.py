"""Git VCS adapter."""

import subprocess
from pathlib import Path
from .base import VcsAdapter, VcsMeta


class GitAdapter:
    """Git VCS adapter."""
    
    def detect(self, repo_root: Path) -> bool:
        """Check if Git is present."""
        return (repo_root / ".git").exists()
    
    def get_metadata(self, repo_root: Path) -> VcsMeta:
        """Get Git metadata."""
        try:
            # Hash (commit hash)
            commit_hash = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()

            # Branch (or HEAD for detached)
            try:
                branch = subprocess.check_output(
                    ["git", "symbolic-ref", "--short", "HEAD"],
                    cwd=repo_root,
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
            except subprocess.CalledProcessError:
                branch = "HEAD"

            # RevNo: human-friendly monotonic-ish number within the repo.
            # For git we use commit count on HEAD.
            try:
                revno = subprocess.check_output(
                    ["git", "rev-list", "--count", "HEAD"],
                    cwd=repo_root,
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
            except subprocess.CalledProcessError:
                revno = "unknown"
            
            # Check if dirty
            try:
                subprocess.check_output(
                    ["git", "diff-index", "--quiet", "HEAD", "--"],
                    cwd=repo_root,
                    stderr=subprocess.DEVNULL
                )
                dirty = "false"
            except subprocess.CalledProcessError:
                dirty = "true"
            
            return VcsMeta(
                provider="git",
                branch=branch,
                revno=revno,
                hash=commit_hash,
                dirty=dirty
            )
        except Exception:
            return VcsMeta(
                provider="git",
                branch="unknown",
                revno="unknown",
                hash="unknown",
                dirty="unknown"
            )