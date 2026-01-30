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
    overrides: Dict[str, Any] = Field(default_factory=dict, description="Product-specific config overrides")

    model_config = ConfigDict(arbitrary_types_allowed=True)

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
                
                products[name] = ProductDefinition(
                    name=product_data.get("name", name),
                    prefix=product_data.get("prefix", ""),
                    backlog_root=product_data.get("backlog_root", ""),
                    overrides=product_data.get("overrides", {})
                )
            
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
        
        try:
            return ProjectConfigLoader.load_project_config(config_path)
        except ConfigError as e:
            logger.warning(f"Failed to load project config: {e}")
            return None

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