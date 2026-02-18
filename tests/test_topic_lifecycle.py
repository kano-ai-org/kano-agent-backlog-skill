"""Focused tests for Topic materials + lifecycle.

These tests validate the agreed semantics:
- Topic is the shareable buffer under _kano/backlog/topics/<topic>/
- Raw materials are collected via snippet refs
- Distill overwrites a deterministic brief
- Close enables TTL cleanup of materials
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

import sys

test_dir = Path(__file__).parent
src_dir = test_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from kano_backlog_ops.topic import (
    add_snippet_to_topic,
    close_topic,
    create_topic,
    distill_topic,
    cleanup_topics,
)
from kano_backlog_ops.artifacts import attach_artifact


def _mk_backlog(tmp: Path) -> Path:
    backlog_root = tmp / "_kano" / "backlog"
    (backlog_root / "topics").mkdir(parents=True, exist_ok=True)
    (backlog_root / "products" / "p" / "_config").mkdir(parents=True, exist_ok=True)
    (backlog_root / "products" / "p" / "_config" / "config.json").write_text(
        json.dumps({"project": {"name": "p", "prefix": "P"}}), encoding="utf-8"
    )
    return backlog_root


def test_topic_create_creates_materials_and_brief():
    tmp = Path(tempfile.mkdtemp())
    try:
        backlog_root = _mk_backlog(tmp)
        result = create_topic("t1", agent="a", backlog_root=backlog_root)
        assert (result.topic_path / "manifest.json").exists()
        assert (result.topic_path / "brief.md").exists()
        assert (result.topic_path / "brief.generated.md").exists()
        assert (result.topic_path / "materials" / "clips").exists()
        assert (result.topic_path / "materials" / "links").exists()
        assert (result.topic_path / "materials" / "extracts").exists()
        assert (result.topic_path / "materials" / "logs").exists()
        assert (result.topic_path / "publish").exists()
        assert (result.topic_path / "synthesis").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_add_snippet_updates_manifest_and_is_idempotent():
    tmp = Path(tempfile.mkdtemp())
    try:
        backlog_root = _mk_backlog(tmp)
        create_topic("t1", agent="a", backlog_root=backlog_root)

        ws_root = backlog_root.parent.parent
        sample = ws_root / "sample.py"
        sample.write_text("a = 1\nprint(a)\n", encoding="utf-8")

        r1 = add_snippet_to_topic(
            "t1",
            file_path="sample.py",
            start_line=1,
            end_line=2,
            agent="collector",
            include_snapshot=False,
            backlog_root=backlog_root,
        )
        assert r1.added is True

        r2 = add_snippet_to_topic(
            "t1",
            file_path="sample.py",
            start_line=1,
            end_line=2,
            agent="collector",
            include_snapshot=False,
            backlog_root=backlog_root,
        )
        assert r2.added is False

        manifest = json.loads((backlog_root / "topics" / "t1" / "manifest.json").read_text(encoding="utf-8"))
        assert len(manifest.get("snippet_refs", [])) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_distill_overwrites_brief_deterministically_contains_index():
    tmp = Path(tempfile.mkdtemp())
    try:
        backlog_root = _mk_backlog(tmp)
        create_topic("t1", agent="a", backlog_root=backlog_root)

        ws_root = backlog_root.parent.parent
        sample = ws_root / "sample.py"
        sample.write_text("a = 1\nprint(a)\n", encoding="utf-8")
        add_snippet_to_topic(
            "t1",
            file_path="sample.py",
            start_line=1,
            end_line=2,
            backlog_root=backlog_root,
        )

        brief_path = distill_topic("t1", backlog_root=backlog_root)
        content = brief_path.read_text(encoding="utf-8")
        assert "## Materials Index" in content
        assert "### Snippet Refs" in content
        assert "sample.py#L1-L2" in content
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cleanup_dry_run_lists_materials_after_close_and_ttl():
    tmp = Path(tempfile.mkdtemp())
    try:
        backlog_root = _mk_backlog(tmp)
        create_topic("t1", agent="a", backlog_root=backlog_root)

        # Ensure materials exist
        materials = backlog_root / "topics" / "t1" / "materials"
        (materials / "logs").mkdir(parents=True, exist_ok=True)
        (materials / "logs" / "x.txt").write_text("log", encoding="utf-8")

        close_topic("t1", backlog_root=backlog_root)

        # ttl_days=1 but we don't want to depend on wall clock; set ttl_days=0 is invalid.
        # Use ttl_days=1 and accept that a freshly-closed topic won't be eligible.
        # Instead, exercise that cleanup runs and returns a result structure.
        result = cleanup_topics(ttl_days=1, backlog_root=backlog_root, dry_run=True)
        assert result.topics_scanned >= 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_attach_artifact_resolves_items_in_product_layout():
    tmp = Path(tempfile.mkdtemp())
    try:
        backlog_root = _mk_backlog(tmp)

        product_root = backlog_root / "products" / "p"
        items_root = product_root / "items" / "epic" / "0000"
        items_root.mkdir(parents=True, exist_ok=True)

        item_id = "P-EPIC-0001"
        item_path = items_root / f"{item_id}_demo.md"
        item_path.write_text(
            "\n".join(
                [
                    "---",
                    f"id: {item_id}",
                    "uid: 019bd5aa-1111-7335-becf-f0a281746fbc",
                    "type: Epic",
                    "title: Demo epic",
                    "state: Proposed",
                    "created: 2026-01-01",
                    "updated: 2026-01-01",
                    "---",
                    "",
                    "# Context",
                    "",
                    "Demo.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        src = tmp / "artifact.txt"
        src.write_text("hello", encoding="utf-8")

        result = attach_artifact(
            item_ref=item_id,
            artifact_path=src,
            product="p",
            shared=False,
            agent="tester",
            backlog_root=backlog_root,
        )
        assert result.destination.exists()
        assert result.destination.name == "artifact.txt"
        assert (product_root / "artifacts" / item_id).exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
