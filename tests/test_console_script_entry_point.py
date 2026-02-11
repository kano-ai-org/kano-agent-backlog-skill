"""
Test console script entry point configuration.

This test validates Requirements 1.2 and 2.2 from the release-0-1-0-beta spec:
- The package declares entry points for the console script `kano-backlog`
- The CLI is available as `kano-backlog` command after installation
"""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib as tomli
else:
    import tomli


def test_console_script_entry_point_exists():
    """Verify [project.scripts] section exists with kano-backlog entry point."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    
    with open(pyproject_path, "rb") as f:
        config = tomli.load(f)
    
    # Verify [project.scripts] section exists
    assert "project" in config, "pyproject.toml missing [project] section"
    assert "scripts" in config["project"], "pyproject.toml missing [project.scripts] section"
    
    # Verify kano-backlog entry point exists
    scripts = config["project"]["scripts"]
    assert "kano-backlog" in scripts, "Missing 'kano-backlog' console script entry point"
    
    # Verify entry point points to correct function
    entry_point = scripts["kano-backlog"]
    assert entry_point == "kano_backlog_cli.cli:main", (
        f"Entry point should be 'kano_backlog_cli.cli:main', got '{entry_point}'"
    )


def test_entry_point_function_is_callable():
    """Verify the entry point function exists and is callable."""
    from kano_backlog_cli.cli import main
    
    assert callable(main), "Entry point function 'main' is not callable"


def test_entry_point_module_structure():
    """Verify the module structure matches the entry point configuration."""
    # Verify the module can be imported
    import kano_backlog_cli.cli
    
    # Verify the main function exists
    assert hasattr(kano_backlog_cli.cli, "main"), (
        "Module kano_backlog_cli.cli missing 'main' function"
    )
    
    # Verify it's the correct type
    main_func = getattr(kano_backlog_cli.cli, "main")
    assert callable(main_func), "main attribute is not callable"


def test_version_accessible_from_cli():
    """Verify version information is accessible from CLI module."""
    from kano_backlog_cli.cli import __version__
    
    assert isinstance(__version__, str), "Version should be a string"
    assert len(__version__) > 0, "Version should not be empty"
    
    # Verify it follows semantic versioning pattern (basic check)
    parts = __version__.split(".")
    assert len(parts) >= 2, f"Version '{__version__}' should have at least MAJOR.MINOR"
