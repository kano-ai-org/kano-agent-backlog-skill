"""Configuration and context resolution for kano-backlog."""

import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from .errors import ConfigError


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
    def from_path(
        resource_path: Path, product: Optional[str] = None, sandbox: Optional[str] = None
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

        # Determine product
        if not product:
            product = ConfigLoader._infer_product(resource_path, backlog_root)
        if not product:
            raise ConfigError(f"Cannot infer product name from path: {resource_path}")

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
        Load default configuration from _kano/backlog/_shared/defaults.json

        Args:
            backlog_root: Backlog root path

        Returns:
            Dictionary with defaults (empty if file not found)
        """
        defaults_path = backlog_root / "_shared" / "defaults.json"
        if not defaults_path.exists():
            return {}

        try:
            with open(defaults_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in {defaults_path}: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load defaults from {defaults_path}: {e}")
