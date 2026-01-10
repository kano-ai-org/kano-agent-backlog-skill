#!/usr/bin/env python3
"""
User-facing prerequisites installer for kano-agent-backlog-skill (stdlib-only).

Use this in consumer repos that *use* the skill (as a submodule or copied folder),
to avoid wasting tokens on ad-hoc installs when a script fails mid-run.

Defaults:
- Creates a local venv: `.venv/`
- Installs the skill in editable mode (no dev extras)

Examples:
  python skills/kano-agent-backlog-skill/scripts/bootstrap/install_prereqs.py
  python skills/kano-agent-backlog-skill/scripts/bootstrap/install_prereqs.py --dev
  python skills/kano-agent-backlog-skill/scripts/bootstrap/install_prereqs.py --with-embeddings
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
        "--dev",
        action="store_true",
        help="Also install developer/test tooling extras (skill contributors).",
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

    if sys.version_info < (3, 10):
        print("ERROR: Python 3.10+ is required.", file=sys.stderr)
        return 2

    venv_dir = Path(args.venv).resolve()
    python_for_venv = Path(args.python).resolve()

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

    target = str(skill_root)
    if args.dev:
        target = f"{target}[dev]"

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

