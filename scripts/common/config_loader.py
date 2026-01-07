#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from context import (
    find_repo_root,
    find_platform_root,
    resolve_product_name,
    get_config_file,
)


DEFAULT_CONFIG_PATH = "_kano/backlog/_config/config.json"
DEFAULT_CONFIG = {
    "project": {
        "name": None,
        "prefix": None,
    },
    "views": {
        "auto_refresh": True,
    },
    "log": {
        "verbosity": "info",
        "debug": False,
    },
    "process": {
        "profile": "builtin/azure-boards-agile",
        "path": None,
    },
    "sandbox": {
        "root": "_kano/backlog_sandbox",
    },
    "index": {
        "enabled": False,
        "backend": "sqlite",
        "path": None,
        "mode": "rebuild",
    },
}


def allowed_roots_for_repo(repo_root: Path) -> List[Path]:
    """Return list of allowed config root directories for the repository.
    
    In multi-product architecture, configs can live under:
    - Platform root: _kano/backlog/
    - Product roots: _kano/backlog/products/<product>/
    - Sandboxes: _kano/backlog/sandboxes/<product>/
    """
    platform_root = find_platform_root(repo_root)
    return [
        platform_root.resolve(),
        (platform_root / "products").resolve(),
        (platform_root / "sandboxes").resolve(),
    ]


def resolve_allowed_root(path: Path, allowed_roots: List[Path]) -> Optional[Path]:
    """Return the allowed root under which the path is located, or None if not under any."""
    resolved = path.resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def resolve_config_path(
    repo_root: Optional[Path] = None,
    config_path: Optional[str] = None,
    product_name: Optional[str] = None,
) -> Path:
    """Resolve config file path for a product.
    
    Priority:
    1. Explicit config_path argument (if provided)
    2. Environment variable KANO_BACKLOG_CONFIG_PATH
    3. Product-specific config: <product_root>/_config/config.json
    4. Legacy fallback: _kano/backlog/_config/config.json
    
    Args:
        repo_root: Repository root (defaults to current working directory).
        config_path: Explicit config path (relative to repo_root or absolute).
        product_name: Product name (used for product-specific config path).
    
    Returns:
        Absolute path to the config file.
    
    Raises:
        SystemExit: If the resolved path is not under an allowed root.
    """
    root = repo_root or Path.cwd().resolve()
    
    # If explicit config_path provided, use it
    if config_path:
        path = Path(config_path)
        if not path.is_absolute():
            path = (root / path).resolve()
        allowed_roots = allowed_roots_for_repo(root)
        if resolve_allowed_root(path, allowed_roots) is None:
            allowed = " or ".join(str(r) for r in allowed_roots)
            raise SystemExit(f"Config path must be under {allowed}: {path}")
        return path
    
    # If environment variable provided, use it
    env_config = os.getenv("KANO_BACKLOG_CONFIG_PATH")
    if env_config:
        path = Path(env_config)
        if not path.is_absolute():
            path = (root / path).resolve()
        allowed_roots = allowed_roots_for_repo(root)
        if resolve_allowed_root(path, allowed_roots) is None:
            allowed = " or ".join(str(r) for r in allowed_roots)
            raise SystemExit(f"Config path must be under {allowed}: {path}")
        return path
    
    # If product_name provided, try to get product-specific config
    if product_name:
        try:
            platform_root = find_platform_root(root)
            return get_config_file(product_name=product_name, platform_root=platform_root)
        except FileNotFoundError:
            # Product root doesn't exist; fall back to legacy path
            pass
    
    # Legacy fallback: platform-level config
    platform_root = find_platform_root(root)
    path = (platform_root / "_config" / "config.json").resolve()
    return path


def load_config(
    repo_root: Optional[Path] = None,
    config_path: Optional[str] = None,
    product_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Load configuration for a product.
    
    Args:
        repo_root: Repository root (defaults to current working directory).
        config_path: Explicit config file path (relative to repo_root or absolute).
        product_name: Product name (used to locate product-specific config).
    
    Returns:
        Configuration dictionary (empty if file not found).
    
    Raises:
        SystemExit: If config file is invalid JSON or not under allowed roots.
    """
    root = repo_root or Path.cwd().resolve()
    path = resolve_config_path(root, config_path, product_name)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid config JSON: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Config must be a JSON object: {path}")
    return data


def default_config() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def merge_defaults(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config_with_defaults(
    repo_root: Optional[Path] = None,
    config_path: Optional[str] = None,
    defaults: Optional[Dict[str, Any]] = None,
    product_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Load configuration with defaults.
    
    Args:
        repo_root: Repository root (defaults to current working directory).
        config_path: Explicit config file path (relative to repo_root or absolute).
        defaults: Default configuration (uses default_config() if not provided).
        product_name: Product name (used to locate product-specific config).
    
    Returns:
        Merged configuration (defaults + overrides).
    """
    base = defaults if defaults is not None else default_config()
    overrides = load_config(repo_root=repo_root, config_path=config_path, product_name=product_name)
    if not overrides:
        return base
    return merge_defaults(base, overrides)


def get_config_value(config: Dict[str, Any], path: str, default: Any = None) -> Any:
    if not config or not path:
        return default
    current: Any = config
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return default
        current = current[segment]
    return current


def validate_config(config: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(config, dict):
        return ["Config must be a JSON object."]

    project_cfg = config.get("project", {})
    if project_cfg is not None and not isinstance(project_cfg, dict):
        errors.append("project must be an object.")
    else:
        name = project_cfg.get("name") if isinstance(project_cfg, dict) else None
        if name is not None and not isinstance(name, str):
            errors.append("project.name must be a string or null.")
        prefix = project_cfg.get("prefix") if isinstance(project_cfg, dict) else None
        if prefix is not None and not isinstance(prefix, str):
            errors.append("project.prefix must be a string or null.")
        elif isinstance(prefix, str):
            trimmed = prefix.strip()
            if trimmed and not trimmed.isalnum():
                errors.append("project.prefix must be alphanumeric (A-Z0-9).")

    views_cfg = config.get("views", {})
    if views_cfg is not None and not isinstance(views_cfg, dict):
        errors.append("views must be an object.")
    else:
        auto_refresh = views_cfg.get("auto_refresh") if isinstance(views_cfg, dict) else None
        if auto_refresh is not None and not isinstance(auto_refresh, bool):
            errors.append("views.auto_refresh must be a boolean.")

    log_cfg = config.get("log", {})
    if log_cfg is not None and not isinstance(log_cfg, dict):
        errors.append("log must be an object.")
    else:
        verbosity = log_cfg.get("verbosity") if isinstance(log_cfg, dict) else None
        if verbosity is not None and not isinstance(verbosity, str):
            errors.append("log.verbosity must be a string.")
        elif isinstance(verbosity, str):
            allowed = {"info", "debug", "warn", "warning", "error", "off", "none", "disabled"}
            if verbosity.strip().lower() not in allowed:
                errors.append("log.verbosity must be one of: info, debug, warn, error, off.")
        debug = log_cfg.get("debug") if isinstance(log_cfg, dict) else None
        if debug is not None and not isinstance(debug, bool):
            errors.append("log.debug must be a boolean.")

    process_cfg = config.get("process", {})
    if process_cfg is not None and not isinstance(process_cfg, dict):
        errors.append("process must be an object.")
    else:
        profile = process_cfg.get("profile") if isinstance(process_cfg, dict) else None
        if profile is not None and not isinstance(profile, str):
            errors.append("process.profile must be a string or null.")
        path_value = process_cfg.get("path") if isinstance(process_cfg, dict) else None
        if path_value is not None and not isinstance(path_value, str):
            errors.append("process.path must be a string or null.")

    index_cfg = config.get("index", {})
    if index_cfg is not None and not isinstance(index_cfg, dict):
        errors.append("index must be an object.")
    else:
        enabled = index_cfg.get("enabled") if isinstance(index_cfg, dict) else None
        if enabled is not None and not isinstance(enabled, bool):
            errors.append("index.enabled must be a boolean.")

        backend = index_cfg.get("backend") if isinstance(index_cfg, dict) else None
        if backend is not None and not isinstance(backend, str):
            errors.append("index.backend must be a string or null.")
        elif isinstance(backend, str):
            allowed_backends = {"sqlite", "postgres"}
            if backend.strip().lower() not in allowed_backends:
                errors.append("index.backend must be one of: sqlite, postgres.")

        path_value = index_cfg.get("path") if isinstance(index_cfg, dict) else None
        if path_value is not None and not isinstance(path_value, str):
            errors.append("index.path must be a string or null.")

        mode = index_cfg.get("mode") if isinstance(index_cfg, dict) else None
        if mode is not None and not isinstance(mode, str):
            errors.append("index.mode must be a string or null.")
        elif isinstance(mode, str):
            allowed_modes = {"rebuild", "incremental"}
            if mode.strip().lower() not in allowed_modes:
                errors.append("index.mode must be one of: rebuild, incremental.")

    sandbox_cfg = config.get("sandbox", {})
    if sandbox_cfg is not None and not isinstance(sandbox_cfg, dict):
        errors.append("sandbox must be an object.")
    else:
        root = sandbox_cfg.get("root") if isinstance(sandbox_cfg, dict) else None
        if root is not None and not isinstance(root, str):
            errors.append("sandbox.root must be a string.")

    return errors
