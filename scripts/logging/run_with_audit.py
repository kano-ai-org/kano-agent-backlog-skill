#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

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
    parser.add_argument(
        "--log-root",
        default=DEFAULT_LOG_ROOT,
        help=f"Log root (default: {DEFAULT_LOG_ROOT}).",
    )
    parser.add_argument(
        "--log-file",
        default=DEFAULT_LOG_FILE,
        help=f"Log file name (default: {DEFAULT_LOG_FILE}).",
    )
    parser.add_argument("--max-bytes", type=int, default=5 * 1024 * 1024)
    parser.add_argument("--max-files", type=int, default=10)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run.")
    return parser.parse_args()


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
    log_tool_invocation(
        tool=tool,
        argv=command,
        cwd=args.cwd,
        status=status,
        exit_code=result.returncode,
        duration_ms=duration_ms,
        log_root=args.log_root,
        log_file=args.log_file,
        max_bytes=args.max_bytes,
        max_files=args.max_files,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
