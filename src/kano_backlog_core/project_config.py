"""Project-level configuration support for multi-product backlog management.

This module provides data structures and loading logic for .kano/backlog_config.toml
files that can define multiple products and their backlog root locations.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, validator

from .errors import ConfigError

# Conditional TOML import: stdlib tomllib (3.11+) or fallback tomli (<3.11)
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore

logger = logging.getLogger(__name__)


class ProductDefinition(BaseModel):
    """Definition of a product in project config."""
    
    name: str = Field(..., description="Product display name")
    prefix: str = Field(..., description="Product ID prefix (e.g., 'KABSD')")
    backlog_root: str = Field(..., description="Path to backlog root (relative or absolute)")

    # Flattened keys (product-level overrides)
    vector_enabled: Optional[bool] = Field(default=None)
    vector_backend: Optional[str] = Field(default=None)
    vector_metric: Optional[str] = Field(default=None)
    analysis_llm_enabled: Optional[bool] = Field(default=None)
    cache_root: Optional[str] = Field(default=None)
    log_debug: Optional[bool] = Field(default=None)
    log_verbosity: Optional[str] = Field(default=None)
    embedding_provider: Optional[str] = Field(default=None)
    embedding_model: Optional[str] = Field(default=None)
    embedding_dimension: Optional[int] = Field(default=None)
    chunking_target_tokens: Optional[int] = Field(default=None)
    chunking_max_tokens: Optional[int] = Field(default=None)
    tokenizer_adapter: Optional[str] = Field(default=None)
    tokenizer_model: Optional[str] = Field(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    def to_overrides(self) -> Dict[str, Any]:
        def set_nested(d: Dict[str, Any], path: tuple[str, ...], value: Any) -> None:
            current: Dict[str, Any] = d
            for part in path[:-1]:
                next_val = current.get(part)
                if not isinstance(next_val, dict):
                    next_val = {}
                    current[part] = next_val
                current = next_val
            current[path[-1]] = value

        overrides: Dict[str, Any] = {}
        mapping: Dict[str, tuple[str, ...]] = {
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

        for attr, path in mapping.items():
            value = getattr(self, attr)
            if value is not None:
                set_nested(overrides, path, value)
        return overrides

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Product name cannot be empty")
        return v.strip()

    @validator('prefix')
    def validate_prefix(cls, v):
        if not v or not v.strip():
            raise ValueError("Product prefix cannot be empty")
        # Basic validation for ID prefix format
        prefix = v.strip().upper()
        if not prefix.replace('-', '').replace('_', '').isalnum():
            raise ValueError("Product prefix must be alphanumeric (with optional - or _)")
        return prefix

    @validator('backlog_root')
    def validate_backlog_root(cls, v):
        if not v or not v.strip():
            raise ValueError("Backlog root cannot be empty")
        return v.strip()


class ProjectConfig(BaseModel):
    """Project-level configuration."""
    
    defaults: Dict[str, Any] = Field(default_factory=dict, description="Default settings for all products")
    products: Dict[str, ProductDefinition] = Field(default_factory=dict, description="Product definitions")
    shared: Dict[str, Any] = Field(default_factory=dict, description="Shared settings for all products")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @validator('products')
    def validate_products(cls, v):
        if not v:
            return v
        
        # Check for duplicate prefixes
        prefixes = [prod.prefix for prod in v.values()]
        if len(prefixes) != len(set(prefixes)):
            raise ValueError("Product prefixes must be unique")
        
        return v

    def get_product(self, product_name: str) -> Optional[ProductDefinition]:
        """Get product definition by name."""
        return self.products.get(product_name)

    def resolve_backlog_root(self, product_name: str, config_file_path: Path) -> Optional[Path]:
        """Resolve backlog root path for a product."""
        product = self.get_product(product_name)
        if not product:
            return None
        
        backlog_root = Path(product.backlog_root)
        if backlog_root.is_absolute():
            return backlog_root.resolve()
        else:
            # Determine project root based on config file location
            if config_file_path.parent.name == ".kano":
                # Standard location: .kano/backlog_config.toml
                project_root = config_file_path.parent.parent
            else:
                # Custom location: assume config file is in project root
                project_root = config_file_path.parent
            
            return (project_root / backlog_root).resolve()

    def list_products(self) -> list[str]:
        """List all product names."""
        return list(self.products.keys())


class ProjectConfigLoader:
    """Load and validate project-level configuration."""

    @staticmethod
    def find_project_config(start_path: Path, custom_config_file: Optional[Path] = None) -> Optional[Path]:
        """Find .kano/backlog_config.toml by walking up the directory tree or use custom file."""
        if custom_config_file:
            if custom_config_file.exists():
                return custom_config_file.resolve()
            else:
                return None
        
        current = start_path if start_path.is_dir() else start_path.parent
        
        for parent in [current, *current.parents]:
            config_path = parent / ".kano" / "backlog_config.toml"
            if config_path.exists():
                return config_path
        
        return None

    @staticmethod
    def load_project_config(config_path: Path) -> ProjectConfig:
        """Load project configuration from .kano/backlog_config.toml."""
        if not config_path.exists():
            raise ConfigError(f"Project config file not found: {config_path}")
        
        if tomllib is None:
            raise ConfigError(
                "TOML support not available. Install tomli package: pip install tomli"
            )
        
        try:
            with open(config_path, 'rb') as f:
                data = tomllib.load(f)
        except Exception as e:
            raise ConfigError(f"Failed to parse TOML from {config_path}: {e}")
        
        if not isinstance(data, dict):
            raise ConfigError(f"Project config must be a TOML table: {config_path}")
        
        try:
            # Parse products section
            products = {}
            products_data = data.get("products", {})
            if not isinstance(products_data, dict):
                raise ConfigError("products section must be a table")
            
            for name, product_data in products_data.items():
                if not isinstance(product_data, dict):
                    raise ConfigError(f"Product '{name}' must be a table")

                if "overrides" in product_data:
                    raise ConfigError(
                        f"Product '{name}' uses legacy [products.{name}.overrides]. "
                        "Use flattened keys directly under [products.<name>] instead."
                    )

                payload = dict(product_data)
                payload["name"] = payload.get("name", name)
                payload["prefix"] = payload.get("prefix", "")
                payload["backlog_root"] = payload.get("backlog_root", "")

                products[name] = ProductDefinition(**payload)
            
            return ProjectConfig(
                defaults=data.get("defaults", {}),
                products=products,
                shared=data.get("shared", {})
            )
        
        except Exception as e:
            raise ConfigError(f"Invalid project config structure in {config_path}: {e}")

    @staticmethod
    def load_project_config_optional(start_path: Path, custom_config_file: Optional[Path] = None) -> Optional[ProjectConfig]:
        """Load project config if found, return None if not found."""
        config_path = ProjectConfigLoader.find_project_config(start_path, custom_config_file)
        if not config_path:
            return None

        return ProjectConfigLoader.load_project_config(config_path)

    @staticmethod
    def resolve_product_backlog_root(
        start_path: Path, 
        product_name: str, 
        project_config: Optional[ProjectConfig] = None,
        custom_config_file: Optional[Path] = None
    ) -> Optional[Path]:
        """Resolve backlog root for a product using project config."""
        if not project_config:
            project_config = ProjectConfigLoader.load_project_config_optional(start_path, custom_config_file)
        
        if not project_config:
            return None
        
        config_path = ProjectConfigLoader.find_project_config(start_path, custom_config_file)
        if not config_path:
            return None
        
        return project_config.resolve_backlog_root(product_name, config_path)
