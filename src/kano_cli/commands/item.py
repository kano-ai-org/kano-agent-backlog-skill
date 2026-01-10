from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

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


def ensure_config_modules_on_path() -> None:
    """Ensure config_loader and context modules are available."""
    # Try multiple possible paths to find the scripts directory
    current_file = Path(__file__).resolve()
    possible_paths = [
        current_file.parents[2] / "scripts" / "common",  # From CLI module
        Path.cwd() / "skills" / "kano-agent-backlog-skill" / "scripts" / "common",  # From repo root
        Path.cwd() / "scripts" / "common",  # From skill root
    ]
    
    # Also try to find the actual skill directory by looking for known files
    for parent in current_file.parents:
        skill_scripts = parent / "scripts" / "common"
        if skill_scripts.exists() and (skill_scripts / "config_loader.py").exists():
            possible_paths.insert(0, skill_scripts)
            break
    
    for common_dir in possible_paths:
        if common_dir.exists() and (common_dir / "config_loader.py").exists():
            if str(common_dir) not in sys.path:
                sys.path.insert(0, str(common_dir))
            return
    
    # If we can't find the modules, raise a more helpful error
    raise ImportError(f"Could not find config_loader module. Searched paths: {[str(p) for p in possible_paths]}")


def load_configuration_context(
    product_arg: Optional[str] = None,
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Load configuration and resolve product context.
    
    Args:
        product_arg: Product name from CLI argument
        config_path: Explicit config file path
        
    Returns:
        Dictionary containing resolved configuration and context
        
    Raises:
        typer.BadParameter: If configuration or context resolution fails
    """
    try:
        ensure_config_modules_on_path()
        from config_loader import load_config_with_defaults, validate_config
        from context import get_context, get_product_name
        
        # Resolve product name using the context module's priority chain
        product_name = get_product_name(product_arg, env_var="KANO_PRODUCT")
        
        # Get full context (repo_root, platform_root, product_root, etc.)
        context = get_context(product_arg=product_name)
        
        # Load configuration with defaults
        config = load_config_with_defaults(
            repo_root=context["repo_root"],
            config_path=config_path,
            product_name=product_name,
        )
        
        # Validate configuration
        validation_errors = validate_config(config)
        if validation_errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in validation_errors)
            raise typer.BadParameter(error_msg)
        
        # Apply environment variable overrides
        config = apply_environment_overrides(config)
        
        return {
            "config": config,
            "context": context,
            "product_name": product_name,
        }
        
    except (ImportError, FileNotFoundError) as e:
        # Fallback to basic product resolution if config modules are not available
        # or if we're in a test environment without a git repository
        try:
            # Try the existing product resolution first
            product_root = resolve_product_root(product_arg)
            product_name = product_arg or product_root.name
        except SystemExit:
            # If that fails (e.g., in test environments), create a minimal fallback
            if product_arg:
                product_name = product_arg
                # Create a fake product root for testing
                product_root = Path.cwd() / "_kano" / "backlog" / "products" / product_name
            else:
                raise typer.BadParameter("Product name is required when configuration system is not available")
        
        # Create minimal config
        config = {
            "project": {"name": product_name, "prefix": None},
            "views": {"auto_refresh": True},
            "log": {"verbosity": "info", "debug": False},
            "process": {"profile": "builtin/azure-boards-agile"},
            "index": {"enabled": False, "backend": "sqlite"}
        }
        
        # Apply environment variable overrides
        config = apply_environment_overrides(config)
        
        # Create minimal context
        context = {
            "product_root": product_root,
            "product_name": product_name,
        }
        
        return {
            "config": config,
            "context": context,
            "product_name": product_name,
        }
        
    except Exception as e:
        raise typer.BadParameter(f"Unexpected error during configuration loading: {e}")


def apply_environment_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides to configuration.
    
    Supported environment variables:
    - KANO_PRODUCT: Override product name
    - KANO_LOG_VERBOSITY: Override log.verbosity
    - KANO_LOG_DEBUG: Override log.debug (true/false)
    - KANO_VIEWS_AUTO_REFRESH: Override views.auto_refresh (true/false)
    - KANO_INDEX_ENABLED: Override index.enabled (true/false)
    - KANO_INDEX_BACKEND: Override index.backend
    - KANO_PROCESS_PROFILE: Override process.profile
    
    Args:
        config: Base configuration dictionary
        
    Returns:
        Configuration with environment overrides applied
    """
    import copy
    
    config = copy.deepcopy(config)
    
    # Log verbosity override
    if "KANO_LOG_VERBOSITY" in os.environ:
        verbosity = os.environ["KANO_LOG_VERBOSITY"].strip().lower()
        if verbosity in {"info", "debug", "warn", "warning", "error", "off", "none", "disabled"}:
            config.setdefault("log", {})["verbosity"] = verbosity
    
    # Log debug override
    if "KANO_LOG_DEBUG" in os.environ:
        debug_val = os.environ["KANO_LOG_DEBUG"].strip().lower()
        if debug_val in {"true", "1", "yes", "on"}:
            config.setdefault("log", {})["debug"] = True
        elif debug_val in {"false", "0", "no", "off"}:
            config.setdefault("log", {})["debug"] = False
    
    # Views auto refresh override
    if "KANO_VIEWS_AUTO_REFRESH" in os.environ:
        auto_refresh_val = os.environ["KANO_VIEWS_AUTO_REFRESH"].strip().lower()
        if auto_refresh_val in {"true", "1", "yes", "on"}:
            config.setdefault("views", {})["auto_refresh"] = True
        elif auto_refresh_val in {"false", "0", "no", "off"}:
            config.setdefault("views", {})["auto_refresh"] = False
    
    # Index enabled override
    if "KANO_INDEX_ENABLED" in os.environ:
        index_enabled_val = os.environ["KANO_INDEX_ENABLED"].strip().lower()
        if index_enabled_val in {"true", "1", "yes", "on"}:
            config.setdefault("index", {})["enabled"] = True
        elif index_enabled_val in {"false", "0", "no", "off"}:
            config.setdefault("index", {})["enabled"] = False
    
    # Index backend override
    if "KANO_INDEX_BACKEND" in os.environ:
        backend = os.environ["KANO_INDEX_BACKEND"].strip().lower()
        if backend in {"sqlite", "postgres"}:
            config.setdefault("index", {})["backend"] = backend
    
    # Process profile override
    if "KANO_PROCESS_PROFILE" in os.environ:
        profile = os.environ["KANO_PROCESS_PROFILE"].strip()
        if profile:
            config.setdefault("process", {})["profile"] = profile
    
    return config


def validate_product_directory_structure(product_root: Path) -> None:
    """Validate that product directory has the expected structure.
    
    Args:
        product_root: Path to the product root directory
        
    Raises:
        typer.BadParameter: If directory structure is invalid
    """
    required_dirs = ["items", "decisions", "views", "_config", "_meta"]
    missing_dirs = []
    
    for dir_name in required_dirs:
        dir_path = product_root / dir_name
        if not dir_path.exists():
            missing_dirs.append(dir_name)
    
    if missing_dirs:
        missing_str = ", ".join(missing_dirs)
        raise typer.BadParameter(
            f"Product directory structure is incomplete. Missing directories: {missing_str}. "
            f"Product root: {product_root}"
        )
    
    # Validate that items directory has the expected type subdirectories
    items_dir = product_root / "items"
    expected_item_types = ["epic", "feature", "userstory", "task", "bug"]
    
    for item_type in expected_item_types:
        type_dir = items_dir / f"{item_type}s"  # pluralized
        if not type_dir.exists():
            # Create missing item type directories
            type_dir.mkdir(parents=True, exist_ok=True)


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


def validate_product_context(product: str | None, config_path: str | None = None) -> Dict[str, Any]:
    """Validate product context and return configuration context.
    
    Args:
        product: Product name from CLI argument
        config_path: Optional explicit config file path
        
    Returns:
        Dictionary containing config, context, and product_name
        
    Raises:
        typer.BadParameter: If validation fails
    """
    try:
        config_context = load_configuration_context(product, config_path)
        product_root = config_context["context"]["product_root"]
        
        # Validate product directory structure
        validate_product_directory_structure(product_root)
        
        return config_context
        
    except typer.BadParameter:
        raise  # Re-raise typer errors as-is
    except Exception as e:
        raise typer.BadParameter(f"Product context validation failed: {e}")


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


def generate_next_item_id(items_root: Path, prefix: str, type_code: str) -> tuple[str, int, str]:
    """
    Generate the next unique item ID within product scope.
    
    Args:
        items_root: Root directory for items
        prefix: Project prefix (e.g., "TE", "KABSD")
        type_code: Type code (e.g., "EPIC", "TSK")
        
    Returns:
        Tuple of (item_id, next_number, bucket_str)
    """
    import re
    
    # Scan entire items root to ensure uniqueness across all type folders
    # This handles both legacy (plural) and new (singular) folder layouts
    pattern = re.compile(rf"{re.escape(prefix)}-{type_code}-(\d{{4}})")
    max_num = 0
    
    if items_root.exists():
        for item_file in items_root.rglob("*.md"):
            # Skip index files and README files
            if item_file.name == "README.md" or item_file.name.endswith(".index.md"):
                continue
            
            # Check both filename and frontmatter ID for robustness
            match = pattern.search(item_file.stem)
            if match:
                number = int(match.group(1))
                max_num = max(max_num, number)
            
            # Also check frontmatter ID as backup
            try:
                content = item_file.read_text(encoding="utf-8")
                lines = content.splitlines()
                if lines and lines[0].strip() == "---":
                    for line in lines[1:]:
                        if line.strip() == "---":
                            break
                        if line.startswith("id:"):
                            frontmatter_id = line.split(":", 1)[1].strip().strip('"')
                            match = pattern.search(frontmatter_id)
                            if match:
                                number = int(match.group(1))
                                max_num = max(max_num, number)
                            break
            except (UnicodeDecodeError, IndexError):
                # Skip files that can't be read or parsed
                continue
    
    next_number = max_num + 1
    bucket = (next_number // 100) * 100
    bucket_str = f"{bucket:04d}"
    item_id = f"{prefix}-{type_code}-{next_number:04d}"
    
    return item_id, next_number, bucket_str


def resolve_item_file_path(items_root: Path, type_folder: str, bucket_str: str, item_id: str, title: str) -> Path:
    """
    Resolve the complete file path for a new item with proper bucket organization.
    
    Args:
        items_root: Root directory for items
        type_folder: Type folder name (e.g., "epic", "task")
        bucket_str: Bucket string (e.g., "0000", "0100")
        item_id: Item ID (e.g., "TE-TSK-0001")
        title: Item title for slug generation
        
    Returns:
        Complete Path object for the item file
    """
    # Use pluralized folder names for consistency with existing structure
    type_folder_path = items_root / f"{type_folder}s"
    
    # Generate slug from title
    slug = slugify(title)
    file_name = f"{item_id}_{slug}.md"
    
    # Create full path with bucket organization
    item_dir = type_folder_path / bucket_str
    item_path = item_dir / file_name
    
    return item_path


def render_item_template(
    item_id: str,
    uid: str,
    type_label: str,
    title: str,
    priority: str,
    parent: str | None,
    area: str,
    iteration: str | None,
    tags: List[str],
    owner: str | None,
    agent: str,
    worklog_message: str = "Created from CLI"
) -> str:
    """
    Render the complete item template with YAML frontmatter and markdown body.
    
    This function creates the same format as workitem_create.py for backward compatibility.
    
    Args:
        item_id: Unique item identifier
        uid: Unique identifier (ULID)
        type_label: Human-readable type (e.g., "Epic", "Task")
        title: Item title
        priority: Priority level (P0-P4)
        parent: Parent item ID or None
        area: Area classification
        iteration: Iteration name or None
        tags: List of tags
        owner: Owner name or None
        agent: Agent name for audit trail
        worklog_message: Initial worklog message
        
    Returns:
        Complete item content as string
    """
    import datetime
    
    # Generate timestamps
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Format nullable values
    parent_val = parent if parent else "null"
    owner_val = owner if owner else "null"
    iteration_val = iteration if iteration else "null"
    
    # Format tags for YAML
    if not tags:
        tag_yaml = "[]"
    else:
        # Escape quotes in tags and format as YAML list
        escaped_tags = [tag.replace('"', '\\"') for tag in tags]
        tag_yaml = "[" + ", ".join(f'"{tag}"' for tag in escaped_tags) + "]"
    
    # Escape title for YAML (handle quotes and special characters)
    escaped_title = title.replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
    
    # Build the complete template
    template = f"""---
id: {item_id}
uid: {uid}
type: {type_label}
title: "{escaped_title}"
state: Proposed
priority: {priority}
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

{timestamp} [agent={agent}] {worklog_message}
"""
    
    return template


def create_item_atomically(item_path: Path, content: str) -> None:
    """
    Create item file atomically to prevent partial writes.
    
    Args:
        item_path: Target file path
        content: File content to write
        
    Raises:
        Exception: If file creation fails
    """
    import tempfile
    import shutil
    
    # Ensure parent directory exists
    item_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temporary file first, then move to final location
    # This ensures atomic operation - either complete success or no file
    temp_dir = item_path.parent
    with tempfile.NamedTemporaryFile(
        mode='w', 
        encoding='utf-8', 
        dir=temp_dir, 
        delete=False,
        suffix='.tmp'
    ) as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)
    
    try:
        # Atomic move from temp to final location
        shutil.move(str(temp_path), str(item_path))
    except Exception:
        # Clean up temp file if move fails
        try:
            temp_path.unlink()
        except Exception:
            pass
        raise


def create_epic_index_if_needed(
    item_path: Path, 
    item_id: str, 
    title: str, 
    type_label: str,
    product_root: Path,
    repo_root: Path | None = None
) -> Path | None:
    """
    Create Epic index file if the item is an Epic.
    
    Args:
        item_path: Path to the main item file
        item_id: Item ID
        title: Item title
        type_label: Type label (should be "Epic")
        product_root: Product root directory
        repo_root: Repository root for relative path calculation
        
    Returns:
        Path to created index file, or None if not created
    """
    if type_label != "Epic":
        return None
    
    import datetime
    
    # Create index file path
    index_path = item_path.with_suffix(".index.md")
    
    # Calculate backlog label for Dataview queries
    backlog_label = f"_kano/backlog/products/{product_root.name}"
    if repo_root:
        try:
            backlog_label = product_root.relative_to(repo_root).as_posix()
        except ValueError:
            pass  # Use default if relative path calculation fails
    
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Render index template
    index_content = f"""---
type: Index
for: {item_id}
title: "{title} Index"
updated: {date}
---

# MOC

## Auto list (Dataview)

```dataview
table id, state, priority
from "{backlog_label}/items"
where parent = "{item_id}"
sort priority asc
```

"""
    
    # Write index file
    create_item_atomically(index_path, index_content)
    
    return index_path


def update_index_registry_if_needed(
    index_path: Path | None,
    item_id: str,
    title: str,
    product_root: Path,
    repo_root: Path | None = None
) -> None:
    """
    Update the index registry if an Epic index was created.
    
    Args:
        index_path: Path to the created index file, or None
        item_id: Item ID
        title: Item title
        product_root: Product root directory
        repo_root: Repository root for relative path calculation
    """
    if not index_path:
        return
    
    import datetime
    
    registry_path = product_root / "_meta" / "indexes.md"
    if not registry_path.exists():
        return
    
    # Check if already registered
    try:
        content = registry_path.read_text(encoding="utf-8")
        if item_id in content:
            return  # Already registered
    except Exception:
        return  # Can't read registry
    
    # Calculate relative path for registry
    index_rel = index_path
    if repo_root:
        try:
            index_rel = index_path.relative_to(repo_root)
        except ValueError:
            pass  # Use absolute path if relative calculation fails
    
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Update registry
    try:
        lines = content.splitlines()
        
        # Find or create table header
        header_idx = None
        for idx, line in enumerate(lines):
            if line.strip().startswith("| type |"):
                header_idx = idx
                break
        
        if header_idx is None:
            # Add table if it doesn't exist
            lines.extend([
                "",
                "| type | item_id | index_file | updated | notes |",
                "| ---- | ------- | ---------- | ------- | ----- |"
            ])
        elif header_idx + 1 >= len(lines) or "|" not in lines[header_idx + 1]:
            # Add separator if missing
            lines.insert(header_idx + 1, "| ---- | ------- | ---------- | ------- | ----- |")
        
        # Add new entry
        lines.append(f"| Epic | {item_id} | {index_rel.as_posix()} | {date} | {title} |")
        
        # Write back to registry
        registry_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        
    except Exception:
        # Don't fail item creation if registry update fails
        pass


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
    config_path: str | None = typer.Option(None, "--config", help="Explicit config file path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print item details without creating"),
):
    """Create a new backlog work item."""
    ensure_core_on_path()
    from kano_backlog_core.canonical import CanonicalStore, ItemType
    
    # Import generate_uid from the correct location
    import sys
    from pathlib import Path
    
    # Get the correct path to the scripts directory
    current_file = Path(__file__).resolve()
    # Go up from src/kano_cli/commands/item.py to the skill root, then to scripts
    skill_root = current_file.parents[3]  # Go up 3 levels from src/kano_cli/commands/
    scripts_dir = skill_root / "scripts"
    backlog_lib_dir = scripts_dir / "backlog" / "lib"
    
    if str(backlog_lib_dir) not in sys.path:
        sys.path.insert(0, str(backlog_lib_dir))
    
    from utils import generate_uid
    
    # Input validation with configuration integration
    try:
        validated_type = validate_item_type(item_type)
        validated_title = validate_title(title)
        validated_priority = validate_priority(priority)
        validated_tags = validate_tags(tags)
        
        # Load configuration and validate product context
        config_context = validate_product_context(product, config_path)
        config = config_context["config"]
        context = config_context["context"]
        product_name = config_context["product_name"]
        product_root = context["product_root"]
        
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
    
    # Generate ID using enhanced logic for uniqueness within product scope
    project_config = config.get("project", {})
    prefix = project_config.get("prefix")
    
    if not prefix:
        # Derive prefix from product name if not configured
        prefix = product_name.split("-")[0].upper()[:2]
        if len(prefix) < 2:
            prefix = product_name.upper()[:2]
    
    # Enhanced ID generation with product-scope uniqueness
    item_id, next_number, bucket_str = generate_next_item_id(items_root, prefix, type_code)
    
    # Enhanced file path resolution with proper bucket organization
    item_path = resolve_item_file_path(items_root, type_folder, bucket_str, item_id, validated_title)
    
    # Check for existing item
    if item_path.exists():
        typer.echo(f"❌ Item already exists: {item_path}", err=True)
        raise typer.Exit(1)
    
    if dry_run:
        typer.echo(f"✓ Would create: {item_id}")
        typer.echo(f"  Path: {item_path}")
        typer.echo(f"  Type: {type_label}")
        typer.echo(f"  Title: {validated_title}")
        typer.echo(f"  Priority: {validated_priority}")
        typer.echo(f"  Product: {product_name}")
        typer.echo(f"  Config: {config.get('process', {}).get('profile', 'default')}")
        if validated_parent:
            typer.echo(f"  Parent: {validated_parent}")
        if validated_tags:
            typer.echo(f"  Tags: {', '.join(validated_tags)}")
        return
    
    # Create the item with enhanced template rendering and atomic operations
    try:
        uid = generate_uid()
        
        # Enhanced template rendering for YAML frontmatter and markdown body
        item_content = render_item_template(
            item_id=item_id,
            uid=uid,
            type_label=type_label,
            title=validated_title,
            priority=validated_priority,
            parent=validated_parent,
            area=area,
            iteration=iteration,
            tags=validated_tags,
            owner=owner,
            agent=agent,
            worklog_message="Created from CLI."
        )
        
        # Atomic file creation
        create_item_atomically(item_path, item_content)
        
        typer.echo(f"✓ Created: {item_id}")
        typer.echo(f"  Path: {item_path}")
        typer.echo(f"  Product: {product_name}")
        
        # Create Epic index if needed
        repo_root = Path.cwd().resolve()  # Get repository root
        index_path = create_epic_index_if_needed(
            item_path, item_id, validated_title, type_label, product_root, repo_root
        )
        
        if index_path:
            typer.echo(f"  Index: {index_path}")
            
            # Update index registry
            update_index_registry_if_needed(
                index_path, item_id, validated_title, product_root, repo_root
            )
        
        # Optional: Trigger dashboard refresh if configured
        views_config = config.get("views", {})
        if views_config.get("auto_refresh", True):
            try:
                # This would integrate with existing dashboard refresh mechanisms
                # For now, just log that refresh would happen
                typer.echo(f"  Dashboard refresh: enabled")
            except Exception as e:
                # Don't fail item creation if dashboard refresh fails
                typer.echo(f"  Dashboard refresh failed: {e}", err=True)
        
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
