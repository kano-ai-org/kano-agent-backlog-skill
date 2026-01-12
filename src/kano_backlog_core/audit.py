"""Audit logging for worklog and file operations."""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime

from .models import BacklogItem, WorklogEntry

# Default cross-product audit log location (shared)
DEFAULT_AUDIT_LOG = Path("_kano/backlog/_shared/logs/agent_tools/tool_invocations.jsonl")
LEGACY_AUDIT_LOG = Path("_kano/backlog/_logs/agent_tools/tool_invocations.jsonl")

class AuditLog:
    """Manage worklog and file operation logs."""

    @staticmethod
    def append_worklog(
        item: BacklogItem,
        message: str,
        agent: Optional[str] = None,
        model: Optional[str] = None
    ) -> None:
        """
        Add worklog entry to item (modifies in-place).

        Args:
            item: BacklogItem to append worklog to
            message: Worklog message
            agent: Agent performing the action (optional)
            model: Model used by agent (e.g., 'claude-sonnet-4.5', 'gpt-5.1') (optional)
        """
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        if agent:
            entry = WorklogEntry(timestamp=timestamp, agent=agent, model=model, message=message)
            item.worklog.append(entry.format())
        else:
            item.worklog.append(f"{timestamp} {message}")

    @staticmethod
    def parse_worklog(item: BacklogItem) -> List[WorklogEntry]:
        """
        Parse worklog section into structured entries.

        Args:
            item: BacklogItem with worklog

        Returns:
            List of parsed WorklogEntry objects (skips unparseable lines)
        """
        entries = []
        for line in item.worklog:
            entry = WorklogEntry.parse(line)
            if entry:
                entries.append(entry)
        return entries

    @staticmethod
    def log_file_operation(
        operation: Literal["create", "update", "delete", "move"],
        path: str,
        tool: str,
        agent: str,
        metadata: Optional[Dict[str, Any]] = None,
        log_path: Optional[Path] = None,
    ) -> None:
        """
        Log file operation to JSONL audit trail.

        Args:
            operation: Operation type
            path: File path affected
            tool: Tool performing the operation
            agent: Agent performing the operation
            metadata: Optional additional metadata
            log_path: Full path to log file (defaults to _kano/backlog/_shared/logs/agent_tools/tool_invocations.jsonl)
        """
        if log_path is None:
            log_path = DEFAULT_AUDIT_LOG
        
        log_path.parent.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "agent": agent,
            "operation": operation,
            "path": path,
            "tool": tool,
            "metadata": metadata or {},
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

    @staticmethod
    def read_file_operations(
        log_path: Optional[Path] = None,
        operation_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Read file operations from audit log.

        Args:
            log_path: Full path to log file (defaults to _kano/backlog/_shared/logs/agent_tools/tool_invocations.jsonl; falls back to legacy path if missing)
            operation_filter: Filter by operation type (e.g., "create")

        Returns:
            List of log entries (dicts)
        """
        if log_path is None:
            log_path = DEFAULT_AUDIT_LOG
            if not log_path.exists() and LEGACY_AUDIT_LOG.exists():
                # Compatibility: read legacy path if the new shared path is absent
                log_path = LEGACY_AUDIT_LOG
        
        if not log_path.exists():
            return []

        entries = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if operation_filter is None or entry.get("operation") == operation_filter:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        pass

        return entries
