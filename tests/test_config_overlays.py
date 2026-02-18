"""Tests for config resolution using defaults + topic/workset overlays.

This exercises kano_backlog_core.config.ConfigLoader without requiring CLI wiring.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

# Ensure src/ is importable when running tests directly.
import sys

test_dir = Path(__file__).parent
src_dir = test_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from kano_backlog_core.config import ConfigLoader
from kano_backlog_core.errors import ConfigError


def _mk_backlog(tmp: Path, *, products: list[str]) -> Path:
    backlog_root = tmp / "_kano" / "backlog"
    (backlog_root / "_shared").mkdir(parents=True, exist_ok=True)
    products_root = backlog_root / "products"
    products_root.mkdir(parents=True, exist_ok=True)

    for product in products:
        product_root = products_root / product
        (product_root / "_config").mkdir(parents=True, exist_ok=True)
        (product_root / "_config" / "config.toml").write_text(
            f"[product]\nname = \"{product}\"\nprefix = \"{product[:3].upper()}\"\n",
            encoding="utf-8",
        )

    # Required project-level config.
    kano_dir = tmp / ".kano"
    kano_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for product in products:
        lines.append(f"[products.{product}]\n")
        lines.append(f"name = \"{product}\"\n")
        lines.append(f"prefix = \"{product[:3].upper()}\"\n")
        lines.append(f"backlog_root = \"_kano/backlog/products/{product}\"\n\n")
    (kano_dir / "backlog_config.toml").write_text("".join(lines), encoding="utf-8")

    return backlog_root


def _tmp_workspace() -> Path:
    return Path(tempfile.mkdtemp())


def _cleanup(tmp: Path) -> None:
    shutil.rmtree(tmp, ignore_errors=True)


def test_from_path_requires_explicit_product_when_multiple_products_defined():
    tmp = _tmp_workspace()
    try:
        _mk_backlog(tmp, products=["prod-a", "prod-b"])

        with pytest.raises(ConfigError):
            ConfigLoader.from_path(tmp)
    finally:
        _cleanup(tmp)


def test_load_effective_config_applies_topic_overrides_when_agent_has_active_topic():
    tmp = _tmp_workspace()
    try:
        backlog_root = _mk_backlog(tmp, products=["prod-a"])
        (backlog_root / "_shared" / "defaults.toml").write_text("x = 1\n", encoding="utf-8")

        # Create topic config override and active topic marker for agent
        topic_name = "mytopic"
        topic_dir = backlog_root / "topics" / topic_name
        topic_dir.mkdir(parents=True, exist_ok=True)
        (topic_dir / "config.toml").write_text(
            "x = 2\n", encoding="utf-8"
        )
        active_marker = backlog_root / ".cache" / "worksets" / "active_topic.copilot.txt"
        active_marker.parent.mkdir(parents=True, exist_ok=True)
        active_marker.write_text(topic_name, encoding="utf-8")

        _, cfg = ConfigLoader.load_effective_config(tmp, product="prod-a", agent="copilot")
        assert cfg["x"] == 2
    finally:
        _cleanup(tmp)


def test_load_effective_config_layers_merge_in_order():
    tmp = _tmp_workspace()
    try:
        backlog_root = _mk_backlog(tmp, products=["prod-a"])
        (backlog_root / "_shared" / "defaults.toml").write_text(
            "x = 1\n\n[views]\nauto_refresh = false\n",
            encoding="utf-8",
        )

        # product config adds nested key
        product_cfg_path = backlog_root / "products" / "prod-a" / "_config" / "config.toml"
        product_cfg_path.write_text(
            "x = 2\n\n[views]\nauto_refresh = false\nmode = \"product\"\n",
            encoding="utf-8",
        )

        # topic override flips auto_refresh
        topic_name = "mytopic"
        topic_dir = backlog_root / "topics" / topic_name
        topic_dir.mkdir(parents=True, exist_ok=True)
        (topic_dir / "config.toml").write_text(
            "[views]\nauto_refresh = true\n", encoding="utf-8"
        )
        active_marker = backlog_root / ".cache" / "worksets" / "active_topic.copilot.txt"
        active_marker.parent.mkdir(parents=True, exist_ok=True)
        active_marker.write_text(topic_name, encoding="utf-8")

        # workset override adds another leaf
        item_id = "PRO-TSK-0001"
        workset_dir = backlog_root / ".cache" / "worksets" / "items" / item_id
        workset_dir.mkdir(parents=True, exist_ok=True)
        (workset_dir / "config.toml").write_text(
            "x = 3\n\n[views]\nmode = \"workset\"\n", encoding="utf-8"
        )

        ctx, cfg = ConfigLoader.load_effective_config(
            tmp,
            agent="copilot",
            workset_item_id=item_id,
        )
        assert ctx.product_name == "prod-a"
        assert cfg["x"] == 3
        assert cfg["views"]["auto_refresh"] is True
        assert cfg["views"]["mode"] == "workset"
    finally:
        _cleanup(tmp)


def test_load_profile_overrides_path_first_then_fallback_to_shorthand():
    tmp = _tmp_workspace()
    try:
        # Minimal project root with .kano/backlog_config.
        profiles_root = tmp / ".kano" / "backlog_config" / "embedding"
        profiles_root.mkdir(parents=True, exist_ok=True)
        (profiles_root / "local-noop.toml").write_text("log_debug = true\n", encoding="utf-8")
        (profiles_root.parent.parent / "backlog_config.toml").write_text(
            "products = {}\n", encoding="utf-8"
        )

        # Also create a repo-root relative file at embedding/local-noop.toml.
        # Shorthand should still prefer .kano/backlog_config.
        repo_rel = tmp / "embedding"
        repo_rel.mkdir(parents=True, exist_ok=True)
        (repo_rel / "local-noop.toml").write_text("log_debug = false\n", encoding="utf-8")

        # Shorthand should prefer project profile (debug=true).
        overrides = ConfigLoader.load_profile_overrides(tmp, profile="embedding/local-noop")
        assert overrides["log"]["debug"] is True

        # Explicit repo-root path should use the repo-root file (debug=false).
        overrides_repo = ConfigLoader.load_profile_overrides(
            tmp, profile=str(repo_rel / "local-noop.toml")
        )
        assert overrides_repo["log"]["debug"] is False

        # Explicit repo-root relative path should be used when it exists.
        direct_path = tmp / ".kano" / "backlog_config" / "embedding" / "local-noop.toml"
        overrides2 = ConfigLoader.load_profile_overrides(tmp, profile=str(direct_path))
        assert overrides2["log"]["debug"] is True
    finally:
        _cleanup(tmp)


def test_load_profile_overrides_rejects_traversal_paths():
    tmp = _tmp_workspace()
    try:
        with pytest.raises(ConfigError):
            ConfigLoader.load_profile_overrides(tmp, profile="../secrets")
    finally:
        _cleanup(tmp)
