"""
test_vcs_metadata.py - Tests for reproducible VCS metadata blocks.
"""

from kano_backlog_core.vcs.base import VcsMeta
from kano_backlog_core.vcs.detector import format_vcs_metadata


def test_format_vcs_metadata_min_schema_and_order() -> None:
    meta = VcsMeta(
        provider="git",
        branch="main",
        revno="123",
        hash="deadbeef",
        dirty="false",
    )

    rendered = format_vcs_metadata(meta, mode="min").splitlines()
    assert rendered == [
        "<!-- kano:build",
        "vcs.provider: git",
        "vcs.branch: main",
        "vcs.revno: 123",
        "vcs.hash: deadbeef",
        "vcs.dirty: false",
        "-->",
    ]


def test_format_vcs_metadata_none_is_empty() -> None:
    meta = VcsMeta(provider="git", branch="main", revno="1", hash="x", dirty="false")
    assert format_vcs_metadata(meta, mode="none") == ""

