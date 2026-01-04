#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

import subprocess

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_logger import (  # noqa: E402
    DEFAULT_LOG_FILE,
    DEFAULT_LOG_ROOT,
    log_tool_invocation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a command and append an audit log entry."
    )
    parser.add_argument("--tool", help="Tool name override.")
    parser.add_argument("--cwd", help="Working directory override.")
    parser.add_argument("--log-root", help=f"Log root (default: {DEFAULT_LOG_ROOT}).")
    parser.add_argument("--log-file", help=f"Log file name (default: {DEFAULT_LOG_FILE}).")
    parser.add_argument("--max-bytes", type=int, help="Rotate when size exceeds bytes.")
    parser.add_argument("--max-files", type=int, help="Number of rotated files to keep.")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run.")
    return parser.parse_args()


def _env_flag(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _env_int(name: str) -> Optional[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _env_str(name: str) -> Optional[str]:
    value = os.getenv(name, "").strip()
    return value or None


def main() -> int:
    args = parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Provide a command after --, e.g. run_with_audit.py -- ls")

    start = time.time()
    result = subprocess.run(command, cwd=args.cwd)
    duration_ms = int((time.time() - start) * 1000)
    status = "ok" if result.returncode == 0 else "error"

    tool = args.tool or command[0]
    if not _env_flag("KANO_AUDIT_LOG_DISABLED"):
        log_root = args.log_root or _env_str("KANO_AUDIT_LOG_ROOT") or DEFAULT_LOG_ROOT
        log_file = args.log_file or _env_str("KANO_AUDIT_LOG_FILE") or DEFAULT_LOG_FILE
        max_bytes = (
            args.max_bytes
            or _env_int("KANO_AUDIT_LOG_MAX_BYTES")
            or 5 * 1024 * 1024
        )
        max_files = args.max_files or _env_int("KANO_AUDIT_LOG_MAX_FILES") or 10
        log_tool_invocation(
            tool=tool,
            argv=command,
            cwd=args.cwd,
            status=status,
            exit_code=result.returncode,
            duration_ms=duration_ms,
            log_root=log_root,
            log_file=log_file,
            max_bytes=max_bytes,
            max_files=max_files,
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
