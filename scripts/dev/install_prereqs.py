#!/usr/bin/env python3
"""
Install prerequisites for using/developing kano-agent-backlog-skill (stdlib-only).

This is intended to be run by agents at the beginning of a session to avoid
ad-hoc dependency installs mid-flight.

What it does:
1) Creates a virtual environment (default: .venv/)
2) Installs kano-agent-backlog-skill in editable mode (+ optional extras)

Examples:
  python skills/kano-agent-backlog-skill/scripts/dev/install_prereqs.py
  python skills/kano-agent-backlog-skill/scripts/dev/install_prereqs.py --no-dev
  python skills/kano-agent-backlog-skill/scripts/dev/install_prereqs.py --venv .venv --with-embeddings
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path


def _format_cmd(cmd: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return " ".join(cmd)


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(cmd: list[str], *, dry_run: bool) -> None:
    print(f"+ {_format_cmd(cmd)}")
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Create a venv and install kano-agent-backlog-skill dependencies.",
    )
    parser.add_argument(
        "--venv",
        default=".venv",
        help="Virtual environment directory (default: .venv).",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to create the venv (default: current Python).",
    )
    parser.add_argument(
        "--no-dev",
        action="store_true",
        help="Do not install dev/test tooling extras.",
    )
    parser.add_argument(
        "--with-embeddings",
        action="store_true",
        help=(
            "Also install optional embedding/FAISS deps used by some indexing scripts "
            "(may not be available on all platforms)."
        ),
    )
    parser.add_argument(
        "--no-upgrade-pip",
        action="store_true",
        help="Do not upgrade pip/setuptools/wheel.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing.",
    )
    args = parser.parse_args(argv)

    venv_dir = Path(args.venv).resolve()
    python_for_venv = Path(args.python).resolve()

    if sys.version_info < (3, 10):
        print("ERROR: Python 3.10+ is required.", file=sys.stderr)
        return 2

    # Locate skill root from this file location (independent of cwd).
    skill_root = Path(__file__).resolve().parents[2]
    if not (skill_root / "pyproject.toml").exists():
        print(f"ERROR: Could not find pyproject.toml at {skill_root}", file=sys.stderr)
        return 2

    vpy = _venv_python(venv_dir)
    if not vpy.exists():
        print(f"Creating venv: {venv_dir}")
        if args.dry_run:
            print(f"+ {python_for_venv} -m venv {venv_dir}")
        else:
            venv.EnvBuilder(with_pip=True).create(venv_dir)

    vpy = _venv_python(venv_dir)
    if not vpy.exists():
        print(f"ERROR: venv python not found at {vpy}", file=sys.stderr)
        return 2

    if not args.no_upgrade_pip:
        _run([str(vpy), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], dry_run=args.dry_run)

    extras: list[str] = []
    if not args.no_dev:
        extras.append("dev")

    target = str(skill_root)
    if extras:
        target = f"{target}[{','.join(extras)}]"

    _run([str(vpy), "-m", "pip", "install", "--editable", target], dry_run=args.dry_run)

    if args.with_embeddings:
        _run(
            [
                str(vpy),
                "-m",
                "pip",
                "install",
                "sentence-transformers",
                "numpy",
                "faiss-cpu",
            ],
            dry_run=args.dry_run,
        )

    print("")
    if os.name == "nt":
        print(f"Activate: {venv_dir}\\Scripts\\Activate.ps1")
    else:
        print(f"Activate: source {venv_dir}/bin/activate")
    print("Verify: kano --help")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

