#!/usr/bin/env python3
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_LOG_ROOT = "_kano/backlog/_logs/agent_tools"
DEFAULT_LOG_FILE = "tool_invocations.jsonl"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_FILES = 10

SENSITIVE_KEYS = {
    "token",
    "api-key",
    "apikey",
    "access-key",
    "secret",
    "client-secret",
    "password",
    "passwd",
    "pwd",
    "authorization",
    "bearer",
    "cookie",
}

SENSITIVE_ENV_RE = re.compile(
    r"(?i)(^|[_-])(token|key|secret|password|passwd|pwd)$"
)


def utc_timestamp() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def normalize_key(text: str) -> str:
    return text.strip().lstrip("-").lower()


def is_sensitive_key(key: str) -> bool:
    normalized = normalize_key(key)
    if normalized in SENSITIVE_KEYS:
        return True
    return bool(SENSITIVE_ENV_RE.search(normalized))


def redact_kv_pair(arg: str) -> str:
    if "=" not in arg:
        return arg
    key, value = arg.split("=", 1)
    if is_sensitive_key(key):
        return f"{key}=***"
    return arg


def redact_argv(argv: List[str]) -> List[str]:
    redacted: List[str] = []
    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if "=" in arg:
            redacted.append(redact_kv_pair(arg))
            idx += 1
            continue
        key = normalize_key(arg)
        if is_sensitive_key(key) and idx + 1 < len(argv):
            redacted.append(arg)
            next_arg = argv[idx + 1]
            if next_arg.startswith("-"):
                idx += 1
                continue
            redacted.append("***")
            idx += 2
            continue
        redacted.append(arg)
        idx += 1
    return redacted


def render_replay_command(argv: List[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return " ".join(shlex_quote(arg) for arg in argv)


def shlex_quote(value: str) -> str:
    if not value:
        return "''"
    if re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def resolve_log_path(log_root: Optional[str], log_file: Optional[str]) -> Path:
    root = Path(log_root or DEFAULT_LOG_ROOT)
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    file_name = log_file or DEFAULT_LOG_FILE
    return root / file_name


def rotate_logs(log_path: Path, max_bytes: int, max_files: int) -> None:
    if not log_path.exists():
        return
    if log_path.stat().st_size < max_bytes:
        return
    oldest = log_path.with_name(f"{log_path.stem}.{max_files}{log_path.suffix}")
    if oldest.exists():
        oldest.unlink()
    for idx in range(max_files - 1, 0, -1):
        src = log_path.with_name(f"{log_path.stem}.{idx}{log_path.suffix}")
        if src.exists():
            dest = log_path.with_name(f"{log_path.stem}.{idx + 1}{log_path.suffix}")
            src.replace(dest)
    log_path.replace(log_path.with_name(f"{log_path.stem}.1{log_path.suffix}"))


def log_tool_invocation(
    tool: str,
    argv: List[str],
    cwd: Optional[str],
    status: str,
    exit_code: Optional[int] = None,
    duration_ms: Optional[int] = None,
    log_root: Optional[str] = None,
    log_file: Optional[str] = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_files: int = DEFAULT_MAX_FILES,
    error: Optional[str] = None,
    notes: Optional[str] = None,
) -> Path:
    log_path = resolve_log_path(log_root, log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rotate_logs(log_path, max_bytes=max_bytes, max_files=max_files)

    redacted_argv = redact_argv(argv)
    entry: Dict[str, object] = {
        "version": 1,
        "timestamp": utc_timestamp(),
        "tool": tool,
        "cwd": cwd or str(Path.cwd()),
        "status": status,
        "command_args": redacted_argv,
        "replay_command": render_replay_command(redacted_argv),
    }
    if exit_code is not None:
        entry["exit_code"] = exit_code
    if duration_ms is not None:
        entry["duration_ms"] = duration_ms
    if error:
        entry["error"] = error
    if notes:
        entry["notes"] = notes

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return log_path
