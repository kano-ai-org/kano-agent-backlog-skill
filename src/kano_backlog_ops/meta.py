"""Meta file maintenance helpers (e.g., conventions)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kano_backlog_core.audit import AuditLog
from kano_backlog_core.config import ConfigLoader


@dataclass
class MetaUpdateResult:
    product: str
    path: Path
    status: str


TICKETING_GUIDANCE_SECTION = """## Ticket type selection

- Epic: multi-release or multi-team milestone spanning multiple Features.
- Feature: a new capability that delivers multiple UserStories.
- UserStory: a single user-facing outcome that requires multiple Tasks.
- Task: a single focused implementation or doc change (typically one session).
- Example: \"End-to-end embedding pipeline\" = Epic; \"Pluggable vector backend\" = Feature; \"MVP chunking pipeline\" = UserStory; \"Implement tokenizer adapter\" = Task.
"""


def add_ticketing_guidance(
    *,
    product: str,
    backlog_root: Optional[Path],
    agent: str,
    model: Optional[str] = None,
    apply: bool = False,
) -> MetaUpdateResult:
    """Append ticketing guidance to _meta/conventions.md if missing."""
    if backlog_root is not None:
        backlog_root = Path(backlog_root).resolve()
        product_root = backlog_root / "products" / product
    else:
        ctx = ConfigLoader.from_path(Path.cwd(), product=product)
        product_root = ctx.product_root

    conventions_path = product_root / "_meta" / "conventions.md"
    if not conventions_path.exists():
        raise FileNotFoundError(f"Conventions file not found: {conventions_path}")

    content = conventions_path.read_text(encoding="utf-8")
    if "## Ticket type selection" in content:
        return MetaUpdateResult(product=product, path=conventions_path, status="unchanged")

    updated = content.rstrip() + "\n\n" + TICKETING_GUIDANCE_SECTION
    status = "would-update"
    if apply:
        conventions_path.write_text(updated, encoding="utf-8")
        AuditLog.log_file_operation(
            operation="update",
            path=str(conventions_path).replace("\\", "/"),
            tool="kano backlog meta add-ticketing-guidance",
            agent=agent,
            metadata={"product": product, "model": model},
        )
        status = "updated"

    return MetaUpdateResult(product=product, path=conventions_path, status=status)
