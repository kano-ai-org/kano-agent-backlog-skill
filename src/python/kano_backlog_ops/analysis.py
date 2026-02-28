"""
analysis.py - Optional LLM analysis generation over deterministic reports.

This module generates analysis prompts and templates when analysis.llm.enabled
is set in the configuration. Analysis files are derived artifacts stored under
views/snapshots/_analysis/.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


PERSONAS = {"developer", "pm", "qa"}


@dataclass
class AnalysisResult:
    """Result of generating analysis files."""

    prompt_path: Path
    template_path: Path
    persona: str


def generate_analysis_for_report(
    *,
    report_path: Path,
    persona: str,
    output_dir: Path,
) -> AnalysisResult:
    """
    Generate analysis prompt and template for a deterministic report.

    Args:
        report_path: Path to the deterministic Report_<persona>.md snapshot
        persona: One of developer/pm/qa
        output_dir: Directory to write _analysis files (typically views/snapshots/_analysis)

    Returns:
        AnalysisResult with paths to generated prompt and template files
    """
    if persona not in PERSONAS:
        raise ValueError(f"Invalid persona: {persona} (allowed: {', '.join(PERSONAS)})")

    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    report_md = report_path.read_text(encoding="utf-8")
    prompt = _build_prompt(persona, report_md)
    template = _build_template(persona, report_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    
    prompt_path = output_dir / f"Report_{persona}_analysis_prompt.md"
    template_path = output_dir / f"Report_{persona}_LLM.md"

    prompt_path.write_text(prompt, encoding="utf-8")
    template_path.write_text(template, encoding="utf-8")

    return AnalysisResult(
        prompt_path=prompt_path,
        template_path=template_path,
        persona=persona,
    )


def _build_prompt(persona: str, report_md: str) -> str:
    """Build a deterministic analysis prompt for the given persona."""
    focus_map = {
        "developer": "technical progress, blockers, concrete next steps, and verification commands",
        "pm": "scope, risks, dependencies, prioritization signals, and decision points",
        "qa": "potential bugs, test ideas, verification checklist, and regression risks",
    }
    focus = focus_map[persona]

    return f"""# LLM Analysis Prompt ({persona})

You are writing a short *analysis* section for a project status report.

**Persona focus**: {persona} ({focus})

## Strict rules

1) **ONLY use facts that appear in the provided report content.** Do not invent items, states, counts, or commands.
2) If information is missing, say "Unknown from the report" and suggest what to capture in backlog to make it known.
3) Output **MUST** be Markdown.
4) Keep it concise (max ~200 lines).

## Required sections

Use these exact headings:

### Key Observations
### Risks / Unknowns
### Recommendations (Actionable)

## Report content (SSOT)

---
{report_md}
---

## Instructions

Generate the analysis section based ONLY on the report above. Do not add facts not present in the report.
Output should be ready to paste into the Report_{persona}_LLM.md template.
"""


def _build_template(persona: str, report_path: Path) -> str:
    """Build analysis template with placeholder sections."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    return f"""# Report + LLM Analysis ({persona})

- Generated: {now}
- Source report: `{report_path.as_posix()}`

> This section is a **derived artifact** for persona `{persona}`.
> It must be grounded ONLY in the report above (SSOT). If something isn't in the report, state it as unknown.

## LLM Analysis

### Key Observations

- _TODO: summarize what the report actually says (no new facts)._

### Risks / Unknowns

- _TODO: list unknowns; suggest what to capture in backlog/worklog._

### Recommendations (Actionable)

- _TODO: propose concrete next steps and verification commands, only if supported by the report._

---

> **Note**: No LLM command configured. Fill in the template above using the deterministic prompt:
> `Report_{persona}_analysis_prompt.md`
"""


def generate_all_persona_analyses(
    *,
    snapshots_dir: Path,
    output_dir: Path,
    personas: Optional[List[str]] = None,
) -> List[AnalysisResult]:
    """
    Generate analysis files for all available persona reports.

    Args:
        snapshots_dir: Directory containing snapshot.report_<persona>.md files
        output_dir: Directory to write _analysis files
        personas: List of personas to generate (default: all available)

    Returns:
        List of AnalysisResult for successfully generated analyses
    """
    if personas is None:
        personas = list(PERSONAS)
    
    results = []
    for persona in personas:
        report_name = f"snapshot.report_{persona}.md"
        report_path = snapshots_dir / report_name
        
        if not report_path.exists():
            continue
        
        try:
            result = generate_analysis_for_report(
                report_path=report_path,
                persona=persona,
                output_dir=output_dir,
            )
            results.append(result)
        except Exception:
            # Skip personas that fail; at least generate the others
            continue
    
    return results
