"""Canonical store for markdown backlog items (SSOT)."""

import re
import sys
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import date

import frontmatter

from .models import BacklogItem, ItemType, ItemState, WorklogEntry
from .errors import ItemNotFoundError, ParseError, ValidationError, WriteError

# Conditional import for UUIDv7
if sys.version_info >= (3, 12):
    from uuid import uuid7  # type: ignore
else:
    from uuid6 import uuid7  # type: ignore


class CanonicalStore:
    """Read and write canonical markdown items."""

    TYPE_PLURALS = {
        ItemType.EPIC: "epics",
        ItemType.FEATURE: "features",
        ItemType.USER_STORY: "userstories",
        ItemType.TASK: "tasks",
        ItemType.BUG: "bugs",
    }

    TYPE_ABBREV = {
        ItemType.EPIC: "EPIC",
        ItemType.FEATURE: "FTR",
        ItemType.USER_STORY: "US",
        ItemType.TASK: "TSK",
        ItemType.BUG: "BUG",
    }

    def __init__(self, product_root: Path):
        """
        Initialize canonical store.

        Args:
            product_root: Product root path (e.g., _kano/backlog/products/<product>)
        """
        self.product_root = product_root
        self.items_root = product_root / "items"

    def read(self, item_path: Path) -> BacklogItem:
        """
        Parse a markdown item from file.

        Args:
            item_path: Absolute path to item file

        Returns:
            BacklogItem

        Raises:
            ItemNotFoundError: If file does not exist
            ParseError: If frontmatter is invalid
        """
        if not item_path.exists():
            raise ItemNotFoundError(item_path)

        try:
            post = frontmatter.load(item_path)
        except Exception as e:
            raise ParseError(item_path, str(e))

        # Parse frontmatter
        try:
            fm = post.metadata
            body_sections = self._parse_body(post.content)

            # Convert date objects to ISO strings if needed
            created = fm["created"]
            if hasattr(created, "isoformat"):
                created = created.isoformat()
            updated = fm["updated"]
            if hasattr(updated, "isoformat"):
                updated = updated.isoformat()

            item = BacklogItem(
                id=fm["id"],
                uid=fm["uid"],
                type=ItemType(fm["type"]),
                title=fm["title"],
                state=ItemState(fm["state"]),
                priority=fm.get("priority"),
                parent=fm.get("parent"),
                owner=fm.get("owner"),
                tags=fm.get("tags", []),
                created=created,
                updated=updated,
                area=fm.get("area"),
                iteration=fm.get("iteration"),
                external=fm.get("external", {}),
                links=fm.get("links", {"relates": [], "blocks": [], "blocked_by": []}),
                decisions=fm.get("decisions", []),
                file_path=item_path,
                **body_sections,
            )
            return item
        except Exception as e:
            raise ParseError(item_path, f"Invalid frontmatter or body: {e}")

    def write(self, item: BacklogItem) -> None:
        """
        Write item to file, preserving frontmatter and body structure.

        Args:
            item: BacklogItem to write

        Raises:
            ValidationError: If item data is invalid
            WriteError: If file write fails
        """
        errors = self.validate_schema(item)
        if errors:
            raise ValidationError(errors)

        if not item.file_path:
            raise WriteError("Item file_path is not set")

        # Update timestamp
        item.updated = date.today().isoformat()

        # Build frontmatter
        fm = {
            "id": item.id,
            "uid": item.uid,
            "type": item.type.value,
            "title": item.title,
            "state": item.state.value,
            "priority": item.priority,
            "parent": item.parent,
            "area": item.area,
            "iteration": item.iteration,
            "tags": item.tags,
            "created": item.created,
            "updated": item.updated,
            "owner": item.owner,
            "external": item.external,
            "links": item.links,
            "decisions": item.decisions,
        }

        # Build body
        body_parts = []
        if item.context:
            body_parts.append(f"# Context\n\n{item.context}")
        if item.goal:
            body_parts.append(f"# Goal\n\n{item.goal}")
        if item.non_goals:
            body_parts.append(f"# Non-Goals\n\n{item.non_goals}")
        if item.approach:
            body_parts.append(f"# Approach\n\n{item.approach}")
        if item.alternatives:
            body_parts.append(f"# Alternatives\n\n{item.alternatives}")
        if item.acceptance_criteria:
            body_parts.append(f"# Acceptance Criteria\n\n{item.acceptance_criteria}")
        if item.risks:
            body_parts.append(f"# Risks / Dependencies\n\n{item.risks}")
        if item.worklog:
            worklog_text = "\n".join(item.worklog)
            body_parts.append(f"# Worklog\n\n{worklog_text}")

        body = "\n\n".join(body_parts)

        # Write file
        try:
            post = frontmatter.Post(body, **fm)
            item.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(item.file_path, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))
        except Exception as e:
            raise WriteError(f"Failed to write {item.file_path}: {e}")

    def create(
        self, item_type: ItemType, title: str, parent: Optional[str] = None, **kwargs: Any
    ) -> BacklogItem:
        """
        Create a new item with auto-generated id, uid, and file path.

        Args:
            item_type: Type of item
            title: Item title
            parent: Parent display ID (optional)
            **kwargs: Additional frontmatter fields

        Returns:
            BacklogItem ready to be written
        """
        # Generate UID
        uid = str(uuid7())

        # Determine next ID number
        next_number = self._get_next_id_number(item_type)
        type_abbrev = self.TYPE_ABBREV[item_type]
        display_id = f"KABSD-{type_abbrev}-{next_number:04d}"

        # Generate slug from title
        slug = self._slugify(title)

        # Determine file path
        type_plural = self.TYPE_PLURALS[item_type]
        bucket = (next_number // 100) * 100
        bucket_str = f"{bucket:04d}"
        filename = f"{display_id}_{slug}.md"
        file_path = self.items_root / type_plural / bucket_str / filename

        # Build item
        today = date.today().isoformat()
        item = BacklogItem(
            id=display_id,
            uid=uid,
            type=item_type,
            title=title,
            state=kwargs.get("state", ItemState.NEW),
            priority=kwargs.get("priority"),
            parent=parent,
            owner=kwargs.get("owner"),
            tags=kwargs.get("tags", []),
            created=today,
            updated=today,
            area=kwargs.get("area"),
            iteration=kwargs.get("iteration"),
            external=kwargs.get("external", {}),
            links=kwargs.get("links", {"relates": [], "blocks": [], "blocked_by": []}),
            decisions=kwargs.get("decisions", []),
            file_path=file_path,
        )

        return item

    def list_items(self, item_type: Optional[ItemType] = None) -> List[Path]:
        """
        List all item files, optionally filtered by type.

        Args:
            item_type: Filter by type (optional)

        Returns:
            List of item file paths
        """
        if item_type:
            type_plural = self.TYPE_PLURALS[item_type]
            type_dir = self.items_root / type_plural
            if not type_dir.exists():
                return []
            return list(type_dir.glob("**/*.md"))
        else:
            # All types
            all_items = []
            for type_dir in self.items_root.iterdir():
                if type_dir.is_dir():
                    all_items.extend(type_dir.glob("**/*.md"))
            return all_items

    def validate_schema(self, item: BacklogItem) -> List[str]:
        """
        Validate item against schema.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Required fields
        if not item.id:
            errors.append("Missing required field: id")
        if not item.uid:
            errors.append("Missing required field: uid")
        if not item.title:
            errors.append("Missing required field: title")
        if not item.created:
            errors.append("Missing required field: created")
        if not item.updated:
            errors.append("Missing required field: updated")

        # Validate ID format
        if item.id:
            # Allow multi-product prefixes; keep type codes stable.
            # Examples: KABSD-TSK-0001, KCCS-USR-0018
            id_pattern = r"^[A-Z][A-Z0-9]{1,15}-(EPIC|FTR|USR|TSK|BUG)-\d{4}$"
            if not re.match(id_pattern, item.id):
                errors.append(
                    f"Invalid id format: {item.id} (expected <PREFIX>-(EPIC|FTR|USR|TSK|BUG)-<NNNN>)"
                )

        # Validate UID format (accept UUIDv4/v7; prefer UUIDv7 going forward)
        if item.uid:
            try:
                uuid.UUID(str(item.uid))
            except Exception:
                errors.append(f"Invalid uid format: {item.uid} (expected UUID)")

        # Validate dates (ISO format)
        date_pattern = r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"
        if item.created and not re.match(date_pattern, item.created):
            errors.append(f"Invalid created date format: {item.created} (expected YYYY-MM-DD)")
        if item.updated and not re.match(date_pattern, item.updated):
            errors.append(f"Invalid updated date format: {item.updated} (expected YYYY-MM-DD)")

        return errors

    def _parse_body(self, body: str) -> Dict[str, Any]:
        """Parse body sections from markdown."""
        sections = {}

        # Define section markers
        section_markers = {
            "context": r"# Context",
            "goal": r"# Goal",
            "non_goals": r"# Non-Goals",
            "approach": r"# Approach",
            "alternatives": r"# Alternatives",
            "acceptance_criteria": r"# Acceptance Criteria",
            "risks": r"# Risks / Dependencies",
            "worklog": r"# Worklog",
        }

        # Split body into sections
        current_section = None
        current_content = []

        for line in body.split("\n"):
            matched_section = None
            for key, marker in section_markers.items():
                if re.match(marker, line.strip()):
                    # Save previous section
                    if current_section:
                        content = "\n".join(current_content).strip()
                        if current_section == "worklog":
                            sections[current_section] = [l.strip() for l in content.split("\n") if l.strip()]
                        else:
                            sections[current_section] = content if content else None
                    # Start new section
                    current_section = key
                    current_content = []
                    matched_section = key
                    break

            if not matched_section and current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            content = "\n".join(current_content).strip()
            if current_section == "worklog":
                sections[current_section] = [l.strip() for l in content.split("\n") if l.strip()]
            else:
                sections[current_section] = content if content else None

        return sections

    def _get_next_id_number(self, item_type: ItemType) -> int:
        """Get next available ID number for type."""
        type_plural = self.TYPE_PLURALS[item_type]
        type_dir = self.items_root / type_plural
        if not type_dir.exists():
            return 1

        # Find highest existing number
        max_num = 0
        type_abbrev = self.TYPE_ABBREV[item_type]
        pattern = re.compile(rf"KABSD-{type_abbrev}-(\d{{4}})")

        for item_path in type_dir.glob("**/*.md"):
            match = pattern.search(item_path.name)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)

        return max_num + 1

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert title to filesystem-safe slug."""
        # Lowercase and replace spaces/special chars with hyphens
        slug = text.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        return slug.strip("-")[:50]  # Limit length
