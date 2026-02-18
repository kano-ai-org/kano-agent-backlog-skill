"""Sandbox initialization operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .init import _resolve_backlog_root, _ensure_dir


ITEM_TYPES = ("epic", "feature", "userstory", "task", "bug")


@dataclass
class SandboxInitResult:
    """Result of initializing a sandbox."""
    sandbox_root: Path
    created_paths: List[Path]


def init_sandbox(
    *,
    name: str,
    product: str,
    agent: str,
    backlog_root: Optional[Path] = None,
    force: bool = False,
) -> SandboxInitResult:
    """
    Initialize a sandbox environment for safe experimentation.

    Creates an isolated copy of the product structure under
    _kano/backlog_sandbox/ for testing without affecting production data.

    Args:
        name: Sandbox name (e.g., 'test-v2', 'experiment-1')
        product: Source product to mirror
        agent: Agent identifier for audit logging
        backlog_root: Backlog root path (auto-detected if None)
        force: Overwrite existing sandbox if it exists

    Returns:
        SandboxInitResult with created paths

    Raises:
        FileNotFoundError: If source product not initialized
        FileExistsError: If sandbox exists and force=False
    """
    backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)
    
    # Verify source product exists
    product_root = backlog_root_path / "products" / product
    if not product_root.exists():
        raise FileNotFoundError(f"Source product not initialized: {product_root}")
    
    # Resolve sandbox location
    sandbox_base = backlog_root_path.parent / "backlog_sandbox"
    sandbox_root = sandbox_base / name
    
    if sandbox_root.exists() and not force:
        raise FileExistsError(
            f"Sandbox already exists: {sandbox_root} (use --force to recreate)"
        )
    
    # Clean up if force=True
    if sandbox_root.exists() and force:
        import shutil
        shutil.rmtree(sandbox_root)
    
    # Create scaffold
    created: List[Path] = []
    
    if _ensure_dir(sandbox_base):
        created.append(sandbox_base)
    if _ensure_dir(sandbox_root):
        created.append(sandbox_root)
    
    directories = [
        sandbox_root / "decisions",
        sandbox_root / "views",
        sandbox_root / "items",
        sandbox_root / "_config",
        sandbox_root / "_meta",
        sandbox_root / ".cache",
        sandbox_root / "artifacts",
    ]
    
    for directory in directories:
        if _ensure_dir(directory):
            created.append(directory)
    
    # Create item type directories
    items_root = sandbox_root / "items"
    for item_type in ITEM_TYPES:
        type_dir = items_root / item_type
        if _ensure_dir(type_dir):
            created.append(type_dir)
        bucket_dir = type_dir / "0000"
        if _ensure_dir(bucket_dir):
            created.append(bucket_dir)
    
    # Copy config from source product (if exists)
    source_config = product_root / "_config" / "config.json"
    if source_config.exists():
        import json
        config_data = json.loads(source_config.read_text(encoding="utf-8"))
        
        # Modify config for sandbox context
        config_data["_comment"] = f"Sandbox '{name}' initialized by {agent} from product '{product}'"
        config_data["sandbox"] = {
            "name": name,
            "source_product": product,
            "initialized": "auto",
        }
        
        target_config = sandbox_root / "_config" / "config.json"
        target_config.write_text(json.dumps(config_data, indent=2) + "\n", encoding="utf-8")
        created.append(target_config)
    
    # Create README
    readme_path = sandbox_root / "README.md"
    readme_content = f"""# Sandbox: {name}

**Source Product:** {product}  
**Initialized By:** {agent}  
**Purpose:** Safe experimentation environment

## Structure

This sandbox mirrors the structure of `{product}` but is isolated from
production data. Changes here will not affect the main backlog.

## Usage

Use the same `kano` CLI commands with `--product {name}` or configure
the sandbox root in your environment.

## Cleanup

To remove this sandbox:
```bash
rm -rf {sandbox_root}
```
"""
    readme_path.write_text(readme_content, encoding="utf-8")
    created.append(readme_path)
    
    return SandboxInitResult(
        sandbox_root=sandbox_root,
        created_paths=created,
    )
