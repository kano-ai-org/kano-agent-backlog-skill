#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

sys.dont_write_bytecode = True

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from context import get_context  # noqa: E402
from product_args import add_product_arguments  # noqa: E402


LANGUAGE_PATTERNS = [
    re.compile(r"[\u4E00-\u9FFF]"),  # CJK Unified Ideographs
    re.compile(r"[\u3400-\u4DBF]"),  # CJK Unified Ideographs Extension A
    re.compile(r"[\u3040-\u309F]"),  # Hiragana
    re.compile(r"[\u30A0-\u30FF]"),  # Katakana
    re.compile(r"[\uAC00-\uD7AF]"),  # Hangul Syllables
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backlog Quality Linter: language-only enforcement with optional Ready/link checks."
    )
    parser.add_argument(
        "--backlog-root",
        help="Backlog root path (defaults to platform root).",
    )
    parser.add_argument(
        "--check-language",
        action="store_true",
        help="Enable language (English-only) check (default when no specific checks provided).",
    )
    parser.add_argument(
        "--check-ready",
        action="store_true",
        help="Validate Ready gate for Tasks/Bugs.",
    )
    parser.add_argument(
        "--check-links",
        action="store_true",
        help="Run link disambiguation report and fail on ambiguous/missing references.",
    )
    parser.add_argument(
        "--check-placement",
        action="store_true",
        help="Ensure all backlog items are in correct product/type folders.",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Glob path(s) to ignore (can repeat).",
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Agent identity running the script (required, used for auditability).",
    )
    add_product_arguments(parser)
    return parser.parse_args()


def is_ignored(path: Path, ignore_globs: List[str], repo_root: Path) -> bool:
    rel = path
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        pass
    for pat in ignore_globs:
        if rel.match(pat) or path.match(pat):
            return True
    return False


def iter_backlog_files(product_root: Path) -> Iterable[Path]:
    for base in (product_root / "items", product_root / "decisions"):
        if not base.exists():
            continue
        for f in base.rglob("*.md"):
            if f.name == "README.md" or f.name.endswith(".index.md"):
                continue
            yield f


@dataclass
class Violation:
    path: Path
    line_no: int
    message: str
    excerpt: str


def contains_cjk(text: str) -> bool:
    for pat in LANGUAGE_PATTERNS:
        if pat.search(text):
            return True
    return False


def strip_inline_code(line: str) -> str:
    # remove content within single backticks: `code`
    return re.sub(r"`[^`]*`", "", line)


def scan_language(path: Path) -> List[Violation]:
    violations: List[Violation] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return violations

    in_fence = False
    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        # toggle fenced code blocks
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # ignore frontmatter region between --- markers
        if i == 1 and line.strip() == "---":
            # fast-forward to closing '---'
            j = i
            while j <= len(lines):
                if lines[j - 1].strip() == "---" and j != i:
                    i = j
                    break
                j += 1
            continue
        text = strip_inline_code(line)
        if contains_cjk(text):
            excerpt = text.strip()
            violations.append(
                Violation(path=path, line_no=i, message="Non-English content detected (CJK)", excerpt=excerpt[:200])
            )
    return violations


def run_ready_check(product_root: Path) -> Tuple[int, str]:
    script = Path(__file__).resolve().parent / "workitem_validate_ready.py"
    failures = 0
    output_lines: List[str] = []
    for f in iter_backlog_files(product_root):
        # Only Tasks/Bugs
        if ".md" in f.suffix:
            pass
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        # simple type detection from frontmatter
        if "type: Task" not in content and "type: Bug" not in content:
            continue
        # run ready validator
        cmd = [sys.executable, str(script), "--item", str(f)]
        result = subprocess.run(cmd, text=True, capture_output=True)
        if result.returncode != 0:
            failures += 1
            msg = result.stderr.strip() or result.stdout.strip()
            output_lines.append(f"[Ready] {f}: {msg}")
    return failures, "\n".join(output_lines)


def run_link_check(platform_root: Path, product: str) -> Tuple[int, str]:
    script = Path(__file__).resolve().parent / "link_disambiguation_report.py"
    cmd = [
        sys.executable,
        str(script),
        "--backlog-root",
        str(platform_root),
        "--format",
        "json",
        "--collisions-only",
        "--product",
        product,
    ]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        # Non-critical; treat as failure with message
        return 1, (result.stderr.strip() or result.stdout.strip() or "link check failed")
    # In collisions-only mode, script may produce empty stdout when no issues
    if not (result.stdout or result.stderr):
        return 0, ""
    try:
        import json
        data = json.loads(result.stdout)
        count = int(data.get("count", 0))
        if count > 0:
            return count, result.stdout
        return 0, ""
    except Exception:
        # If output isn't JSON, treat it as informational and not a failure
        return 0, ""


def run_placement_check(platform_root: Path, product_root: Path) -> List[Violation]:
    violations: List[Violation] = []
    backlog_root = platform_root / "_kano" / "backlog"

    # 1. Global scan for misplaced files outside products/
    for f in backlog_root.glob("*.md"):
        if f.name == "README.md" or f.name.endswith(".index.md"):
            continue
        violations.append(
            Violation(path=f, line_no=0, message="File located outside product directory", excerpt=str(f.relative_to(platform_root)))
        )
    
    decisions_dir = backlog_root / "decisions"
    if decisions_dir.exists():
        for f in decisions_dir.rglob("*.md"):
            if f.name == "README.md" or f.name.endswith(".index.md"):
                continue
            violations.append(
                Violation(path=f, line_no=0, message="File located in legacy decisions directory", excerpt=str(f.relative_to(platform_root)))
            )

    # 2. Per-product structure check
    type_map = {
        "epic": "Epic",
        "feature": "Feature",
        "userstory": "UserStory",
        "task": "Task",
        "bug": "Bug",
    }

    items_dir = product_root / "items"
    if items_dir.exists():
        for type_dir_name, expected_type in type_map.items():
            dir_path = items_dir / type_dir_name
            if not dir_path.exists():
                continue
            for f in dir_path.rglob("*.md"):
                if f.name == "README.md" or f.name.endswith(".index.md"):
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    if f"type: {expected_type}" not in content:
                         violations.append(
                            Violation(path=f, line_no=0, message=f"Item type mismatch: folder is '{type_dir_name}', but 'type: {expected_type}' not found in frontmatter", excerpt="")
                        )
                except Exception:
                    continue

    decisions_dir = product_root / "decisions"
    if decisions_dir.exists():
        for f in decisions_dir.rglob("*.md"):
            if f.name == "README.md" or f.name.endswith(".index.md"):
                continue
            try:
                content = f.read_text(encoding="utf-8")
                if "type: Decision" not in content and "type: ADR" not in content:
                     violations.append(
                        Violation(path=f, line_no=0, message="ADR type mismatch: 'type: Decision' or 'type: ADR' not found in frontmatter", excerpt="")
                    )
            except Exception:
                continue

    return violations


def main() -> int:
    args = parse_args()
    ctx = get_context(product_arg=args.product)
    repo_root: Path = ctx["repo_root"]
    platform_root: Path = ctx["platform_root"]
    product_name: str = ctx["product_name"]
    product_root: Path = ctx["product_root"]

    ignore_globs: List[str] = list(args.ignore or [])

    # If no specific checks requested, default to language-only
    checks = {
        "language": args.check_language or (not args.check_ready and not args.check_links and not args.check_placement),
        "ready": args.check_ready,
        "links": args.check_links,
        "placement": args.check_placement,
    }

    lang_violations: List[Violation] = []
    if checks["language"]:
        for f in iter_backlog_files(product_root):
            if is_ignored(f, ignore_globs, repo_root):
                continue
            lang_violations.extend(scan_language(f))

    ready_failures = 0
    ready_output = ""
    if checks["ready"]:
        ready_failures, ready_output = run_ready_check(product_root)

    link_failures = 0
    link_output = ""
    if checks["links"]:
        link_failures, link_output = run_link_check(platform_root, product_name)

    placement_violations: List[Violation] = []
    if checks["placement"]:
        placement_violations = run_placement_check(platform_root, product_root)

    total_failures = len(lang_violations) + ready_failures + link_failures + len(placement_violations)

    if lang_violations:
        print("Language Guard Report")
        print("=====================")
        print(f"Violations: {len(lang_violations)}")
        for v in lang_violations[:200]:
            print(f"- {v.path}#{v.line_no}: {v.message}")
            if v.excerpt:
                print(f"  Excerpt: {v.excerpt}")
        if len(lang_violations) > 200:
            print(f"... and {len(lang_violations) - 200} more")
        print()

    if ready_output.strip():
        print("Ready Gate Report")
        print("=================")
        print(ready_output)
        print()

    if link_output.strip():
        print("Link Integrity Report")
        print("=====================")
        print(link_output)
        print()

    if placement_violations:
        print("Placement Check Report")
        print("======================")
        print(f"Violations: {len(placement_violations)}")
        for v in placement_violations:
            print(f"- {v.path}: {v.message}")
        print()

    if total_failures:
        return 1
    print("Backlog quality checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
