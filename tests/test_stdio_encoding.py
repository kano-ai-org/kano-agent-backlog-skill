"""
test_stdio_encoding.py - Regression tests for Windows console encoding safety.
"""

from __future__ import annotations

import io
import sys
from typing import TextIO

from kano_backlog_cli.util import configure_stdio


def _make_text_stream(encoding: str, errors: str) -> TextIO:
    buffer = io.BytesIO()
    return io.TextIOWrapper(buffer, encoding=encoding, errors=errors, write_through=True)


def test_configure_stdio_sets_replace_errors_on_windows() -> None:
    if sys.platform != "win32":
        return

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        sys.stdout = _make_text_stream("cp1252", "strict")
        sys.stderr = _make_text_stream("cp1252", "strict")

        configure_stdio()

        assert getattr(sys.stdout, "errors", None) == "replace"
        assert getattr(sys.stderr, "errors", None) == "replace"
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

