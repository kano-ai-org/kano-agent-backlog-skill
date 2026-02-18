"""Tests for TOML config loading and precedence over JSON."""

import json
import tempfile
from pathlib import Path

import pytest

from kano_backlog_core.config import ConfigLoader


def test_toml_loads_correctly(tmp_path: Path):
    """Verify TOML config loads with correct structure."""
    backlog_root = tmp_path / "_kano" / "backlog"
    backlog_root.mkdir(parents=True)
    
    defaults_dir = backlog_root / "_shared"
    defaults_dir.mkdir(parents=True)
    
    toml_path = defaults_dir / "defaults.toml"
    toml_path.write_text("""
default_product = "my-product"
max_depth = 5

[views]
auto_refresh = true
markdown_engine = "dataview"

[items]
default_type = "Task"
""", encoding="utf-8")
    
    config = ConfigLoader.load_defaults(backlog_root)
    assert config["default_product"] == "my-product"
    assert config["max_depth"] == 5
    assert config["views"]["auto_refresh"] is True
    assert config["views"]["markdown_engine"] == "dataview"
    assert config["items"]["default_type"] == "Task"


def test_toml_precedence_over_json(tmp_path: Path):
    """TOML takes precedence over JSON at same layer."""
    backlog_root = tmp_path / "_kano" / "backlog"
    backlog_root.mkdir(parents=True)
    
    defaults_dir = backlog_root / "_shared"
    defaults_dir.mkdir(parents=True)
    
    # Create both JSON and TOML
    json_path = defaults_dir / "defaults.json"
    json_path.write_text(json.dumps({
        "default_product": "old-product",
        "max_depth": 3,
        "views": {"auto_refresh": False}
    }), encoding="utf-8")
    
    toml_path = defaults_dir / "defaults.toml"
    toml_path.write_text("""
default_product = "new-product"
max_depth = 7

[views]
auto_refresh = true
""", encoding="utf-8")
    
    config = ConfigLoader.load_defaults(backlog_root)
    # TOML should win
    assert config["default_product"] == "new-product"
    assert config["max_depth"] == 7
    assert config["views"]["auto_refresh"] is True


def test_json_loads_when_no_toml(tmp_path: Path):
    """JSON still works when no TOML present (backward compat)."""
    backlog_root = tmp_path / "_kano" / "backlog"
    backlog_root.mkdir(parents=True)
    
    defaults_dir = backlog_root / "_shared"
    defaults_dir.mkdir(parents=True)
    
    json_path = defaults_dir / "defaults.json"
    json_path.write_text(json.dumps({
        "default_product": "json-product",
        "max_depth": 4
    }), encoding="utf-8")
    
    config = ConfigLoader.load_defaults(backlog_root)
    assert config["default_product"] == "json-product"
    assert config["max_depth"] == 4


def test_empty_when_neither_exists(tmp_path: Path):
    """Return {} when neither TOML nor JSON exists."""
    backlog_root = tmp_path / "_kano" / "backlog"
    backlog_root.mkdir(parents=True)
    
    defaults_dir = backlog_root / "_shared"
    defaults_dir.mkdir(parents=True)
    
    config = ConfigLoader.load_defaults(backlog_root)
    assert config == {}


def test_topic_config_toml_precedence(tmp_path: Path):
    """Topic config.toml takes precedence over config.json."""
    backlog_root = tmp_path / "_kano" / "backlog"
    topic_path = ConfigLoader.get_topic_path(backlog_root, "test-topic")
    topic_path.mkdir(parents=True)
    
    # Create both
    json_path = topic_path / "config.json"
    json_path.write_text(json.dumps({"focus": "old"}), encoding="utf-8")
    
    toml_path = topic_path / "config.toml"
    toml_path.write_text('focus = "new"', encoding="utf-8")
    
    config = ConfigLoader.load_topic_overrides(backlog_root, topic="test-topic")
    assert config["focus"] == "new"


def test_workset_config_toml_precedence(tmp_path: Path):
    """Workset config.toml takes precedence over config.json."""
    backlog_root = tmp_path / "_kano" / "backlog"
    workset_path = ConfigLoader.get_workset_path(backlog_root, "TST-001")
    workset_path.mkdir(parents=True)
    
    # Create both
    json_path = workset_path / "config.json"
    json_path.write_text(json.dumps({"mode": "old"}), encoding="utf-8")
    
    toml_path = workset_path / "config.toml"
    toml_path.write_text('mode = "new"', encoding="utf-8")
    
    config = ConfigLoader.load_workset_overrides(backlog_root, item_id="TST-001")
    assert config["mode"] == "new"


def test_deep_merge_toml_and_json(tmp_path: Path):
    """Verify deep merge works across TOML defaults + JSON overrides."""
    backlog_root = tmp_path / "_kano" / "backlog"
    backlog_root.mkdir(parents=True)
    
    # Defaults (TOML)
    defaults_dir = backlog_root / "_shared"
    defaults_dir.mkdir(parents=True)
    defaults_toml = defaults_dir / "defaults.toml"
    defaults_toml.write_text("""
[views]
auto_refresh = true
markdown_engine = "dataview"

[items]
default_type = "Task"
""", encoding="utf-8")
    
    # Topic overrides (JSON for variety)
    topic_path = ConfigLoader.get_topic_path(backlog_root, "test-topic")
    topic_path.mkdir(parents=True)
    (topic_path / "config.json").write_text(
        json.dumps(
            {
                "views": {"auto_refresh": False},
                "items": {"default_priority": "Medium"},
            }
        ),
        encoding="utf-8",
    )
    
    # Load and merge
    defaults = ConfigLoader.load_defaults(backlog_root)
    topic_cfg = ConfigLoader.load_topic_overrides(backlog_root, topic="test-topic")
    merged = ConfigLoader._deep_merge(defaults, topic_cfg)
    
    # Verify nested merge
    assert merged["views"]["auto_refresh"] is False  # product override
    assert merged["views"]["markdown_engine"] == "dataview"  # defaults preserved
    assert merged["items"]["default_type"] == "Task"  # defaults preserved
    assert merged["items"]["default_priority"] == "Medium"  # product added


def test_json_deprecation_warning(tmp_path: Path):
    """JSON loading emits deprecation warning."""
    backlog_root = tmp_path / "_kano" / "backlog"
    defaults_dir = backlog_root / "_shared"
    defaults_dir.mkdir(parents=True)
    
    json_path = defaults_dir / "defaults.json"
    json_path.write_text(json.dumps({"test": "value"}), encoding="utf-8")
    
    with pytest.warns(DeprecationWarning, match="JSON config is deprecated"):
        ConfigLoader.load_defaults(backlog_root)


def test_invalid_toml_raises_error(tmp_path: Path):
    """Invalid TOML syntax raises ConfigError."""
    from kano_backlog_core.errors import ConfigError
    
    backlog_root = tmp_path / "_kano" / "backlog"
    defaults_dir = backlog_root / "_shared"
    defaults_dir.mkdir(parents=True)
    
    toml_path = defaults_dir / "defaults.toml"
    toml_path.write_text("invalid [ toml", encoding="utf-8")
    
    with pytest.raises(ConfigError, match="Failed to load TOML"):
        ConfigLoader.load_defaults(backlog_root)
