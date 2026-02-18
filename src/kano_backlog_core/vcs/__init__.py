"""VCS abstraction layer for reproducible metadata."""

from .base import VcsAdapter, VcsMeta
from .git_adapter import GitAdapter
from .null_adapter import NullAdapter

__all__ = ["VcsAdapter", "VcsMeta", "GitAdapter", "NullAdapter"]