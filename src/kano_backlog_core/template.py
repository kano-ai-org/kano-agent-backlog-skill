"""
Template system for topic creation.

This module provides data models and utilities for topic templates,
enabling standardized topic creation with predefined structures and content.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class TemplateVariable:
    """Template variable definition."""
    
    name: str
    type: str = "string"  # string, boolean, integer, choice
    description: str = ""
    required: bool = False
    default: Optional[Union[str, int, bool]] = None
    choices: Optional[List[str]] = None  # For choice type
    
    def validate_value(self, value: Any) -> bool:
        """Validate a value against this variable definition."""
        if self.required and (value is None or value == ""):
            return False
            
        if value is None:
            return True
            
        if self.type == "string":
            return isinstance(value, str)
        elif self.type == "boolean":
            return isinstance(value, bool)
        elif self.type == "integer":
            return isinstance(value, int)
        elif self.type == "choice":
            return self.choices is not None and str(value) in self.choices
            
        return False


@dataclass
class TemplateStructure:
    """Template directory and file structure definition."""
    
    directories: List[str] = field(default_factory=list)
    files: Dict[str, str] = field(default_factory=dict)  # target_path -> template_path


@dataclass
class TopicTemplate:
    """Topic template definition."""
    
    name: str
    display_name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    created_at: str = ""
    tags: List[str] = field(default_factory=list)
    structure: TemplateStructure = field(default_factory=TemplateStructure)
    manifest_defaults: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, TemplateVariable] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TopicTemplate":
        """Create template from dictionary."""
        # Parse variables
        variables = {}
        for var_name, var_data in data.get("variables", {}).items():
            if isinstance(var_data, dict):
                variables[var_name] = TemplateVariable(
                    name=var_name,
                    type=var_data.get("type", "string"),
                    description=var_data.get("description", ""),
                    required=var_data.get("required", False),
                    default=var_data.get("default"),
                    choices=var_data.get("choices"),
                )
            else:
                # Simple string default
                variables[var_name] = TemplateVariable(
                    name=var_name,
                    default=str(var_data),
                )
        
        # Parse structure
        structure_data = data.get("structure", {})
        structure = TemplateStructure(
            directories=structure_data.get("directories", []),
            files=structure_data.get("files", {}),
        )
        
        return cls(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            created_at=data.get("created_at", ""),
            tags=data.get("tags", []),
            structure=structure,
            manifest_defaults=data.get("manifest_defaults", {}),
            variables=variables,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "created_at": self.created_at,
            "tags": self.tags,
            "structure": {
                "directories": self.structure.directories,
                "files": self.structure.files,
            },
            "manifest_defaults": self.manifest_defaults,
            "variables": {
                name: {
                    "type": var.type,
                    "description": var.description,
                    "required": var.required,
                    "default": var.default,
                    "choices": var.choices,
                }
                for name, var in self.variables.items()
            },
        }
    
    def validate_variables(self, values: Dict[str, Any]) -> List[str]:
        """Validate variable values against template definition."""
        errors = []
        
        # Check required variables
        for name, var in self.variables.items():
            value = values.get(name)
            if not var.validate_value(value):
                if var.required:
                    errors.append(f"Required variable '{name}' is missing or invalid")
                else:
                    errors.append(f"Variable '{name}' has invalid value: {value}")
        
        return errors
    
    def get_default_variables(self) -> Dict[str, Any]:
        """Get default values for all variables."""
        defaults = {}
        for name, var in self.variables.items():
            if var.default is not None:
                defaults[name] = var.default
        return defaults


class TemplateEngine:
    """Simple template engine for variable substitution."""
    
    # Simple variable pattern: {{variable_name}}
    VARIABLE_PATTERN = re.compile(r'\{\{(\w+)\}\}')
    
    @classmethod
    def substitute(cls, content: str, variables: Dict[str, Any]) -> str:
        """Substitute variables in template content."""
        def replace_var(match):
            var_name = match.group(1)
            value = variables.get(var_name, f"{{{{ {var_name} }}}}")  # Keep unresolved
            return str(value)
        
        return cls.VARIABLE_PATTERN.sub(replace_var, content)
    
    @classmethod
    def extract_variables(cls, content: str) -> List[str]:
        """Extract variable names from template content."""
        return cls.VARIABLE_PATTERN.findall(content)


@dataclass
class TemplateValidationError:
    """Template validation error."""
    
    path: str
    message: str
    line: Optional[int] = None


class TemplateValidator:
    """Template validation utilities."""
    
    @classmethod
    def validate_template(cls, template: TopicTemplate, template_dir: Path) -> List[TemplateValidationError]:
        """Validate a template definition and its files."""
        errors = []
        
        # Validate basic fields
        if not template.name:
            errors.append(TemplateValidationError("template.json", "Template name is required"))
        
        if not template.display_name:
            errors.append(TemplateValidationError("template.json", "Display name is required"))
        
        # Validate template files exist
        for target_path, template_path in template.structure.files.items():
            full_template_path = template_dir / template_path
            if not full_template_path.exists():
                errors.append(TemplateValidationError(
                    template_path, 
                    f"Template file not found: {full_template_path}"
                ))
            else:
                # Validate template content
                try:
                    content = full_template_path.read_text(encoding="utf-8")
                    # Check for undefined variables
                    used_vars = TemplateEngine.extract_variables(content)
                    for var_name in used_vars:
                        if var_name not in template.variables:
                            errors.append(TemplateValidationError(
                                template_path,
                                f"Undefined variable '{var_name}' used in template"
                            ))
                except Exception as e:
                    errors.append(TemplateValidationError(
                        template_path,
                        f"Cannot read template file: {e}"
                    ))
        
        return errors
    
    @classmethod
    def validate_template_name(cls, name: str) -> List[str]:
        """Validate template name."""
        errors = []
        
        if not name:
            errors.append("Template name cannot be empty")
            return errors
        
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', name):
            errors.append("Template name must start with letter and contain only alphanumeric, hyphens, underscores")
        
        if len(name) > 64:
            errors.append(f"Template name too long ({len(name)} chars, max 64)")
        
        return errors


def get_builtin_template_dir() -> Path:
    """Get the built-in template directory."""
    # This should point to skills/kano-agent-backlog-skill/templates/
    current_file = Path(__file__)
    skill_root = current_file.parent.parent.parent  # Go up from src/kano_backlog_core/
    return skill_root / "templates"


def get_custom_template_dir(backlog_root: Path, product: Optional[str] = None) -> Path:
    """Get the custom template directory for a product."""
    if product:
        return backlog_root / "products" / product / "_config" / "templates"
    else:
        return backlog_root / "_config" / "templates"