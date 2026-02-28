"""Reference parsing and resolution for backlog items."""

import re
from typing import Optional, List, Tuple
from pathlib import Path

from .models import BacklogItem
from .canonical import CanonicalStore
from .derived import DerivedStore
from .errors import RefNotFoundError, AmbiguousRefError, ParseError


class RefParser:
    """Parse reference strings to their components."""

    # Patterns for different reference types
    DISPLAY_ID_PATTERN = r"^(KABSD|KCCS|[A-Z]+)-(EPIC|FTR|US|TSK|BUG)-(\d{4})$"
    ADR_PATTERN = r"^ADR-(\d{4})(?:-appendix_([a-z0-9_-]+))?$"
    UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"

    @classmethod
    def parse_display_id(cls, ref: str) -> Optional[Tuple[str, str, str, int]]:
        """
        Parse display ID reference (e.g., KABSD-TSK-0001).

        Returns:
            Tuple of (product_prefix, type_abbrev, numeric_part) or None
        """
        match = re.match(cls.DISPLAY_ID_PATTERN, ref.strip())
        if match:
            product, type_abbrev, number = match.groups()
            return (product, type_abbrev, int(number))
        return None

    @classmethod
    def parse_adr(cls, ref: str) -> Optional[Tuple[int, Optional[str]]]:
        """
        Parse ADR reference (e.g., ADR-0003, ADR-0003-appendix_migration-plan).

        Returns:
            Tuple of (adr_number, appendix_name) or None
        """
        match = re.match(cls.ADR_PATTERN, ref.strip())
        if match:
            adr_num, appendix = match.groups()
            return (int(adr_num), appendix)
        return None

    @classmethod
    def parse_uid(cls, ref: str) -> Optional[str]:
        """Parse UUIDv7 reference."""
        if re.match(cls.UUID_PATTERN, ref.strip()):
            return ref.strip()
        return None

    @classmethod
    def parse(cls, ref: str) -> Optional[dict]:
        """
        Parse any reference type.

        Returns:
            Dict with 'type' and type-specific fields, or None if unparseable
        """
        # Try display ID
        result = cls.parse_display_id(ref)
        if result:
            product, type_abbrev, number = result
            return {
                "type": "display_id",
                "product": product,
                "type_abbrev": type_abbrev,
                "number": number,
                "raw": ref,
            }

        # Try ADR
        result = cls.parse_adr(ref)
        if result:
            adr_num, appendix = result
            return {
                "type": "adr",
                "adr_number": adr_num,
                "appendix": appendix,
                "raw": ref,
            }

        # Try UUID
        result = cls.parse_uid(ref)
        if result:
            return {"type": "uuid", "uuid": result, "raw": ref}

        return None


class RefResolver:
    """Resolve reference strings to canonical items."""

    def __init__(self, canonical: CanonicalStore, derived: Optional[DerivedStore] = None):
        """
        Initialize resolver.

        Args:
            canonical: CanonicalStore instance
            derived: Optional DerivedStore for faster lookups
        """
        self.canonical = canonical
        self.derived = derived

    def resolve(self, ref: str) -> BacklogItem:
        """
        Resolve reference to canonical item.

        Args:
            ref: Reference string (display ID, ADR, UUID, etc.)

        Returns:
            BacklogItem

        Raises:
            RefNotFoundError: If reference cannot be resolved
            AmbiguousRefError: If reference matches multiple items
            ParseError: If reference format is invalid
        """
        parsed = RefParser.parse(ref)
        if not parsed:
            raise ParseError(None, f"Cannot parse reference: {ref}")

        if parsed["type"] == "display_id":
            return self._resolve_display_id(parsed)
        elif parsed["type"] == "adr":
            return self._resolve_adr(parsed)
        elif parsed["type"] == "uuid":
            return self._resolve_uuid(parsed)
        else:
            raise ParseError(None, f"Unknown reference type: {parsed['type']}")

    def resolve_many(self, refs: List[str]) -> List[BacklogItem]:
        """
        Resolve multiple references.

        Args:
            refs: List of reference strings

        Returns:
            List of resolved BacklogItem objects (skips unresolvable refs)
        """
        items = []
        for ref in refs:
            try:
                item = self.resolve(ref)
                items.append(item)
            except (RefNotFoundError, AmbiguousRefError, ParseError):
                # Skip unresolvable references
                pass
        return items

    def resolve_or_none(self, ref: str) -> Optional[BacklogItem]:
        """
        Resolve reference, returning None if not found.

        Args:
            ref: Reference string

        Returns:
            BacklogItem or None
        """
        try:
            return self.resolve(ref)
        except (RefNotFoundError, AmbiguousRefError, ParseError):
            return None

    def _resolve_display_id(self, parsed: dict) -> BacklogItem:
        """Resolve display ID reference."""
        display_id = parsed["raw"]

        # Try derived store first (faster)
        if self.derived:
            item = self.derived.get_by_id(display_id)
            if item:
                return item

        # Fall back to canonical search
        for item_path in self.canonical.list_items():
            try:
                item = self.canonical.read(item_path)
                if item.id == display_id:
                    return item
            except Exception:
                pass

        raise RefNotFoundError(display_id)

    def _resolve_adr(self, parsed: dict) -> BacklogItem:
        """Resolve ADR reference to corresponding decision item."""
        adr_num = parsed["adr_number"]
        appendix = parsed.get("appendix")

        # For now, ADR references resolve to ADR task items
        # Pattern: KABSD-ADR-{adr_number:04d}
        display_id = f"KABSD-ADR-{adr_num:04d}"

        if self.derived:
            item = self.derived.get_by_id(display_id)
            if item:
                return item

        for item_path in self.canonical.list_items():
            try:
                item = self.canonical.read(item_path)
                if item.id == display_id:
                    return item
            except Exception:
                pass

        raise RefNotFoundError(display_id)

    def _resolve_uuid(self, parsed: dict) -> BacklogItem:
        """Resolve UUID reference."""
        uid = parsed["uuid"]

        # Try derived store first
        if self.derived:
            item = self.derived.get_by_uid(uid)
            if item:
                return item

        # Fall back to canonical search
        for item_path in self.canonical.list_items():
            try:
                item = self.canonical.read(item_path)
                if item.uid == uid:
                    return item
            except Exception:
                pass

        raise RefNotFoundError(uid)

    def get_references(self, item: BacklogItem) -> List[str]:
        """Extract all references from an item's content."""
        refs = set()

        # Extract from links
        for link_type in ["relates", "blocks", "blocked_by"]:
            if link_type in item.links:
                refs.update(item.links[link_type])

        # Extract from decisions
        refs.update(item.decisions)

        # Extract from body sections (regex-based)
        pattern = r"\b(?:KABSD-[A-Z]+-\d{4}|ADR-\d{4}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b"
        for section in [item.context, item.goal, item.approach, item.acceptance_criteria, item.risks]:
            if section:
                refs.update(re.findall(pattern, section))

        return sorted(list(refs))

    def validate_references(self, item: BacklogItem) -> List[str]:
        """
        Validate all references in an item.

        Returns:
            List of unresolvable reference strings (empty if all valid)
        """
        refs = self.get_references(item)
        unresolvable = []

        for ref in refs:
            try:
                self.resolve(ref)
            except (RefNotFoundError, AmbiguousRefError, ParseError):
                unresolvable.append(ref)

        return unresolvable
