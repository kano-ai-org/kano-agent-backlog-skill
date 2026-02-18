"""Kano Backlog Core - Transport-agnostic backlog domain library."""

from .__version__ import __version__, __version_info__

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
    chunk_text_with_tokenizer,
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
    get_supported_huggingface_models,
    is_sentence_transformers_model,
    suggest_huggingface_model,
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
    "__version_info__",
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
    "chunk_text_with_tokenizer",
    "normalize_text",
    "token_spans",
    "DEFAULT_MAX_TOKENS",
    "MODEL_MAX_TOKENS",
    "HeuristicTokenizer",
    "TokenCount",
    "TokenizerAdapter",
    "resolve_model_max_tokens",
    "resolve_tokenizer",
    "get_supported_huggingface_models",
    "is_sentence_transformers_model",
    "suggest_huggingface_model",
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
