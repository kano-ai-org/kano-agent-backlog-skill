"""
artifacts.py - Attach artifacts to backlog items.

Implements copying a file into the artifacts store and appending a Worklog entry
linking to the attached artifact. Supports shared and product-local artifact roots.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os
import shutil

from kano_backlog_core.config import ConfigLoader
from kano_backlog_ops import frontmatter, worklog, item_utils


@dataclass
class AttachArtifactResult:
    """Result of attaching an artifact to a work item."""
    id: str
    source: Path
    destination: Path
    worklog_appended: bool


def _resolve_item_path(item_ref: str, *, product: Optional[str] = None, backlog_root: Optional[Path] = None) -> Path:
    """Resolve an item path from an ID/UID/path reference."""
    if item_ref.startswith("/") or ":\\" in item_ref:
        return Path(item_ref).resolve()

    def _find_platform_backlog_root() -> Path:
        current = Path.cwd()
        while current != current.parent:
            candidate = current / "_kano" / "backlog"
            if candidate.exists():
                return candidate
            current = current.parent
        raise ValueError("Cannot find backlog root")

    if backlog_root is None:
        backlog_root = _find_platform_backlog_root()

    # Prefer canonical resolution shared with Worksets (supports product layout + ID/UID refs).
    try:
        from kano_backlog_ops.workset import _resolve_item_ref

        item_path, _ = _resolve_item_ref(item_ref, backlog_root)
        return item_path
    except Exception:
        pass

    # Fallback: legacy file-name scan under items/ (single-product layout).
    items_root = backlog_root / "items"
    if items_root.exists():
        for path in items_root.rglob("*.md"):
            if path.name.endswith(".index.md"):
                continue
            stem = path.stem
            file_id = stem.split("_", 1)[0] if "_" in stem else stem
            if file_id == item_ref:
                return path

    raise FileNotFoundError(f"Item not found: {item_ref}")


def attach_artifact(
    item_ref: str,
    artifact_path: str | Path,
    *,
    product: Optional[str] = None,
    shared: bool = True,
    agent: str,
    note: Optional[str] = None,
    backlog_root: Optional[Path] = None,
) -> AttachArtifactResult:
    """
    Attach an artifact file to a backlog item and append a Worklog entry.

    Args:
        item_ref: Item ID/UID/path
        artifact_path: Path to file to attach (must exist)
        product: Product name for context resolution
        shared: If True, store under _shared/artifacts; else under artifacts/
        agent: Agent identity for audit logging
        note: Optional note to include in Worklog message
        backlog_root: Explicit backlog root (optional)

    Returns:
        AttachArtifactResult with details
    """
    src = Path(artifact_path).resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"Artifact not found or not a file: {src}")

    # Resolve platform/product context to determine artifact roots
    ctx = ConfigLoader.from_path(Path.cwd(), product=product) if backlog_root is None else None
    platform_backlog_root = (ctx.backlog_root if ctx else backlog_root)  # _kano/backlog
    product_root = (ctx.product_root if ctx else None)

    # If backlog_root was explicitly provided, derive product_root from it when possible.
    if backlog_root is not None and product:
        candidate = backlog_root / "products" / product
        if candidate.exists():
            product_root = candidate

    # Resolve the item path and ID
    item_path = _resolve_item_path(item_ref, product=product, backlog_root=(product_root or platform_backlog_root))
    lines = frontmatter.load_lines(item_path)
    fm = frontmatter.parse_frontmatter(lines)
    item_id = fm.get("id") or item_path.stem.split("_", 1)[0]

    # Determine destination directory
    if shared:
        base_root = platform_backlog_root / "_shared" / "artifacts"
    else:
        # Prefer product-local artifacts directory when product context is available
        base_root = (product_root / "artifacts") if product_root else (platform_backlog_root / "artifacts")
    dest_dir = base_root / item_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Compute destination file path (avoid overwrite; add suffix if exists)
    dest = dest_dir / src.name
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        i = 1
        while True:
            candidate = dest_dir / f"{stem}-{i}{suffix}"
            if not candidate.exists():
                dest = candidate
                break
            i += 1

    # Copy file with metadata
    shutil.copy2(src, dest)

    # Append worklog entry with a relative link from the item file
    rel_link = os.path.relpath(dest, start=item_path.parent)
    message = f"Artifact attached: [{dest.name}]({rel_link})"
    if note:
        message = f"{message} — {note}"
    new_lines = worklog.append_worklog_entry(lines, message, agent)
    frontmatter.write_lines(item_path, new_lines)

    return AttachArtifactResult(
        id=item_id,
        source=src,
        destination=dest,
        worklog_appended=True,
    )
