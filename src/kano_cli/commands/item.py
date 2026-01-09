from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import List, Optional

import typer

from ..util import ensure_core_on_path, resolve_product_root, find_item_path_by_id

app = typer.Typer()


def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    import re
    import unicodedata
    
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "untitled"


@app.command()
def read(
    item_id: str = typer.Argument(..., help="Display ID, e.g., KABSD-TSK-0001"),
    product: str | None = typer.Option(None, help="Product name under _kano/backlog/products"),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Read a backlog item from canonical store."""
    ensure_core_on_path()
    from kano_backlog_core.canonical import CanonicalStore

    product_root = resolve_product_root(product)
    store = CanonicalStore(product_root)
    item_path = find_item_path_by_id(store.items_root, item_id)
    item = store.read(item_path)

    if output_format == "json":
        data = item.model_dump()
        # Path is not JSON serializable
        data["file_path"] = str(data.get("file_path"))
        typer.echo(json.dumps(data, ensure_ascii=False))
    else:
        typer.echo(f"ID: {item.id}\nTitle: {item.title}\nState: {item.state.value}\nOwner: {item.owner}")


def validate_item_type(item_type: str) -> str:
    """Validate and normalize item type."""
    TYPE_MAP = {
        "epic": ("Epic", "EPIC", "epic"),
        "feature": ("Feature", "FTR", "feature"),
        "userstory": ("UserStory", "USR", "userstory"),
        "task": ("Task", "TSK", "task"),
        "bug": ("Bug", "BUG", "bug"),
    }
    
    type_key = item_type.lower()
    if type_key not in TYPE_MAP:
        valid_types = ", ".join(TYPE_MAP.keys())
        raise typer.BadParameter(f"Invalid item type '{item_type}'. Valid types: {valid_types}")
    
    return type_key


def validate_title(title: str) -> str:
    """Validate title is non-empty and contains valid characters."""
    if not title or not title.strip():
        raise typer.BadParameter("Title cannot be empty")
    
    # Check for invalid characters that could cause file system issues
    invalid_chars = ['<', '>', ':', '"', '|', '?', '*', '\0']
    for char in invalid_chars:
        if char in title:
            raise typer.BadParameter(f"Title contains invalid character: '{char}'")
    
    # Check length (reasonable limit for file names)
    if len(title) > 200:
        raise typer.BadParameter("Title too long (max 200 characters)")
    
    return title.strip()


def validate_parent_exists(parent: str | None, items_root: Path) -> str | None:
    """Validate that parent item exists when specified."""
    if not parent:
        return None
    
    # Try to find the parent item
    try:
        from ..util import find_item_path_by_id
        find_item_path_by_id(items_root, parent)
        return parent
    except SystemExit:
        raise typer.BadParameter(f"Parent item '{parent}' not found")


def validate_product_context(product: str | None) -> Path:
    """Validate product context and return product root."""
    try:
        return resolve_product_root(product)
    except SystemExit as e:
        raise typer.BadParameter(str(e))


def validate_priority(priority: str) -> str:
    """Validate priority value."""
    valid_priorities = ["P0", "P1", "P2", "P3", "P4"]
    if priority not in valid_priorities:
        valid_str = ", ".join(valid_priorities)
        raise typer.BadParameter(f"Invalid priority '{priority}'. Valid priorities: {valid_str}")
    return priority


def validate_tags(tags: str) -> List[str]:
    """Validate and parse tags."""
    if not tags:
        return []
    
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    
    # Validate each tag
    for tag in tag_list:
        if len(tag) > 50:
            raise typer.BadParameter(f"Tag too long (max 50 characters): '{tag}'")
        
        # Check for invalid characters in tags
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*', '\0', ',']
        for char in invalid_chars:
            if char in tag:
                raise typer.BadParameter(f"Tag '{tag}' contains invalid character: '{char}'")
    
    return tag_list


@app.command()
def create(
    item_type: str = typer.Option(..., "--type", help="epic|feature|userstory|task|bug"),
    title: str = typer.Option(..., "--title", help="Work item title"),
    parent: str | None = typer.Option(None, "--parent", help="Parent item ID (optional for Epic)"),
    priority: str = typer.Option("P2", "--priority", help="Priority (P0-P4, default: P2)"),
    area: str = typer.Option("general", "--area", help="Area tag"),
    iteration: str | None = typer.Option(None, "--iteration", help="Iteration name"),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags"),
    owner: str | None = typer.Option(None, "--owner", help="Owner name"),
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print item details without creating"),
):
    """Create a new backlog work item."""
    ensure_core_on_path()
    from kano_backlog_core.canonical import CanonicalStore, ItemType
    
    # Import generate_uid from the correct location
    import sys
    from pathlib import Path
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from backlog.lib.utils import generate_uid
    
    # Input validation
    try:
        validated_type = validate_item_type(item_type)
        validated_title = validate_title(title)
        validated_priority = validate_priority(priority)
        validated_tags = validate_tags(tags)
        product_root = validate_product_context(product)
        
        store = CanonicalStore(product_root)
        items_root = store.items_root
        
        validated_parent = validate_parent_exists(parent, items_root)
        
    except typer.BadParameter as e:
        typer.echo(f"❌ Validation error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Error during validation: {e}", err=True)
        raise typer.Exit(1)
    
    # Type mapping
    TYPE_MAP = {
        "epic": ("Epic", "EPIC", "epic"),
        "feature": ("Feature", "FTR", "feature"),
        "userstory": ("UserStory", "USR", "userstory"),
        "task": ("Task", "TSK", "task"),
        "bug": ("Bug", "BUG", "bug"),
    }
    
    type_label, type_code, type_folder = TYPE_MAP[validated_type]
    
    # Find next number in sequence
    import re
    max_num = 0
    type_folder_path = items_root / f"{type_folder}s"  # pluralize folder name
    if type_folder_path.exists():
        for item_file in type_folder_path.rglob("*.md"):
            if item_file.name.endswith(".index.md"):
                continue
            match = re.search(rf"(\w+)-{type_code}-(\d{{4}})", item_file.stem)
            if match:
                max_num = max(max_num, int(match.group(2)))
    
    next_number = max_num + 1
    bucket = (next_number // 100) * 100
    bucket_str = f"{bucket:04d}"
    
    # Generate ID (assuming prefix is first 2-3 letters of first word in product name)
    prefix = product_root.name.split("-")[0].upper()[:2]
    if len(prefix) < 2:
        prefix = product_root.name.upper()[:2]
    item_id = f"{prefix}-{type_code}-{next_number:04d}"
    
    slug = slugify(validated_title)
    file_name = f"{item_id}_{slug}.md"
    
    item_dir = type_folder_path / bucket_str
    item_path = item_dir / file_name
    
    if item_path.exists():
        typer.echo(f"❌ Item already exists: {item_path}", err=True)
        raise typer.Exit(1)
    
    if dry_run:
        typer.echo(f"✓ Would create: {item_id}")
        typer.echo(f"  Path: {item_path}")
        typer.echo(f"  Type: {type_label}")
        typer.echo(f"  Title: {validated_title}")
        typer.echo(f"  Priority: {validated_priority}")
        if validated_parent:
            typer.echo(f"  Parent: {validated_parent}")
        if validated_tags:
            typer.echo(f"  Tags: {', '.join(validated_tags)}")
        return
    
    # Create the item
    try:
        uid = generate_uid()
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Format tags for YAML
        tag_yaml = "[]" if not validated_tags else "[" + ", ".join(f'"{t}"' for t in validated_tags) + "]"
        
        parent_val = validated_parent if validated_parent else "null"
        owner_val = owner if owner else "null"
        iteration_val = iteration if iteration else "null"
        
        frontmatter = f"""---
id: {item_id}
uid: {uid}
type: {type_label}
title: "{validated_title}"
state: Proposed
priority: {validated_priority}
parent: {parent_val}
area: {area}
iteration: {iteration_val}
tags: {tag_yaml}
created: {date}
updated: {date}
owner: {owner_val}
external:
  azure_id: null
  jira_key: null
links:
  relates: []
  blocks: []
  blocked_by: []
decisions: []
---

# Context

# Goal

# Non-Goals

# Approach

# Alternatives

# Acceptance Criteria

# Risks / Dependencies

# Worklog

{timestamp} [agent={agent}] Created from CLI.
"""
        
        # Create directory if needed
        item_dir.mkdir(parents=True, exist_ok=True)
        
        # Write file atomically
        item_path.write_text(frontmatter, encoding="utf-8")
        
        typer.echo(f"✓ Created: {item_id}")
        typer.echo(f"  Path: {item_path}")
        
    except Exception as e:
        typer.echo(f"❌ Error creating item: {e}", err=True)
        # Clean up partial creation if needed
        if item_path.exists():
            try:
                item_path.unlink()
            except Exception:
                pass
        raise typer.Exit(1)


@app.command()
def validate(
    item_id: str = typer.Argument(..., help="Display ID, e.g., KABSD-TSK-0001"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Validate a work item against the Ready gate."""
    ensure_core_on_path()
    from kano_backlog_core.canonical import CanonicalStore
    
    product_root = resolve_product_root(product)
    store = CanonicalStore(product_root)
    item_path = find_item_path_by_id(store.items_root, item_id)
    item = store.read(item_path)
    
    # Ready gate fields
    ready_fields = ["context", "goal", "approach", "acceptance_criteria", "risks"]
    gaps = []
    
    for field in ready_fields:
        value = getattr(item, field, None)
        if not value or not value.strip():
            gaps.append(field)
    
    is_ready = len(gaps) == 0
    
    if output_format == "json":
        result = {
            "id": item.id,
            "is_ready": is_ready,
            "gaps": gaps,
        }
        typer.echo(json.dumps(result, ensure_ascii=False))
    else:
        if is_ready:
            typer.echo(f"✓ {item.id} is READY")
        else:
            typer.echo(f"❌ {item.id} is NOT READY")
            typer.echo("Missing fields:")
            for field in gaps:
                typer.echo(f"  - {field}")
