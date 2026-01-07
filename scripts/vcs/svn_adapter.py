#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

from base import Commit, VCSAdapter


class SVNAdapter(VCSAdapter):
    """SVN VCS adapter using svn log."""
    
    def query_commits(
        self,
        ref_pattern: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        author: Optional[str] = None,
        max_count: Optional[int] = None,
    ) -> List[Commit]:
        """Query SVN commits containing Refs: pattern."""
        
        # Build svn log command with XML output for easier parsing
        cmd = ["svn", "log", "--xml"]
        
        # Date filters (SVN uses -r {date}:{date} format)
        if since or until:
            start = since if since else "1970-01-01"
            end = until if until else "HEAD"
            cmd.extend(["-r", f"{{{start}}}:{{{end}}}"])
        
        # Limit
        if max_count:
            cmd.extend(["-l", str(max_count)])
        
        # Search in repository root
        cmd.append(str(self.repo_root))
        
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
        
        return self._parse_log_xml(result.stdout, ref_pattern, author)
    
    def _parse_log_xml(self, xml_output: str, ref_pattern: str, author_filter: Optional[str]) -> List[Commit]:
        """Parse SVN log XML output into Commit objects."""
        commits = []
        
        try:
            root = ET.fromstring(xml_output)
        except ET.ParseError:
            return []
        
        for logentry in root.findall("logentry"):
            revision = logentry.get("revision", "unknown")
            
            author_elem = logentry.find("author")
            author = author_elem.text if author_elem is not None and author_elem.text else "unknown"
            
            # Apply author filter
            if author_filter and author != author_filter:
                continue
            
            date_elem = logentry.find("date")
            date = date_elem.text if date_elem is not None and date_elem.text else ""
            # Convert ISO 8601 format: 2026-01-07T15:30:00.000000Z -> 2026-01-07T15:30:00Z
            if date:
                date = date.split(".")[0] + "Z"
            
            msg_elem = logentry.find("msg")
            message = msg_elem.text if msg_elem is not None and msg_elem.text else ""
            
            # Check if message contains Refs: pattern
            if not re.search(rf"Refs:.*{re.escape(ref_pattern)}", message, re.IGNORECASE):
                continue
            
            # Extract Refs: values
            refs = self._extract_refs(message, ref_pattern)
            
            commits.append(Commit(
                hash=f"r{revision}",
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
            for ref in re.split(r"[,\s]+", ref_line):
                ref = ref.strip()
                if ref:
                    refs.append(ref)
        
        return refs
