"""Configuration and context resolution for kano-backlog.

This module resolves project/product roots and provides an "effective config"
view by layering config sources.

Layer order (later wins):
1) _kano/backlog/_shared/defaults.toml (preferred) or defaults.json (deprecated)
2) _kano/backlog/products/<product>/_config/config.json (or config.toml)
3) .kano/backlog_config.toml (project-level config) - NEW
4) _kano/backlog/.cache/worksets/topics/<topic>/config.json (or config.toml) (optional)
5) _kano/backlog/.cache/worksets/items/<item_id>/config.json (or config.toml) (optional)
6) CLI arguments (highest priority)

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
from .project_config import ProjectConfig, ProjectConfigLoader

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
    """Resolved backlog context with project and product roots."""

    project_root: Path = Field(..., description="Workspace root")
    backlog_root: Path = Field(..., description="e.g., project_root / _kano/backlog")
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
    def from_path(
        resource_path: Path,
        product: Optional[str] = None,
        sandbox: Optional[str] = None,
        *,
        agent: Optional[str] = None,
        topic: Optional[str] = None,
        custom_config_file: Optional[Path] = None,
    ) -> BacklogContext:
        """
        Resolve backlog context from a file/folder path.
        
        BREAKING CHANGE: Only project-level configs are supported.
        Traditional product structure is no longer used.

        Args:
            resource_path: Starting path (file or directory)
            product: Product name (REQUIRED, must be defined in project config)
            sandbox: Sandbox name (optional, for isolated operations)

        Returns:
            BacklogContext with resolved roots

        Raises:
            ConfigError: If project config or product not found
        """
        resource_path = resource_path.resolve()

        # Load project config (REQUIRED)
        project_config = ProjectConfigLoader.load_project_config_optional(resource_path, custom_config_file)
        if not project_config:
            raise ConfigError(
                f"Project config required but not found. Create .kano/backlog_config.toml in project root."
            )

        # Resolve backlog root from project config
        if not product:
            # Auto-detect single product
            products = project_config.list_products()
            if len(products) == 1:
                product = products[0]
            elif len(products) > 1:
                raise ConfigError(f"Multiple products found; specify --product: {', '.join(products)}")
            else:
                raise ConfigError("No products defined in project config")

        backlog_root = ProjectConfigLoader.resolve_product_backlog_root(
            resource_path, product, project_config, custom_config_file
        )
        
        if not backlog_root:
            raise ConfigError(f"Product '{product}' not found in project config")

        # Determine project root
        config_path = ProjectConfigLoader.find_project_config(resource_path, custom_config_file)
        if not config_path:
            raise ConfigError("Project config file not found")
            
        if config_path.parent.name == ".kano":
            # Standard location: .kano/backlog_config.toml
            project_root = config_path.parent.parent
        else:
            # Custom location: assume config file is in project root
            project_root = config_path.parent

        # For project config, the backlog_root IS the product root
        product_root = backlog_root

        # Determine sandbox
        sandbox_root = None
        is_sandbox = False
        if sandbox:
            sandbox_root = backlog_root.parent / "backlog_sandbox" / sandbox
            is_sandbox = True

        return BacklogContext(
            project_root=project_root,
            backlog_root=backlog_root,
            product_root=product_root,
            sandbox_root=sandbox_root,
            product_name=product,
            is_sandbox=is_sandbox,
        )

    # REMOVED: Traditional methods no longer supported in breaking change
    # - _find_project_root() - no longer needed
    # - _infer_product() - no longer needed  
    # - _list_products() - no longer needed
    # - _normalize_product_name() - no longer needed

    @staticmethod
    def get_system_defaults() -> dict[str, Any]:
        """
        Get system-level default configuration values.
        These are the defaults defined in code, used when no config is provided.
        """
        return {
            "skill_developer": False,
            "persona": "developer",
            "auto_refresh": False,
            "log": {
                "verbosity": "info",
                "debug": False,
            },
            "index": {
                "enabled": False,
                "backend": "noop",
                "mode": "incremental",
            },
            "analysis": {
                "llm": {
                    "enabled": False,
                },
            },
            "chunking": {
                "target_tokens": 512,
                "max_tokens": 2048,
            },
            "tokenizer": {
                "adapter": "auto",
                "model": "text-embedding-3-small",
            },
            "embedding": {
                "provider": "noop",
                "model": "noop-embedding",
                "dimension": 1536,
            },
            "vector": {
                "backend": "noop",
                "path": ".cache/vector",
                "collection": "backlog",
                "metric": "cosine",
            },
        }

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
    def load_project_config(start_path: Path, custom_config_file: Optional[Path] = None) -> dict[str, Any]:
        """
        Load project-level configuration from .kano/backlog_config.toml
        
        BREAKING CHANGE: This is now REQUIRED, not optional.
        
        Args:
            start_path: Starting path to search for project config
            custom_config_file: Optional custom config file path
            
        Returns:
            Dictionary with project config
            
        Raises:
            ConfigError: If project config not found
        """
        project_config = ProjectConfigLoader.load_project_config_optional(start_path, custom_config_file)
        if not project_config:
            raise ConfigError(
                "Project config required but not found. Create .kano/backlog_config.toml in project root."
            )
        
        # Convert to flat dictionary for merging
        result = {}
        
        # Add defaults
        if project_config.defaults:
            result.update(project_config.defaults)
        
        # Add shared settings
        if project_config.shared:
            result = ConfigLoader._deep_merge(result, project_config.shared)
        
        return result

    @staticmethod
    def load_project_product_overrides(start_path: Path, product_name: str, custom_config_file: Optional[Path] = None) -> dict[str, Any]:
        """
        Load product-specific overrides from project config
        
        Args:
            start_path: Starting path to search for project config
            product_name: Product name to get overrides for
            custom_config_file: Optional custom config file path
            
        Returns:
            Dictionary with product overrides
            
        Raises:
            ConfigError: If project config not found
        """
        project_config = ProjectConfigLoader.load_project_config_optional(start_path, custom_config_file)
        if not project_config:
            raise ConfigError(
                "Project config required but not found. Create .kano/backlog_config.toml in project root."
            )
        
        product = project_config.get_product(product_name)
        if not product:
            return {}
        
        return product.overrides

    @staticmethod
    def load_effective_config(
        resource_path: Path,
        *,
        product: Optional[str] = None,
        sandbox: Optional[str] = None,
        agent: Optional[str] = None,
        topic: Optional[str] = None,
        workset_item_id: Optional[str] = None,
        custom_config_file: Optional[Path] = None,
    ) -> tuple[BacklogContext, dict[str, Any]]:
        """Return (context, effective_config) using the layered merge order.
        
        BREAKING CHANGE: Traditional product configs are no longer supported.
        Only project-level configs (.kano/backlog_config.toml) are used.
        """
        ctx = ConfigLoader.from_path(
            resource_path,
            product=product,
            sandbox=sandbox,
            agent=agent,
            topic=topic,
            custom_config_file=custom_config_file,
        )

        # Load configuration layers in precedence order (lowest to highest)
        # Start with system defaults (defined in code)
        system_defaults = ConfigLoader.get_system_defaults()
        
        # Then load file-based configurations
        defaults = ConfigLoader.load_defaults(ctx.backlog_root)
        
        # Project-level configuration (REQUIRED)
        project_cfg = ConfigLoader.load_project_config(resource_path, custom_config_file)
        # Note: project_cfg can be an empty dict if no defaults/shared are defined
        
        project_product_overrides = ConfigLoader.load_project_product_overrides(
            resource_path, ctx.product_name, custom_config_file
        )
        
        topic_cfg = ConfigLoader.load_topic_overrides(ctx.backlog_root, topic=topic, agent=agent)
        workset_cfg = ConfigLoader.load_workset_overrides(ctx.backlog_root, item_id=workset_item_id)

        # Merge layers in precedence order (system defaults first, then user configs)
        effective: dict[str, Any] = {}
        for layer in (system_defaults, defaults, project_cfg, project_product_overrides, topic_cfg, workset_cfg):
            if isinstance(layer, dict):
                effective = ConfigLoader._deep_merge(effective, layer)

        # Compile human-friendly backend blocks into canonical URIs (local-first; no network calls)
        effective = compile_effective_config(effective, default_filesystem_root=ctx.project_root)
        return ctx, effective

    @staticmethod
    def validate_pipeline_config(config: dict[str, Any]) -> Any:
        # Avoid circular import if possible, or Import here
        from .pipeline_config import PipelineConfig
        pc = PipelineConfig.from_dict(config)
        pc.validate()
        return pc
