#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

sys.dont_write_bytecode = True

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402


PERSONAS = {"developer", "pm", "qa"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an optional LLM analysis section from a deterministic Report_<persona>.md. "
            "This keeps the report as the stable SSOT and appends non-deterministic analysis as a derived artifact."
        )
    )
    parser.add_argument("--report", required=True, help="Input report markdown path.")
    parser.add_argument("--persona", required=True, help="Persona: developer|pm|qa.")
    parser.add_argument("--output", required=True, help="Output markdown path (derived).")
    parser.add_argument(
        "--prompt-output",
        help="Optional path to write the generated prompt (deterministic).",
    )
    parser.add_argument(
        "--llm-command",
        help=(
            "LLM command to execute (avoid putting secrets here; prefer env-based auth). "
            "If omitted, uses env var KANO_LLM_COMMAND."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write prompt (if requested) but do not execute the LLM command.",
    )
    return parser.parse_args()


def normalize_persona(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value not in PERSONAS:
        raise SystemExit(f"Invalid persona: {raw} (allowed: developer, pm, qa)")
    return value


def build_prompt(persona: str, report_md: str) -> str:
    focus = {
        "developer": "technical progress, blockers, concrete next steps, and verification commands",
        "pm": "scope, risks, dependencies, prioritization signals, and decision points",
        "qa": "potential bugs, test ideas, verification checklist, and regression risks",
    }[persona]

    instructions = f"""You are writing a short *analysis* section for a project status report.

Persona focus: {persona} ({focus})

Strict rules:
1) ONLY use facts that appear in the provided report content. Do not invent items, states, counts, or commands.
2) If information is missing, say "Unknown from the report" and suggest what to capture in backlog to make it known.
3) Output MUST be Markdown.
4) Keep it concise (max ~200 lines).

Required sections (use these exact headings):
## LLM Analysis
### Key Observations
### Risks / Unknowns
### Recommendations (Actionable)

Report content (SSOT):
---
{report_md}
---
"""
    return instructions


def build_analysis_template(persona: str, prompt_output: Optional[Path]) -> str:
    prompt_hint = ""
    if prompt_output:
        prompt_hint = f"\n\nPrompt (deterministic): `{prompt_output.as_posix()}`"
    return (
        "## LLM Analysis\n"
        "\n"
        f"> This section is a **derived artifact** for persona `{persona}`.\n"
        "> It must be grounded ONLY in the report above (SSOT). If something isn't in the report, state it as unknown.\n"
        f">{prompt_hint}\n"
        "\n"
        "### Key Observations\n"
        "- _TODO: summarize what the report actually says (no new facts)._ \n"
        "\n"
        "### Risks / Unknowns\n"
        "- _TODO: list unknowns; suggest what to capture in backlog/worklog._\n"
        "\n"
        "### Recommendations (Actionable)\n"
        "- _TODO: propose concrete next steps and verification commands, only if supported by the report._\n"
    )


def main() -> int:
    args = parse_args()
    persona = normalize_persona(args.persona)

    report_path = Path(args.report).resolve()
    if not report_path.exists():
        raise SystemExit(f"Report not found: {report_path}")
    report_md = report_path.read_text(encoding="utf-8")

    prompt = build_prompt(persona, report_md)

    prompt_output = Path(args.prompt_output).resolve() if args.prompt_output else None
    if prompt_output:
        prompt_output.parent.mkdir(parents=True, exist_ok=True)
        prompt_output.write_text(prompt, encoding="utf-8")

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = [
        f"# Report + LLM Analysis ({persona})",
        "",
        f"- Generated: {now}",
        f"- Source report: `{report_path.as_posix()}`",
        "",
    ]

    llm_command = (args.llm_command or os.getenv("KANO_LLM_COMMAND") or "").strip()
    template = build_analysis_template(persona, prompt_output)

    if args.dry_run:
        content = "\n".join(header) + report_md.rstrip() + "\n\n" + template.rstrip() + "\n"
        output_path.write_text(content, encoding="utf-8")
        print(f"Wrote (dry-run): {output_path}")
        return 0

    if not llm_command:
        content = (
            "\n".join(header)
            + report_md.rstrip()
            + "\n\n"
            + template.rstrip()
            + "\n\n"
            + "> Note: No `KANO_LLM_COMMAND` configured, so analysis was not auto-generated.\n"
            + "> Fill in the template above (ideally using the saved prompt) or configure an LLM command and rerun.\n"
        )
        output_path.write_text(content, encoding="utf-8")
        print(f"Wrote (template only): {output_path}")
        return 0

    cmd = shlex.split(llm_command)
    try:
        result = subprocess.run(cmd, input=prompt, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise SystemExit(f"LLM command not found: {cmd[0]}") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        raise SystemExit(stderr or stdout or f"LLM command failed: {llm_command}")

    analysis_md = (result.stdout or "").strip()
    if not analysis_md:
        raise SystemExit("LLM returned empty output.")

    content = "\n".join(header) + report_md.rstrip() + "\n\n" + analysis_md.rstrip() + "\n"
    output_path.write_text(content, encoding="utf-8")
    print(f"Wrote: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
