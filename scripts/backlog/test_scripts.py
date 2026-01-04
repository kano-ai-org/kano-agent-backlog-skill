#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import List, Optional

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402


def backlog_root_for_repo(repo_root: Path) -> Path:
    return (repo_root / "_kano" / "backlog").resolve()


def ensure_under_backlog(path: Path, backlog_root: Path, label: str) -> None:
    try:
        path.resolve().relative_to(backlog_root)
    except ValueError as exc:
        raise SystemExit(f"{label} must be under {backlog_root}: {path}") from exc

def run(
    cmd: List[str],
    expect_ok: bool = True,
    show_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    print(f"[CMD] {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True, capture_output=True)
    if show_output and result.stdout:
        print(result.stdout.strip())
    if show_output and result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    if expect_ok and result.returncode != 0:
        raise SystemExit(f"Command failed: {cmd}")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke tests for kano-agent-backlog-skill scripts.")
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the temporary test directory for inspection.",
    )
    parser.add_argument(
        "--temp-root",
        help="Optional temp root path (default: _kano/backlog/_tmp_tests).",
    )
    return parser.parse_args()


def read_frontmatter_id(path: Path) -> Optional[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("id:"):
            return line.split(":", 1)[1].strip().strip("\"")
    return None


def fill_ready_sections(path: Path) -> None:
    required = {
        "# Context",
        "# Goal",
        "# Approach",
        "# Acceptance Criteria",
        "# Risks / Dependencies",
    }
    lines = path.read_text(encoding="utf-8").splitlines()
    out: List[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        out.append(line)
        if line in required:
            next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            if not next_line.strip():
                out.append("OK")
        idx += 1
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    python = sys.executable
    repo_root = Path.cwd().resolve()
    allowed_root = backlog_root_for_repo(repo_root)

    create_item = script_dir / "create_item.py"
    update_state = script_dir / "update_state.py"
    validate_ready = script_dir / "validate_ready.py"
    generate_view = script_dir / "generate_view.py"

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.temp_root:
        temp_root = Path(args.temp_root)
        if not temp_root.is_absolute():
            temp_root = (repo_root / temp_root).resolve()
        ensure_under_backlog(temp_root, allowed_root, "temp-root")
    else:
        temp_root = allowed_root / "_tmp_tests"
    temp_root.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:6]
    test_root = temp_root / f"script_tests_{stamp}_{suffix}"
    test_root.mkdir(parents=True, exist_ok=True)
    try:
        backlog_root = test_root / "backlog"
        items_root = backlog_root / "items"
        meta_root = backlog_root / "_meta"
        meta_root.mkdir(parents=True, exist_ok=True)
        indexes = meta_root / "indexes.md"
        indexes.write_text(
            "\n".join(
                [
                    "# Index Registry",
                    "",
                    "| type | item_id | index_file | updated | notes |",
                    "| ---- | ------- | ---------- | ------- | ----- |",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        run(
            [
                python,
                str(create_item),
                "--items-root",
                str(items_root),
                "--backlog-root",
                str(backlog_root),
                "--type",
                "Epic",
                "--title",
                "Demo Epic",
                "--prefix",
                "DM",
            ]
        )

        epic_files = [
            path
            for path in (items_root / "epics").rglob("*.md")
            if not path.name.endswith(".index.md")
        ]
        if len(epic_files) != 1:
            raise SystemExit("Expected exactly one Epic item.")
        epic_path = epic_files[0]
        epic_id = read_frontmatter_id(epic_path)
        if not epic_id:
            raise SystemExit("Epic id missing.")

        run(
            [
                python,
                str(create_item),
                "--items-root",
                str(items_root),
                "--type",
                "Task",
                "--title",
                "Demo Task",
                "--prefix",
                "DM",
                "--parent",
                epic_id,
            ]
        )

        task_files = [path for path in (items_root / "tasks").rglob("*.md")]
        if len(task_files) != 1:
            raise SystemExit("Expected exactly one Task item.")
        task_path = task_files[0]
        task_id = read_frontmatter_id(task_path)
        if not task_id:
            raise SystemExit("Task id missing.")

        result = run(
            [python, str(validate_ready), "--item", str(task_path)],
            expect_ok=False,
            show_output=False,
        )
        if result.returncode == 0:
            raise SystemExit("Expected Ready gate failure for empty sections.")

        fill_ready_sections(task_path)
        run([python, str(validate_ready), "--item", str(task_path)])

        run([python, str(update_state), "--item", str(task_path), "--action", "start"])
        updated = task_path.read_text(encoding="utf-8")
        if "state: InProgress" not in updated:
            raise SystemExit("State not updated to InProgress.")
        if "State -> InProgress." not in updated:
            raise SystemExit("Worklog entry missing for InProgress.")

        view_path = backlog_root / "views" / "new.md"
        run(
            [
                python,
                str(generate_view),
                "--items-root",
                str(items_root),
                "--groups",
                "New",
                "--title",
                "New Work",
                "--output",
                str(view_path),
                "--source-label",
                "backlog/items",
            ]
        )
        output = view_path.read_text(encoding="utf-8")
        if epic_id not in output:
            raise SystemExit("Epic not found in generated New view.")

        run([python, str(update_state), "--item", str(task_path), "--action", "done"])
        done_view = backlog_root / "views" / "done.md"
        run(
            [
                python,
                str(generate_view),
                "--items-root",
                str(items_root),
                "--groups",
                "Done",
                "--title",
                "Done Work",
                "--output",
                str(done_view),
                "--source-label",
                "backlog/items",
            ]
        )
        done_output = done_view.read_text(encoding="utf-8")
        if task_id not in done_output:
            raise SystemExit("Task not found in generated Done view.")
    finally:
        if args.keep_temp:
            print(f"Kept temp data at {test_root}")
        else:
            shutil.rmtree(test_root, ignore_errors=True)
            if test_root.exists():
                print(f"Warning: temp directory not removed: {test_root}")

    print("All script smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
