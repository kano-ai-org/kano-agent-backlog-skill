from __future__ import annotations

import pytest

import importlib.util


def test_resolve_embedder_sentence_transformers_optional_dependency() -> None:
    from kano_backlog_core.embedding import resolve_embedder

    cfg = {
        "provider": "sentence-transformers",
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "dimension": 384,
    }

    module_name = "sentence" + "_" + "transformers"
    if importlib.util.find_spec(module_name) is None:
        with pytest.raises(ValueError, match="sentence-transformers"):
            resolve_embedder(cfg)
        return

    adapter = resolve_embedder(cfg)
    assert adapter.model_name == cfg["model"]


def test_resolve_embedder_huggingface_alias_optional_dependency() -> None:
    from kano_backlog_core.embedding import resolve_embedder

    cfg = {
        "provider": "huggingface",
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "dimension": 384,
    }

    module_name = "sentence" + "_" + "transformers"
    if importlib.util.find_spec(module_name) is None:
        with pytest.raises(ValueError, match="sentence-transformers"):
            resolve_embedder(cfg)
        return

    adapter = resolve_embedder(cfg)
    assert adapter.model_name == cfg["model"]
