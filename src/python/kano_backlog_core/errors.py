"""Exception taxonomy for kano-backlog-core."""

from pathlib import Path
from typing import List


class BacklogError(Exception):
    """Base exception for all backlog errors."""

    pass


# Config errors


class ConfigError(BacklogError):
    """Failed to resolve backlog context or load configuration."""

    pass


# Canonical store errors


class ItemNotFoundError(BacklogError):
    """Item file not found."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Item not found: {path}")


class ParseError(BacklogError):
    """Failed to parse item frontmatter or body."""

    def __init__(self, path: Path, details: str) -> None:
        self.path = path
        self.details = details
        super().__init__(f"Parse error in {path}: {details}")


class ValidationError(BacklogError):
    """Item data failed schema validation."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        error_list = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"Validation failed:\n{error_list}")


class WriteError(BacklogError):
    """Failed to write item to file."""

    pass


# State machine errors (placeholder for future modules)


class InvalidTransitionError(BacklogError):
    """State transition not allowed."""

    def __init__(self, from_state: str, to_state: str, reason: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(f"Invalid transition {from_state} -> {to_state}: {reason}")


class ReadyGateError(BacklogError):
    """Item failed Ready gate validation."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        error_list = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"Ready gate failed:\n{error_list}")


# Ref resolution errors (placeholder for future modules)


class RefNotFoundError(BacklogError):
    """Reference could not be resolved."""

    def __init__(self, ref: str) -> None:
        self.ref = ref
        super().__init__(f"Reference not found: {ref}")


class AmbiguousRefError(BacklogError):
    """Reference matched multiple items."""

    def __init__(self, ref: str, matches: List[str]) -> None:
        self.ref = ref
        self.matches = matches
        match_list = ", ".join(matches)
        super().__init__(f"Ambiguous reference '{ref}' matches: {match_list}")


# Index errors (placeholder for future modules)


class IndexError(BacklogError):
    """Derived index operation failed."""

    pass


class MigrationError(IndexError):
    """Schema migration failed."""

    def __init__(self, current_version: int, target_version: int, details: str) -> None:
        self.current_version = current_version
        self.target_version = target_version
        self.details = details
        super().__init__(
            f"Migration failed (v{current_version} -> v{target_version}): {details}"
        )
