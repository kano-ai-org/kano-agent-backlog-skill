from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from kano_backlog_cli.cli import app


def test_topic_commands_respect_backlog_root_override(tmp_path: Path) -> None:
    runner = CliRunner()

    main_backlog_root = tmp_path / "_kano" / "backlog"
    sandbox_root = tmp_path / "_kano" / "backlog_sandbox" / "s1"

    # Ensure we don't accidentally write to main backlog.
    (main_backlog_root / "topics").mkdir(parents=True, exist_ok=True)

    cwd_before = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(
            app,
            [
                "topic",
                "--backlog-root-override",
                str(sandbox_root),
                "create",
                "t1",
                "--agent",
                "tester",
            ],
        )
        assert result.exit_code == 0, result.output

        assert (sandbox_root / "topics" / "t1" / "manifest.json").exists()
        assert not (main_backlog_root / "topics" / "t1").exists()
    finally:
        os.chdir(cwd_before)
