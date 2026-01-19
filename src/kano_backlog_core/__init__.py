"""Kano Backlog Core - Transport-agnostic backlog domain library."""

__version__ = "0.1.0"

from .config import BacklogContext, ConfigLoader
from .canonical import BacklogItem, CanonicalStore, ItemType, ItemState
from .derived import DerivedStore, InMemoryDerivedStore
from .refs import RefParser, RefResolver
from .state import StateMachine, ReadyValidator, StateAction
from .audit import AuditLog, WorklogEntry
from .chunking import (
    Chunk,
    ChunkingOptions,
    build_chunk_id,
    chunk_text,
    normalize_text,
    token_spans,
)
from .tokenizer import (
    DEFAULT_MAX_TOKENS,
    MODEL_MAX_TOKENS,
    HeuristicTokenizer,
    TokenCount,
    TokenizerAdapter,
    resolve_model_max_tokens,
    resolve_tokenizer,
)
from .token_budget import (
    BudgetedChunk,
    TokenBudgetPolicy,
    TokenBudgetResult,
    budget_chunks,
    enforce_token_budget,
)
from .errors import (
    BacklogError,
    ConfigError,
    ItemNotFoundError,
    ParseError,
    ValidationError,
    WriteError,
)

__all__ = [
    # Version
    "__version__",
    # Config
    "BacklogContext",
    "ConfigLoader",
    # Canonical
    "BacklogItem",
    "CanonicalStore",
    "ItemType",
    "ItemState",
    # Derived
    "DerivedStore",
    "InMemoryDerivedStore",
    # Refs
    "RefParser",
    "RefResolver",
    # State
    "StateMachine",
    "ReadyValidator",
    "StateAction",
    # Audit
    "AuditLog",
    "WorklogEntry",
    # Chunking
    "Chunk",
    "ChunkingOptions",
    "build_chunk_id",
    "chunk_text",
    "normalize_text",
    "token_spans",
    "DEFAULT_MAX_TOKENS",
    "MODEL_MAX_TOKENS",
    "HeuristicTokenizer",
    "TokenCount",
    "TokenizerAdapter",
    "resolve_model_max_tokens",
    "resolve_tokenizer",
    "BudgetedChunk",
    "TokenBudgetPolicy",
    "TokenBudgetResult",
    "budget_chunks",
    "enforce_token_budget",
    # Errors
    "BacklogError",
    "ConfigError",
    "ItemNotFoundError",
    "ParseError",
    "ValidationError",
    "WriteError",
]
