#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate kano-agent-backlog-skill user story expectations."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repo root path (default: current directory).",
    )
    parser.add_argument(
        "--config",
        default="_kano/backlog/_config/config.json",
        help="Config path (default: _kano/backlog/_config/config.json).",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object.")
    return data


def check_exists(path: Path, label: str) -> Tuple[bool, str]:
    if path.exists():
        return True, f"{label} exists"
    return False, f"{label} missing: {path}"


def check_contains(path: Path, needle: str, label: str) -> Tuple[bool, str]:
    if not path.exists():
        return False, f"{label} missing: {path}"
    content = read_text(path)
    if needle in content:
        return True, f"{label} contains '{needle}'"
    return False, f"{label} missing '{needle}'"


def check_config_key(config: Dict[str, object], keys: List[str], label: str) -> Tuple[bool, str]:
    current: object = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return False, f"{label} missing key: {'.'.join(keys)}"
        current = current[key]
    return True, f"{label} has {'.'.join(keys)}"


def run_checks(checks: List[Tuple[str, Callable[[], Tuple[bool, str]]]]) -> List[Tuple[str, bool, str]]:
    results: List[Tuple[str, bool, str]] = []
    for name, fn in checks:
        try:
            ok, message = fn()
        except Exception as exc:
            ok = False
            message = f"{name} error: {exc}"
        results.append((name, ok, message))
    return results


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    config_path = (repo_root / args.config).resolve()
    config: Dict[str, object] = {}
    if config_path.exists():
        try:
            config = load_json(config_path)
        except Exception:
            config = {}

    skill_root = repo_root / "skills" / "kano-agent-backlog-skill"
    references = skill_root / "references"

    checks: List[Tuple[str, Callable[[], Tuple[bool, str]]]] = []

    checks.append(
        (
            "KABSD-USR-0001",
            lambda: check_contains(
                skill_root / "SKILL.md",
                "Planning before coding",
                "SKILL planning rule",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0002",
            lambda: check_exists(
                skill_root / "scripts" / "logging" / "audit_logger.py",
                "Audit logger",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0003",
            lambda: check_contains(
                skill_root / "scripts" / "logging" / "audit_logger.py",
                "DEFAULT_MAX_BYTES",
                "Rotation defaults",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0004",
            lambda: check_exists(
                skill_root / "scripts" / "backlog" / "init_backlog.py",
                "Bootstrap initializer",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0005",
            lambda: check_exists(
                skill_root / "scripts" / "backlog" / "seed_demo.py",
                "Demo seed script",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0006",
            lambda: check_exists(
                config_path,
                "Config file",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0007",
            lambda: check_config_key(
                config,
                ["log", "verbosity"],
                "Config log verbosity",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0008",
            lambda: check_contains(
                references / "processes.md",
                "work_item_types",
                "Process schema",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0009",
            lambda: check_exists(
                references / "processes" / "azure-boards-agile.json",
                "Built-in Agile profile",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0010",
            lambda: check_config_key(
                config,
                ["sandbox", "root"],
                "Sandbox root config",
            ),
        )
    )

    checks.append(
        (
            "KABSD-USR-0012",
            lambda: check_exists(
                skill_root / "scripts" / "indexing" / "build_sqlite_index.py",
                "SQLite index builder script",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0012.schema",
            lambda: check_exists(
                references / "indexing_schema.sql",
                "SQLite index schema (SQL)",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0012.schema.json",
            lambda: check_exists(
                references / "indexing_schema.json",
                "SQLite index schema (JSON)",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0014.index_enabled",
            lambda: check_config_key(
                config,
                ["index", "enabled"],
                "Index enabled config",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0016",
            lambda: check_contains(
                references / "indexing.md",
                "DB-first is out of scope",
                "Indexing reference (file-first)",
            ),
        )
    )
    checks.append(
        (
            "KABSD-USR-0017",
            lambda: check_exists(
                skill_root / "scripts" / "indexing" / "query_sqlite_index.py",
                "SQLite index query script",
            ),
        )
    )

    results = run_checks(checks)

    print("User Story Validation Results")
    print("============================")
    failures = 0
    for story_id, ok, message in results:
        status = "PASS" if ok else "FAIL"
        print(f"{story_id}: {status} - {message}")
        if not ok:
            failures += 1

    if failures:
        print("")
        print(f"Missing/failed checks: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
