"""Deterministic chunking primitives.

This module provides a small, local-first, dependency-free chunking core that:
- Normalizes text deterministically
- Selects boundaries deterministically (paragraph -> sentence -> hard cut)
- Applies fixed overlap (in tokenizer-agnostic "tokens")
- Produces stable chunk IDs
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import hashlib
import re
import unicodedata
from typing import Iterable, List, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class ChunkingOptions:
    target_tokens: int = 256
    max_tokens: int = 512
    overlap_tokens: int = 32
    version: str = "chunk-v1"

    def __post_init__(self) -> None:
        if self.target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.target_tokens > self.max_tokens:
            raise ValueError("target_tokens must be <= max_tokens")
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens must be >= 0")
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be < max_tokens")
        if not self.version:
            raise ValueError("version must be non-empty")


@dataclass(frozen=True)
class Chunk:
    source_id: str
    start_char: int
    end_char: int
    text: str
    chunk_id: str


_PARA_BREAK_RE = re.compile(r"\n{2,}")
_SENT_END_RE = re.compile(r"(?:[.!?]+|[。！？]+)(?=\s|$)")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    return normalized.rstrip()


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF  # CJK Ext A
        or 0x4E00 <= code <= 0x9FFF  # CJK Unified
        or 0x3040 <= code <= 0x30FF  # Hiragana/Katakana
        or 0xAC00 <= code <= 0xD7AF  # Hangul
    )


def token_spans(text: str) -> List[Tuple[int, int]]:
    """Return deterministic token spans for tokenizer-agnostic chunking.

    This intentionally avoids external tokenizer dependencies:
    - ASCII/Latin: groups alnum + underscore
    - CJK: treats each CJK character as a token
    - Punctuation: each punctuation mark is a token
    """
    spans: List[Tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue

        if _is_cjk(ch):
            spans.append((i, i + 1))
            i += 1
            continue

        if ch.isalnum() or ch == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            spans.append((i, j))
            i = j
            continue

        spans.append((i, i + 1))
        i += 1

    return spans


def _boundary_token_indexes(boundary_chars: Iterable[int], spans: Sequence[Tuple[int, int]]) -> List[int]:
    ends = [e for _, e in spans]
    token_indexes: Set[int] = set()
    for c in boundary_chars:
        idx = bisect_right(ends, c)
        token_indexes.add(idx)
    return sorted(token_indexes)


def _paragraph_boundary_chars(text: str) -> List[int]:
    boundaries: List[int] = []
    for match in _PARA_BREAK_RE.finditer(text):
        boundaries.append(match.start())
    boundaries.append(len(text))
    return boundaries


def _sentence_boundary_chars(text: str) -> List[int]:
    boundaries: List[int] = []
    for match in _SENT_END_RE.finditer(text):
        boundaries.append(match.end())
    boundaries.append(len(text))
    return boundaries


def _pick_boundary(
    *,
    boundaries: Sequence[int],
    start_token: int,
    preferred_end: int,
    max_end: int,
) -> Optional[int]:
    left = bisect_left(boundaries, start_token + 1)
    right = bisect_right(boundaries, max_end)
    if left >= right:
        return None

    forward_left = bisect_left(boundaries, preferred_end, lo=left, hi=right)
    if forward_left < right and boundaries[forward_left] >= preferred_end:
        return boundaries[forward_left]

    backward_right = bisect_right(boundaries, preferred_end, lo=left, hi=right) - 1
    if backward_right >= left:
        return boundaries[backward_right]

    return None


def build_chunk_id(
    *, source_id: str, version: str, start_char: int, end_char: int, span_text: str
) -> str:
    """Build a deterministic chunk id for a given span."""
    digest = hashlib.sha256(
        f"{source_id}\n{version}\n{start_char}\n{end_char}\n{span_text}".encode("utf-8")
    ).hexdigest()
    return f"{source_id}:{version}:{start_char}:{end_char}:{digest[:16]}"


def chunk_text(source_id: str, text: str, options: ChunkingOptions) -> List[Chunk]:
    """Chunk text into deterministic spans with stable IDs.

    Args:
        source_id: Stable identifier for the source document.
        text: Raw input text.
        options: Chunking options (size, overlap, version).

    Returns:
        Deterministic list of chunks ordered by increasing start_char.
    """
    if not source_id:
        raise ValueError("source_id must be non-empty")

    normalized = normalize_text(text)
    spans = token_spans(normalized)
    if not spans:
        return []

    para_boundaries = _boundary_token_indexes(_paragraph_boundary_chars(normalized), spans)
    sent_boundaries = _boundary_token_indexes(_sentence_boundary_chars(normalized), spans)

    chunks: List[Chunk] = []
    start_token = 0
    total_tokens = len(spans)

    while start_token < total_tokens:
        max_end = min(start_token + options.max_tokens, total_tokens)
        preferred_end = min(start_token + options.target_tokens, max_end)

        end_token = _pick_boundary(
            boundaries=para_boundaries,
            start_token=start_token,
            preferred_end=preferred_end,
            max_end=max_end,
        )
        if end_token is None:
            end_token = _pick_boundary(
                boundaries=sent_boundaries,
                start_token=start_token,
                preferred_end=preferred_end,
                max_end=max_end,
            )
        if end_token is None:
            end_token = max_end

        if end_token <= start_token:
            end_token = min(start_token + 1, total_tokens)

        start_char = spans[start_token][0]
        end_char = spans[end_token - 1][1]
        span_text = normalized[start_char:end_char]
        chunks.append(
            Chunk(
                source_id=source_id,
                start_char=start_char,
                end_char=end_char,
                text=span_text,
                chunk_id=build_chunk_id(
                    source_id=source_id,
                    version=options.version,
                    start_char=start_char,
                    end_char=end_char,
                    span_text=span_text,
                ),
            )
        )

        if end_token >= total_tokens:
            break

        chunk_len = end_token - start_token
        if options.overlap_tokens <= 0 or chunk_len <= options.overlap_tokens:
            start_token = end_token
        else:
            start_token = end_token - options.overlap_tokens

    return chunks
