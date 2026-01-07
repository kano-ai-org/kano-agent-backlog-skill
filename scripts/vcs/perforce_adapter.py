#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Optional

from base import Commit, VCSAdapter


class PerforceAdapter(VCSAdapter):
    """Perforce VCS adapter using p4 changes."""
    
    def query_commits(
        self,
        ref_pattern: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        author: Optional[str] = None,
        max_count: Optional[int] = None,
    ) -> List[Commit]:
        """Query Perforce changelists containing Refs: pattern."""
        
        # Build p4 changes command
        cmd = ["p4", "changes", "-l"]
        
        # Date filters (Perforce uses @date format)
        if since:
            cmd.append(f"@>={since}")
        if until:
            cmd.append(f"@<={until}")
        
        # Author filter
        if author:
            cmd.extend(["-u", author])
        
        # Limit
        if max_count:
            cmd.extend(["-m", str(max_count)])
        
        # Add path to search in current client view
        cmd.append("//...")
        
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
        
        return self._parse_changes_output(result.stdout, ref_pattern)
    
    def _parse_changes_output(self, output: str, ref_pattern: str) -> List[Commit]:
        """Parse p4 changes output into Commit objects."""
        commits = []
        
        # Parse format:
        # Change 12345 on 2026/01/07 by user@client
        #     Description text
        #     Refs: KABSD-TSK-0042
        
        pattern = re.compile(
            r"Change (\d+) on ([\d/]+) by ([\w@.]+)\n\n\t(.+?)(?=\n\nChange|\Z)",
            re.DOTALL,
        )
        
        for match in pattern.finditer(output):
            changelist, date, author, description = match.groups()
            
            # Check if description contains Refs: pattern
            if not re.search(rf"Refs:.*{re.escape(ref_pattern)}", description, re.IGNORECASE):
                continue
            
            # Convert date format: 2026/01/07 -> 2026-01-07
            iso_date = date.replace("/", "-")
            
            # Extract Refs: values
            refs = self._extract_refs(description, ref_pattern)
            
            commits.append(Commit(
                hash=f"@{changelist}",  # Perforce uses @changelist notation
                author=author.split("@")[0],  # Remove client name
                date=iso_date,
                message=description.strip().replace("\t", "  "),
                refs=refs,
            ))
        
        return commits
    
    def _extract_refs(self, message: str, ref_pattern: str) -> List[str]:
        """Extract Refs: values from changelist description."""
        refs = []
        pattern = re.compile(r"Refs:\s*(.+?)(?:\n|$)", re.IGNORECASE)
        
        for match in pattern.finditer(message):
            ref_line = match.group(1).strip()
            for ref in re.split(r"[,\s]+", ref_line):
                ref = ref.strip()
                if ref:
                    refs.append(ref)
        
        return refs
