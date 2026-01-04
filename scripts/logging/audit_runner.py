#!/usr/bin/env python3
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

from audit_logger import log_tool_invocation


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
        try:
            log_tool_invocation(
                tool=tool_name,
                argv=args,
                cwd=cwd,
                status=status,
                exit_code=exit_code,
                duration_ms=duration_ms,
                error=error,
            )
        except Exception:
            pass
