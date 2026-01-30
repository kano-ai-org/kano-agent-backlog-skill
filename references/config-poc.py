#!/usr/bin/env python3
"""
Proof of Concept: Project-Level Multi-Product Backlog Configuration

This demonstrates the proposed config resolution hierarchy:
1. CLI Arguments (highest priority)
2. Project Config (.kano/backlog_config.toml)
3. Product Config (<backlog_root>/_config/config.toml)
4. Defaults (lowest priority)
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ProductDefinition:
    """Definition of a product in project config."""
    name: str
    prefix: str
    backlog_root: str
    overrides: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectConfig:
    """Project-level configuration."""
    defaults: Dict[str, Any] = field(default_factory=dict)
    products: Dict[str, ProductDefinition] = field(default_factory=dict)
    shared: Dict[str, Any] = field(default_factory=dict)


def load_project_config(config_path: Path) -> Optional[ProjectConfig]:
    """Load project-level configuration."""
    if not config_path.exists():
        return None
    
    # For demo purposes, we'll simulate TOML loading with dict
    # In real implementation, use tomllib (Python 3.11+) or toml library
    data = {}  # Would be: tomllib.load(config_path.open('rb'))
    
    # Parse products
    products = {}
    for name, product_data in data.get("products", {}).items():
        products[name] = ProductDefinition(
            name=product_data["name"],
            prefix=product_data["prefix"],
            backlog_root=product_data["backlog_root"],
            overrides=product_data.get("overrides", {})
        )
    
    return ProjectConfig(
        defaults=data.get("defaults", {}),
        products=products,
        shared=data.get("shared", {})
    )


def load_product_config(backlog_root: Path) -> Dict[str, Any]:
    """Load product-specific configuration."""
    config_path = backlog_root / "_config" / "config.toml"
    if config_path.exists():
        # Would be: return tomllib.load(config_path.open('rb'))
        return {}
    return {}


def merge_configs(
    defaults: Dict[str, Any],
    product_config: Dict[str, Any],
    project_config: Optional[ProjectConfig],
    product_name: str,
    cli_args: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge configurations with proper precedence."""
    result = defaults.copy()
    
    # Apply product-specific config
    deep_merge(result, product_config)
    
    # Apply project config if available
    if project_config:
        # Apply shared settings
        deep_merge(result, project_config.shared)
        
        # Apply defaults
        deep_merge(result, project_config.defaults)
        
        # Apply product-specific overrides
        if product_name in project_config.products:
            product_def = project_config.products[product_name]
            deep_merge(result, product_def.overrides)
    
    # Apply CLI arguments (highest priority)
    deep_merge(result, cli_args)
    
    return result


def deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    """Deep merge source into target."""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            deep_merge(target[key], value)
        else:
            target[key] = value


def resolve_backlog_root(
    product_name: str,
    project_config: Optional[ProjectConfig],
    default_root: str
) -> Path:
    """Resolve backlog root for a product."""
    if project_config and product_name in project_config.products:
        root = project_config.products[product_name].backlog_root
        return Path(root).expanduser().resolve()
    
    return Path(default_root).expanduser().resolve()


# Example usage
def main():
    """Demonstrate config resolution."""
    
    # Simulate project config
    project_config_data = {
        "defaults": {
            "skill_developer": True,
            "persona": "developer",
            "auto_refresh": True
        },
        "products": {
            "kano-agent-backlog-skill": {
                "name": "kano-agent-backlog-skill-demo",
                "prefix": "KABSD",
                "backlog_root": "_kano/backlog/products/kano-agent-backlog-skill",
                "overrides": {
                    "analysis": {"llm": {"enabled": True}}
                }
            },
            "kano-opencode-quickstart": {
                "name": "kano-opencode-quickstart",
                "prefix": "KO",
                "backlog_root": "../kano-opencode-quickstart/_kano/backlog",
                "overrides": {
                    "analysis": {"llm": {"enabled": False}}
                }
            }
        },
        "shared": {
            "log": {"verbosity": "warning", "debug": False},
            "index": {"enabled": True, "backend": "sqlite"}
        }
    }
    
    # Create project config object
    project_config = ProjectConfig(
        defaults=project_config_data["defaults"],
        products={
            name: ProductDefinition(**data)
            for name, data in project_config_data["products"].items()
        },
        shared=project_config_data["shared"]
    )
    
    # Simulate product-specific config
    product_config = {
        "mode": {"skill_developer": True},
        "views": {"auto_refresh": False}  # This will be overridden
    }
    
    # Simulate CLI args
    cli_args = {
        "log": {"verbosity": "debug"}  # Override shared setting
    }
    
    # Default config
    defaults = {
        "mode": {"skill_developer": False, "persona": "user"},
        "log": {"verbosity": "info", "debug": False},
        "views": {"auto_refresh": False}
    }
    
    # Resolve config for a product
    product_name = "kano-agent-backlog-skill"
    final_config = merge_configs(
        defaults=defaults,
        product_config=product_config,
        project_config=project_config,
        product_name=product_name,
        cli_args=cli_args
    )
    
    print("Final Configuration:")
    print(json.dumps(final_config, indent=2))
    
    # Show backlog root resolution
    backlog_root = resolve_backlog_root(
        product_name=product_name,
        project_config=project_config,
        default_root="_kano/backlog"
    )
    print(f"\nBacklog Root: {backlog_root}")


if __name__ == "__main__":
    main()