from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


def ensure_core_on_path() -> None:
    try:
        import kano_backlog_core  # noqa: F401
        return
    except Exception:
        pass
    # Try local path fallback: kano_backlog_core is in the same src/ directory as kano_backlog_cli
    skill_src = Path(__file__).resolve().parent.parent
    if (skill_src / "kano_backlog_core").exists():
        sys.path.insert(0, str(skill_src))
        try:
            import kano_backlog_core  # noqa: F401
            return
        except Exception:
            pass
    # Also try upward search for backward compatibility
    search_roots = [Path.cwd().resolve(), Path(__file__).resolve().parent.parent.parent.parent.parent]
    for root in search_roots:
        candidate = root / "kano-backlog-core" / "src"
        if candidate.exists() and (candidate / "kano_backlog_core").exists():
            sys.path.insert(0, str(candidate))
            try:
                import kano_backlog_core  # noqa: F401
                return
            except Exception:
                pass
    raise SystemExit("kano_backlog_core not found; install the package or check that kano_backlog_core is in src/ directory.")


def resolve_model(model: Optional[str]) -> tuple[str, bool]:
    """
    Resolve the model name deterministically.

    Order:
    1) explicit CLI flag
    2) env vars KANO_AGENT_MODEL, KANO_MODEL
    3) "unknown"

    Returns:
        (model_value, is_default_unknown)
    """
    if model and model.strip():
        return model.strip(), False
    env_model = (os.environ.get("KANO_AGENT_MODEL") or os.environ.get("KANO_MODEL") or "").strip()
    if env_model:
        return env_model, False
    return "unknown", True


def find_platform_root(start: Optional[Path] = None) -> Path:
    """Find repo platform root containing _kano/backlog."""
    cur = (start or Path.cwd()).resolve()
    while True:
        if (cur / "_kano" / "backlog").exists():
            return cur
        if cur.parent == cur:
            raise SystemExit("Could not locate _kano/backlog from current path.")
        cur = cur.parent


def resolve_product_root(product: Optional[str] = None, start: Optional[Path] = None) -> Path:
    platform_root = find_platform_root(start)
    backlog_root = platform_root / "_kano" / "backlog"
    products_dir = backlog_root / "products"
    if product:
        root = products_dir / product
        if not root.exists():
            raise SystemExit(f"Product not found: {root}")
        return root

    # If defaults specify a product, honor it (TOML-first; JSON is deprecated fallback).
    try:
        ensure_core_on_path()
        from kano_backlog_core.config import ConfigLoader

        defaults = ConfigLoader.load_defaults(backlog_root)
        default_product = defaults.get("default_product") if isinstance(defaults, dict) else None
        if isinstance(default_product, str) and default_product.strip():
            candidate = products_dir / default_product.strip()
            if candidate.exists():
                return candidate
    except Exception:
        # Keep fallback behavior if defaults cannot be loaded.
        pass
    # Fallback: pick the only product if exactly one exists
    candidates = [p for p in products_dir.iterdir() if p.is_dir()]
    if len(candidates) == 1:
        return candidates[0]
    raise SystemExit("Multiple products found; specify --product.")


def find_item_path_by_id(items_root: Path, display_id: str) -> Path:
    # Quick filename match first (exclude .index.md files)
    for path in items_root.rglob(f"{display_id}_*.md"):
        if not path.name.endswith(".index.md"):
            return path
    # Fallback: scan all and check frontmatter ids
    try:
        import frontmatter
    except Exception as e:
        raise SystemExit(f"frontmatter is required for scanning items: {e}")
    for path in items_root.rglob("*.md"):
        if path.name.endswith(".index.md"):
            continue  # Skip index files
        try:
            post = frontmatter.load(path)
            if post.get("id") == display_id:
                return path
        except Exception:
            continue
    raise SystemExit(f"Item not found: {display_id}")
