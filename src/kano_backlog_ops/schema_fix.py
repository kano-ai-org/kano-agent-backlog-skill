"""Schema validation and auto-fix for backlog items."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import frontmatter
from datetime import datetime

from kano_backlog_core.config import ConfigLoader
from kano_backlog_ops import worklog


@dataclass
class MissingField:
    field: str
    expected_type: str


@dataclass
class SchemaIssue:
    path: Path
    item_id: str
    missing_fields: list[MissingField]


@dataclass
class SchemaFixResult:
    product: str
    checked: int
    issues: list[SchemaIssue]
    fixed: int


# Required fields per item type
REQUIRED_FIELDS = {
    "id": "str",
    "uid": "str",
    "type": "str",
    "title": "str",
    "state": "str",
    "created": "str",
    "updated": "str",
    "priority": "str",
    "parent": "str | None",
    "owner": "str | None",
    "tags": "list",
    "area": "str | None",
    "iteration": "str | None",
    "external": "dict",
    "links": "dict",
    "decisions": "list",
}


def _get_default_value(field: str, field_type: str):
    """Get default value for missing field."""
    if field == "state":
        return "Proposed"
    if field == "priority":
        return "P2"
    if field == "tags":
        return []
    if field == "decisions":
        return []
    if field == "external":
        return {"azure_id": None, "jira_key": None}
    if field == "links":
        return {"relates": [], "blocks": [], "blocked_by": []}
    if field == "area":
        return "general"
    if field == "iteration":
        return "backlog"
    if field == "created":
        return datetime.now().strftime("%Y-%m-%d")
    if field == "updated":
        return datetime.now().strftime("%Y-%m-%d")
    if field in ("parent", "owner"):
        return None
    return None


def validate_schema(
    product: str | None = None,
    backlog_root: Path | None = None,
) -> list[SchemaFixResult]:
    """Validate item schemas and report missing fields."""
    results: list[SchemaFixResult] = []
    
    product_roots: list[Path] = []
    if backlog_root:
        backlog_root = Path(backlog_root).resolve()
        if product:
            product_roots.append(backlog_root / "products" / product)
        else:
            products_dir = backlog_root / "products"
            if products_dir.exists():
                product_roots.extend([p for p in products_dir.iterdir() if p.is_dir()])
    else:
        if product:
            ctx = ConfigLoader.from_path(Path.cwd(), product=product)
            product_roots.append(ctx.product_root)
        else:
            ctx = ConfigLoader.from_path(Path.cwd())
            products_dir = ctx.backlog_root / "products"
            if products_dir.exists():
                product_roots.extend([p for p in products_dir.iterdir() if p.is_dir()])

    for root in product_roots:
        issues: list[SchemaIssue] = []
        checked = 0
        
        for item_path in (root / "items").rglob("*.md"):
            name = item_path.name.lower()
            if name.startswith("readme") or name.endswith(".index.md"):
                continue
            
            try:
                post = frontmatter.load(item_path)
            except Exception:
                continue
            
            checked += 1
            missing: list[MissingField] = []
            
            for field, field_type in REQUIRED_FIELDS.items():
                if field not in post.metadata:
                    missing.append(MissingField(field=field, expected_type=field_type))
            
            if missing:
                item_id = str(post.get("id", item_path.stem.split("_")[0]))
                issues.append(SchemaIssue(
                    path=item_path,
                    item_id=item_id,
                    missing_fields=missing,
                ))
        
        results.append(SchemaFixResult(
            product=root.name,
            checked=checked,
            issues=issues,
            fixed=0,
        ))
    
    return results


def fix_schema(
    product: str | None = None,
    backlog_root: Path | None = None,
    *,
    agent: str,
    model: Optional[str] = None,
    apply: bool = False,
) -> list[SchemaFixResult]:
    """Fix missing fields in item schemas."""
    results = validate_schema(product=product, backlog_root=backlog_root)
    
    for result in results:
        fixed = 0
        for issue in result.issues:
            try:
                post = frontmatter.load(issue.path)
            except Exception:
                continue
            
            changed = False
            for missing in issue.missing_fields:
                default = _get_default_value(missing.field, missing.expected_type)
                post.metadata[missing.field] = default
                changed = True
            
            if changed and apply:
                content = frontmatter.dumps(post)
                lines = content.splitlines()
                
                # Add worklog entry
                lines = worklog.append_worklog_entry(
                    lines,
                    f"Auto-fixed missing fields: {', '.join(m.field for m in issue.missing_fields)}",
                    agent,
                    model=model,
                )
                
                issue.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                fixed += 1
        
        result.fixed = fixed
    
    return results
