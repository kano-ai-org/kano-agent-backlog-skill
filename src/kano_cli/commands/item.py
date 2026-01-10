from __future__ import annotations

import datetime
import json
import os
import sys
import errno
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
        FileNotFoundError: If required configuration files are missing
        PermissionError: If configuration files cannot be accessed
    """
    try:
        ensure_config_modules_on_path()
        from config_loader import load_config_with_defaults, validate_config
        from context import get_context, get_product_name
        
        # Resolve product name using the context module's priority chain
        try:
            product_name = get_product_name(product_arg, env_var="KANO_PRODUCT")
        except Exception as e:
            raise typer.BadParameter(f"Product name resolution failed: {e}")
        
        # Get full context (repo_root, platform_root, product_root, etc.)
        try:
            context = get_context(product_arg=product_name)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Product directory not found: {e}")
        except PermissionError as e:
            raise PermissionError(f"Cannot access product directory: {e}")
        except Exception as e:
            raise typer.BadParameter(f"Context resolution failed: {e}")
        
        # Load configuration with defaults
        try:
            config = load_config_with_defaults(
                repo_root=context["repo_root"],
                config_path=config_path,
                product_name=product_name,
            )
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Configuration file not found: {e}")
        except PermissionError as e:
            raise PermissionError(f"Cannot read configuration file: {e}")
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise typer.BadParameter(f"Configuration loading failed: {e}")
        
        # Validate configuration
        try:
            validation_errors = validate_config(config)
            if validation_errors:
                error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in validation_errors)
                raise typer.BadParameter(error_msg)
        except Exception as e:
            raise typer.BadParameter(f"Configuration validation failed: {e}")
        
        # Apply environment variable overrides
        try:
            config = apply_environment_overrides(config)
        except Exception as e:
            raise typer.BadParameter(f"Environment override processing failed: {e}")
        
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
                if not product_root.exists():
                    raise FileNotFoundError(f"Product directory does not exist: {product_root}")
            else:
                raise typer.BadParameter("Product name is required when configuration system is not available")
        except Exception as e:
            raise typer.BadParameter(f"Product resolution failed: {e}")
        
        # Create minimal config
        config = {
            "project": {"name": product_name, "prefix": None},
            "views": {"auto_refresh": True},
            "log": {"verbosity": "info", "debug": False},
            "process": {"profile": "builtin/azure-boards-agile"},
            "index": {"enabled": False, "backend": "sqlite"}
        }
        
        # Apply environment variable overrides
        try:
            config = apply_environment_overrides(config)
        except Exception as e:
            raise typer.BadParameter(f"Environment override processing failed: {e}")
        
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
        
    except typer.BadParameter:
        raise  # Re-raise typer errors as-is
    except FileNotFoundError:
        raise  # Re-raise file not found errors as-is
    except PermissionError:
        raise  # Re-raise permission errors as-is
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
        FileNotFoundError: If product root doesn't exist
        PermissionError: If directories cannot be accessed
    """
    if not product_root.exists():
        raise FileNotFoundError(f"Product directory does not exist: {product_root}")
    
    if not product_root.is_dir():
        raise typer.BadParameter(f"Product path is not a directory: {product_root}")
    
    try:
        # Test if we can access the directory
        list(product_root.iterdir())
    except PermissionError:
        raise PermissionError(f"Cannot access product directory: {product_root}")
    except OSError as e:
        raise typer.BadParameter(f"Cannot access product directory {product_root}: {e}")
    
    required_dirs = ["items", "decisions", "views", "_config", "_meta"]
    missing_dirs = []
    permission_errors = []
    
    for dir_name in required_dirs:
        dir_path = product_root / dir_name
        if not dir_path.exists():
            missing_dirs.append(dir_name)
        else:
            try:
                # Test if we can access the directory
                if dir_path.is_dir():
                    list(dir_path.iterdir())
            except PermissionError:
                permission_errors.append(dir_name)
            except OSError as e:
                raise typer.BadParameter(f"Cannot access directory {dir_path}: {e}")
    
    if permission_errors:
        error_dirs = ", ".join(permission_errors)
        raise PermissionError(f"Cannot access required directories: {error_dirs}")
    
    if missing_dirs:
        missing_str = ", ".join(missing_dirs)
        raise typer.BadParameter(
            f"Product directory structure is incomplete. Missing directories: {missing_str}. "
            f"Product root: {product_root}"
        )
    
    # Validate that items directory has the expected type subdirectories
    items_dir = product_root / "items"
    expected_item_types = ["epic", "feature", "userstory", "task", "bug"]
    
    try:
        for item_type in expected_item_types:
            type_dir = items_dir / f"{item_type}s"  # pluralized
            if not type_dir.exists():
                # Create missing item type directories
                type_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise PermissionError(f"Cannot create item type directories in: {items_dir}")
    except OSError as e:
        raise typer.BadParameter(f"Cannot create item type directories: {e}")


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
        typer.BadParameter: If file creation fails with descriptive error message
    """
    import tempfile
    import shutil
    import errno
    
    try:
        # Ensure parent directory exists
        item_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise typer.BadParameter(f"Permission denied: Cannot create directory {item_path.parent}")
    except OSError as e:
        if e.errno == errno.ENOSPC:
            raise typer.BadParameter("Disk full: Cannot create directory")
        elif e.errno == errno.ENAMETOOLONG:
            raise typer.BadParameter(f"Path too long: {item_path.parent}")
        else:
            raise typer.BadParameter(f"Cannot create directory {item_path.parent}: {e}")
    
    # Write to temporary file first, then move to final location
    # This ensures atomic operation - either complete success or no file
    temp_dir = item_path.parent
    temp_path = None
    
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', 
            encoding='utf-8', 
            dir=temp_dir, 
            delete=False,
            suffix='.tmp'
        ) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)
    except PermissionError:
        raise typer.BadParameter(f"Permission denied: Cannot write to {temp_dir}")
    except OSError as e:
        if e.errno == errno.ENOSPC:
            raise typer.BadParameter("Disk full: Cannot write file")
        elif e.errno == errno.ENAMETOOLONG:
            raise typer.BadParameter(f"Filename too long: {item_path.name}")
        else:
            raise typer.BadParameter(f"Cannot write file: {e}")
    
    try:
        # Atomic move from temp to final location
        shutil.move(str(temp_path), str(item_path))
    except PermissionError:
        # Clean up temp file
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise typer.BadParameter(f"Permission denied: Cannot create file {item_path}")
    except OSError as e:
        # Clean up temp file
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        
        if e.errno == errno.ENOSPC:
            raise typer.BadParameter("Disk full: Cannot create file")
        elif e.errno == errno.EEXIST:
            raise typer.BadParameter(f"File already exists: {item_path}")
        else:
            raise typer.BadParameter(f"Cannot create file {item_path}: {e}")
    except Exception as e:
        # Clean up temp file for any other error
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise typer.BadParameter(f"Unexpected error creating file {item_path}: {e}")


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


def refresh_parent_index_if_needed(
    items_root: Path,
    product_root: Path,
    parent_id: str | None,
    agent: str
) -> None:
    """
    Refresh parent index if a parent is specified and has an index file.
    
    Enhanced integration for hierarchical items:
    - Validates parent item existence before attempting refresh
    - Uses proper error handling and logging
    - Integrates with existing index generation tools
    - Handles both Epic and non-Epic parent types gracefully
    
    Args:
        items_root: Root directory for items
        product_root: Product root directory
        parent_id: Parent item ID, or None
        agent: Agent name for audit trail
    """
    if not parent_id or parent_id == "null":
        return
    
    try:
        # Try to find the parent item and its potential index file
        from ..util import find_item_path_by_id
        parent_path = find_item_path_by_id(items_root, parent_id)
        parent_index_path = parent_path.with_suffix(".index.md")
        
        if parent_index_path.exists():
            # Call the workitem_generate_index.py script to refresh the parent index
            import subprocess
            import sys
            
            # Find the script path
            current_file = Path(__file__).resolve()
            skill_root = current_file.parents[3]  # Go up from src/kano_cli/commands/
            index_script = skill_root / "scripts" / "backlog" / "workitem_generate_index.py"
            
            if index_script.exists():
                cmd = [
                    sys.executable, str(index_script),
                    "--root-id", parent_id,
                    "--items-root", str(items_root),
                    "--backlog-root", str(product_root),
                    "--agent", agent
                ]
                
                # Run with timeout and proper error handling
                result = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
                
                if result.returncode == 0:
                    typer.echo(f"  Parent index refresh: updated {parent_id}")
                else:
                    # Log warning but don't fail item creation
                    error_msg = result.stderr.strip() if result.stderr else "unknown error"
                    typer.echo(f"  Parent index refresh: warning - {error_msg}", err=True)
            else:
                typer.echo(f"  Parent index refresh: script not found")
        else:
            # Parent exists but has no index file - this is normal for non-Epic items
            typer.echo(f"  Parent index refresh: {parent_id} has no index file (normal for non-Epic items)")
    
    except subprocess.TimeoutExpired:
        typer.echo(f"  Parent index refresh: timed out for {parent_id}", err=True)
    except SystemExit:
        # Parent item doesn't exist - this should have been caught in validation
        typer.echo(f"  Parent index refresh: parent {parent_id} not found", err=True)
    except Exception as e:
        # Don't fail item creation if parent index refresh fails
        typer.echo(f"  Parent index refresh: error for {parent_id} - {e}", err=True)


def refresh_dashboards_if_needed(
    product_root: Path,
    agent: str,
    config_path: str | None,
    no_refresh: bool,
    config: Dict[str, Any]
) -> None:
    """
    Refresh dashboards if auto-refresh is enabled and not disabled by user.
    
    Enhanced integration with existing dashboard refresh mechanisms:
    - Respects configuration-based refresh settings
    - Passes appropriate parameters based on configuration
    - Supports both product-specific and platform-wide refresh
    - Handles optional features gracefully
    
    Args:
        product_root: Product root directory
        agent: Agent name for audit trail
        config_path: Configuration file path
        no_refresh: Whether user disabled refresh
        config: Configuration dictionary
    """
    if no_refresh:
        return
    
    views_config = config.get("views", {})
    if not views_config.get("auto_refresh", True):
        return
    
    try:
        import subprocess
        import sys
        
        # Find the dashboard refresh script
        current_file = Path(__file__).resolve()
        skill_root = current_file.parents[3]  # Go up from src/kano_cli/commands/
        refresh_script = skill_root / "scripts" / "backlog" / "view_refresh_dashboards.py"
        
        if not refresh_script.exists():
            typer.echo(f"  Dashboard refresh: script not found at {refresh_script}")
            return
        
        # Build command with enhanced configuration-based parameters
        cmd = [
            sys.executable, str(refresh_script),
            "--backlog-root", str(product_root),
            "--agent", agent
        ]
        
        # Add configuration file if specified
        if config_path:
            cmd.extend(["--config", config_path])
        
        # Add configuration-based parameters
        
        # Data source preference (auto, files, sqlite)
        source = views_config.get("source", "auto")
        if source in ["auto", "files", "sqlite"]:
            cmd.extend(["--source", source])
        
        # Index refresh behavior (auto, skip, rebuild, incremental)
        refresh_index = views_config.get("refresh_index", "auto")
        if refresh_index in ["auto", "skip", "rebuild", "incremental"]:
            cmd.extend(["--refresh-index", refresh_index])
        
        # Multi-product aggregation support
        if views_config.get("all_products", False):
            cmd.append("--all-products")
        elif "products" in views_config and views_config["products"]:
            # Support comma-separated product list
            products = views_config["products"]
            if isinstance(products, str):
                cmd.extend(["--products", products])
            elif isinstance(products, list):
                cmd.extend(["--products", ",".join(products)])
        
        # Persona-aware dashboard generation
        if views_config.get("all_personas", False):
            cmd.append("--all-personas")
        
        # Execute dashboard refresh with enhanced error handling
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=300)
        
        if result.returncode == 0:
            typer.echo(f"  Dashboard refresh: completed")
            
            # Show additional information if available in stdout
            if result.stdout and result.stdout.strip():
                # Look for summary information in the output
                lines = result.stdout.strip().split('\n')
                summary_lines = [line for line in lines if 'generated' in line.lower() or 'refreshed' in line.lower()]
                if summary_lines:
                    # Show the last summary line
                    typer.echo(f"    {summary_lines[-1]}")
        else:
            error_msg = result.stderr.strip() if result.stderr else "unknown error"
            typer.echo(f"  Dashboard refresh: failed ({error_msg})", err=True)
            
            # Show stdout if it contains useful information
            if result.stdout and result.stdout.strip():
                typer.echo(f"    Output: {result.stdout.strip()}", err=True)
    
    except subprocess.TimeoutExpired:
        typer.echo(f"  Dashboard refresh: timed out (>300s)", err=True)
    except FileNotFoundError:
        typer.echo(f"  Dashboard refresh: Python interpreter not found", err=True)
    except Exception as e:
        # Don't fail item creation if dashboard refresh fails
        typer.echo(f"  Dashboard refresh: error ({e})", err=True)


def should_create_index(
    type_label: str,
    create_index: bool,
    no_index: bool
) -> bool:
    """
    Determine whether to create an Epic index file based on type and user options.
    
    Args:
        type_label: Item type label (e.g., "Epic", "Task")
        create_index: User explicitly requested index creation
        no_index: User explicitly disabled index creation
        
    Returns:
        True if index should be created, False otherwise
    """
    if type_label != "Epic":
        return False
    
    if no_index:
        return False
    
    if create_index:
        return True
    
    # Default behavior: create index for Epic items
    return True


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
    
    # Update registry with enhanced error handling
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
        
        # Add new entry with proper escaping
        escaped_title = title.replace("|", "\\|").replace("\n", " ").replace("\r", " ")
        lines.append(f"| Epic | {item_id} | {index_rel.as_posix()} | {date} | {escaped_title} |")
        
        # Write back to registry atomically
        registry_content = "\n".join(lines) + "\n"
        
        # Use atomic write for registry update
        import tempfile
        import shutil
        
        temp_dir = registry_path.parent
        with tempfile.NamedTemporaryFile(
            mode='w', 
            encoding='utf-8', 
            dir=temp_dir, 
            delete=False,
            suffix='.tmp'
        ) as temp_file:
            temp_file.write(registry_content)
            temp_path = Path(temp_file.name)
        
        try:
            shutil.move(str(temp_path), str(registry_path))
        except Exception:
            # Clean up temp file if move fails
            try:
                temp_path.unlink()
            except Exception:
                pass
            raise
        
    except Exception:
        # Don't fail item creation if registry update fails
        pass
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


def create_item_with_audit(
    item_type: str,
    title: str,
    parent: str | None,
    priority: str,
    area: str,
    iteration: str | None,
    tags: str,
    owner: str | None,
    agent: str,
    product: str | None,
    config_path: str | None,
    create_index: bool,
    no_index: bool,
    no_refresh: bool,
    dry_run: bool,
) -> int:
    """Core item creation logic wrapped for audit logging."""
    
    # Initialize variables for cleanup
    item_path = None
    index_path = None
    
    try:
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
        
    except ImportError as e:
        typer.echo(f"❌ System error: Required modules not available: {e}", err=True)
        typer.echo("Please ensure the kano-agent-backlog-skill is properly installed.", err=True)
        return 2
    except Exception as e:
        typer.echo(f"❌ System error: Failed to initialize: {e}", err=True)
        return 2
    
    # Input validation with enhanced error handling
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
        return 1
    except FileNotFoundError as e:
        typer.echo(f"❌ Configuration error: Required file not found: {e}", err=True)
        typer.echo("Please ensure the product directory structure is properly initialized.", err=True)
        return 1
    except PermissionError as e:
        typer.echo(f"❌ Permission error: Cannot access configuration: {e}", err=True)
        typer.echo("Please check file permissions for the product directory.", err=True)
        return 1
    except Exception as e:
        typer.echo(f"❌ Configuration error: {e}", err=True)
        return 1
    
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
    try:
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
        
    except Exception as e:
        typer.echo(f"❌ ID generation error: {e}", err=True)
        return 1
    
    # Check for existing item
    if item_path.exists():
        typer.echo(f"❌ Item already exists: {item_path}", err=True)
        return 1
    
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
        
        # Show index creation status
        should_create_epic_index = should_create_index(type_label, create_index, no_index)
        if should_create_epic_index:
            index_path = item_path.with_suffix(".index.md")
            typer.echo(f"  Would create index: {index_path}")
        
        # Show refresh status
        if not no_refresh and config.get("views", {}).get("auto_refresh", True):
            typer.echo(f"  Would refresh dashboards: yes")
        else:
            typer.echo(f"  Would refresh dashboards: no")
        
        return 0
    
    # Create the item with enhanced error handling and rollback capability
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
        
        # Atomic file creation with comprehensive error handling
        create_item_atomically(item_path, item_content)
        
        typer.echo(f"✓ Created: {item_id}")
        typer.echo(f"  Path: {item_path}")
        typer.echo(f"  Product: {product_name}")
        
        # Create Epic index if needed with enhanced option handling
        repo_root = Path.cwd().resolve()  # Get repository root
        
        should_create_epic_index = should_create_index(type_label, create_index, no_index)
        
        if should_create_epic_index:
            try:
                index_path = create_epic_index_if_needed(
                    item_path, item_id, validated_title, type_label, product_root, repo_root
                )
                
                if index_path:
                    typer.echo(f"  Index: {index_path}")
                    
                    # Update index registry with enhanced error handling
                    try:
                        update_index_registry_if_needed(
                            index_path, item_id, validated_title, product_root, repo_root
                        )
                    except Exception as e:
                        # Don't fail item creation if registry update fails
                        typer.echo(f"  Warning: Index registry update failed: {e}", err=True)
            except Exception as e:
                # Don't fail item creation if index creation fails
                typer.echo(f"  Warning: Index creation failed: {e}", err=True)
        
        # Refresh parent index if needed
        try:
            refresh_parent_index_if_needed(
                items_root, product_root, validated_parent, agent
            )
        except Exception as e:
            # Don't fail item creation if parent index refresh fails
            typer.echo(f"  Warning: Parent index refresh failed: {e}", err=True)
        
        # Enhanced dashboard refresh with proper integration
        try:
            refresh_dashboards_if_needed(
                product_root, agent, config_path, no_refresh, config
            )
        except Exception as e:
            # Don't fail item creation if dashboard refresh fails
            typer.echo(f"  Warning: Dashboard refresh failed: {e}", err=True)
        
        return 0
        
    except typer.BadParameter as e:
        # Clean up any partial creation
        cleanup_partial_creation(item_path, index_path)
        typer.echo(f"❌ {e}", err=True)
        return 1
    except PermissionError as e:
        cleanup_partial_creation(item_path, index_path)
        typer.echo(f"❌ Permission denied: {e}", err=True)
        typer.echo("Please check file permissions for the target directory.", err=True)
        return 1
    except OSError as e:
        cleanup_partial_creation(item_path, index_path)
        import errno
        if e.errno == errno.ENOSPC:
            typer.echo("❌ Disk full: Cannot create item file", err=True)
        elif e.errno == errno.ENAMETOOLONG:
            typer.echo("❌ Path too long: Cannot create item file", err=True)
        else:
            typer.echo(f"❌ File system error: {e}", err=True)
        return 1
    except Exception as e:
        cleanup_partial_creation(item_path, index_path)
        typer.echo(f"❌ Unexpected error creating item: {e}", err=True)
        return 1


def ensure_audit_modules_on_path() -> None:
    """Ensure audit logging modules are available."""
    current_file = Path(__file__).resolve()
    skill_root = current_file.parents[3]  # Go up from src/kano_cli/commands/
    logging_dir = skill_root / "scripts" / "logging"
    
    if str(logging_dir) not in sys.path:
        sys.path.insert(0, str(logging_dir))


def cleanup_partial_creation(item_path: Path | None, index_path: Path | None) -> None:
    """
    Clean up any partially created files in case of failure.
    
    Args:
        item_path: Path to the main item file that might have been created
        index_path: Path to the index file that might have been created
    """
    if item_path and item_path.exists():
        try:
            item_path.unlink()
        except Exception:
            pass  # Ignore cleanup errors
    
    if index_path and index_path.exists():
        try:
            index_path.unlink()
        except Exception:
            pass  # Ignore cleanup errors


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


@app.command(name="create-v2")
def create_v2(
    item_type: str = typer.Option(..., "--type", help="epic|feature|userstory|task|bug"),
    title: str = typer.Option(..., "--title", help="Work item title"),
    parent: str | None = typer.Option(None, "--parent", help="Parent item ID (optional)"),
    priority: str = typer.Option("P2", "--priority", help="Priority (P0-P4, default: P2)"),
    area: str = typer.Option("general", "--area", help="Area tag"),
    iteration: str | None = typer.Option(None, "--iteration", help="Iteration name"),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags"),
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Create a new backlog work item (ops layer implementation)."""
    try:
        import sys
        from pathlib import Path
        
        # Setup path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from kano_backlog_ops.workitem import create_item as ops_create_item
        from kano_backlog_core.models import ItemType
        
        # Map CLI type to ItemType enum
        type_map = {
            "epic": ItemType.EPIC,
            "feature": ItemType.FEATURE,
            "userstory": ItemType.USER_STORY,
            "task": ItemType.TASK,
            "bug": ItemType.BUG,
        }
        
        item_type_lower = item_type.lower()
        if item_type_lower not in type_map:
            typer.echo(f"❌ Invalid item type: {item_type}", err=True)
            raise typer.Exit(1)
        
        item_type_enum = type_map[item_type_lower]
        
        # Parse tags
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        
        # Call ops layer
        result = ops_create_item(
            item_type=item_type_enum,
            title=title,
            product=product or "demo",
            agent=agent,
            parent=parent,
            priority=priority,
            area=area,
            iteration=iteration,
            tags=tag_list,
        )
        
        # Output result
        if output_format == "json":
            import json as json_lib
            output = {
                "id": result.id,
                "uid": result.uid,
                "path": str(result.path),
                "type": result.type.value,
            }
            typer.echo(json_lib.dumps(output, ensure_ascii=False))
        else:
            typer.echo(f"✓ Created: {result.id}")
            typer.echo(f"  Path: {result.path.name}")
            typer.echo(f"  Type: {result.type.value}")
            
    except FileNotFoundError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise typer.Exit(2)


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
    create_index: bool = typer.Option(False, "--create-index", help="Force Epic index file creation"),
    no_index: bool = typer.Option(False, "--no-index", help="Skip Epic index file creation"),
    no_refresh: bool = typer.Option(False, "--no-refresh", help="Skip dashboard refresh"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print item details without creating"),
):
    """Create a new backlog work item."""
    
    # Try to use audit logging if available
    audit_available = False
    try:
        ensure_audit_modules_on_path()
        from audit_runner import run_with_audit
        audit_available = True
    except ImportError:
        pass
    except Exception:
        pass
    
    if audit_available:
        # Create a wrapper function that captures the CLI arguments
        def main_with_args() -> int:
            exit_code = create_item_with_audit(
                item_type=item_type,
                title=title,
                parent=parent,
                priority=priority,
                area=area,
                iteration=iteration,
                tags=tags,
                owner=owner,
                agent=agent,
                product=product,
                config_path=config_path,
                create_index=create_index,
                no_index=no_index,
                no_refresh=no_refresh,
                dry_run=dry_run,
            )
            # Raise SystemExit for audit_runner compatibility
            if exit_code != 0:
                raise SystemExit(exit_code)
            return exit_code
        
        # Run with audit logging
        try:
            # Create the command arguments that should be logged
            cli_argv = [
                "kano", "item", "create",
                "--type", item_type,
                "--title", title,
                "--priority", priority,
                "--agent", agent,
                "--product", product or "auto-detected"
            ]
            
            # Add optional arguments
            if parent:
                cli_argv.extend(["--parent", parent])
            if area != "general":
                cli_argv.extend(["--area", area])
            if iteration:
                cli_argv.extend(["--iteration", iteration])
            if tags:
                cli_argv.extend(["--tags", tags])
            if owner:
                cli_argv.extend(["--owner", owner])
            if config_path:
                cli_argv.extend(["--config", config_path])
            if create_index:
                cli_argv.append("--create-index")
            if no_index:
                cli_argv.append("--no-index")
            if no_refresh:
                cli_argv.append("--no-refresh")
            if dry_run:
                cli_argv.append("--dry-run")
            
            exit_code = run_with_audit(
                main_fn=main_with_args,
                argv=cli_argv,
                tool=f"kano-cli-item-create",
                cwd=str(Path.cwd())
            )
            
            # Exit with the returned code
            if exit_code != 0:
                raise typer.Exit(exit_code)
                
        except SystemExit as e:
            # Re-raise SystemExit from the main function
            raise typer.Exit(e.code if isinstance(e.code, int) else 1)
        except Exception as e:
            typer.echo(f"❌ Audit system error: {e}", err=True)
            # Fall through to direct execution
            audit_available = False
    
    # Direct execution without audit logging (fallback)
    if not audit_available:
        exit_code = create_item_with_audit(
            item_type=item_type,
            title=title,
            parent=parent,
            priority=priority,
            area=area,
            iteration=iteration,
            tags=tags,
            owner=owner,
            agent=agent,
            product=product,
            config_path=config_path,
            create_index=create_index,
            no_index=no_index,
            no_refresh=no_refresh,
            dry_run=dry_run,
        )
        
        if exit_code != 0:
            raise typer.Exit(exit_code)


@app.command(name="update-state")
def update_state_command(
    item_ref: str = typer.Argument(..., help="Item ID, UID, or path"),
    state: str = typer.Option(..., "--state", help="Target state (New|Proposed|Ready|InProgress|Review|Done|Blocked|Dropped)"),
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    message: str = typer.Option("", "--message", help="Worklog message"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    sync_parent: bool = typer.Option(True, "--sync-parent/--no-sync-parent", help="Sync parent state forward"),
    refresh_dashboards: bool = typer.Option(True, "--refresh/--no-refresh", help="Refresh dashboards after update"),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """
    Update work item state.
    
    Transitions the item to the specified state, appends a worklog entry,
    optionally syncs parent state, and refreshes dashboards.
    
    Examples:
        kano item update-state KABSD-TSK-0001 --state InProgress --agent copilot
        kano item update-state KABSD-TSK-0001 --state Done --agent copilot --message "All tests passing"
    """
    try:
        # Import ops layer
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # Add src/ to path
        from kano_backlog_ops.workitem import update_state as ops_update_state
        from kano_backlog_core.models import ItemState
        
        # Parse state
        try:
            item_state = ItemState(state.upper() if state.lower() == "new" else state.title())
        except ValueError:
            typer.echo(f"❌ Invalid state: {state}", err=True)
            typer.echo("Valid states: New, Proposed, Ready, InProgress, Review, Done, Blocked, Dropped", err=True)
            raise typer.Exit(1)
        
        # Call ops layer
        result = ops_update_state(
            item_ref=item_ref,
            new_state=item_state,
            agent=agent,
            message=message or None,
            product=product,
            sync_parent=sync_parent,
            refresh_dashboards=refresh_dashboards,
        )
        
        # Output result
        if output_format == "json":
            import json as json_lib
            output = {
                "id": result.id,
                "old_state": result.old_state.value,
                "new_state": result.new_state.value,
                "worklog_appended": result.worklog_appended,
                "parent_synced": result.parent_synced,
                "dashboards_refreshed": result.dashboards_refreshed,
            }
            typer.echo(json_lib.dumps(output, ensure_ascii=False))
        else:
            typer.echo(f"✓ Updated {result.id}: {result.old_state.value} → {result.new_state.value}")
            if result.worklog_appended:
                typer.echo(f"  Worklog: {message}")
            if result.parent_synced:
                typer.echo("  Parent state synced")
            if result.dashboards_refreshed:
                typer.echo("  Dashboards refreshed")
                
    except RuntimeError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(2)
