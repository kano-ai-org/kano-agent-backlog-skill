"""
doctor.py - Environment health check command.

Checks prerequisites and backlog initialization status.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@dataclass
class CheckResult:
    """Result of a single check."""
    name: str
    passed: bool
    message: str
    details: Optional[str] = None


@dataclass
class DoctorResult:
    """Overall doctor check result."""
    all_passed: bool
    checks: List[CheckResult]


def check_python_prereqs() -> CheckResult:
    """Check that required Python packages are installed."""
    missing = []
    packages = [
        ("pydantic", "pydantic"),
        ("frontmatter", "python-frontmatter"),
        ("typer", "typer"),
        ("rich", "rich"),
    ]
    
    for import_name, pip_name in packages:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)
    
    if missing:
        return CheckResult(
            name="Python Prerequisites",
            passed=False,
            message=f"Missing packages: {', '.join(missing)}",
            details=f"Install with: pip install {' '.join(missing)}",
        )
    
    return CheckResult(
        name="Python Prerequisites",
        passed=True,
        message="All required packages installed",
    )


def check_backlog_initialized(
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> CheckResult:
    """Check that backlog is initialized for the product."""
    # Find project root
    if backlog_root is None:
        # Try to find _kano/backlog in current directory or parents
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            candidate = parent / "_kano" / "backlog"
            if candidate.exists():
                backlog_root = candidate
                break
    
    if backlog_root is None or not backlog_root.exists():
        return CheckResult(
            name="Backlog Initialized",
            passed=False,
            message="Backlog root not found",
            details=(
                "Initialize the backlog with 'python skills/kano-agent-backlog-skill/scripts/kano-backlog admin "
                "init --product <name> --agent <id>' or follow SKILL.md for manual scaffolding."
            ),
        )
    
    # Check for products directory
    products_root = backlog_root / "products"
    if not products_root.exists():
        return CheckResult(
            name="Backlog Initialized",
            passed=False,
            message="No products directory found",
            details=f"Expected: {products_root}",
        )
    
    # If product specified, check that specific product
    if product:
        product_root = products_root / product
        config_path = product_root / "_config" / "config.json"
        if not config_path.exists():
            return CheckResult(
                name="Backlog Initialized",
                passed=False,
                message=f"Product '{product}' not initialized",
                details=f"Missing: {config_path}",
            )
        return CheckResult(
            name="Backlog Initialized",
            passed=True,
            message=f"Product '{product}' initialized at {product_root}",
        )
    
    # List available products
    products = [p.name for p in products_root.iterdir() if p.is_dir() and not p.name.startswith("_")]
    if not products:
        return CheckResult(
            name="Backlog Initialized",
            passed=False,
            message="No products found",
            details=(
                "Create one with 'python skills/kano-agent-backlog-skill/scripts/kano-backlog admin init --product <name> "
                "--agent <id>' or follow SKILL.md for manual scaffolding."
            ),
        )
    
    return CheckResult(
        name="Backlog Initialized",
        passed=True,
        message=f"Found {len(products)} product(s): {', '.join(products)}",
    )


def check_skill_layout() -> CheckResult:
    """Detect common repo-layout regressions (developer workflow guardrail)."""
    cwd = Path.cwd().resolve()
    skill_root: Optional[Path] = None
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "skills" / "kano-agent-backlog-skill"
        if candidate.exists() and candidate.is_dir():
            skill_root = candidate
            break

    if skill_root is None:
        return CheckResult(
            name="Skill Layout",
            passed=True,
            message="Skill root not found from cwd (skipping layout checks)",
        )

    legacy_cli_root = skill_root / "src" / "kano_cli"
    legacy_py_files = list(legacy_cli_root.rglob("*.py")) if legacy_cli_root.exists() else []
    if legacy_py_files:
        sample = legacy_py_files[0].as_posix()
        return CheckResult(
            name="Skill Layout",
            passed=False,
            message="Legacy CLI package reintroduced under src/kano_cli",
            details=(
                "Move CLI code under src/kano_backlog_cli instead. "
                f"Example offending file: {sample}"
            ),
        )

    return CheckResult(
        name="Skill Layout",
        passed=True,
        message="OK (no legacy src/kano_cli python files)",
    )


def check_kano_backlog_cli() -> CheckResult:
    """Check that kano-backlog CLI is available."""
    try:
        from kano_backlog_cli import cli
        return CheckResult(
            name="Kano CLI",
            passed=True,
            message="CLI module available",
        )
    except ImportError as e:
        return CheckResult(
            name="Kano CLI",
            passed=False,
            message="CLI module not found",
            details=str(e),
        )


def run_doctor(
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> DoctorResult:
    """Run all doctor checks."""
    checks = [
        check_python_prereqs(),
        check_skill_layout(),
        check_backlog_initialized(product=product, backlog_root=backlog_root),
        check_kano_backlog_cli(),
    ]
    
    all_passed = all(c.passed for c in checks)
    return DoctorResult(all_passed=all_passed, checks=checks)


def format_result_plain(result: DoctorResult) -> None:
    """Print result in plain text format."""
    table = Table(title="Kano Doctor", show_header=True)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Message")
    
    for check in result.checks:
        status = "[green]✓ PASS[/green]" if check.passed else "[red]✗ FAIL[/red]"
        table.add_row(check.name, status, check.message)
        if check.details:
            table.add_row("", "", f"[dim]{check.details}[/dim]")
    
    console.print(table)
    
    if result.all_passed:
        console.print("\n[green bold]All checks passed![/green bold]")
    else:
        console.print("\n[red bold]Some checks failed.[/red bold]")


def format_result_json(result: DoctorResult) -> None:
    """Print result in JSON format."""
    output = {
        "all_passed": result.all_passed,
        "checks": [asdict(c) for c in result.checks],
    }
    print(json.dumps(output, indent=2))


@app.command()
def doctor(
    product: Optional[str] = typer.Option(
        None, "--product", "-p",
        help="Product name to check (optional)",
    ),
    format: str = typer.Option(
        "plain", "--format", "-f",
        help="Output format: plain, json",
    ),
) -> None:
    """
    Check environment health.
    
    Verifies:
    - Python prerequisites are installed
    - Backlog is initialized
    - Kano CLI is available
    """
    result = run_doctor(product=product)
    
    if format == "json":
        format_result_json(result)
    else:
        format_result_plain(result)
    
    raise typer.Exit(0 if result.all_passed else 1)


if __name__ == "__main__":
    app()
