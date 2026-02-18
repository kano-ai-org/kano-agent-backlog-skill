from __future__ import annotations

import importlib.util

import pytest


def test_resolve_embedder_gemini_optional_dependency() -> None:
    from kano_backlog_core.embedding import resolve_embedder

    cfg = {
        "provider": "gemini",
        "model": "gemini-embedding-001",
        "dimension": 3072,
    }

    try:
        has_genai = importlib.util.find_spec("google.genai") is not None
    except ModuleNotFoundError:
        has_genai = False

    if not has_genai:
        with pytest.raises(ValueError, match="google-genai"):
            resolve_embedder(cfg)
        return

    adapter = resolve_embedder(cfg)
    assert adapter.model_name == cfg["model"]


def test_resolve_embedder_google_alias_optional_dependency() -> None:
    from kano_backlog_core.embedding import resolve_embedder

    cfg = {
        "provider": "google",
        "model": "gemini-embedding-001",
        "dimension": 3072,
    }

    try:
        has_genai = importlib.util.find_spec("google.genai") is not None
    except ModuleNotFoundError:
        has_genai = False

    if not has_genai:
        with pytest.raises(ValueError, match="google-genai"):
            resolve_embedder(cfg)
        return

    adapter = resolve_embedder(cfg)
    assert adapter.model_name == cfg["model"]
