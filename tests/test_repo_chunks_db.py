"""Tests for repo corpus chunks DB operations."""

from pathlib import Path

import pytest

from kano_backlog_ops.repo_chunks_db import (
    build_repo_chunks_db,
    query_repo_chunks_fts,
    _should_exclude,
    _scan_repo_files,
    DEFAULT_INCLUDE_PATTERNS,
    DEFAULT_EXCLUDE_PATTERNS,
)


def test_should_exclude_basic(tmp_path: Path) -> None:
    project_root = tmp_path
    
    git_dir = project_root / ".git" / "objects"
    git_dir.mkdir(parents=True)
    assert _should_exclude(git_dir, project_root, DEFAULT_EXCLUDE_PATTERNS)
    
    cache_dir = project_root / ".cache" / "chunks.sqlite3"
    cache_dir.parent.mkdir(parents=True)
    cache_dir.touch()
    assert _should_exclude(cache_dir, project_root, DEFAULT_EXCLUDE_PATTERNS)
    
    env_file = project_root / ".env"
    env_file.touch()
    assert _should_exclude(env_file, project_root, DEFAULT_EXCLUDE_PATTERNS)
    
    normal_file = project_root / "README.md"
    normal_file.touch()
    assert not _should_exclude(normal_file, project_root, DEFAULT_EXCLUDE_PATTERNS)


def test_should_exclude_node_modules(tmp_path: Path) -> None:
    project_root = tmp_path
    
    node_file = project_root / "node_modules" / "package" / "index.js"
    node_file.parent.mkdir(parents=True)
    node_file.touch()
    assert _should_exclude(node_file, project_root, DEFAULT_EXCLUDE_PATTERNS)


def test_should_exclude_pycache(tmp_path: Path) -> None:
    project_root = tmp_path
    
    cache_file = project_root / "src" / "__pycache__" / "module.pyc"
    cache_file.parent.mkdir(parents=True)
    cache_file.touch()
    assert _should_exclude(cache_file, project_root, DEFAULT_EXCLUDE_PATTERNS)


def test_scan_repo_files_basic(tmp_path: Path) -> None:
    project_root = tmp_path
    
    (project_root / "README.md").write_text("# Test", encoding="utf-8")
    (project_root / "src").mkdir()
    (project_root / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (project_root / "config.toml").write_text("[tool]", encoding="utf-8")
    
    (project_root / ".git").mkdir()
    (project_root / ".git" / "config").write_text("", encoding="utf-8")
    
    results = _scan_repo_files(project_root, DEFAULT_INCLUDE_PATTERNS, DEFAULT_EXCLUDE_PATTERNS)
    
    paths = [p.relative_to(project_root).as_posix() for p, _ in results]
    assert "README.md" in paths
    assert "src/main.py" in paths
    assert "config.toml" in paths
    assert ".git/config" not in paths


def test_scan_repo_files_excludes_large_files(tmp_path: Path) -> None:
    project_root = tmp_path
    
    small_file = project_root / "small.txt"
    small_file.write_text("small content", encoding="utf-8")
    
    large_file = project_root / "large.txt"
    large_file.write_bytes(b"x" * (11 * 1024 * 1024))
    
    results = _scan_repo_files(project_root, DEFAULT_INCLUDE_PATTERNS, DEFAULT_EXCLUDE_PATTERNS)
    
    paths = [p.relative_to(project_root).as_posix() for p, _ in results]
    assert "small.txt" in paths
    assert "large.txt" not in paths


def test_scan_repo_files_excludes_empty_files(tmp_path: Path) -> None:
    project_root = tmp_path
    
    empty_file = project_root / "empty.txt"
    empty_file.touch()
    
    non_empty = project_root / "content.txt"
    non_empty.write_text("content", encoding="utf-8")
    
    results = _scan_repo_files(project_root, DEFAULT_INCLUDE_PATTERNS, DEFAULT_EXCLUDE_PATTERNS)
    
    paths = [p.relative_to(project_root).as_posix() for p, _ in results]
    assert "content.txt" in paths
    assert "empty.txt" not in paths


def test_build_repo_chunks_db_basic(tmp_path: Path) -> None:
    project_root = tmp_path
    
    (project_root / "README.md").write_text("# Test Project\n\nThis is a test.", encoding="utf-8")
    (project_root / "src").mkdir()
    (project_root / "src" / "main.py").write_text("def hello():\n    print('hello')", encoding="utf-8")
    
    result = build_repo_chunks_db(project_root=project_root, force=True)
    
    assert result.db_path.exists()
    assert result.files_indexed == 2
    assert result.chunks_indexed > 0
    assert result.build_time_ms > 0


def test_build_repo_chunks_db_with_backlog_root(tmp_path: Path) -> None:
    project_root = tmp_path
    backlog_root = project_root / "_kano" / "backlog"
    backlog_root.mkdir(parents=True)
    
    (project_root / "README.md").write_text("# Test", encoding="utf-8")
    
    result = build_repo_chunks_db(backlog_root=backlog_root, force=True)
    
    assert result.db_path.exists()
    assert result.files_indexed >= 1


def test_build_repo_chunks_db_excludes_patterns(tmp_path: Path) -> None:
    project_root = tmp_path
    
    (project_root / "README.md").write_text("# Test", encoding="utf-8")
    
    git_dir = project_root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("", encoding="utf-8")
    
    cache_dir = project_root / ".cache"
    cache_dir.mkdir()
    (cache_dir / "data.json").write_text("{}", encoding="utf-8")
    
    result = build_repo_chunks_db(project_root=project_root, force=True)
    
    assert result.db_path.exists()
    assert result.files_indexed == 1


def test_build_repo_chunks_db_custom_patterns(tmp_path: Path) -> None:
    project_root = tmp_path
    
    (project_root / "README.md").write_text("# Test", encoding="utf-8")
    (project_root / "script.sh").write_text("#!/bin/bash", encoding="utf-8")
    
    result = build_repo_chunks_db(
        project_root=project_root,
        include_patterns=["*.md", "*.sh"],
        exclude_patterns=[],
        force=True,
    )
    
    assert result.db_path.exists()
    assert result.files_indexed == 2


def test_query_repo_chunks_fts_basic(tmp_path: Path) -> None:
    project_root = tmp_path
    
    (project_root / "README.md").write_text(
        "# Test Project\n\nThis project uses SQLite for indexing.",
        encoding="utf-8",
    )
    (project_root / "docs.md").write_text(
        "# Documentation\n\nPostgreSQL is not used here.",
        encoding="utf-8",
    )
    
    build_repo_chunks_db(project_root=project_root, force=True)
    
    hits = query_repo_chunks_fts(project_root=project_root, query="SQLite", k=10)
    
    assert len(hits) > 0
    assert any("README.md" in hit.file_path for hit in hits)
    assert "SQLite" in hits[0].content


def test_query_repo_chunks_fts_no_results(tmp_path: Path) -> None:
    project_root = tmp_path
    
    (project_root / "README.md").write_text("# Test", encoding="utf-8")
    
    build_repo_chunks_db(project_root=project_root, force=True)
    
    hits = query_repo_chunks_fts(project_root=project_root, query="nonexistent", k=10)
    
    assert len(hits) == 0


def test_query_repo_chunks_fts_empty_query(tmp_path: Path) -> None:
    project_root = tmp_path
    
    (project_root / "README.md").write_text("# Test", encoding="utf-8")
    
    build_repo_chunks_db(project_root=project_root, force=True)
    
    hits = query_repo_chunks_fts(project_root=project_root, query="", k=10)
    
    assert len(hits) == 0


def test_query_repo_chunks_fts_limit(tmp_path: Path) -> None:
    project_root = tmp_path
    
    for i in range(10):
        (project_root / f"file{i}.md").write_text(f"# File {i}\n\ntest content", encoding="utf-8")
    
    build_repo_chunks_db(project_root=project_root, force=True)
    
    hits = query_repo_chunks_fts(project_root=project_root, query="test", k=3)
    
    assert len(hits) <= 3


def test_build_repo_chunks_db_force_rebuild(tmp_path: Path) -> None:
    project_root = tmp_path
    
    (project_root / "README.md").write_text("# Test", encoding="utf-8")
    
    result1 = build_repo_chunks_db(project_root=project_root, force=True)
    assert result1.db_path.exists()
    
    with pytest.raises(FileExistsError):
        build_repo_chunks_db(project_root=project_root, force=False)
    
    result2 = build_repo_chunks_db(project_root=project_root, force=True)
    assert result2.db_path.exists()


def test_query_repo_chunks_fts_db_not_found(tmp_path: Path) -> None:
    project_root = tmp_path
    
    with pytest.raises(FileNotFoundError):
        query_repo_chunks_fts(project_root=project_root, query="test", k=10)
