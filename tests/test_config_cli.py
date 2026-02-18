import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from typer.testing import CliRunner

from kano_backlog_cli.cli import app

from conftest import write_project_backlog_config

runner = CliRunner()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _scaffold_backlog(tmp_path: Path) -> Path:
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "demo"

    (product_root / "items" / "task" / "0000").mkdir(parents=True, exist_ok=True)

    # Provide an existing product-level config file so `config init` can exercise
    # overwrite/refresh behavior.
    (product_root / "_config").mkdir(parents=True, exist_ok=True)
    (product_root / "_config" / "config.toml").write_text(
        "[product]\nname = \"demo\"\nprefix = \"KABSD\"\n",
        encoding="utf-8",
    )

    kano_dir = tmp_path / ".kano"
    kano_dir.mkdir(parents=True, exist_ok=True)
    (kano_dir / "backlog_config.toml").write_text(
        "\n".join(
            [
                "[products.demo]",
                'name = "demo"',
                'prefix = "KABSD"',
                'backlog_root = "_kano/backlog/products/demo"',
                "",
                "[shared.backends.jira]",
                'type = "jira"',
                'host = "example.atlassian.net"',
                'project = "DEMO"',
                "",
            ]
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    return product_root


def test_config_show_outputs_effective_config(tmp_path: Path):
    product_root = _scaffold_backlog(tmp_path)
    result = runner.invoke(app, ["config", "show", "--path", str(product_root)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["config"]["backends"]["jira"]["uri"] == "jira://example.atlassian.net/DEMO"
    assert data["context"]["product_name"] == "demo"


def test_config_validate_success(tmp_path: Path):
    product_root = _scaffold_backlog(tmp_path)
    result = runner.invoke(app, ["config", "validate", "--path", str(product_root)])
    assert result.exit_code == 0, result.output
    assert "Config is valid" in result.output


def test_config_validate_fails_on_product_prefix(tmp_path: Path):
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "demo"
    (product_root / "items" / "task" / "0000").mkdir(parents=True, exist_ok=True)

    kano_dir = tmp_path / ".kano"
    kano_dir.mkdir(parents=True, exist_ok=True)
    (kano_dir / "backlog_config.toml").write_text(
        "\n".join(
            [
                "[products.demo]",
                'name = "demo"',
                '# prefix missing',
                'backlog_root = "_kano/backlog/products/demo"',
                "",
            ]
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["config", "validate", "--path", str(product_root)])
    assert result.exit_code == 1


def test_config_validate_rejects_secret_literal(tmp_path: Path):
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "demo"
    (product_root / "items" / "task" / "0000").mkdir(parents=True, exist_ok=True)

    kano_dir = tmp_path / ".kano"
    kano_dir.mkdir(parents=True, exist_ok=True)
    (kano_dir / "backlog_config.toml").write_text(
        "\n".join(
            [
                "[products.demo]",
                'name = "demo"',
                'prefix = "KABSD"',
                'backlog_root = "_kano/backlog/products/demo"',
                "",
                "[shared.backends.jira]",
                'type = "jira"',
                'host = "example.atlassian.net"',
                'project = "DEMO"',
                'api_key = "secret-token"',
                "",
            ]
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["config", "validate", "--path", str(product_root)])
    assert result.exit_code == 1
    assert "Secrets must not be stored in config" in result.output


def test_config_validate_allows_env_secret(tmp_path: Path):
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / "demo"
    (product_root / "items" / "task" / "0000").mkdir(parents=True, exist_ok=True)

    kano_dir = tmp_path / ".kano"
    kano_dir.mkdir(parents=True, exist_ok=True)
    (kano_dir / "backlog_config.toml").write_text(
        "\n".join(
            [
                "[products.demo]",
                'name = "demo"',
                'prefix = "KABSD"',
                'backlog_root = "_kano/backlog/products/demo"',
                "",
                "[shared.backends.jira]",
                'type = "jira"',
                'host = "example.atlassian.net"',
                'project = "DEMO"',
                'api_key = "env:OPENAI_API_KEY"',
                "",
            ]
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["config", "validate", "--path", str(product_root)])
    assert result.exit_code == 0, result.output


def test_config_export_writes_file(tmp_path: Path):
    product_root = _scaffold_backlog(tmp_path)
    out_path = tmp_path / "exported_config.toml"
    result = runner.invoke(app, ["config", "export", "--path", str(product_root), "--format", "toml", "--out", str(out_path)])
    assert result.exit_code == 0, result.output
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert "config" in data and "context" in data


def test_config_init_renders_template(tmp_path: Path):
    product_root = _scaffold_backlog(tmp_path)
    # Remove config to test init path
    cfg_path = product_root / "_config" / "config.toml"
    cfg_path.unlink()

    result = runner.invoke(app, ["config", "init", "--path", str(product_root)])
    assert result.exit_code == 0, result.output
    assert cfg_path.exists()
    text = cfg_path.read_text(encoding="utf-8")
    assert "[product]" in text
    assert "name = \"demo\"" in text
