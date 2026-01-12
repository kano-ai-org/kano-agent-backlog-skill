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
from typing import Optional

import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Manage topic-based context groupings")


@app.command()
def create(
    name: str = typer.Argument(..., help="Topic name"),
    agent: str = typer.Option(..., "--agent", help="Agent identity"),
    no_notes: bool = typer.Option(False, "--no-notes", help="Skip creating notes.md"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Create a new topic."""
    ensure_core_on_path()
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
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"✓ Topic created: {name}")
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
