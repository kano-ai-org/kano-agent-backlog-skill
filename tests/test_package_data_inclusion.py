"""
Test package data inclusion in distribution.

Validates Requirements: 2.3, 2.5, 1.4
"""

import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import List, Set

import pytest


def test_sdist_includes_required_files():
    """Verify source distribution includes all required files."""
    # Build the package
    result = subprocess.run(
        ["python", "-m", "build", "--sdist", "--outdir", "dist-test"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"Build failed: {result.stderr}"

    # Find the sdist file
    dist_dir = Path(__file__).parent.parent / "dist-test"
    sdist_files = list(dist_dir.glob("kano_agent_backlog_skill-*.tar.gz"))
    assert len(sdist_files) > 0, "No sdist file found"
    sdist_path = sdist_files[0]

    # Extract file list from sdist
    with tarfile.open(sdist_path, "r:gz") as tar:
        file_list = [member.name for member in tar.getmembers()]

    # Check required documentation files
    assert any("LICENSE" in f for f in file_list), "LICENSE not in sdist"
    assert any("README.md" in f for f in file_list), "README.md not in sdist"
    assert any("CHANGELOG.md" in f for f in file_list), "CHANGELOG.md not in sdist"

    # Check templates directory is included
    template_files = [f for f in file_list if "templates/" in f]
    assert len(template_files) > 0, "No template files in sdist"

    # Check specific template files
    assert any("config.template.toml" in f for f in template_files), (
        "config.template.toml not in sdist"
    )
    assert any("bugfix/brief.md.template" in f for f in template_files), (
        "bugfix template not in sdist"
    )
    assert any("feature/spec/requirements.md.template" in f for f in template_files), (
        "feature spec template not in sdist"
    )

    # Check schema files are included
    schema_files = [f for f in file_list if "schema/" in f and f.endswith(".sql")]
    assert len(schema_files) >= 2, f"Expected at least 2 SQL schema files, found {len(schema_files)}"
    assert any("canonical_schema.sql" in f for f in schema_files), (
        "canonical_schema.sql not in sdist"
    )
    assert any("indexing_schema.sql" in f for f in schema_files), (
        "indexing_schema.sql not in sdist"
    )


def test_wheel_includes_package_data():
    """Verify wheel includes package data (SQL schemas, py.typed)."""
    # Build the package
    result = subprocess.run(
        ["python", "-m", "build", "--wheel", "--outdir", "dist-test"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"Build failed: {result.stderr}"

    # Find the wheel file
    dist_dir = Path(__file__).parent.parent / "dist-test"
    wheel_files = list(dist_dir.glob("kano_agent_backlog_skill-*.whl"))
    assert len(wheel_files) > 0, "No wheel file found"
    wheel_path = wheel_files[0]

    # Extract file list from wheel
    with zipfile.ZipFile(wheel_path, "r") as whl:
        file_list = whl.namelist()

    # Check SQL schema files are included in wheel
    schema_files = [f for f in file_list if "schema/" in f and f.endswith(".sql")]
    assert len(schema_files) >= 2, f"Expected at least 2 SQL schema files in wheel, found {len(schema_files)}"
    assert any("canonical_schema.sql" in f for f in schema_files), (
        "canonical_schema.sql not in wheel"
    )
    assert any("indexing_schema.sql" in f for f in schema_files), (
        "indexing_schema.sql not in wheel"
    )

    # Check py.typed marker files are included
    py_typed_files = [f for f in file_list if f.endswith("py.typed")]
    assert len(py_typed_files) >= 3, (
        f"Expected at least 3 py.typed files (core, ops, cli), found {len(py_typed_files)}"
    )
    assert any("kano_backlog_core/py.typed" in f for f in py_typed_files), (
        "kano_backlog_core/py.typed not in wheel"
    )
    assert any("kano_backlog_ops/py.typed" in f for f in py_typed_files), (
        "kano_backlog_ops/py.typed not in wheel"
    )
    assert any("kano_backlog_cli/py.typed" in f for f in py_typed_files), (
        "kano_backlog_cli/py.typed not in wheel"
    )


def test_wheel_excludes_development_files():
    """Verify wheel excludes development and test files."""
    # Build the package
    result = subprocess.run(
        ["python", "-m", "build", "--wheel", "--outdir", "dist-test"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"Build failed: {result.stderr}"

    # Find the wheel file
    dist_dir = Path(__file__).parent.parent / "dist-test"
    wheel_files = list(dist_dir.glob("kano_agent_backlog_skill-*.whl"))
    assert len(wheel_files) > 0, "No wheel file found"
    wheel_path = wheel_files[0]

    # Extract file list from wheel
    with zipfile.ZipFile(wheel_path, "r") as whl:
        file_list = whl.namelist()

    # Check that development files are NOT included
    excluded_patterns = [
        "tests/",
        ".git/",
        ".github/",
        ".hypothesis/",
        ".pytest_cache/",
        "htmlcov/",
        ".cache/",
        ".kano/",
        "__pycache__/",
        ".pyc",
        ".pyo",
    ]

    for pattern in excluded_patterns:
        matching_files = [f for f in file_list if pattern in f]
        assert len(matching_files) == 0, (
            f"Development files with pattern '{pattern}' found in wheel: {matching_files[:5]}"
        )


def test_package_discovery_finds_all_packages():
    """Verify setuptools discovers all packages under src/."""
    # Build the package
    result = subprocess.run(
        ["python", "-m", "build", "--wheel", "--outdir", "dist-test"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"Build failed: {result.stderr}"

    # Find the wheel file
    dist_dir = Path(__file__).parent.parent / "dist-test"
    wheel_files = list(dist_dir.glob("kano_agent_backlog_skill-*.whl"))
    assert len(wheel_files) > 0, "No wheel file found"
    wheel_path = wheel_files[0]

    # Extract file list from wheel
    with zipfile.ZipFile(wheel_path, "r") as whl:
        file_list = whl.namelist()

    # Check that all expected packages are included
    expected_packages = [
        "kano_backlog_core",
        "kano_backlog_ops",
        "kano_backlog_cli",
        "kano_backlog_core/schema",
        "kano_backlog_core/embedding",
        "kano_backlog_core/vector",
        "kano_backlog_core/vcs",
        "kano_backlog_cli/commands",
    ]

    for package in expected_packages:
        # Check for __init__.py or at least one .py file in the package
        package_files = [f for f in file_list if f.startswith(package + "/") and f.endswith(".py")]
        assert len(package_files) > 0, f"Package '{package}' not found in wheel"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
