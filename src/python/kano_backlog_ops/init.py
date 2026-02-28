"""Backlog initialization operations."""

from __future__ import annotations

import json
import re
from datetime import datetime
import tomli_w
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from kano_backlog_core.config import BacklogContext

from . import item_utils


ITEM_TYPES = ("epic", "feature", "userstory", "task", "bug")
GUIDE_MARKER = "kano-agent-backlog-skill"


@dataclass
class InitBacklogResult:
    """Result of initializing a backlog product."""

    context: BacklogContext
    product_root: Path
    config_path: Path
    created_paths: List[Path]
    views_refreshed: List[Path]
    guides_updated: List[Path]


def init_backlog(
    product: str,
    backlog_root: Optional[Path] = None,
    *,
    agent: str,
    product_name: Optional[str] = None,
    prefix: Optional[str] = None,
    persona: str = "developer",
    skill_developer: bool = False,
    force: bool = False,
    create_guides: bool = False,
    refresh_views: bool = True,
) -> InitBacklogResult:
    """Initialize backlog structure for a product."""

    normalized_product = _normalize_product_name(product)
    backlog_root_path, backlog_created = _resolve_backlog_root(backlog_root, create_if_missing=True)
    created_paths: List[Path] = [backlog_root_path] if backlog_created else []

    products_root = backlog_root_path / "products"
    if _ensure_dir(products_root):
        created_paths.append(products_root)

    product_root = products_root / normalized_product
    if product_root.exists() and not force:
        raise FileExistsError(f"Product backlog already exists: {product_root}")
    if _ensure_dir(product_root):
        created_paths.append(product_root)

    created_paths.extend(_create_scaffold(product_root))

    actual_product_name = product_name.strip() if product_name else normalized_product
    if not actual_product_name:
        raise ValueError("Product name cannot be empty")
    actual_prefix = (prefix or item_utils.derive_prefix(actual_product_name)).upper()

    project_root = _resolve_project_root(backlog_root_path)
    config_path, config_created = _upsert_project_backlog_config(
        project_root=project_root,
        product=normalized_product,
        product_name=actual_product_name,
        prefix=actual_prefix,
        backlog_root=str(_relativize(product_root, project_root)),
        agent=agent,
        force=force,
    )
    if config_created:
        created_paths.append(config_path)

    views_refreshed: List[Path] = []
    if refresh_views:
        try:
            from .view import refresh_dashboards

            result = refresh_dashboards(
                product=normalized_product,
                agent=agent,
                backlog_root=backlog_root_path,
            )
            views_refreshed = result.views_refreshed
        except FileNotFoundError:
            # Items folder exists but has no items yet; skip refresh silently.
            views_refreshed = []

    guides_updated: List[Path] = []
    if create_guides:
        guides_updated = _update_guides(backlog_root_path)

    context = BacklogContext(
        project_root=project_root,
        backlog_root=backlog_root_path,
        product_root=product_root,
        sandbox_root=None,
        product_name=normalized_product,
        is_sandbox=False,
    )

    return InitBacklogResult(
        context=context,
        product_root=product_root,
        config_path=config_path,
        created_paths=created_paths,
        views_refreshed=views_refreshed,
        guides_updated=guides_updated,
    )


def check_initialized(
    product: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> bool:
    """Return True if the backlog (or specific product) is initialized."""

    try:
        backlog_root_path, _ = _resolve_backlog_root(backlog_root, create_if_missing=False)
    except FileNotFoundError:
        return False

    if product:
        target = backlog_root_path / "products" / _normalize_product_name(product)
        return (target / "items").exists() and (target / "views").exists()

    products_root = backlog_root_path / "products"
    if not products_root.exists():
        return False

    for candidate in products_root.iterdir():
        if not candidate.is_dir():
            continue
        if (candidate / "items").exists():
            return True
    return False


def _create_scaffold(product_root: Path) -> List[Path]:
    created: List[Path] = []

    directories = [
        product_root / "decisions",
        product_root / "views",
        product_root / "items",
        product_root / "_meta",
        product_root / "artifacts",
    ]

    for directory in directories:
        if _ensure_dir(directory):
            created.append(directory)

    items_root = product_root / "items"
    for item_type in ITEM_TYPES:
        type_dir = items_root / item_type
        if _ensure_dir(type_dir):
            created.append(type_dir)
        bucket_dir = type_dir / "0000"
        if _ensure_dir(bucket_dir):
            created.append(bucket_dir)

    return created


def _upsert_project_backlog_config(
    *,
    project_root: Path,
    product: str,
    product_name: str,
    prefix: str,
    backlog_root: str,
    agent: str,
    force: bool,
) -> tuple[Path, bool]:
    """Ensure the project-level .kano/backlog_config.toml contains this product."""
    kano_dir = project_root / ".kano"
    kano_dir.mkdir(parents=True, exist_ok=True)
    config_path = kano_dir / "backlog_config.toml"
    created = False

    header = (
        "# Project-Level Backlog Configuration\n"
        "# This file is source-of-truth and should be committed.\n\n"
        "[defaults]\n"
        "auto_refresh = true\n"
        "skill_developer = false\n\n"
        "[shared.cache]\n"
        "root = \".kano/cache/backlog\"\n\n"
        "[shared.vector]\n"
        "enabled = true\n"
        "backend = \"sqlite\"\n"
        "path = \".kano/cache/backlog/vector\"\n"
        "collection = \"backlog\"\n"
        "metric = \"cosine\"\n\n"
    )

    if not config_path.exists():
        config_path.write_text(header, encoding="utf-8")
        created = True

    text = config_path.read_text(encoding="utf-8")

    # If product already exists, keep it unless force=true.
    product_table = f"[products.{product}]"
    if product_table in text and not force:
        return config_path, created

    # Best-effort remove old block when force=true to avoid duplicates.
    if product_table in text and force:
        pattern = rf"(?ms)^\[products\.{re.escape(product)}\]\s*$.*?(?=^\[|\Z)"
        text = re.sub(pattern, "", text).rstrip() + "\n"

    stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") + "Z"
    block = (
        f"\n# Added by kano-backlog admin init ({stamp}, agent={agent})\n"
        f"[products.{product}]\n"
        f"name = {json.dumps(product_name)}\n"
        f"prefix = {json.dumps(prefix)}\n"
        f"backlog_root = {json.dumps(backlog_root)}\n"
    )

    config_path.write_text(text.rstrip() + block, encoding="utf-8")
    return config_path, True


def _update_guides(backlog_root: Path) -> List[Path]:
    skill_root = Path(__file__).resolve().parents[2]
    repo_root = skill_root.parent.parent if skill_root.parent.name == "skills" else skill_root.parent

    replacements = {
        "SKILL_ROOT": _relativize(skill_root, repo_root),
        "BACKLOG_ROOT": _relativize(backlog_root, repo_root),
    }

    templates_dir = skill_root / "templates"
    updates: List[Path] = []
    guides = {
        "AGENTS.block.md": repo_root / "AGENTS.md",
        "CLAUDE.block.md": repo_root / "CLAUDE.md",
    }

    for template_name, target_path in guides.items():
        template_path = templates_dir / template_name
        if not template_path.exists():
            continue
        block = _render_template(template_path, replacements)
        if _write_block(target_path, block):
            updates.append(target_path)

    return updates


def _render_template(template_path: Path, replacements: Dict[str, str]) -> str:
    content = template_path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    return content.rstrip() + "\n"


def _write_block(target_path: Path, block: str) -> bool:
    start_tag = f"<!-- {GUIDE_MARKER}:start -->"
    end_tag = f"<!-- {GUIDE_MARKER}:end -->"

    if target_path.exists():
        original = target_path.read_text(encoding="utf-8")
    else:
        original = f"# {target_path.stem}\n\n"

    start_idx = original.find(start_tag)
    end_idx = original.find(end_tag)

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        end_idx += len(end_tag)
        updated = original[:start_idx] + block + original[end_idx:]
    else:
        separator = "\n" if original.endswith("\n\n") else "\n\n"
        updated = original.rstrip() + separator + block

    if updated == original:
        return False

    target_path.write_text(updated, encoding="utf-8")
    return True


def _ensure_dir(path: Path) -> bool:
    if path.exists():
        return False
    path.mkdir(parents=True, exist_ok=True)
    return True


def _resolve_backlog_root(
    backlog_root: Optional[Path],
    *,
    create_if_missing: bool,
) -> Tuple[Path, bool]:
    if backlog_root:
        path = Path(backlog_root).expanduser().resolve()
        if path.name == "products":
            path = path.parent
        if path.exists():
            return path, False
        if not create_if_missing:
            raise FileNotFoundError(f"Backlog root not found: {path}")
        path.mkdir(parents=True, exist_ok=True)
        return path, True

    start = Path.cwd().resolve()
    for candidate in [start, *start.parents]:
        possible = candidate / "_kano" / "backlog"
        if possible.exists():
            return possible, False

    if not create_if_missing:
        raise FileNotFoundError("Could not locate _kano/backlog")

    repo_root = _find_repo_root(start)
    path = repo_root / "_kano" / "backlog"
    path.mkdir(parents=True, exist_ok=True)
    return path, True


def _find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return start


def _resolve_project_root(backlog_root: Path) -> Path:
    if backlog_root.parent.name == "_kano":
        return backlog_root.parent.parent
    return backlog_root.parent


def _normalize_product_name(product: str) -> str:
    if product is None:
        raise ValueError("Product name is required")
    cleaned = product.strip()
    if not cleaned:
        raise ValueError("Product name cannot be empty")
    if any(sep in cleaned for sep in ("/", "\\", "..")):
        raise ValueError("Product name cannot contain path separators")
    return cleaned


def _relativize(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()

