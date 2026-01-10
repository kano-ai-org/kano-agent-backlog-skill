#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

sys.dont_write_bytecode = True


CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def iter_markdown_files(root: Path) -> Iterable[Path]:
    ignore_dir_names = {
        ".git",
        ".venv",
        ".pytest_cache",
        "htmlcov",
        ".hypothesis",
    }

    include_roots = [
        root / "_kano" / "backlog",
        root / "skills",
    ]

    for base in include_roots:
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            if any(part in ignore_dir_names for part in path.parts):
                continue
            yield path


def find_cjk_lines(text: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if CJK_PATTERN.search(line):
            hits.append((idx, line))
    return hits


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that backlog/docs markdown contains no CJK characters. "
            "This repo enforces English-only content for backlog and documentation."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root path (default: current directory).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()

    offenders: list[tuple[Path, list[tuple[int, str]]]] = []
    for path in iter_markdown_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        hits = find_cjk_lines(text)
        if hits:
            offenders.append((path, hits))

    if not offenders:
        print("OK: no CJK characters found in backlog/docs markdown.")
        return 0

    print("ERROR: found non-English (CJK) characters in markdown files:\n")
    for path, hits in offenders:
        rel = path.relative_to(repo_root)
        print(f"- {rel}")
        for line_no, line in hits[:10]:
            preview = line.strip()
            if len(preview) > 160:
                preview = preview[:157] + "..."
            print(f"  - L{line_no}: {preview}")
        if len(hits) > 10:
            print(f"  - (+{len(hits) - 10} more lines)")
        print()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

