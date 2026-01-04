#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

from audit_logger import DEFAULT_MAX_BYTES, DEFAULT_MAX_FILES, log_tool_invocation


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


def _logging_disabled() -> bool:
    return _env_flag("KANO_AUDIT_LOG_DISABLED")


def _resolve_tool_name(argv: List[str], tool: Optional[str]) -> str:
    if tool:
        return tool
    if argv:
        return Path(argv[0]).stem
    return "unknown"


def run_with_audit(
    main_fn: Callable[[], int],
    argv: Optional[List[str]] = None,
    tool: Optional[str] = None,
    cwd: Optional[str] = None,
) -> int:
    args = list(argv) if argv is not None else list(sys.argv)
    tool_name = _resolve_tool_name(args, tool)
    start = time.monotonic()
    status = "ok"
    exit_code = 0
    error: Optional[str] = None
    try:
        exit_code = main_fn() or 0
        if exit_code != 0:
            status = "error"
        return exit_code
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            exit_code = code
        elif code is None:
            exit_code = 0
        else:
            exit_code = 1
        status = "ok" if exit_code == 0 else "error"
        if code not in (0, None):
            error = str(code)
        raise
    except Exception as exc:
        exit_code = 1
        status = "error"
        error = str(exc)
        raise
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        if not _logging_disabled():
            log_root = _env_str("KANO_AUDIT_LOG_ROOT")
            log_file = _env_str("KANO_AUDIT_LOG_FILE")
            max_bytes = _env_int("KANO_AUDIT_LOG_MAX_BYTES") or DEFAULT_MAX_BYTES
            max_files = _env_int("KANO_AUDIT_LOG_MAX_FILES") or DEFAULT_MAX_FILES
            try:
                log_tool_invocation(
                    tool=tool_name,
                    argv=args,
                    cwd=cwd,
                    status=status,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    error=error,
                    log_root=log_root,
                    log_file=log_file,
                    max_bytes=max_bytes,
                    max_files=max_files,
                )
            except Exception:
                pass
