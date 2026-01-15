import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kano_backlog_cli.cli import app

runner = CliRunner()


def _scaffold_product(tmp_path: Path, name: str = "demo") -> tuple[Path, Path]:
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / name
    items_root = product_root / "items"

    for item_type in ["epic", "feature", "userstory", "task", "bug"]:
        (items_root / item_type / "0000").mkdir(parents=True, exist_ok=True)

    for required_dir in ["decisions", "views", "_meta"]:
        (product_root / required_dir).mkdir(parents=True, exist_ok=True)

    cfg_dir = product_root / "_config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_text = f"""
[product]
name = "{name}"
prefix = "{name[:2].upper()}"

[views]
auto_refresh = false

[log]
verbosity = "info"
debug = false
"""
    (cfg_dir / "config.toml").write_text(cfg_text.strip() + "\n", encoding="utf-8")

    shared = backlog_root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "defaults.json").write_text(json.dumps({"default_product": name}), encoding="utf-8")

    return backlog_root, product_root


def test_item_alias_help_lists_create():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "item" in result.output

    create_help = runner.invoke(app, ["item", "create", "--help"])
    assert create_help.exit_code == 0, create_help.output
    for flag in ["--type", "--title", "--agent", "--product"]:
        assert flag in create_help.output


def test_item_create_creates_file_and_uses_config_prefix(tmp_path: Path):
    backlog_root, product_root = _scaffold_product(tmp_path, name="demo-product")
    cwd_before = Path.cwd()
    os.chdir(tmp_path)

    try:
        result = runner.invoke(
            app,
            [
                "item",
                "create",
                "--type",
                "task",
                "--title",
                "Test Task",
                "--priority",
                "P2",
                "--agent",
                "tester",
                "--product",
                "demo-product",
            ],
        )
        assert result.exit_code == 0, result.output
        lines = [line.strip() for line in result.output.splitlines() if line.strip()]
        created_line = next(line for line in lines if line.startswith("OK: Created:"))
        created_id = created_line.split(":", 2)[-1].strip()
        assert created_id.startswith("DE-TSK-")

        created_files = list((product_root / "items").rglob(f"{created_id}_*.md"))
        assert created_files, "Expected created item file on disk"
    finally:
        os.chdir(cwd_before)


def test_item_create_records_unknown_model_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _scaffold_product(tmp_path, name="demo-product")
    cwd_before = Path.cwd()
    os.chdir(tmp_path)

    monkeypatch.delenv("KANO_AGENT_MODEL", raising=False)
    monkeypatch.delenv("KANO_MODEL", raising=False)

    try:
        result = runner.invoke(
            app,
            [
                "item",
                "create",
                "--type",
                "task",
                "--title",
                "Model-less Task",
                "--priority",
                "P2",
                "--agent",
                "tester",
                "--product",
                "demo-product",
            ],
        )
        assert result.exit_code == 0, result.output

        lines = [line.strip() for line in result.output.splitlines() if line.strip()]
        created_line = next(line for line in lines if line.startswith("OK: Created:"))
        created_id = created_line.split(":", 2)[-1].strip()

        product_root = tmp_path / "_kano" / "backlog" / "products" / "demo-product"
        created_files = list((product_root / "items").rglob(f"{created_id}_*.md"))
        assert created_files, "Expected created item file on disk"

        content = created_files[0].read_text(encoding="utf-8")
        assert "# Worklog" in content
        assert "[agent=tester]" in content
        assert "[model=unknown]" in content
    finally:
        os.chdir(cwd_before)


def test_item_create_invalid_type_exits_with_error(tmp_path: Path):
    _scaffold_product(tmp_path)
    cwd_before = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(
            app,
            [
                "item",
                "create",
                "--type",
                "invalid",
                "--title",
                "Bad",
                "--priority",
                "P2",
                "--agent",
                "tester",
            ],
        )
        assert result.exit_code != 0
        assert "Invalid item type" in result.output
    finally:
        os.chdir(cwd_before)


def test_item_create_unknown_product_fails(tmp_path: Path):
    tmp_root = tmp_path / "sandbox"
    tmp_root.mkdir(parents=True, exist_ok=True)
    cwd_before = Path.cwd()
    os.chdir(tmp_root)
    try:
        result = runner.invoke(
            app,
            [
                "item",
                "create",
                "--type",
                "task",
                "--title",
                "Test",
                "--priority",
                "P2",
                "--agent",
                "tester",
                "--product",
                "missing-product",
            ],
        )
        assert result.exit_code != 0
        assert "product" in result.output.lower() or "backlog" in result.output.lower()
    finally:
        os.chdir(cwd_before)
