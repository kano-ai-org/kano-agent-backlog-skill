"""Check for orphan commits (commits without backlog item IDs)."""

import re
import subprocess
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Check for commits without backlog item IDs")
console = Console()


def get_commits_since(days: int = 7) -> List[Tuple[str, str, str]]:
    """Get commits from the last N days.
    
    Returns:
        List of (hash, date, message) tuples
    """
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    try:
        output = subprocess.check_output(
            ['git', 'log', f'--since={since_date}', '--pretty=format:%h|%ai|%s'],
            encoding='utf-8',
            stderr=subprocess.DEVNULL
        )
        
        commits = []
        for line in output.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 2)
            if len(parts) == 3:
                commits.append((parts[0], parts[1][:10], parts[2]))
        
        return commits
    except subprocess.CalledProcessError:
        return []


def has_ticket_id(message: str) -> Optional[str]:
    """Check if commit message contains a backlog item ID.
    
    Returns:
        Ticket ID if found, None otherwise
    """
    match = re.search(r'(KABSD-(FTR|TSK|BUG|USR|EPC)-\d+)', message)
    return match.group(1) if match else None


def is_trivial_commit(message: str) -> bool:
    """Check if this is a trivial commit that doesn't need a ticket."""
    trivial_patterns = [
        r'^(docs|chore|style|typo|format):',
        r'^Merge ',
        r'^Revert ',
        r'^WIP:',
    ]
    return any(re.match(pattern, message, re.IGNORECASE) for pattern in trivial_patterns)


@app.command()
def check(
    days: int = typer.Option(7, "--days", "-d", help="Check commits from last N days"),
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all commits (including trivial)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table|json|plain"),
):
    """Check for commits without backlog item IDs."""
    
    commits = get_commits_since(days)
    
    if not commits:
        console.print("[yellow]No commits found in the last {days} days[/yellow]")
        return
    
    orphans = []
    with_tickets = []
    trivial = []
    
    for commit_hash, date, message in commits:
        ticket_id = has_ticket_id(message)
        is_trivial = is_trivial_commit(message)
        
        if ticket_id:
            with_tickets.append((commit_hash, date, message, ticket_id))
        elif is_trivial:
            trivial.append((commit_hash, date, message))
        else:
            orphans.append((commit_hash, date, message))
    
    # Output based on format
    if format == "json":
        import json
        result = {
            "summary": {
                "total": len(commits),
                "with_tickets": len(with_tickets),
                "orphans": len(orphans),
                "trivial": len(trivial),
            },
            "orphans": [
                {"hash": h, "date": d, "message": m}
                for h, d, m in orphans
            ]
        }
        console.print_json(data=result)
        return
    
    if format == "plain":
        for commit_hash, date, message in orphans:
            console.print(f"{commit_hash} {date} {message}")
        return
    
    # Table format (default)
    console.print()
    console.print(f"[bold]Commit Analysis (last {days} days)[/bold]")
    console.print()
    
    # Summary
    summary_table = Table(show_header=False, box=None)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Count", style="bold")
    
    summary_table.add_row("Total commits", str(len(commits)))
    summary_table.add_row("✅ With tickets", f"[green]{len(with_tickets)}[/green]")
    summary_table.add_row("⚠️  Orphan commits", f"[yellow]{len(orphans)}[/yellow]" if orphans else "[green]0[/green]")
    summary_table.add_row("📝 Trivial commits", str(len(trivial)))
    
    console.print(summary_table)
    console.print()
    
    # Orphan commits
    if orphans:
        console.print("[bold yellow]⚠️  Orphan Commits (need tickets):[/bold yellow]")
        console.print()
        
        orphan_table = Table(show_header=True)
        orphan_table.add_column("Hash", style="cyan")
        orphan_table.add_column("Date", style="dim")
        orphan_table.add_column("Message", style="white")
        
        for commit_hash, date, message in orphans:
            orphan_table.add_row(commit_hash, date, message[:60])
        
        console.print(orphan_table)
        console.print()
        
        console.print("[bold]Suggested actions:[/bold]")
        console.print()
        console.print("  1. Create tickets for these commits:")
        console.print("     [dim]kano-backlog item create --type task --title \"...\"[/dim]")
        console.print()
        console.print("  2. Amend commit messages:")
        console.print("     [dim]git rebase -i HEAD~N  # Interactive rebase[/dim]")
        console.print()
        console.print("  3. Or add to existing tickets:")
        console.print("     [dim]kano-backlog worklog append KABSD-TSK-XXXX --message \"...\"[/dim]")
        console.print()
    else:
        console.print("[bold green]✅ All commits have tickets or are trivial![/bold green]")
        console.print()
    
    # Show trivial commits if requested
    if show_all and trivial:
        console.print("[bold]📝 Trivial Commits (no ticket needed):[/bold]")
        console.print()
        
        trivial_table = Table(show_header=True)
        trivial_table.add_column("Hash", style="cyan")
        trivial_table.add_column("Date", style="dim")
        trivial_table.add_column("Message", style="dim")
        
        for commit_hash, date, message in trivial:
            trivial_table.add_row(commit_hash, date, message[:60])
        
        console.print(trivial_table)
        console.print()


@app.command()
def suggest(
    commit_hash: str = typer.Argument(..., help="Commit hash to analyze"),
):
    """Suggest ticket type and title for a commit."""
    
    try:
        # Get commit message
        message = subprocess.check_output(
            ['git', 'log', '-1', '--pretty=%B', commit_hash],
            encoding='utf-8'
        ).strip()
        
        # Get changed files
        files = subprocess.check_output(
            ['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', commit_hash],
            encoding='utf-8'
        ).strip().split('\n')
        
    except subprocess.CalledProcessError:
        console.print(f"[red]Error: Commit {commit_hash} not found[/red]")
        return
    
    # Check if already has ticket
    ticket_id = has_ticket_id(message)
    if ticket_id:
        console.print(f"[green]✅ Commit already has ticket: {ticket_id}[/green]")
        return
    
    # Suggest ticket type
    msg_lower = message.lower()
    
    if any(kw in msg_lower for kw in ['feat', 'feature', 'add', 'implement', 'new']):
        ticket_type = 'task'
        description = 'Feature implementation'
    elif any(kw in msg_lower for kw in ['fix', 'bug', 'issue', 'error', 'crash']):
        ticket_type = 'bug'
        description = 'Bug fix'
    elif any(kw in msg_lower for kw in ['refactor', 'cleanup', 'improve', 'optimize']):
        ticket_type = 'task'
        description = 'Code refactoring'
    elif any(kw in msg_lower for kw in ['test', 'spec']) or any('test' in f for f in files):
        ticket_type = 'task'
        description = 'Test implementation'
    else:
        ticket_type = 'task'
        description = 'Code change'
    
    # Extract title from commit message
    title = message.split('\n')[0]
    if ':' in title:
        title = title.split(':', 1)[1].strip()
    
    console.print()
    console.print(f"[bold]Commit: {commit_hash}[/bold]")
    console.print(f"Message: {message.split(chr(10))[0]}")
    console.print(f"Files: {len(files)}")
    console.print()
    console.print(f"[bold cyan]💡 Suggested ticket:[/bold cyan]")
    console.print(f"  Type: {ticket_type.upper()}")
    console.print(f"  Title: {title}")
    console.print()
    console.print("[bold]Create ticket:[/bold]")
    console.print(f"  kano-backlog item create \\")
    console.print(f"    --type {ticket_type} \\")
    console.print(f"    --title \"{title}\" \\")
    console.print(f"    --product kano-agent-backlog-skill \\")
    console.print(f"    --agent $(whoami)")
    console.print()


if __name__ == "__main__":
    app()
