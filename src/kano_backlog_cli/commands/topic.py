"""
Topic CLI commands for managing topic-based context groupings.

This module provides the `kano topic` command group for:
- Creating topics for context grouping
- Adding items to topics
- Pinning documents to topics
- Switching active topics
- Exporting topic context bundles
- Listing all topics

Requirements: 6.1-11.4
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, List

import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Manage topic-based context groupings")


@app.command()
def create(
    name: str = typer.Argument(..., help="Topic name"),
    agent: str = typer.Option(..., "--agent", help="Agent identity"),
    template: Optional[str] = typer.Option(None, "--template", help="Template name to use"),
    list_templates: bool = typer.Option(False, "--list-templates", help="List available templates"),
    variables: Optional[List[str]] = typer.Option(None, "--var", help="Template variables in format key=value"),
    no_notes: bool = typer.Option(False, "--no-notes", help="Skip creating notes.md (ignored when using templates)"),
    with_spec: bool = typer.Option(False, "--with-spec", help="Initialize spec/ directory with templates (ignored when using templates)"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Create a new topic, optionally from a template."""
    ensure_core_on_path()
    
    # Handle template listing
    if list_templates:
        from kano_backlog_ops.template import get_available_templates
        try:
            templates = get_available_templates()
            if output_format == "json":
                payload = {
                    "templates": [
                        {
                            "name": t.name,
                            "display_name": t.display_name,
                            "description": t.description,
                            "tags": t.tags,
                        }
                        for t in templates.templates
                    ],
                    "builtin_count": templates.builtin_count,
                    "custom_count": templates.custom_count,
                }
                typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                if not templates.templates:
                    typer.echo("No templates available")
                else:
                    typer.echo(f"Available templates ({len(templates.templates)} total):")
                    typer.echo("")
                    for t in templates.templates:
                        typer.echo(f"  {t.name}")
                        typer.echo(f"    {t.description}")
                        if t.tags:
                            typer.echo(f"    Tags: {', '.join(t.tags)}")
                        typer.echo("")
            return
        except Exception as exc:
            typer.echo(f"❌ Error listing templates: {exc}", err=True)
            raise typer.Exit(1)
    
    # Parse template variables
    template_vars = {}
    if variables:
        for var_str in variables:
            if "=" not in var_str:
                typer.echo(f"❌ Invalid variable format: {var_str}. Use key=value format.", err=True)
                raise typer.Exit(1)
            key, value = var_str.split("=", 1)
            template_vars[key.strip()] = value.strip()
    
    # Create topic with or without template
    if template:
        # Template-based creation
        from kano_backlog_ops.template import (
            create_topic_from_template,
            TemplateNotFoundError,
            TemplateValidationError as TemplateValidationError,
            TemplateError,
        )
        
        try:
            result = create_topic_from_template(
                name,
                template,
                agent=agent,
                variables=template_vars,
            )
        except TemplateNotFoundError as exc:
            typer.echo(f"❌ {exc.message}", err=True)
            if exc.suggestion:
                typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
            raise typer.Exit(1)
        except TemplateValidationError as exc:
            typer.echo(f"❌ {exc.message}", err=True)
            raise typer.Exit(1)
        except TemplateError as exc:
            typer.echo(f"❌ {exc.message}", err=True)
            if exc.suggestion:
                typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
            raise typer.Exit(1)
        except Exception as exc:
            typer.echo(f"❌ Unexpected error: {exc}", err=True)
            raise typer.Exit(2)
    else:
        # Standard creation
        from kano_backlog_ops.topic import (
            create_topic,
            TopicExistsError,
            TopicValidationError,
            TopicError,
        )

        try:
            result = create_topic(
                name,
                agent=agent,
                create_notes=not no_notes,
                create_spec=with_spec,
            )
        except TopicExistsError as exc:
            typer.echo(f"❌ {exc.message}", err=True)
            if exc.suggestion:
                typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
            raise typer.Exit(1)
        except TopicValidationError as exc:
            typer.echo(f"❌ {exc.message}", err=True)
            raise typer.Exit(1)
        except TopicError as exc:
            typer.echo(f"❌ {exc.message}", err=True)
            if exc.suggestion:
                typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
            raise typer.Exit(1)
        except Exception as exc:
            typer.echo(f"❌ Unexpected error: {exc}", err=True)
            raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": result.manifest.topic,
            "topic_path": str(result.topic_path),
            "agent": result.manifest.agent,
            "created_at": result.manifest.created_at,
            "template_used": template,
            "variables_used": template_vars if template else None,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"✓ Topic created: {name}")
        if template:
            typer.echo(f"  Template: {template}")
            if template_vars:
                typer.echo(f"  Variables: {len(template_vars)} provided")
        typer.echo(f"  Path: {result.topic_path}")


@app.command()
def add(
    topic_name: str = typer.Argument(..., help="Topic name"),
    item: str = typer.Option(..., "--item", help="Item ID, UID, or path"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Add an item to a topic."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        add_item_to_topic,
        TopicNotFoundError,
        TopicError,
    )

    try:
        result = add_item_to_topic(topic_name, item)
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": result.topic,
            "item_uid": result.item_uid,
            "added": result.added,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        if result.added:
            typer.echo(f"✓ Added item {result.item_uid} to topic '{topic_name}'")
        else:
            typer.echo(f"Item {result.item_uid} already in topic '{topic_name}'")



@app.command()
def pin(
    topic_name: str = typer.Argument(..., help="Topic name"),
    doc: str = typer.Option(..., "--doc", help="Document path (relative to workspace root)"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Pin a document to a topic."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        pin_document,
        TopicNotFoundError,
        TopicError,
    )

    try:
        result = pin_document(topic_name, doc)
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": result.topic,
            "doc_path": result.doc_path,
            "pinned": result.pinned,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        if result.pinned:
            typer.echo(f"✓ Pinned document to topic '{topic_name}'")
            typer.echo(f"  Path: {result.doc_path}")
        else:
            typer.echo(f"Document already pinned to topic '{topic_name}'")


@app.command("add-snippet")
def add_snippet(
    topic_name: str = typer.Argument(..., help="Topic name"),
    file: str = typer.Option(..., "--file", help="Workspace-relative or absolute file path"),
    start: int = typer.Option(..., "--start", help="Start line (1-based, inclusive)"),
    end: int = typer.Option(..., "--end", help="End line (1-based, inclusive)"),
    agent: Optional[str] = typer.Option(None, "--agent", help="Collector agent identity"),
    snapshot: bool = typer.Option(False, "--snapshot", help="Include cached_text snapshot (cache)"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Collect a code snippet reference into the topic materials buffer."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        add_snippet_to_topic,
        TopicNotFoundError,
        TopicError,
    )

    try:
        result = add_snippet_to_topic(
            topic_name,
            file_path=file,
            start_line=start,
            end_line=end,
            agent=agent,
            include_snapshot=snapshot,
        )
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": result.topic,
            "added": result.added,
            "snippet": result.snippet.to_dict(),
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if result.added:
            typer.echo(f"✓ Added snippet to topic '{topic_name}'")
        else:
            typer.echo(f"Snippet already present in topic '{topic_name}'")
        rng = result.snippet.lines
        typer.echo(f"  {result.snippet.file}#L{rng[0]}-L{rng[1]} ({result.snippet.hash})")


@app.command("distill")
def distill(
    topic_name: str = typer.Argument(..., help="Topic name"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Generate/overwrite deterministic brief.md from collected materials."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import distill_topic, TopicNotFoundError, TopicError

    try:
        brief_path = distill_topic(topic_name)
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        typer.echo(json.dumps({"topic": topic_name, "brief_path": str(brief_path)}, ensure_ascii=False))
    else:
        typer.echo(f"✓ Distilled brief: {brief_path}")


@app.command("close")
def close(
    topic_name: str = typer.Argument(..., help="Topic name"),
    agent: Optional[str] = typer.Option(None, "--agent", help="Agent identity"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Mark topic as closed (enables TTL cleanup of materials)."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import close_topic, TopicNotFoundError, TopicError

    try:
        result = close_topic(topic_name, agent=agent)
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        typer.echo(
            json.dumps(
                {"topic": result.topic, "closed": result.closed, "closed_at": result.closed_at},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if result.closed:
            typer.echo(f"✓ Closed topic '{topic_name}' at {result.closed_at}")
        else:
            typer.echo(f"Topic '{topic_name}' already closed at {result.closed_at}")


@app.command("cleanup")
def cleanup(
    ttl_days: int = typer.Option(14, "--ttl-days", help="Delete materials older than N days after close"),
    apply: bool = typer.Option(False, "--apply", help="Perform deletion (default is dry-run)"),
    delete_topic_dir: bool = typer.Option(False, "--delete-topic", help="Delete whole topic dir (dangerous)"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Cleanup raw materials for closed topics after TTL (dry-run by default)."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import cleanup_topics, TopicError

    try:
        result = cleanup_topics(ttl_days=ttl_days, dry_run=(not apply), delete_topic_dir=delete_topic_dir)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topics_scanned": result.topics_scanned,
            "topics_cleaned": result.topics_cleaned,
            "materials_deleted": result.materials_deleted,
            "deleted_paths": [str(p) for p in result.deleted_paths],
            "dry_run": not apply,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        mode = "DRY RUN" if not apply else "APPLY"
        typer.echo(f"{mode}: scanned={result.topics_scanned} cleaned={result.topics_cleaned}")
        for p in result.deleted_paths:
            typer.echo(f"  - {p}")


@app.command()
def switch(
    topic_name: str = typer.Argument(..., help="Topic name"),
    agent: str = typer.Option(..., "--agent", help="Agent identity"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Switch active topic."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        switch_topic,
        TopicNotFoundError,
        TopicError,
    )

    try:
        result = switch_topic(topic_name, agent=agent)
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": result.topic,
            "item_count": result.item_count,
            "pinned_doc_count": result.pinned_doc_count,
            "previous_topic": result.previous_topic,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"✓ Switched to topic '{topic_name}'")
        typer.echo(f"  Items: {result.item_count}")
        typer.echo(f"  Pinned docs: {result.pinned_doc_count}")
        if result.previous_topic:
            typer.echo(f"  Previous: {result.previous_topic}")


@app.command("export-context")
def export_context(
    topic_name: str = typer.Argument(..., help="Topic name"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Export topic context bundle."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        export_topic_context,
        TopicNotFoundError,
        TopicError,
    )

    try:
        bundle = export_topic_context(topic_name, format=output_format)
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": bundle.topic,
            "items": bundle.items,
            "pinned_docs": bundle.pinned_docs,
            "generated_at": bundle.generated_at,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        # Markdown format
        typer.echo(f"# Topic Context: {bundle.topic}\n")
        typer.echo(f"Generated: {bundle.generated_at}\n")
        
        typer.echo("## Items\n")
        if not bundle.items:
            typer.echo("No items in this topic.\n")
        else:
            for item in bundle.items:
                if "error" in item:
                    typer.echo(f"- **{item['uid']}**: {item['error']}")
                else:
                    typer.echo(f"- **{item.get('id', item['uid'])}**: {item.get('title', 'Untitled')}")
                    typer.echo(f"  - State: {item.get('state', 'Unknown')}")
                    typer.echo(f"  - Type: {item.get('type', 'Unknown')}")
            typer.echo("")
        
        typer.echo("## Pinned Documents\n")
        if not bundle.pinned_docs:
            typer.echo("No pinned documents.\n")
        else:
            for doc in bundle.pinned_docs:
                typer.echo(f"### {doc['path']}\n")
                if "error" in doc:
                    typer.echo(f"*Error: {doc['error']}*\n")
                elif "content" in doc:
                    # Truncate long content
                    content = doc["content"]
                    if len(content) > 2000:
                        content = content[:2000] + "\n\n... (truncated)"
                    typer.echo(content)
                    typer.echo("")


@app.command("list")
def list_cmd(
    agent: Optional[str] = typer.Option(None, "--agent", help="Agent to check active topic for"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """List all topics."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import list_topics, get_active_topic, TopicError

    try:
        topics = list_topics()
        active_topic = get_active_topic(agent) if agent else None
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topics": [
                {
                    "topic": t.topic,
                    "agent": t.agent,
                    "item_count": len(t.seed_items),
                    "pinned_doc_count": len(t.pinned_docs),
                    "created_at": t.created_at,
                    "updated_at": t.updated_at,
                    "is_active": t.topic == active_topic,
                }
                for t in topics
            ],
            "active_topic": active_topic,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not topics:
            typer.echo("No topics found")
        else:
            typer.echo(f"Found {len(topics)} topic(s):\n")
            for t in topics:
                is_active = t.topic == active_topic
                active_marker = " (active)" if is_active else ""
                typer.echo(f"  {t.topic}{active_marker}")
                typer.echo(f"    Items: {len(t.seed_items)}")
                typer.echo(f"    Pinned docs: {len(t.pinned_docs)}")
                typer.echo(f"    Updated: {t.updated_at}")
                typer.echo("")


@app.command("add-reference")
def add_reference(
    topic_name: str = typer.Argument(..., help="Source topic name"),
    referenced_topic: str = typer.Option(..., "--to", help="Target topic name to reference"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Add a reference from one topic to another (bidirectional)."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        add_topic_reference,
        TopicNotFoundError,
        TopicError,
    )

    try:
        result = add_topic_reference(topic_name, referenced_topic)
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": result.topic,
            "referenced_topic": result.referenced_topic,
            "added": result.added,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        if result.added:
            typer.echo(f"✓ Added reference: '{result.topic}' → '{result.referenced_topic}'")
            typer.echo("  Bidirectional linking applied automatically")
        else:
            typer.echo(f"Reference already exists: '{result.topic}' → '{result.referenced_topic}'")


@app.command("remove-reference")
def remove_reference(
    topic_name: str = typer.Argument(..., help="Source topic name"),
    referenced_topic: str = typer.Option(..., "--to", help="Target topic name to unreference"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Remove a reference from one topic to another (bidirectional cleanup)."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        remove_topic_reference,
        TopicNotFoundError,
        TopicError,
    )

    try:
        result = remove_topic_reference(topic_name, referenced_topic)
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": result.topic,
            "referenced_topic": result.referenced_topic,
            "removed": result.removed,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        if result.removed:
            typer.echo(f"✓ Removed reference: '{result.topic}' → '{result.referenced_topic}'")
            typer.echo("  Bidirectional cleanup applied automatically")
        else:
            typer.echo(f"Reference does not exist: '{result.topic}' → '{result.referenced_topic}'")


# Template management commands
template_app = typer.Typer(help="Template management commands")
app.add_typer(template_app, name="template")


@template_app.command("list")
def template_list(
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """List available templates."""
    ensure_core_on_path()
    from kano_backlog_ops.template import get_available_templates, TemplateError

    try:
        templates = get_available_templates()
    except TemplateError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "templates": [
                {
                    "name": t.name,
                    "display_name": t.display_name,
                    "description": t.description,
                    "version": t.version,
                    "author": t.author,
                    "tags": t.tags,
                    "variables": {
                        name: {
                            "type": var.type,
                            "description": var.description,
                            "required": var.required,
                            "default": var.default,
                            "choices": var.choices,
                        }
                        for name, var in t.variables.items()
                    },
                }
                for t in templates.templates
            ],
            "builtin_count": templates.builtin_count,
            "custom_count": templates.custom_count,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not templates.templates:
            typer.echo("No templates available")
        else:
            typer.echo(f"Available templates ({len(templates.templates)} total):")
            typer.echo(f"  Built-in: {templates.builtin_count}")
            typer.echo(f"  Custom: {templates.custom_count}")
            typer.echo("")
            
            for t in templates.templates:
                typer.echo(f"  📋 {t.name} - {t.display_name}")
                typer.echo(f"     {t.description}")
                if t.tags:
                    typer.echo(f"     Tags: {', '.join(t.tags)}")
                if t.variables:
                    typer.echo(f"     Variables: {len(t.variables)} configurable")
                typer.echo("")


@template_app.command("show")
def template_show(
    template_name: str = typer.Argument(..., help="Template name"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Show detailed information about a template."""
    ensure_core_on_path()
    from kano_backlog_ops.template import get_template_info, TemplateNotFoundError, TemplateError

    try:
        template_info = get_template_info(template_name)
        template = template_info.template
    except TemplateNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TemplateError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "template": template.to_dict(),
            "source_path": str(template_info.source_path),
            "is_builtin": template_info.is_builtin,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        source_type = "Built-in" if template_info.is_builtin else "Custom"
        typer.echo(f"📋 Template: {template.name}")
        typer.echo(f"   Display Name: {template.display_name}")
        typer.echo(f"   Description: {template.description}")
        typer.echo(f"   Version: {template.version}")
        typer.echo(f"   Author: {template.author}")
        typer.echo(f"   Source: {source_type}")
        typer.echo(f"   Path: {template_info.source_path}")
        
        if template.tags:
            typer.echo(f"   Tags: {', '.join(template.tags)}")
        
        if template.variables:
            typer.echo(f"\n   Variables ({len(template.variables)}):")
            for name, var in template.variables.items():
                required_marker = " (required)" if var.required else ""
                typer.echo(f"     • {name}{required_marker}")
                typer.echo(f"       Type: {var.type}")
                typer.echo(f"       Description: {var.description}")
                if var.default is not None:
                    typer.echo(f"       Default: {var.default}")
                if var.choices:
                    typer.echo(f"       Choices: {', '.join(var.choices)}")
        
        if template.structure.directories:
            typer.echo(f"\n   Directory Structure:")
            for directory in template.structure.directories:
                typer.echo(f"     📁 {directory}")
        
        if template.structure.files:
            typer.echo(f"\n   Template Files:")
            for target, source in template.structure.files.items():
                typer.echo(f"     📄 {target} ← {source}")


@template_app.command("validate")
def template_validate(
    template_name: str = typer.Argument(..., help="Template name"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Validate a template."""
    ensure_core_on_path()
    from kano_backlog_ops.template import validate_template_by_name, TemplateError

    try:
        errors = validate_template_by_name(template_name)
    except TemplateError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "template": template_name,
            "valid": len(errors) == 0,
            "errors": [
                {
                    "path": error.path,
                    "message": error.message,
                    "line": error.line,
                }
                for error in errors
            ],
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not errors:
            typer.echo(f"✅ Template '{template_name}' is valid")
        else:
            typer.echo(f"❌ Template '{template_name}' has {len(errors)} error(s):")
            for error in errors:
                location = f" (line {error.line})" if error.line else ""
                typer.echo(f"   • {error.path}{location}: {error.message}")
            raise typer.Exit(1)

# Snapshot management commands
snapshot_app = typer.Typer(help="Topic snapshot management commands")
app.add_typer(snapshot_app, name="snapshot")


@snapshot_app.command("create")
def snapshot_create(
    topic_name: str = typer.Argument(..., help="Topic name"),
    snapshot_name: str = typer.Argument(..., help="Snapshot name"),
    agent: str = typer.Option(..., "--agent", help="Agent identity"),
    description: str = typer.Option("", "--description", help="Snapshot description"),
    no_materials: bool = typer.Option(False, "--no-materials", help="Skip materials in snapshot"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Create a snapshot of a topic's current state."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        create_topic_snapshot,
        TopicNotFoundError,
        TopicError,
    )

    try:
        result = create_topic_snapshot(
            topic_name,
            snapshot_name,
            description=description,
            agent=agent,
            include_materials=not no_materials,
        )
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": result.topic,
            "snapshot_name": result.snapshot_name,
            "snapshot_path": str(result.snapshot_path),
            "created_at": result.created_at,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"✓ Created snapshot '{result.snapshot_name}' for topic '{result.topic}'")
        typer.echo(f"  Created at: {result.created_at}")
        typer.echo(f"  Path: {result.snapshot_path}")


@snapshot_app.command("list")
def snapshot_list(
    topic_name: str = typer.Argument(..., help="Topic name"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """List all snapshots for a topic."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        list_topic_snapshots,
        TopicNotFoundError,
        TopicError,
    )

    try:
        result = list_topic_snapshots(topic_name)
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": result.topic,
            "snapshots": result.snapshots,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not result.snapshots:
            typer.echo(f"No snapshots found for topic '{result.topic}'")
        else:
            typer.echo(f"Snapshots for topic '{result.topic}' ({len(result.snapshots)} total):")
            typer.echo("")
            for snapshot in result.snapshots:
                typer.echo(f"  📸 {snapshot['name']}")
                typer.echo(f"     Created: {snapshot['created_at']}")
                typer.echo(f"     By: {snapshot['created_by']}")
                if snapshot['description']:
                    typer.echo(f"     Description: {snapshot['description']}")
                typer.echo("")


@snapshot_app.command("restore")
def snapshot_restore(
    topic_name: str = typer.Argument(..., help="Topic name"),
    snapshot_name: str = typer.Argument(..., help="Snapshot name"),
    agent: str = typer.Option(..., "--agent", help="Agent identity"),
    no_backup: bool = typer.Option(False, "--no-backup", help="Skip creating backup before restore"),
    manifest_only: bool = typer.Option(False, "--manifest-only", help="Restore manifest.json only"),
    brief_only: bool = typer.Option(False, "--brief-only", help="Restore brief.md only"),
    notes_only: bool = typer.Option(False, "--notes-only", help="Restore notes.md only"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Restore a topic from a snapshot."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        restore_topic_snapshot,
        TopicNotFoundError,
        TopicError,
    )

    # Determine what to restore
    if manifest_only or brief_only or notes_only:
        restore_manifest = manifest_only
        restore_brief = brief_only
        restore_notes = notes_only
    else:
        # Default: restore everything
        restore_manifest = True
        restore_brief = True
        restore_notes = True

    try:
        result = restore_topic_snapshot(
            topic_name,
            snapshot_name,
            agent=agent,
            restore_manifest=restore_manifest,
            restore_brief=restore_brief,
            restore_notes=restore_notes,
            backup_current=not no_backup,
        )
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "topic": result.topic,
            "snapshot_name": result.snapshot_name,
            "restored_at": result.restored_at,
            "restored_components": result.restored_components,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"✓ Restored topic '{result.topic}' from snapshot '{result.snapshot_name}'")
        typer.echo(f"  Restored at: {result.restored_at}")
        typer.echo(f"  Components restored: {', '.join(result.restored_components)}")
        if not no_backup:
            typer.echo("  Automatic backup created before restore")


@snapshot_app.command("cleanup")
def snapshot_cleanup(
    topic_name: str = typer.Argument(..., help="Topic name"),
    ttl_days: int = typer.Option(30, "--ttl-days", help="Delete snapshots older than N days"),
    keep_latest: int = typer.Option(5, "--keep-latest", help="Always keep N most recent snapshots"),
    apply: bool = typer.Option(False, "--apply", help="Perform deletion (default is dry-run)"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Clean up old snapshots for a topic."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        cleanup_topic_snapshots,
        TopicNotFoundError,
        TopicError,
    )

    try:
        result = cleanup_topic_snapshots(
            topic_name,
            ttl_days=ttl_days,
            keep_latest=keep_latest,
            dry_run=not apply,
        )
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        mode = "DRY RUN" if result["dry_run"] else "APPLY"
        typer.echo(f"{mode}: Topic '{result['topic']}'")
        typer.echo(f"  Snapshots scanned: {result['snapshots_scanned']}")
        typer.echo(f"  Snapshots deleted: {result['snapshots_deleted']}")
        if result["deleted_files"]:
            typer.echo("  Deleted files:")
            for file_path in result["deleted_files"]:
                typer.echo(f"    - {file_path}")

@app.command("split")
def split_topic_cmd(
    source_topic: str = typer.Argument(..., help="Source topic name to split"),
    agent: str = typer.Option(..., "--agent", help="Agent identity"),
    config_file: Optional[str] = typer.Option(None, "--config", help="JSON file with split configuration"),
    new_topic: Optional[List[str]] = typer.Option(None, "--new-topic", help="New topic in format 'name:item1,item2'"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without making changes"),
    no_snapshots: bool = typer.Option(False, "--no-snapshots", help="Skip creating snapshots before split"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Split a topic into multiple focused subtopics."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        split_topic,
        TopicNotFoundError,
        TopicError,
    )

    # Parse split configuration
    split_config = {}
    
    if config_file:
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                split_config = json.load(f)
        except Exception as e:
            typer.echo(f"❌ Error reading config file: {e}", err=True)
            raise typer.Exit(1)
    elif new_topic:
        for topic_spec in new_topic:
            if ':' not in topic_spec:
                typer.echo(f"❌ Invalid topic spec: {topic_spec}. Use format 'name:item1,item2'", err=True)
                raise typer.Exit(1)
            
            name, items_str = topic_spec.split(':', 1)
            items = [item.strip() for item in items_str.split(',') if item.strip()]
            split_config[name.strip()] = items
    else:
        typer.echo("❌ Must provide either --config file or --new-topic specifications", err=True)
        raise typer.Exit(1)

    try:
        result = split_topic(
            source_topic,
            split_config,
            agent=agent,
            dry_run=dry_run,
            create_snapshots=not no_snapshots,
        )
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        if dry_run:
            payload = {
                "source_topic": result.source_topic,
                "new_topics": result.new_topics,
                "conflicts": result.conflicts,
                "references_to_update": result.references_to_update,
                "dry_run": True,
            }
        else:
            payload = {
                "source_topic": result.source_topic,
                "new_topics": result.new_topics,
                "items_redistributed": result.items_redistributed,
                "materials_redistributed": result.materials_redistributed,
                "references_updated": result.references_updated,
                "split_at": result.split_at,
            }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if dry_run:
            typer.echo(f"🔍 DRY RUN: Split plan for '{result.source_topic}'")
            typer.echo(f"  Would create {len(result.new_topics)} new topics:")
            for topic_info in result.new_topics:
                typer.echo(f"    - {topic_info['name']}: {len(topic_info['items'])} items")
            if result.conflicts:
                typer.echo(f"  ⚠️  Conflicts detected: {len(result.conflicts)}")
        else:
            typer.echo(f"✓ Split topic '{result.source_topic}' into {len(result.new_topics)} topics")
            typer.echo(f"  Split at: {result.split_at}")
            typer.echo(f"  New topics created:")
            for topic, items in result.items_redistributed.items():
                typer.echo(f"    - {topic}: {len(items)} items")
            if result.references_updated:
                typer.echo(f"  Updated references in {len(result.references_updated)} topics")


@app.command("merge")
def merge_topics_cmd(
    target_topic: str = typer.Argument(..., help="Target topic name to merge into"),
    source_topics: List[str] = typer.Argument(..., help="Source topic names to merge from"),
    agent: str = typer.Option(..., "--agent", help="Agent identity"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without making changes"),
    no_snapshots: bool = typer.Option(False, "--no-snapshots", help="Skip creating snapshots before merge"),
    delete_sources: bool = typer.Option(False, "--delete-sources", help="Delete source topics after merge"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Merge multiple topics into a target topic."""
    ensure_core_on_path()
    from kano_backlog_ops.topic import (
        merge_topics,
        TopicNotFoundError,
        TopicError,
    )

    try:
        result = merge_topics(
            target_topic,
            source_topics,
            agent=agent,
            dry_run=dry_run,
            create_snapshots=not no_snapshots,
            delete_source_topics=delete_sources,
        )
    except TopicNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except TopicError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        if dry_run:
            payload = {
                "target_topic": result.target_topic,
                "source_topics": result.source_topics,
                "item_conflicts": result.item_conflicts,
                "material_conflicts": result.material_conflicts,
                "references_to_update": result.references_to_update,
                "dry_run": True,
            }
        else:
            payload = {
                "target_topic": result.target_topic,
                "merged_topics": result.merged_topics,
                "items_merged": result.items_merged,
                "materials_merged": result.materials_merged,
                "references_updated": result.references_updated,
                "merged_at": result.merged_at,
            }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if dry_run:
            typer.echo(f"🔍 DRY RUN: Merge plan for '{result.target_topic}'")
            typer.echo(f"  Would merge {len(result.source_topics)} topics:")
            for topic in result.source_topics:
                typer.echo(f"    - {topic}")
            if result.item_conflicts:
                typer.echo(f"  ⚠️  Item conflicts: {len(result.item_conflicts)}")
            if result.material_conflicts:
                typer.echo(f"  ⚠️  Material conflicts: {len(result.material_conflicts)}")
        else:
            typer.echo(f"✓ Merged {len(result.merged_topics)} topics into '{result.target_topic}'")
            typer.echo(f"  Merged at: {result.merged_at}")
            typer.echo(f"  Topics merged:")
            for topic, items in result.items_merged.items():
                typer.echo(f"    - {topic}: {len(items)} items")
            if result.references_updated:
                typer.echo(f"  Updated references in {len(result.references_updated)} topics")
            if delete_sources:
                typer.echo(f"  Deleted {len(result.merged_topics)} source topics")