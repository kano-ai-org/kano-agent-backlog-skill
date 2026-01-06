#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.dont_write_bytecode = True

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from config_loader import (  # noqa: E402
    allowed_roots_for_repo,
    default_config,
    get_config_value,
    load_config_with_defaults,
    resolve_allowed_root,
    validate_config,
)
from product_args import add_product_arguments  # noqa: E402


MARKER_START = "<!-- kano-agent-backlog-skill:start -->"
MARKER_END = "<!-- kano-agent-backlog-skill:end -->"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "First-run bootstrap for kano-agent-backlog-skill: create `_kano/backlog/` scaffold, "
            "write baseline config, refresh dashboards, and optionally update agent guide files."
        )
    )
    parser.add_argument(
        "--backlog-root",
        default="_kano/backlog",
        help="Backlog root path (default: _kano/backlog).",
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Agent identity running the script (required, used for auditability).",
    )
    parser.add_argument(
        "--project-name",
        help="Project name to store in config (default: repo folder name).",
    )
    parser.add_argument(
        "--prefix",
        help="ID prefix override to store in config (default: derived from project name).",
    )
    parser.add_argument(
        "--force-project",
        action="store_true",
        help="Overwrite existing config project.name/prefix values.",
    )
    parser.add_argument(
        "--write-guides",
        choices=["none", "create", "append", "update"],
        default="none",
        help=(
            "Update agent guide files at repo root. "
            "`create` creates missing files; `append` appends the block; `update` replaces block if present "
            "(default: none)."
        ),
    )
    parser.add_argument(
        "--guides",
        default="AGENTS.md,CLAUDE.md",
        help="Comma-separated guide filenames to update at repo root (default: AGENTS.md,CLAUDE.md).",
    )
    parser.add_argument(
        "--skill-root",
        help="Skill root path to render into guide templates (default: auto-detect or `skills/kano-agent-backlog-skill`).",
    )
    parser.add_argument(
        "--refresh-dashboards",
        choices=["yes", "no"],
        default="yes",
        help="Whether to refresh dashboards after init (default: yes).",
    )
    parser.add_argument(
        "--process-profile",
        help="Process profile ID (e.g. builtin/azure-boards-agile). Overrides defaults.",
    )
    parser.add_argument(
        "--process-path",
        help="Process profile JSON path (relative to repo root or absolute). Overrides defaults.",
    )
    parser.add_argument(
        "--force-process",
        action="store_true",
        help="Overwrite existing config process.profile/path values.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing files.",
    )
    add_product_arguments(parser)
    return parser.parse_args()


def ensure_under_allowed(path: Path, allowed_roots: List[Path], label: str) -> Path:
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(root) for root in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def run_cmd(cmd: List[str], dry_run: bool) -> None:
    if dry_run:
        print("[DRY] " + " ".join(cmd))
        return
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"Command failed: {' '.join(cmd)}")


def split_segments(name: str) -> List[str]:
    import re

    parts = re.split(r"[^A-Za-z0-9]+", name)
    segments: List[str] = []
    for part in parts:
        if not part:
            continue
        segments.extend(re.findall(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+", part))
    return segments


def derive_prefix(name: str) -> str:
    segments = split_segments(name)
    letters = []
    for seg in segments:
        for ch in seg:
            if ch.isalpha():
                letters.append(ch)
                break
    prefix = "".join(letters)

    if len(prefix) == 1:
        seed = segments[0] if segments else name
        consonant = ""
        for ch in seed[1:]:
            if ch.isalpha() and ch.upper() not in "AEIOU":
                consonant = ch
                break
        if consonant:
            prefix += consonant
        else:
            for ch in seed[1:]:
                if ch.isalpha():
                    prefix += ch
                    break

    if len(prefix) < 2:
        letters = [ch for ch in name if ch.isalpha()]
        if len(letters) >= 2:
            prefix = letters[0] + letters[1]

    prefix = prefix.upper()
    if not prefix or not prefix.isalnum():
        raise SystemExit("Unable to derive a safe project prefix. Provide --prefix.")
    return prefix


def load_template_block(skill_root: Path, file_name: str) -> str:
    templates_dir = skill_root / "templates"
    path = templates_dir / file_name
    if not path.exists():
        raise SystemExit(f"Missing template: {path}")
    return path.read_text(encoding="utf-8")


def render_block(template: str, replacements: Dict[str, str]) -> str:
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered.rstrip() + "\n"


def upsert_marked_block(existing: str, block: str, mode: str) -> str:
    if MARKER_START in existing and MARKER_END in existing:
        if mode not in {"update", "append", "create"}:
            return existing
        before, rest = existing.split(MARKER_START, 1)
        _, after = rest.split(MARKER_END, 1)
        return before.rstrip() + "\n\n" + block.strip() + "\n\n" + after.lstrip()
    if mode == "append":
        return existing.rstrip() + "\n\n" + block.strip() + "\n"
    return existing


def safe_write(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[DRY] write {path}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"Wrote: {path}")


def main() -> int:
    args = parse_args()
    agent = args.agent
    repo_root = Path.cwd().resolve()

    # Backlog root must stay under allowed roots (protects against misuse).
    allowed_roots = allowed_roots_for_repo(repo_root)
    backlog_root = Path(args.backlog_root)
    if not backlog_root.is_absolute():
        backlog_root = (repo_root / backlog_root).resolve()
    ensure_under_allowed(backlog_root, allowed_roots, "backlog-root")

    # Detect skill root from this file, but allow override for unusual layouts.
    skill_root = Path(args.skill_root).resolve() if args.skill_root else Path(__file__).resolve().parents[2]
    skill_root_hint = None
    try:
        skill_root_hint = skill_root.relative_to(repo_root).as_posix()
    except ValueError:
        skill_root_hint = skill_root.as_posix()

    project_name = (args.project_name or repo_root.name).strip()
    prefix = (args.prefix or "").strip()
    if not prefix:
        prefix = derive_prefix(project_name)

    init_backlog = Path(__file__).resolve().parent / "bootstrap_init_backlog.py"
    python = sys.executable
    init_cmd = [python, str(init_backlog), "--backlog-root", str(backlog_root)]
    if args.process_profile:
        init_cmd.extend(["--process-profile", args.process_profile])
    if args.process_path:
        init_cmd.extend(["--process-path", args.process_path])
    run_cmd(init_cmd, args.dry_run)

    # Ensure baseline config exists and inject project fields.
    config_path = backlog_root / "_config" / "config.json"
    if config_path.exists():
        config = load_config_with_defaults(repo_root=repo_root, config_path=str(config_path))
    else:
        config = {"_comment": "Baseline config for kano-agent-backlog-skill."}
        config.update(default_config())

    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    if args.force_project or not get_config_value(config, "project.name"):
        config.setdefault("project", {})
        config["project"]["name"] = project_name
    if args.force_project or not get_config_value(config, "project.prefix"):
        config.setdefault("project", {})
        config["project"]["prefix"] = prefix
    if args.process_profile or args.process_path:
        if args.force_process or not get_config_value(config, "process.profile") and not get_config_value(config, "process.path"):
            config.setdefault("process", {})
            if args.process_profile:
                config["process"]["profile"] = args.process_profile
                config["process"]["path"] = None
            if args.process_path:
                config["process"]["path"] = args.process_path
                config["process"]["profile"] = None

    rendered_config = json.dumps(config, indent=2, ensure_ascii=True) + "\n"
    if config_path.exists() and not args.dry_run:
        try:
            existing_config = config_path.read_text(encoding="utf-8")
        except OSError:
            existing_config = None
        if existing_config == rendered_config:
            print(f"Skip config: no changes ({config_path})")
        else:
            safe_write(config_path, rendered_config, args.dry_run)
    else:
        safe_write(config_path, rendered_config, args.dry_run)

    if args.refresh_dashboards == "yes":
        refresh = Path(__file__).resolve().parent / "view_refresh_dashboards.py"
        run_cmd([python, str(refresh), "--backlog-root", str(backlog_root), "--agent", agent], args.dry_run)

    mode = args.write_guides
    if mode != "none":
        guide_names = [p.strip() for p in args.guides.split(",") if p.strip()]
        replacements = {
            "SKILL_ROOT": skill_root_hint,
            "BACKLOG_ROOT": backlog_root.relative_to(repo_root).as_posix(),
        }
        for name in guide_names:
            if name not in {"AGENTS.md", "CLAUDE.md"}:
                raise SystemExit(f"Unsupported guide name: {name} (allowed: AGENTS.md, CLAUDE.md)")
            template_name = "AGENTS.block.md" if name == "AGENTS.md" else "CLAUDE.block.md"
            block = render_block(load_template_block(skill_root, template_name), replacements)
            target = repo_root / name
            if target.exists():
                existing = target.read_text(encoding="utf-8")
                updated = upsert_marked_block(existing, block, mode=mode)
                if updated != existing:
                    safe_write(target, updated, args.dry_run)
                else:
                    if MARKER_START not in existing:
                        print(f"Skip {name}: no marker block found. Use --write-guides append to add it.")
                    else:
                        print(f"Skip {name}: mode={mode} made no changes.")
            else:
                if mode in {"create"}:
                    header = f"# {name.replace('.md','')}\n\n"
                    safe_write(target, header + block, args.dry_run)
                else:
                    print(f"Skip {name}: file does not exist. Use --write-guides create to create it.")
    else:
        print("Next steps:")
        print(f"- Create items: python {skill_root_hint}/scripts/backlog/workitem_create.py --agent <agent-name> --type Task --title \"...\"")
        print(f"- Refresh dashboards: python {skill_root_hint}/scripts/backlog/view_refresh_dashboards.py --backlog-root {backlog_root.relative_to(repo_root).as_posix()} --agent <agent-name>")
        print("Tip: add the skill block to AGENTS.md/CLAUDE.md via:")
        print(f"- Create missing: python {skill_root_hint}/scripts/backlog/bootstrap_init_project.py --agent <agent-name> --write-guides create")
        print(f"- Append to existing: python {skill_root_hint}/scripts/backlog/bootstrap_init_project.py --agent <agent-name> --write-guides append")

    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
