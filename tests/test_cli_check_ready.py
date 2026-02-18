"""Tests for check-ready CLI command."""
import os
from pathlib import Path

from typer.testing import CliRunner

from kano_backlog_cli.cli import app

from conftest import write_project_backlog_config

runner = CliRunner()


def _invoke_from(tmp_path: Path, args: list[str]):
    cwd_before = Path.cwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(app, args)
    finally:
        os.chdir(cwd_before)

def test_check_ready_command(tmp_path: Path):
    """Test item check-ready command."""
    write_project_backlog_config(tmp_path)
    # Setup backlog
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    
    # Create Feature (not ready)
    feature_dir = product_root / "items" / "feature" / "0000"
    feature_dir.mkdir(parents=True)
    feature_path = feature_dir / "TEST-FTR-0001_test-feature.md"
    feature_path.write_text("""---
id: TEST-FTR-0001
uid: 00000000-0000-0000-0000-000000000001
type: Feature
title: Test Feature
state: Proposed
created: 2026-01-01
updated: 2026-01-01
---
""", encoding="utf-8")

    # Create Task (ready) with parent
    task_dir = product_root / "items" / "task" / "0000"
    task_dir.mkdir(parents=True)
    task_path = task_dir / "TEST-TSK-0001_test-task.md"
    task_path.write_text("""---
id: TEST-TSK-0001
uid: 00000000-0000-0000-0000-000000000002
type: Task
title: Test Task
state: Proposed
parent: TEST-FTR-0001
created: 2026-01-01
updated: 2026-01-01
---

# Context
Context

# Goal
Goal

# Approach
Approach

# Acceptance Criteria
AC

# Risks / Dependencies
Risks
""", encoding="utf-8")

    # Run check-ready on Task (should FAIL because parent is not Ready)
    result = _invoke_from(
        tmp_path,
        [
            "item",
            "check-ready",
            "TEST-TSK-0001",
            "--product",
            "test-product",
            "--backlog-root-override",
            str(backlog_root),
        ],
    )
    assert result.exit_code == 1
    assert "TEST-TSK-0001 is NOT READY" in result.stdout
    assert "Parent TEST-FTR-0001 is NOT READY" in result.stdout
    
    # Run check-ready with --no-check-parent (should pass)
    result = _invoke_from(
        tmp_path,
        [
            "item",
            "check-ready",
            "TEST-TSK-0001",
            "--no-check-parent",
            "--product",
            "test-product",
            "--backlog-root-override",
            str(backlog_root),
        ],
    )
    assert result.exit_code == 0
    assert "OK: TEST-TSK-0001 is READY" in result.stdout
    
    # Make feature ready
    feature_path.write_text("""---
id: TEST-FTR-0001
uid: 00000000-0000-0000-0000-000000000001
type: Feature
title: Test Feature
state: Proposed
created: 2026-01-01
updated: 2026-01-01
---

# Context
Context

# Goal
Goal

# Approach
Approach

# Acceptance Criteria
AC

# Risks / Dependencies
Risks
""", encoding="utf-8")

    # Run check-ready again (should pass)
    result = _invoke_from(
        tmp_path,
        [
            "item",
            "check-ready",
            "TEST-TSK-0001",
            "--product",
            "test-product",
            "--backlog-root-override",
            str(backlog_root),
        ],
    )
    assert result.exit_code == 0
    assert "OK: TEST-TSK-0001 is READY" in result.stdout

def test_check_ready_parent_failure(tmp_path: Path):
    """Test check-ready fails when parent task is not ready."""
    write_project_backlog_config(tmp_path)
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    
    task_dir = product_root / "items" / "task" / "0000"
    task_dir.mkdir(parents=True)
    parent_path = task_dir / "TEST-TSK-0001_parent.md"
    parent_path.write_text("""---
id: TEST-TSK-0001
uid: 00000000-0000-0000-0000-000000000001
type: Task
title: Parent Task
state: Proposed
created: 2026-01-01
updated: 2026-01-01
---
""", encoding="utf-8")

    child_path = task_dir / "TEST-TSK-0002_child.md"
    child_path.write_text("""---
id: TEST-TSK-0002
uid: 00000000-0000-0000-0000-000000000002
type: Task
title: Child Task
state: Proposed
parent: TEST-TSK-0001
created: 2026-01-01
updated: 2026-01-01
---

# Context
Context

# Goal
Goal

# Approach
Approach

# Acceptance Criteria
AC

# Risks / Dependencies
Risks
""", encoding="utf-8")

    result = _invoke_from(
        tmp_path,
        [
            "item",
            "check-ready",
            "TEST-TSK-0002",
            "--product",
            "test-product",
            "--backlog-root-override",
            str(backlog_root),
        ],
    )
    assert result.exit_code == 1
    assert "Parent TEST-TSK-0001 is NOT READY" in result.stdout

def test_check_ready_task_failure(tmp_path: Path):
    """Test that check-ready fails for incomplete task."""
    write_project_backlog_config(tmp_path)
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "test-product"
    
    task_dir = product_root / "items" / "task" / "0000"
    task_dir.mkdir(parents=True)
    task_path = task_dir / "TEST-TSK-0002_incomplete.md"
    task_path.write_text("""---
id: TEST-TSK-0002
uid: 00000000-0000-0000-0000-000000000003
type: Task
title: Incomplete Task
state: Proposed
created: 2026-01-01
updated: 2026-01-01
---
""", encoding="utf-8")

    result = _invoke_from(
        tmp_path,
        [
            "item",
            "check-ready",
            "TEST-TSK-0002",
            "--product",
            "test-product",
            "--backlog-root-override",
            str(backlog_root),
        ],
    )
    assert result.exit_code == 1
    assert "TEST-TSK-0002 is NOT READY" in result.stdout
    assert "Missing fields in TEST-TSK-0002" in result.stdout
    assert "Context" in result.stdout
