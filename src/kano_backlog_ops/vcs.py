from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_UNKNOWN = "unknown"


@dataclass
class VcsMeta:
    """VCS metadata for reproducible outputs.

    Design intent: provide three human-meaningful concepts across providers:
    - branch: human context (e.g., git branch, svn path, p4 stream)
    - revno: human-friendly revision number (e.g., git commit-count, svn rev, p4 changelist)
    - hash: collision-resistant identity (e.g., git commit hash; derived hash for non-hash providers)
    """

    provider: str
    branch: str
    revno: str
    hash: str
    dirty: str  # "true" | "false" | "unknown"


def _run_git(args: list[str], cwd: Path) -> Optional[str]:
    """Run a git command and return stripped stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    return result.stdout.strip() or None


def _run_svn(args: list[str], cwd: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["svn", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _run_p4(args: list[str], cwd: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["p4", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _get_git_meta(root_path: Path) -> Optional[VcsMeta]:
    """Collect git metadata if available; return None when not in a git repo."""
    toplevel = _run_git(["rev-parse", "--show-toplevel"], root_path)
    if not toplevel:
        return None

    commit_hash = _run_git(["rev-parse", "HEAD"], root_path) or _UNKNOWN
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], root_path) or _UNKNOWN
    revno = _run_git(["rev-list", "--count", "HEAD"], root_path) or _UNKNOWN

    status = _run_git(["status", "--porcelain"], root_path)
    dirty = "unknown"
    if status is not None:
        dirty = "true" if status.strip() else "false"

    return VcsMeta(provider="git", branch=branch, revno=revno, hash=commit_hash, dirty=dirty)


def _find_svn_wc_root(start: Path) -> Optional[Path]:
    cur = start.resolve()
    for p in [cur, *cur.parents]:
        if (p / ".svn").exists():
            return p
    return None


def _get_svn_meta(root_path: Path) -> Optional[VcsMeta]:
    wc_root = _find_svn_wc_root(root_path)
    if not wc_root:
        return None

    revno = _run_svn(["info", "--show-item", "revision"], wc_root) or _UNKNOWN
    branch = _run_svn(["info", "--show-item", "relative-url"], wc_root) or _UNKNOWN
    repos_uuid = _run_svn(["info", "--show-item", "repos-uuid"], wc_root) or _UNKNOWN

    status = _run_svn(["status"], wc_root)
    dirty = "unknown"
    if status is not None:
        dirty = "true" if status.strip() else "false"

    # SVN has no content hash. Derive a stable collision-resistant hash.
    if repos_uuid != _UNKNOWN and revno != _UNKNOWN:
        derived = hashlib.sha1(f"{repos_uuid}:{revno}".encode("utf-8")).hexdigest()
        vcs_hash = derived
    else:
        vcs_hash = _UNKNOWN

    return VcsMeta(provider="svn", branch=branch, revno=revno, hash=vcs_hash, dirty=dirty)


def _parse_p4_info_value(info_text: str, key: str) -> Optional[str]:
    for line in info_text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip().lower() == key.lower():
            return v.strip() or None
    return None


def _get_p4_meta(root_path: Path) -> Optional[VcsMeta]:
    info = _run_p4(["info"], root_path)
    if not info:
        return None

    # Best-effort: these may require auth; treat failures as unknown.
    server = _parse_p4_info_value(info, "Server address") or _UNKNOWN
    client = _parse_p4_info_value(info, "Client name") or _UNKNOWN

    change = _UNKNOWN
    changes = _run_p4(["changes", "-m", "1"], root_path)
    if changes:
        # Typical format: "Change 12345 on ..."
        parts = changes.split()
        if len(parts) >= 2 and parts[0].lower() == "change":
            change = parts[1]

    opened = _run_p4(["opened"], root_path)
    dirty = "unknown"
    if opened is not None:
        dirty = "true" if opened.strip() else "false"

    branch = _UNKNOWN
    # Try stream from client spec (optional)
    client_spec = _run_p4(["client", "-o"], root_path)
    if client_spec:
        for line in client_spec.splitlines():
            if line.strip().lower().startswith("stream:"):
                branch = line.split(":", 1)[1].strip() or _UNKNOWN
                break

    # P4 has no hash; derive one from server/client/changelist.
    if change != _UNKNOWN and server != _UNKNOWN:
        vcs_hash = hashlib.sha1(f"{server}:{client}:{change}".encode("utf-8")).hexdigest()
    else:
        vcs_hash = _UNKNOWN

    return VcsMeta(provider="p4", branch=branch, revno=change, hash=vcs_hash, dirty=dirty)


def get_vcs_meta(root_path: Path) -> VcsMeta:
    """
    Return VCS metadata for the repository containing root_path.

    Falls back to unknown values when no supported VCS is detected.
    """
    git_meta = _get_git_meta(root_path)
    if git_meta:
        return git_meta

    svn_meta = _get_svn_meta(root_path)
    if svn_meta:
        return svn_meta

    p4_meta = _get_p4_meta(root_path)
    if p4_meta:
        return p4_meta

    return VcsMeta(
        provider=_UNKNOWN,
        branch=_UNKNOWN,
        revno=_UNKNOWN,
        hash=_UNKNOWN,
        dirty=_UNKNOWN,
    )
