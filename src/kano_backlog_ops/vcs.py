from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_UNKNOWN = "unknown"


@dataclass
class VcsMeta:
    """VCS-agnostic metadata used for reproducible outputs."""

    provider: str
    revision: str
    ref: str
    label: Optional[str]
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


def _get_git_meta(root_path: Path) -> Optional[VcsMeta]:
    """Collect git metadata if available; return None when not in a git repo."""
    # Ensure git is available and we are inside a repo.
    toplevel = _run_git(["rev-parse", "--show-toplevel"], root_path)
    if not toplevel:
        return None

    revision = _run_git(["rev-parse", "HEAD"], root_path) or _UNKNOWN
    ref = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], root_path) or _UNKNOWN

    label = _run_git(["describe", "--tags", "--abbrev=0"], root_path)
    if not label:
        # Fallback to a short describe to get a human hint without failing hard.
        label = _run_git(["describe", "--always", "--abbrev=8"], root_path)

    status = _run_git(["status", "--porcelain"], root_path)
    dirty = "unknown"
    if status is not None:
        dirty = "true" if status.strip() else "false"

    return VcsMeta(
        provider="git",
        revision=revision,
        ref=ref,
        label=label,
        dirty=dirty,
    )


def get_vcs_meta(root_path: Path) -> VcsMeta:
    """
    Return VCS metadata for the repository containing root_path.

    Falls back to unknown values when no supported VCS is detected.
    """
    git_meta = _get_git_meta(root_path)
    if git_meta:
        return git_meta

    return VcsMeta(
        provider=_UNKNOWN,
        revision=_UNKNOWN,
        ref=_UNKNOWN,
        label=None,
        dirty=_UNKNOWN,
    )
