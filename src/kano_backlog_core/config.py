"""Configuration and context resolution for kano-backlog.

This module resolves project/product roots and provides an "effective config"
view by layering config sources.

Layer order (later wins):
1) System defaults (hardcoded)
2) _kano/backlog/_shared/defaults.toml (preferred) or defaults.json (deprecated)
3) .kano/backlog_config.toml (project-level defaults + shared)
4) Product settings from .kano/backlog_config.toml [products.<name>] (flattened keys)
5) Optional profile override: .kano/backlog_config/<profile>.toml (supports subfolders)
6) Topic overrides: _kano/backlog/topics/<topic>/config.toml (optional)
7) Workset overrides: _kano/backlog/.cache/worksets/items/<item_id>/config.toml (optional)

TOML files take precedence over JSON at the same layer. JSON support is deprecated.

Topic selection is agent-scoped via active topic marker:
_kano/backlog/.cache/worksets/active_topic.<agent>.txt
"""

import json
import logging
import re
import os
import warnings
from datetime import datetime, timezone
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

try:
    import tomli_w  # type: ignore
except ImportError:
    tomli_w = None  # type: ignore

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
    def _resolve_optional_config_path(base_path: Path, filename_stem: str) -> Path:
        toml_path = base_path / f"{filename_stem}.toml"
        if toml_path.exists():
            return toml_path
        json_path = base_path / f"{filename_stem}.json"
        if json_path.exists():
            return json_path
        return toml_path

    @staticmethod
    def _stringify_paths(value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {k: ConfigLoader._stringify_paths(v) for k, v in value.items()}
        if isinstance(value, list):
            return [ConfigLoader._stringify_paths(v) for v in value]
        return value

    @staticmethod
    def _strip_nulls(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: ConfigLoader._strip_nulls(v) for k, v in value.items() if v is not None}
        if isinstance(value, list):
            return [ConfigLoader._strip_nulls(v) for v in value if v is not None]
        return value

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
    def get_profiles_root(project_root: Path) -> Path:
        """Return the project-level profiles root.

        Profiles are intentionally *project-scoped* (adjacent to
        `.kano/backlog_config.toml`), not backlog-scoped.
        """

        return project_root / ".kano" / "backlog_config"

    @staticmethod
    def _validate_profile_ref(profile: str) -> str:
        """Validate a profile reference.

        Allows folder organization via safe relative paths:
        - OK: "usage", "embedding/local-noop", "logging/debug"
        - Not OK: "../secrets", "/abs/path", ".hidden", "a/..", "a//b"
        """

        raw = profile.strip()
        if not raw:
            raise ConfigError("profile name must be non-empty")

        normalized = raw.replace("\\", "/").strip("/")
        if not normalized:
            raise ConfigError("profile name must be non-empty")

        parts = normalized.split("/")
        for part in parts:
            if not part or part in {".", ".."}:
                raise ConfigError(f"invalid profile name: {profile!r}")
            if part.startswith("."):
                raise ConfigError(f"invalid profile name: {profile!r}")
            # Keep it filesystem-safe and ASCII-ish.
            if not re.fullmatch(r"[A-Za-z0-9._-]+", part):
                raise ConfigError(f"invalid profile name: {profile!r}")

        return normalized

    @staticmethod
    def _set_nested(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
        current: dict[str, Any] = target
        for part in path[:-1]:
            next_val = current.get(part)
            if not isinstance(next_val, dict):
                next_val = {}
                current[part] = next_val
            current = next_val
        current[path[-1]] = value

    @staticmethod
    def get_chunks_cache_root(
        backlog_root: Path,
        effective_config: Optional[dict[str, Any]] = None
    ) -> Path:
        """Get the root directory for chunks/vectors cache.
        
        Priority:
        1. config.cache.root (if specified)
        2. Default: backlog_root.parent.parent / ".kano" / "cache" / "backlog"
        
        This allows cache to be stored in a shared location (e.g., NAS)
        independent of where the backlog data is stored.
        """
        repo_root = backlog_root.parent.parent

        if effective_config:
            cache_config = effective_config.get("cache", {})
            if isinstance(cache_config, dict):
                cache_root = cache_config.get("root")
                if isinstance(cache_root, str) and cache_root.strip():
                    candidate = Path(cache_root.strip())
                    return (candidate if candidate.is_absolute() else (repo_root / candidate)).resolve()

        return (repo_root / ".kano" / "cache" / "backlog").resolve()

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
    def _resolve_topic_name(backlog_root: Path, topic: Optional[str], agent: Optional[str]) -> Optional[str]:
        return (topic or "").strip() or (ConfigLoader.get_active_topic(backlog_root, agent or "") or "") or None

    @staticmethod
    def load_topic_overrides(
        backlog_root: Path,
        *,
        topic: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> dict[str, Any]:
        topic_name = ConfigLoader._resolve_topic_name(backlog_root, topic, agent)
        if not topic_name:
            return {}
        return ConfigLoader._read_config_optional(ConfigLoader.get_topic_path(backlog_root, topic_name), "config")

    @staticmethod
    def load_workset_overrides(backlog_root: Path, *, item_id: Optional[str] = None) -> dict[str, Any]:
        if not item_id:
            return {}
        return ConfigLoader._read_config_optional(ConfigLoader.get_workset_path(backlog_root, item_id), "config")

    @staticmethod
    def _get_project_cache_root(project_root: Path) -> Path:
        return project_root / ".kano" / "cache"

    @staticmethod
    def _get_stable_cache_path(project_root: Path) -> Path:
        return ConfigLoader._get_project_cache_root(project_root) / "effective_backlog_config.toml"

    @staticmethod
    def _get_runtime_cache_path(project_root: Path) -> Path:
        return (
            ConfigLoader._get_project_cache_root(project_root)
            / "effective_runtime_backlog_config.toml"
        )

    @staticmethod
    def _get_mtime(path: Optional[Path]) -> Optional[float]:
        if not path:
            return None
        try:
            if path.exists():
                return path.stat().st_mtime
        except Exception:
            return None
        return None

    @staticmethod
    def _collect_sources(
        *,
        ctx: BacklogContext,
        project_config_path: Path,
        profile_path: Optional[Path],
        topic_name: Optional[str],
        workset_item_id: Optional[str],
    ) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []

        sources.append({
            "kind": "system_defaults",
            "path": "",
            "exists": False,
            "mtime": None,
        })

        defaults_path = ConfigLoader._resolve_optional_config_path(
            ctx.backlog_root / "_shared", "defaults"
        )
        sources.append({
            "kind": "defaults",
            "path": str(defaults_path),
            "exists": defaults_path.exists(),
            "mtime": ConfigLoader._get_mtime(defaults_path),
        })

        sources.append({
            "kind": "project_config",
            "path": str(project_config_path),
            "exists": project_config_path.exists(),
            "mtime": ConfigLoader._get_mtime(project_config_path),
        })

        if profile_path:
            sources.append({
                "kind": "profile",
                "path": str(profile_path),
                "exists": profile_path.exists(),
                "mtime": ConfigLoader._get_mtime(profile_path),
            })

        if topic_name:
            topic_path = ConfigLoader.get_topic_path(ctx.backlog_root, topic_name)
            topic_cfg_path = ConfigLoader._resolve_optional_config_path(topic_path, "config")
            sources.append({
                "kind": "topic",
                "path": str(topic_cfg_path),
                "exists": topic_cfg_path.exists(),
                "mtime": ConfigLoader._get_mtime(topic_cfg_path),
            })

        if workset_item_id:
            workset_path = ConfigLoader.get_workset_path(ctx.backlog_root, workset_item_id)
            workset_cfg_path = ConfigLoader._resolve_optional_config_path(workset_path, "config")
            sources.append({
                "kind": "workset",
                "path": str(workset_cfg_path),
                "exists": workset_cfg_path.exists(),
                "mtime": ConfigLoader._get_mtime(workset_cfg_path),
            })

        return ConfigLoader._strip_nulls(sources)

    @staticmethod
    def _build_cache_inputs(
        *,
        ctx: BacklogContext,
        profile: Optional[str],
        topic_name: Optional[str],
        workset_item_id: Optional[str],
        agent: Optional[str],
        custom_config_file: Optional[Path],
    ) -> dict[str, Any]:
        inputs = {
            "product": ctx.product_name,
            "profile": profile,
            "topic": topic_name,
            "workset": workset_item_id,
            "agent": agent,
            "custom_config_file": str(custom_config_file) if custom_config_file else None,
        }
        return ConfigLoader._strip_nulls(inputs)

    @staticmethod
    def _load_cached_effective_config(
        cache_path: Path,
        *,
        sources: list[dict[str, Any]],
        inputs: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        if not cache_path.exists():
            return None
        data = ConfigLoader._read_toml_optional(cache_path)
        if not isinstance(data, dict):
            return None
        meta = data.get("meta")
        if not isinstance(meta, dict):
            return None
        if meta.get("version") != 1:
            return None
        if meta.get("sources") != sources:
            return None
        if meta.get("inputs") != inputs:
            return None
        config = data.get("config")
        if not isinstance(config, dict):
            return None
        return config

    @staticmethod
    def _write_effective_cache(
        *,
        cache_path: Path,
        ctx: BacklogContext,
        effective: dict[str, Any],
        sources: list[dict[str, Any]],
        inputs: dict[str, Any],
    ) -> None:
        if tomli_w is None:
            raise ConfigError("tomli-w is required to write effective config cache")

        payload = {
            "meta": {
                "version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "sources": sources,
                "inputs": inputs,
            },
            "context": ConfigLoader._stringify_paths(ctx.model_dump()),
            "config": effective,
        }

        cleaned = ConfigLoader._strip_nulls(ConfigLoader._stringify_paths(payload))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        text = tomli_w.dumps(cleaned)
        cache_path.write_text(text, encoding="utf-8")

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

        product_root = ProjectConfigLoader.resolve_product_backlog_root(
            resource_path, product, project_config, custom_config_file
        )
        
        if not product_root:
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

        # Derive canonical backlog root.
        # In this repo layout, product roots live under: _kano/backlog/products/<product>
        # and shared state (topics/worksets/defaults/profiles) lives under: _kano/backlog/
        backlog_root = product_root
        if product_root.parent.name == "products" and product_root.parent.parent.name == "backlog":
            backlog_root = product_root.parent.parent

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
                "enabled": False,
                "backend": "sqlite",
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

        return product.to_overrides()

    @staticmethod
    def _resolve_project_root_for_profiles(start_path: Path, custom_config_file: Optional[Path] = None) -> Path:
        config_path = ProjectConfigLoader.find_project_config(start_path, custom_config_file)
        if not config_path:
            raise ConfigError("Project config file not found; cannot resolve profile root")
        if config_path.parent.name == ".kano":
            return config_path.parent.parent
        return config_path.parent

    @staticmethod
    def _resolve_profile_path(project_root: Path, profile_name: str) -> Path:
        profiles_root = (project_root / ".kano" / "backlog_config").resolve()

        raw = profile_name.strip()
        norm = raw.replace("\\", "/")
        explicit_path = Path(raw).is_absolute() or norm.startswith(".") or norm.endswith(".toml")

        if explicit_path:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = (project_root / candidate).resolve()
                if project_root.resolve() not in candidate.parents and candidate != project_root.resolve():
                    raise ConfigError(f"Invalid profile path traversal: {profile_name}")
            else:
                candidate = candidate.resolve()
            if candidate.suffix == "":
                candidate = candidate.with_suffix(".toml")
            if not candidate.exists():
                raise ConfigError(f"Profile config not found: {candidate}")
        else:
            name = ConfigLoader._validate_profile_ref(raw)
            rel = Path(name)
            if not rel.suffix:
                rel = rel.with_suffix(".toml")
            candidate = (profiles_root / rel).resolve()
            if profiles_root not in candidate.parents and candidate != profiles_root:
                raise ConfigError(f"Invalid profile path traversal: {profile_name}")

            if not candidate.exists():
                fallback = (project_root / rel).resolve()
                if project_root.resolve() not in fallback.parents and fallback != project_root.resolve():
                    raise ConfigError(f"Invalid profile path traversal: {profile_name}")
                if fallback.exists():
                    candidate = fallback
                else:
                    raise ConfigError(f"Profile config not found: {candidate}")

        if not candidate.is_file():
            raise ConfigError(f"Profile config is not a file: {candidate}")

        return candidate

    @staticmethod
    def load_profile_overrides(
        start_path: Path,
        *,
        profile: Optional[str] = None,
        custom_config_file: Optional[Path] = None,
    ) -> dict[str, Any]:
        """Load an optional profile overlay TOML.

        Profile resolution:
        - CLI/env provides `profile` (or env KANO_BACKLOG_PROFILE).
        - Explicit paths (absolute, or starting with '.', or ending in .toml) are honored.
        - Shorthand resolves under <project_root>/.kano/backlog_config/<profile>.toml.
          If not found, fallback checks <project_root>/<profile>.toml.

        The profile file is treated as a config overlay (higher priority than
        topic/workset in this implementation, but lower than explicit CLI flags).
        """
        profile_name = (profile or os.environ.get("KANO_BACKLOG_PROFILE") or "").strip()
        if not profile_name:
            return {}

        project_root = ConfigLoader._resolve_project_root_for_profiles(start_path, custom_config_file)
        candidate = ConfigLoader._resolve_profile_path(project_root, profile_name)

        data = ConfigLoader._read_toml_optional(candidate)
        if not isinstance(data, dict):
            raise ConfigError(f"Profile config must be a TOML table: {candidate}")

        flat_map: dict[str, tuple[str, ...]] = {
            "vector_enabled": ("vector", "enabled"),
            "vector_backend": ("vector", "backend"),
            "vector_metric": ("vector", "metric"),
            "analysis_llm_enabled": ("analysis", "llm", "enabled"),
            "cache_root": ("cache", "root"),
            "log_debug": ("log", "debug"),
            "log_verbosity": ("log", "verbosity"),
            "embedding_provider": ("embedding", "provider"),
            "embedding_model": ("embedding", "model"),
            "embedding_dimension": ("embedding", "dimension"),
            "chunking_target_tokens": ("chunking", "target_tokens"),
            "chunking_max_tokens": ("chunking", "max_tokens"),
            "tokenizer_adapter": ("tokenizer", "adapter"),
            "tokenizer_model": ("tokenizer", "model"),
        }

        overlay: dict[str, Any] = {}
        for key, path in flat_map.items():
            if key not in data:
                continue
            ConfigLoader._set_nested(overlay, path, data[key])

        cleaned = {k: v for k, v in data.items() if k not in flat_map}
        return ConfigLoader._deep_merge(cleaned, overlay)

    @staticmethod
    def load_effective_config(
        resource_path: Path,
        *,
        product: Optional[str] = None,
        sandbox: Optional[str] = None,
        agent: Optional[str] = None,
        topic: Optional[str] = None,
        profile: Optional[str] = None,
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

        project_default_profile = None
        candidate = project_cfg.get("profile")
        if isinstance(candidate, str) and candidate.strip():
            project_default_profile = candidate.strip()
        else:
            profiles_block = project_cfg.get("profiles")
            if isinstance(profiles_block, dict):
                active = profiles_block.get("active")
                if isinstance(active, str) and active.strip():
                    project_default_profile = active.strip()

        env_profile = os.environ.get("KANO_BACKLOG_PROFILE") or ""
        explicit_profile = (profile or env_profile).strip() or None
        resolved_profile = explicit_profile or project_default_profile

        stable_profile = project_default_profile
        stable_profile_cfg = (
            ConfigLoader.load_profile_overrides(ctx.project_root, profile=stable_profile)
            if stable_profile
            else {}
        )
        profile_cfg = (
            ConfigLoader.load_profile_overrides(ctx.project_root, profile=resolved_profile)
            if resolved_profile
            else {}
        )

        topic_name = ConfigLoader._resolve_topic_name(ctx.backlog_root, topic, agent)
        topic_cfg = ConfigLoader.load_topic_overrides(ctx.backlog_root, topic=topic_name, agent=agent)
        workset_cfg = ConfigLoader.load_workset_overrides(ctx.backlog_root, item_id=workset_item_id)

        config_path = ProjectConfigLoader.find_project_config(resource_path, custom_config_file)
        if not config_path:
            raise ConfigError("Project config file not found")

        project_config_obj = ProjectConfigLoader.load_project_config(config_path)
        product_def = project_config_obj.get_product(ctx.product_name)
        if not product_def:
            raise ConfigError(f"Product '{ctx.product_name}' not found in project config")
        product_block: dict[str, Any] = {
            "name": product_def.name,
            "prefix": product_def.prefix,
        }

        stable_profile_path = (
            ConfigLoader._resolve_profile_path(ctx.project_root, stable_profile)
            if stable_profile
            else None
        )
        runtime_profile_path = (
            ConfigLoader._resolve_profile_path(ctx.project_root, resolved_profile)
            if resolved_profile
            else None
        )

        stable_sources = ConfigLoader._collect_sources(
            ctx=ctx,
            project_config_path=config_path,
            profile_path=stable_profile_path,
            topic_name=None,
            workset_item_id=None,
        )
        runtime_sources = ConfigLoader._collect_sources(
            ctx=ctx,
            project_config_path=config_path,
            profile_path=runtime_profile_path,
            topic_name=topic_name,
            workset_item_id=workset_item_id,
        )

        stable_inputs = ConfigLoader._build_cache_inputs(
            ctx=ctx,
            profile=stable_profile,
            topic_name=None,
            workset_item_id=None,
            agent=agent,
            custom_config_file=custom_config_file,
        )
        runtime_inputs = ConfigLoader._build_cache_inputs(
            ctx=ctx,
            profile=resolved_profile,
            topic_name=topic_name,
            workset_item_id=workset_item_id,
            agent=agent,
            custom_config_file=custom_config_file,
        )

        stable_cache_path = ConfigLoader._get_stable_cache_path(ctx.project_root)
        runtime_cache_path = ConfigLoader._get_runtime_cache_path(ctx.project_root)

        stable_effective = ConfigLoader._load_cached_effective_config(
            stable_cache_path, sources=stable_sources, inputs=stable_inputs
        )

        runtime_effective = ConfigLoader._load_cached_effective_config(
            runtime_cache_path, sources=runtime_sources, inputs=runtime_inputs
        )

        if stable_effective is None:
            stable_effective = {}
            for layer in (
                system_defaults,
                defaults,
                project_cfg,
                project_product_overrides,
                stable_profile_cfg,
            ):
                if isinstance(layer, dict):
                    stable_effective = ConfigLoader._deep_merge(stable_effective, layer)

            stable_effective["product"] = dict(product_block)
            stable_effective = compile_effective_config(
                stable_effective, default_filesystem_root=ctx.project_root
            )
            ConfigLoader._write_effective_cache(
                cache_path=stable_cache_path,
                ctx=ctx,
                effective=stable_effective,
                sources=stable_sources,
                inputs=stable_inputs,
            )

        runtime_overrides = bool(explicit_profile or topic_name or workset_item_id)
        if runtime_overrides:
            if runtime_effective is None:
                runtime_effective = {}
                for layer in (
                    system_defaults,
                    defaults,
                    project_cfg,
                    project_product_overrides,
                    profile_cfg,
                    topic_cfg,
                    workset_cfg,
                ):
                    if isinstance(layer, dict):
                        runtime_effective = ConfigLoader._deep_merge(runtime_effective, layer)

                runtime_effective["product"] = dict(product_block)
                runtime_effective = compile_effective_config(
                    runtime_effective, default_filesystem_root=ctx.project_root
                )
                ConfigLoader._write_effective_cache(
                    cache_path=runtime_cache_path,
                    ctx=ctx,
                    effective=runtime_effective,
                    sources=runtime_sources,
                    inputs=runtime_inputs,
                )
        else:
            runtime_effective = stable_effective

        return ctx, runtime_effective

    @staticmethod
    def validate_pipeline_config(config: dict[str, Any]) -> Any:
        # Avoid circular import if possible, or Import here
        from .pipeline_config import PipelineConfig
        pc = PipelineConfig.from_dict(config)
        pc.validate()
        return pc


