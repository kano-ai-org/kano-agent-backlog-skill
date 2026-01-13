"""Configuration and context resolution for kano-backlog.

This module resolves platform/product roots and provides an "effective config"
view by layering config sources.

Layer order (later wins):
1) _kano/backlog/_shared/defaults.toml (preferred) or defaults.json (deprecated)
2) _kano/backlog/products/<product>/_config/config.json (or config.toml)
3) _kano/backlog/.cache/worksets/topics/<topic>/config.json (or config.toml) (optional)
4) _kano/backlog/.cache/worksets/items/<item_id>/config.json (or config.toml) (optional)

TOML files take precedence over JSON at the same layer. JSON support is deprecated.

Topic selection is agent-scoped via active topic marker:
_kano/backlog/.cache/worksets/active_topic.<agent>.txt
"""

import json
import logging
import warnings
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .errors import ConfigError
from .backend_uri import compile_effective_config

# Conditional TOML import: stdlib tomllib (3.11+) or fallback tomli (<3.11)
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore

logger = logging.getLogger(__name__)


class BacklogContext(BaseModel):
    """Resolved backlog context with platform and product roots."""

    platform_root: Path = Field(..., description="Workspace root")
    backlog_root: Path = Field(..., description="e.g., platform_root / _kano/backlog")
    product_root: Path = Field(..., description="e.g., backlog_root / products / <product>")
    sandbox_root: Optional[Path] = Field(
        None, description="e.g., backlog_root.parent / backlog_sandbox / <sandbox>"
    )
    product_name: str = Field(..., description="Product name")
    is_sandbox: bool = Field(default=False, description="True if operating in sandbox mode")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ConfigLoader:
    """Load and resolve backlog configuration."""

    @staticmethod
    def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = dict(base)
        for key, value in overlay.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _read_json_optional(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ConfigError(f"Config JSON must be an object: {path}")
            warnings.warn(
                f"JSON config is deprecated; migrate to TOML: {path}",
                DeprecationWarning,
                stacklevel=3,
            )
            return data
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in {path}: {e}")
        except ConfigError:
            raise
        except Exception as e:
            raise ConfigError(f"Failed to load config from {path}: {e}")

    @staticmethod
    def _read_toml_optional(path: Path) -> dict[str, Any]:
        """Read TOML config file; return {} if not found."""
        if not path.exists():
            return {}
        if tomllib is None:
            logger.warning("tomllib/tomli not available; install tomli for TOML support")
            return {}
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            if not isinstance(data, dict):
                raise ConfigError(f"Config TOML must be a table: {path}")
            return data
        except Exception as e:
            raise ConfigError(f"Failed to load TOML from {path}: {e}")

    @staticmethod
    def _read_config_optional(base_path: Path, filename_stem: str) -> dict[str, Any]:
        """Read config from .toml (preferred) or .json (deprecated); return {} if neither exists."""
        toml_path = base_path / f"{filename_stem}.toml"
        json_path = base_path / f"{filename_stem}.json"

        toml_data = ConfigLoader._read_toml_optional(toml_path)
        if toml_data:
            return toml_data

        return ConfigLoader._read_json_optional(json_path)

    @staticmethod
    def _normalize_product_name(product: str) -> str:
        return product.strip()

    @staticmethod
    def _list_products(backlog_root: Path) -> list[str]:
        products_dir = backlog_root / "products"
        if not products_dir.exists():
            return []
        return sorted([p.name for p in products_dir.iterdir() if p.is_dir()])

    @staticmethod
    def get_cache_root(backlog_root: Path) -> Path:
        return backlog_root / ".cache" / "worksets"

    @staticmethod
    def get_topics_root(backlog_root: Path) -> Path:
        # Scheme B: durable, shareable topic roots live under _kano/backlog/topics/
        # Raw materials inside a topic should be treated as cache via .gitignore/TTL.
        return backlog_root / "topics"

    @staticmethod
    def get_topic_path(backlog_root: Path, topic_name: str) -> Path:
        return ConfigLoader.get_topics_root(backlog_root) / topic_name

    @staticmethod
    def get_worksets_items_root(backlog_root: Path) -> Path:
        return ConfigLoader.get_cache_root(backlog_root) / "items"

    @staticmethod
    def get_workset_path(backlog_root: Path, item_id: str) -> Path:
        return ConfigLoader.get_worksets_items_root(backlog_root) / item_id

    @staticmethod
    def get_active_topic(backlog_root: Path, agent: str) -> Optional[str]:
        if not agent or not agent.strip():
            return None
        marker = ConfigLoader.get_cache_root(backlog_root) / f"active_topic.{agent}.txt"
        if not marker.exists():
            return None
        topic = marker.read_text(encoding="utf-8").strip()
        return topic or None

    @staticmethod
    def load_product_config(product_root: Path) -> dict[str, Any]:
        return ConfigLoader._read_config_optional(product_root / "_config", "config")

    @staticmethod
    def load_topic_overrides(
        backlog_root: Path,
        *,
        topic: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> dict[str, Any]:
        topic_name = (topic or "").strip() or (ConfigLoader.get_active_topic(backlog_root, agent or "") or "")
        if not topic_name:
            return {}
        return ConfigLoader._read_config_optional(ConfigLoader.get_topic_path(backlog_root, topic_name), "config")

    @staticmethod
    def load_workset_overrides(backlog_root: Path, *, item_id: Optional[str] = None) -> dict[str, Any]:
        if not item_id:
            return {}
        return ConfigLoader._read_config_optional(ConfigLoader.get_workset_path(backlog_root, item_id), "config")

    @staticmethod
    def _resolve_product_name(
        resource_path: Path,
        backlog_root: Path,
        *,
        product: Optional[str] = None,
        agent: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> str:
        if product and product.strip():
            candidate = ConfigLoader._normalize_product_name(product)
            if (backlog_root / "products" / candidate).exists():
                return candidate
            raise ConfigError(f"Product root does not exist: {backlog_root / 'products' / candidate}")

        inferred = ConfigLoader._infer_product(resource_path, backlog_root)
        if inferred:
            return inferred

        topic_overrides = ConfigLoader.load_topic_overrides(backlog_root, topic=topic, agent=agent)
        topic_default = topic_overrides.get("default_product")
        if isinstance(topic_default, str) and topic_default.strip():
            candidate = ConfigLoader._normalize_product_name(topic_default)
            if (backlog_root / "products" / candidate).exists():
                return candidate

        defaults = ConfigLoader.load_defaults(backlog_root)
        default_product = defaults.get("default_product")
        if isinstance(default_product, str) and default_product.strip():
            candidate = ConfigLoader._normalize_product_name(default_product)
            if (backlog_root / "products" / candidate).exists():
                return candidate

        products = ConfigLoader._list_products(backlog_root)
        if len(products) == 1:
            return products[0]

        raise ConfigError(
            "Cannot determine product; specify --product or set _kano/backlog/_shared/defaults.toml:default_product",
        )

    @staticmethod
    def from_path(
        resource_path: Path,
        product: Optional[str] = None,
        sandbox: Optional[str] = None,
        *,
        agent: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> BacklogContext:
        """
        Resolve backlog context from a file/folder path.

        Args:
            resource_path: Starting path (file or directory)
            product: Product name (optional, can be inferred)
            sandbox: Sandbox name (optional, for isolated operations)

        Returns:
            BacklogContext with resolved roots

        Raises:
            ConfigError: If platform/product root cannot be determined
        """
        resource_path = resource_path.resolve()

        # Find backlog root (the _kano/backlog directory)
        backlog_root = ConfigLoader._find_platform_root(resource_path)
        if not backlog_root:
            raise ConfigError(
                f"Could not find _kano/backlog directory from: {resource_path}"
            )

        platform_root = backlog_root.parent.parent  # Go up from _kano/backlog to platform root

        # Determine product (explicit -> inferred -> topic override -> defaults -> single-product)
        product = ConfigLoader._resolve_product_name(
            resource_path,
            backlog_root,
            product=product,
            agent=agent,
            topic=topic,
        )

        product_root = backlog_root / "products" / product
        if not product_root.exists():
            raise ConfigError(f"Product root does not exist: {product_root}")

        # Determine sandbox
        sandbox_root = None
        is_sandbox = False
        if sandbox:
            sandbox_root = backlog_root.parent / "backlog_sandbox" / sandbox
            is_sandbox = True

        return BacklogContext(
            platform_root=platform_root,
            backlog_root=backlog_root,
            product_root=product_root,
            sandbox_root=sandbox_root,
            product_name=product,
            is_sandbox=is_sandbox,
        )

    @staticmethod
    def _find_platform_root(start_path: Path) -> Optional[Path]:
        """Walk up to find platform root (_kano/backlog directory itself)."""
        current = start_path if start_path.is_dir() else start_path.parent
        for parent in [current, *current.parents]:
            candidate = parent / "_kano" / "backlog"
            if candidate.exists() and candidate.is_dir():
                return candidate
        return None

    @staticmethod
    def _infer_product(resource_path: Path, backlog_root: Path) -> Optional[str]:
        """Infer product name from path (if under products/<product>/)."""
        try:
            relative = resource_path.relative_to(backlog_root / "products")
            # Extract first directory component
            parts = relative.parts
            if parts:
                return parts[0]
        except ValueError:
            pass
        return None

    @staticmethod
    def load_defaults(backlog_root: Path) -> dict:
        """
        Load default configuration from _kano/backlog/_shared/defaults.toml (preferred) or defaults.json (deprecated)

        Args:
            backlog_root: Backlog root path

        Returns:
            Dictionary with defaults (empty if neither file exists)
        """
        return ConfigLoader._read_config_optional(backlog_root / "_shared", "defaults")

    @staticmethod
    def load_effective_config(
        resource_path: Path,
        *,
        product: Optional[str] = None,
        sandbox: Optional[str] = None,
        agent: Optional[str] = None,
        topic: Optional[str] = None,
        workset_item_id: Optional[str] = None,
    ) -> tuple[BacklogContext, dict[str, Any]]:
        """Return (context, effective_config) using the layered merge order."""
        ctx = ConfigLoader.from_path(
            resource_path,
            product=product,
            sandbox=sandbox,
            agent=agent,
            topic=topic,
        )

        defaults = ConfigLoader.load_defaults(ctx.backlog_root)
        product_cfg = ConfigLoader.load_product_config(ctx.product_root)
        topic_cfg = ConfigLoader.load_topic_overrides(ctx.backlog_root, topic=topic, agent=agent)
        workset_cfg = ConfigLoader.load_workset_overrides(ctx.backlog_root, item_id=workset_item_id)

        effective: dict[str, Any] = {}
        for layer in (defaults, product_cfg, topic_cfg, workset_cfg):
            if isinstance(layer, dict):
                effective = ConfigLoader._deep_merge(effective, layer)

        # Compile human-friendly backend blocks into canonical URIs (local-first; no network calls)
        effective = compile_effective_config(effective, default_filesystem_root=ctx.platform_root)
        return ctx, effective
