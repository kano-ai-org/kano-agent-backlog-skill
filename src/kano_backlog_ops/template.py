"""
Template operations for topic creation.

This module provides use-case functions for managing and using topic templates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from kano_backlog_core.errors import BacklogError
from kano_backlog_core.template import (
    TopicTemplate,
    TemplateEngine,
    TemplateValidator,
    TemplateValidationError,
    get_builtin_template_dir,
    get_custom_template_dir,
)


class TemplateError(BacklogError):
    """Base error for template operations."""
    
    def __init__(self, message: str, suggestion: Optional[str] = None):
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class TemplateNotFoundError(TemplateError):
    """Template not found."""
    
    def __init__(self, template_name: str):
        self.template_name = template_name
        super().__init__(
            f"Template not found: {template_name}",
            suggestion="Use 'kano topic template list' to see available templates"
        )


class TemplateValidationError(TemplateError):
    """Template validation failed."""
    
    def __init__(self, errors: List[str]):
        self.errors = errors
        error_list = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"Template validation failed:\n{error_list}")


@dataclass
class TemplateListResult:
    """Result of listing templates."""
    
    templates: List[TopicTemplate]
    builtin_count: int
    custom_count: int


@dataclass
class TemplateLoadResult:
    """Result of loading a template."""
    
    template: TopicTemplate
    source_path: Path
    is_builtin: bool


class TemplateLoader:
    """Template loading and resolution."""
    
    def __init__(self, backlog_root: Optional[Path] = None, product: Optional[str] = None):
        self.backlog_root = backlog_root
        self.product = product
        self._template_cache: Dict[str, TemplateLoadResult] = {}
    
    def _find_backlog_root(self) -> Path:
        """Find backlog root directory."""
        if self.backlog_root:
            return self.backlog_root
        
        current = Path.cwd().resolve()
        while current != current.parent:
            backlog_check = current / "_kano" / "backlog"
            if backlog_check.exists():
                return backlog_check
            current = current.parent
        
        raise TemplateError(
            "Cannot find backlog root (_kano/backlog)",
            suggestion="Ensure you are in a directory with a _kano/backlog structure"
        )
    
    def get_template_search_paths(self) -> List[Path]:
        """Get template search paths in priority order."""
        paths = []
        
        # Custom templates (higher priority)
        try:
            backlog_root = self._find_backlog_root()
            custom_dir = get_custom_template_dir(backlog_root, self.product)
            if custom_dir.exists():
                paths.append(custom_dir)
        except TemplateError:
            pass  # No backlog root, skip custom templates
        
        # Built-in templates (lower priority)
        builtin_dir = get_builtin_template_dir()
        if builtin_dir.exists():
            paths.append(builtin_dir)
        
        return paths
    
    def find_template(self, name: str) -> Optional[TemplateLoadResult]:
        """Find template by name in search paths."""
        if name in self._template_cache:
            return self._template_cache[name]
        
        for search_path in self.get_template_search_paths():
            template_dir = search_path / name
            template_file = template_dir / "template.json"
            
            if template_file.exists():
                try:
                    with open(template_file, "r", encoding="utf-8") as f:
                        template_data = json.load(f)
                    
                    template = TopicTemplate.from_dict(template_data)
                    is_builtin = search_path == get_builtin_template_dir()
                    
                    result = TemplateLoadResult(
                        template=template,
                        source_path=template_dir,
                        is_builtin=is_builtin,
                    )
                    
                    self._template_cache[name] = result
                    return result
                    
                except Exception as e:
                    # Skip invalid templates
                    continue
        
        return None
    
    def load_template(self, name: str) -> TemplateLoadResult:
        """Load template by name."""
        result = self.find_template(name)
        if result is None:
            raise TemplateNotFoundError(name)
        return result
    
    def list_templates(self) -> TemplateListResult:
        """List all available templates."""
        templates = []
        builtin_count = 0
        custom_count = 0
        seen_names = set()
        
        for search_path in self.get_template_search_paths():
            if not search_path.exists():
                continue
            
            is_builtin = search_path == get_builtin_template_dir()
            
            for template_dir in search_path.iterdir():
                if not template_dir.is_dir():
                    continue
                
                template_file = template_dir / "template.json"
                if not template_file.exists():
                    continue
                
                try:
                    with open(template_file, "r", encoding="utf-8") as f:
                        template_data = json.load(f)
                    
                    template = TopicTemplate.from_dict(template_data)
                    
                    # Skip duplicates (custom overrides builtin)
                    if template.name in seen_names:
                        continue
                    
                    seen_names.add(template.name)
                    templates.append(template)
                    
                    if is_builtin:
                        builtin_count += 1
                    else:
                        custom_count += 1
                        
                except Exception:
                    # Skip invalid templates
                    continue
        
        # Sort by name for consistent output
        templates.sort(key=lambda t: t.name)
        
        return TemplateListResult(
            templates=templates,
            builtin_count=builtin_count,
            custom_count=custom_count,
        )
    
    def validate_template(self, name: str) -> List[TemplateValidationError]:
        """Validate a template."""
        result = self.find_template(name)
        if result is None:
            return [TemplateValidationError("", f"Template not found: {name}")]
        
        return TemplateValidator.validate_template(result.template, result.source_path)


def create_topic_from_template(
    topic_name: str,
    template_name: str,
    *,
    agent: str,
    variables: Optional[Dict[str, Any]] = None,
    backlog_root: Optional[Path] = None,
    product: Optional[str] = None,
) -> "TopicCreateResult":
    """Create a topic from a template."""
    # Import here to avoid circular imports
    from kano_backlog_ops.topic import (
        TopicCreateResult,
        TopicManifest,
        validate_topic_name,
        TopicValidationError as TopicValidationError,
        TopicExistsError,
        _normalize_topic_name,
        get_topic_path,
        ensure_topic_dirs,
        _find_backlog_root,
    )
    
    # Validate topic name
    validation_errors = validate_topic_name(topic_name)
    if validation_errors:
        raise TopicValidationError(validation_errors)
    
    # Load template
    loader = TemplateLoader(backlog_root, product)
    template_result = loader.load_template(template_name)
    template = template_result.template
    
    # Prepare variables
    if variables is None:
        variables = {}
    
    # Add built-in variables
    now = datetime.now(timezone.utc)
    builtin_vars = {
        "topic_name": topic_name,
        "created_date": now.strftime("%Y-%m-%d"),
        "created_datetime": now.isoformat().replace("+00:00", "Z"),
        "agent": agent,
    }
    
    # Merge with defaults and user variables
    final_variables = {}
    final_variables.update(template.get_default_variables())
    final_variables.update(builtin_vars)
    final_variables.update(variables)
    
    # Validate variables
    var_errors = template.validate_variables(final_variables)
    if var_errors:
        raise TemplateValidationError(var_errors)
    
    # Resolve paths
    if backlog_root is None:
        backlog_root = _find_backlog_root()
    
    canonical_name = _normalize_topic_name(topic_name)
    topic_path = get_topic_path(canonical_name, backlog_root)
    
    # Check if topic already exists
    if topic_path.exists():
        raise TopicExistsError(canonical_name)
    
    # Ensure topic directories exist
    ensure_topic_dirs(backlog_root)
    
    # Create topic directory
    topic_path.mkdir(parents=True, exist_ok=True)
    
    # Create directory structure
    for directory in template.structure.directories:
        dir_path = topic_path / directory
        dir_path.mkdir(parents=True, exist_ok=True)
    
    # Create files from templates
    for target_path, template_file_path in template.structure.files.items():
        source_file = template_result.source_path / template_file_path
        target_file = topic_path / target_path
        
        # Ensure parent directory exists
        target_file.parent.mkdir(parents=True, exist_ok=True)
        
        if source_file.exists():
            # Read template content and substitute variables
            template_content = source_file.read_text(encoding="utf-8")
            final_content = TemplateEngine.substitute(template_content, final_variables)
            target_file.write_text(final_content, encoding="utf-8")
        else:
            # Create empty file if template doesn't exist
            target_file.touch()
    
    # Create manifest with template defaults
    manifest_data = {
        "topic": canonical_name,
        "agent": agent,
        "seed_items": [],
        "pinned_docs": [],
        "snippet_refs": [],
        "status": "open",
        "closed_at": None,
        "created_at": builtin_vars["created_datetime"],
        "updated_at": builtin_vars["created_datetime"],
        "has_spec": False,
    }
    
    # Apply template defaults
    manifest_data.update(template.manifest_defaults)
    
    manifest = TopicManifest.from_dict(manifest_data)
    
    # Save manifest
    manifest_path = topic_path / "manifest.json"
    manifest.save(manifest_path)
    
    return TopicCreateResult(
        topic_path=topic_path,
        manifest=manifest,
    )


def get_available_templates(
    backlog_root: Optional[Path] = None,
    product: Optional[str] = None,
) -> TemplateListResult:
    """Get list of available templates."""
    loader = TemplateLoader(backlog_root, product)
    return loader.list_templates()


def get_template_info(
    template_name: str,
    *,
    backlog_root: Optional[Path] = None,
    product: Optional[str] = None,
) -> TemplateLoadResult:
    """Get information about a specific template."""
    loader = TemplateLoader(backlog_root, product)
    return loader.load_template(template_name)


def validate_template_by_name(
    template_name: str,
    *,
    backlog_root: Optional[Path] = None,
    product: Optional[str] = None,
) -> List[TemplateValidationError]:
    """Validate a template by name."""
    loader = TemplateLoader(backlog_root, product)
    return loader.validate_template(template_name)