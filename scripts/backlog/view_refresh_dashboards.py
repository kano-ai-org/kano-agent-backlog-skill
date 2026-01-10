#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    get_config_value,
    load_config_with_defaults,
    resolve_allowed_root,
    validate_config,
)
from context import find_platform_root, get_product_root, get_sandbox_root_or_none  # noqa: E402
from product_args import add_product_arguments, get_product_and_sandbox_flags  # noqa: E402

LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))
from deprecation import warn_deprecated_script  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh generated Markdown dashboards (optionally using SQLite index)."
    )
    parser.add_argument(
        "--backlog-root",
        default="_kano/backlog",
        help="Backlog root path (default: _kano/backlog).",
    )
    parser.add_argument(
        "--config",
        help=(
            "Optional config path override. When omitted, uses KANO_BACKLOG_CONFIG_PATH if set, "
            "otherwise `<backlog-root>/_config/config.json` when present."
        ),
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Agent identity running the script (required, used for auditability).",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "files", "sqlite"],
        default="auto",
        help="Dashboard data source (default: auto).",
    )
    parser.add_argument(
        "--refresh-index",
        choices=["auto", "skip", "rebuild", "incremental"],
        default="auto",
        help="Whether to refresh the SQLite index before rendering (default: auto).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing.",
    )
    parser.add_argument(
        "--products",
        action="append",
        help="Comma-separated product names to aggregate (repeatable).",
    )
    parser.add_argument(
        "--all-products",
        action="store_true",
        help="Aggregate across all products under the platform root.",
    )
    parser.add_argument(
        "--all-personas",
        action="store_true",
        help=(
            "Generate persona views for all personas (developer/pm/qa). "
            "When enabled, also generates derived analysis templates from each report."
        ),
    )
    add_product_arguments(parser)
    return parser.parse_args()


def ensure_under_allowed(path: Path, allowed_roots: List[Path], label: str) -> Path:
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(root) for root in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def resolve_config_for_backlog_root(backlog_root: Path, cli_config: Optional[str]) -> Optional[str]:
    if cli_config is not None:
        return cli_config
    if os.getenv("KANO_BACKLOG_CONFIG_PATH"):
        return None
    candidate = backlog_root / "_config" / "config.json"
    if candidate.exists():
        return str(candidate)
    return None


def run_cmd(cmd: List[str], dry_run: bool) -> None:
    if dry_run:
        print("[DRY] " + " ".join(cmd))
        return
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"Command failed: {' '.join(cmd)}")


def parse_products_values(values: Optional[List[str]]) -> List[str]:
    if not values:
        return []
    products: List[str] = []
    for raw in values:
        if not raw:
            continue
        for part in raw.split(","):
            name = part.strip()
            if name:
                products.append(name)
    deduped: List[str] = []
    seen: set[str] = set()
    for name in products:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


def list_all_products(platform_root: Path) -> List[str]:
    products_dir = platform_root / "products"
    if not products_dir.exists():
        return []
    names: List[str] = []
    for entry in sorted(products_dir.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            names.append(entry.name)
    return names


def main() -> int:
    warn_deprecated_script("view_refresh_dashboards.py", "kano view refresh")
    args = parse_args()
    agent = args.agent

    repo_root = Path.cwd().resolve()
    allowed_roots = allowed_roots_for_repo(repo_root)

    products = parse_products_values(getattr(args, "products", None))
    if getattr(args, "all_products", False):
        if products:
            raise SystemExit("--products and --all-products cannot be used together.")
        products = list_all_products(find_platform_root(repo_root))

    product_name, use_sandbox = get_product_and_sandbox_flags(args)
    if product_name and products:
        raise SystemExit("Use either --product or --products/--all-products, not both.")

    backlog_root = Path(args.backlog_root)
    if not backlog_root.is_absolute():
        backlog_root = (repo_root / backlog_root).resolve()
    if product_name and str(args.backlog_root).strip() == "_kano/backlog":
        platform_root = find_platform_root(repo_root)
        if use_sandbox:
            backlog_root = get_sandbox_root_or_none(product_name, platform_root) or (platform_root / "sandboxes" / product_name)
        else:
            backlog_root = get_product_root(product_name, platform_root)
    root = ensure_under_allowed(backlog_root, allowed_roots, "backlog-root")

    config_path = resolve_config_for_backlog_root(backlog_root, args.config)
    config = load_config_with_defaults(repo_root=repo_root, config_path=config_path)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))

    persona = str(get_config_value(config, "mode.persona") or "developer").strip().lower()
    if persona not in {"developer", "pm", "qa"}:
        persona = "developer"

    llm_analysis_enabled = bool(get_config_value(config, "analysis.llm.enabled", False))

    personas: List[str] = ["developer", "pm", "qa"] if args.all_personas else [persona]
    analysis_enabled_for_run = llm_analysis_enabled or args.all_personas

    refresh = args.refresh_index

    python = sys.executable
    scripts_root = Path(__file__).resolve().parents[1]

    if products:
        platform_root = find_platform_root(repo_root)
        if refresh != "skip":
            build = scripts_root / "indexing" / "build_sqlite_index.py"
            for name in products:
                product_root = (
                    (get_sandbox_root_or_none(name, platform_root) or (platform_root / "sandboxes" / name))
                    if use_sandbox
                    else get_product_root(name, platform_root)
                )
                per_config_path = resolve_config_for_backlog_root(product_root, args.config)
                per_config = load_config_with_defaults(
                    repo_root=repo_root,
                    config_path=per_config_path,
                    product_name=name,
                )
                per_errors = validate_config(per_config)
                if per_errors:
                    raise SystemExit("Invalid config:\n- " + "\n- ".join(per_errors))
                index_enabled = bool(get_config_value(per_config, "index.enabled", False))
                backend = str(get_config_value(per_config, "index.backend") or "sqlite").strip().lower()
                mode = refresh
                if mode == "auto":
                    mode = "incremental" if index_enabled and backend == "sqlite" else "skip"
                if mode == "skip":
                    continue
                if backend != "sqlite":
                    print(f"Skip index refresh: backend={backend} (only sqlite supported).")
                    continue
                cmd = [python, str(build), "--backlog-root", str(product_root), "--agent", agent, "--mode", mode]
                if args.config:
                    cmd.extend(["--config", args.config])
                run_cmd(cmd, args.dry_run)
    else:
        index_enabled = bool(get_config_value(config, "index.enabled", False))
        backend = str(get_config_value(config, "index.backend") or "sqlite").strip().lower()
        mode = refresh
        if mode == "auto":
            mode = "incremental" if index_enabled and backend == "sqlite" else "skip"
        if mode != "skip":
            if backend != "sqlite":
                print(f"Skip index refresh: backend={backend} (only sqlite supported).")
            else:
                build = scripts_root / "indexing" / "build_sqlite_index.py"
                cmd = [python, str(build), "--backlog-root", str(backlog_root), "--agent", agent, "--mode", mode]
                if args.config:
                    cmd.extend(["--config", args.config])
                run_cmd(cmd, args.dry_run)

    generate = scripts_root / "backlog" / "view_generate.py"
    items_root = backlog_root / "items"
    views_root = backlog_root / "views"

    if products:
        platform_root = find_platform_root(repo_root)
        items_root = platform_root / "items"
        views_root = platform_root / "views"

    dashboards = [
        ("New,InProgress", "InProgress Work", views_root / "Dashboard_PlainMarkdown_Active.md"),
        ("New", "New Work", views_root / "Dashboard_PlainMarkdown_New.md"),
        ("Done", "Done Work", views_root / "Dashboard_PlainMarkdown_Done.md"),
    ]

    for groups, title, output in dashboards:
        cmd = [
            python,
            str(generate),
            "--source",
            args.source,
            "--items-root",
            str(items_root),
            "--backlog-root",
            str(backlog_root),
            "--output",
            str(output),
            "--groups",
            groups,
            "--title",
            title,
        ]
        if products:
            cmd.extend(["--products", ",".join(products)])
        if args.config:
            cmd.extend(["--config", args.config])
        run_cmd(cmd, args.dry_run)

    for persona_value in personas:
        # Persona-aware summary (deterministic, non-LLM).
        summary = scripts_root / "backlog" / "view_generate_summary.py"
        summary_output = views_root / f"Summary_{persona_value}.md"
        cmd = [
            python,
            str(summary),
            "--source",
            args.source,
            "--items-root",
            str(items_root),
            "--backlog-root",
            str(backlog_root),
            "--persona",
            persona_value,
            "--output",
            str(summary_output),
        ]
        if products:
            cmd.extend(["--products", ",".join(products)])
        elif product_name:
            cmd.extend(["--product", product_name])
        if use_sandbox:
            cmd.append("--sandbox")
        if args.config:
            cmd.extend(["--config", args.config])
        run_cmd(cmd, args.dry_run)

        # Persona-aware narrative report (deterministic, non-LLM).
        report = scripts_root / "backlog" / "view_generate_report.py"
        report_output = views_root / f"Report_{persona_value}.md"
        cmd = [
            python,
            str(report),
            "--source",
            args.source,
            "--items-root",
            str(items_root),
            "--backlog-root",
            str(backlog_root),
            "--persona",
            persona_value,
            "--output",
            str(report_output),
        ]
        if products:
            cmd.extend(["--products", ",".join(products)])
        elif product_name:
            cmd.extend(["--product", product_name])
        if use_sandbox:
            cmd.append("--sandbox")
        if args.config:
            cmd.extend(["--config", args.config])
        run_cmd(cmd, args.dry_run)

        # Derived: analysis template (and optional auto-generation if KANO_LLM_COMMAND is set).
        if analysis_enabled_for_run:
            analysis = scripts_root / "backlog" / "view_generate_report_analysis.py"
            analysis_dir = views_root / "_analysis"
            analysis_output = analysis_dir / f"Report_{persona_value}_LLM.md"
            prompt_output = analysis_dir / f"Report_{persona_value}_analysis_prompt.md"
            cmd = [
                python,
                str(analysis),
                "--report",
                str(report_output),
                "--persona",
                persona_value,
                "--output",
                str(analysis_output),
                "--prompt-output",
                str(prompt_output),
            ]
            if args.dry_run:
                cmd.append("--dry-run")
            run_cmd(cmd, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))

