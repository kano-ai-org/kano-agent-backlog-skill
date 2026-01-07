#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Optional

from base import Commit, VCSAdapter


class GitAdapter(VCSAdapter):
    """Git VCS adapter using git log."""
    
    def query_commits(
        self,
        ref_pattern: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        author: Optional[str] = None,
        max_count: Optional[int] = None,
    ) -> List[Commit]:
        """Query Git commits containing Refs: pattern."""
        
        # Build git log command
        cmd = ["git", "-C", str(self.repo_root), "log", "--all"]
        
        # Format: hash|author|date|message (with \x00 separators for safe parsing)
        cmd.extend(["--format=%H%x00%an%x00%aI%x00%B%x00"])
        
        # Grep for Refs: pattern (case-insensitive)
        cmd.extend(["--grep", f"Refs:.*{re.escape(ref_pattern)}", "-i"])
        
        # Date filters
        if since:
            cmd.extend(["--since", since])
        if until:
            cmd.extend(["--until", until])
        
        # Author filter
        if author:
            cmd.extend(["--author", author])
        
        # Limit
        if max_count:
            cmd.extend(["-n", str(max_count)])
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            return []
        
        return self._parse_log_output(result.stdout, ref_pattern)
    
    def _parse_log_output(self, output: str, ref_pattern: str) -> List[Commit]:
        """Parse git log output into Commit objects."""
        commits = []
        
        # Split by commit separator
        entries = output.split("\x00\x00")
        
        for entry in entries:
            if not entry.strip():
                continue
            
            parts = entry.split("\x00")
            if len(parts) < 4:
                continue
            
            commit_hash, author, date, message = parts[0], parts[1], parts[2], parts[3]
            
            # Extract Refs: values from message
            refs = self._extract_refs(message, ref_pattern)
            
            commits.append(Commit(
                hash=commit_hash[:12],  # Short hash
                author=author,
                date=date,
                message=message.strip(),
                refs=refs,
            ))
        
        return commits
    
    def _extract_refs(self, message: str, ref_pattern: str) -> List[str]:
        """Extract Refs: values from commit message."""
        refs = []
        pattern = re.compile(r"Refs:\s*(.+?)(?:\n|$)", re.IGNORECASE)
        
        for match in pattern.finditer(message):
            ref_line = match.group(1).strip()
            # Split by comma or whitespace
            for ref in re.split(r"[,\s]+", ref_line):
                ref = ref.strip()
                if ref:
                    refs.append(ref)
        
        return refs
