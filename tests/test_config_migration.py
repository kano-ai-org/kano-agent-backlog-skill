import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kano_backlog_cli.cli import app

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


runner = CliRunner()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _scaffold_backlog(tmp_path: Path) -> tuple[Path, Path]:
    backlog_root = tmp_path / "_kano" / "backlog"
    shared = backlog_root / "_shared"
    product_root = backlog_root / "products" / "demo"
    product_cfg = product_root / "_config"

    _write_json(shared / "defaults.json", {"default_product": "demo"})
    _write_json(
        product_cfg / "config.json",
        {
            "project": {"name": "demo", "prefix": "DEMO"},
            "log": {"verbosity": "info", "debug": False},
            "process": {"profile": "builtin/azure-boards-agile", "path": None},
            "index": {"enabled": True, "backend": "sqlite", "path": None, "mode": "rebuild"},
        },
    )

    return backlog_root, product_root


def test_migrate_json_dry_run_leaves_files_untouched(tmp_path: Path):
    backlog_root, product_root = _scaffold_backlog(tmp_path)

    result = runner.invoke(app, ["config", "migrate-json", "--path", str(product_root)])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    labels = {plan["label"] for plan in payload["plans"]}
    assert payload["applied"] is False
    assert "defaults" in labels and "product" in labels
    assert not (backlog_root / "_shared" / "defaults.toml").exists()
    assert not (product_root / "_config" / "config.toml").exists()


def test_migrate_json_writes_toml_and_backup(tmp_path: Path):
    backlog_root, product_root = _scaffold_backlog(tmp_path)
    product_cfg = product_root / "_config"

    result = runner.invoke(app, ["config", "migrate-json", "--path", str(product_root), "--write"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    product_plan = next(plan for plan in payload["plans"] if plan["label"] == "product")
    backup_path = Path(product_plan["backup"])
    toml_path = product_cfg / "config.toml"

    assert backup_path.exists(), "Backup should be created before writing TOML"
    assert toml_path.exists(), "TOML config should be written"

    toml_data = _read_toml(toml_path)
    assert toml_data["product"]["prefix"] == "DEMO"
    assert toml_data["log"]["verbosity"] == "info"
    assert "path" not in toml_data["index"], "Null fields should be stripped"

    original_json = json.loads((product_cfg / "config.json").read_text(encoding="utf-8"))
    assert original_json["project"]["name"] == "demo", "Original JSON should remain intact"


@pytest.mark.parametrize(
    "existing_toml",
    [True, False],
)
def test_migrate_json_skips_when_toml_exists(tmp_path: Path, existing_toml: bool):
    backlog_root, product_root = _scaffold_backlog(tmp_path)
    product_cfg = product_root / "_config"

    if existing_toml:
        product_cfg.mkdir(parents=True, exist_ok=True)
        (product_cfg / "config.toml").write_text("[product]\nname = 'demo'\nprefix = 'DEMO'\n", encoding="utf-8")

    result = runner.invoke(app, ["config", "migrate-json", "--path", str(product_root), "--write"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    has_skip = any(plan["status"] == "skipped-toml-exists" for plan in payload["plans"])
    assert has_skip is existing_toml
