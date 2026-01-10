from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

PLAN_AUTO_BEGIN = "<!-- WORKSET:AUTO:BEGIN -->"
PLAN_AUTO_END = "<!-- WORKSET:AUTO:END -->"
PLAN_CUSTOM_BEGIN = "<!-- WORKSET:CUSTOM:BEGIN -->"
PLAN_CUSTOM_END = "<!-- WORKSET:CUSTOM:END -->"
DEFAULT_CUSTOM_BLOCK = "- [ ] Add agent-specific checklist items"
SECTION_RE = re.compile(r"^(#+)\s+(.*)$")
DECISION_RE = re.compile(r"^\s*Decision\s*:\s*(.*)$", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*[-*+]\s*(\[[ xX]?\])?\s*(.+)$")
NUMBER_RE = re.compile(r"^\s*\d+\.\s*(.+)$")


@dataclass
class DecisionBlock:
    headline: str
    body: str


def split_sections(body: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current = "Preamble"
    buffer: List[str] = []

    def flush(name: str) -> None:
        if not buffer:
            return
        text = "\n".join(buffer).strip()
        buffer.clear()
        if not text:
            return
        if name.lower() == "worklog":
            return
        sections[name] = text

    for raw in body.splitlines():
        stripped = raw.strip()
        match = SECTION_RE.match(stripped)
        if match:
            flush(current)
            title = match.group(2).strip() or current
            current = title
            continue
        buffer.append(raw)

    flush(current)
    return sections


def find_section(sections: Dict[str, str], candidates: List[str]) -> Optional[str]:
    lower_map = {name.lower(): text for name, text in sections.items()}
    for candidate in candidates:
        text = lower_map.get(candidate.lower())
        if text:
            return text
    return None


def _format_block(text: Optional[str], fallback: str) -> List[str]:
    if not text:
        return [fallback]
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    return lines or [fallback]


def _derive_tasks(section_text: Optional[str], placeholder: str) -> List[str]:
    if not section_text:
        return [f"- [ ] {placeholder}"]

    tasks: List[str] = []
    for raw in section_text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        bullet = BULLET_RE.match(stripped)
        if bullet:
            tasks.append(f"- [ ] {bullet.group(2).strip()}")
            continue
        number = NUMBER_RE.match(stripped)
        if number:
            tasks.append(f"- [ ] {number.group(1).strip()}")
            continue
        tasks.append(f"- [ ] {stripped}")
    return tasks or [f"- [ ] {placeholder}"]


def extract_custom_block(plan_text: str) -> Optional[str]:
    start = plan_text.find(PLAN_CUSTOM_BEGIN)
    end = plan_text.find(PLAN_CUSTOM_END)
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = plan_text[start + len(PLAN_CUSTOM_BEGIN):end].strip()
    return snippet or None


def build_plan_text(
    *,
    item_id: str,
    title: str,
    item_type: str,
    state: str,
    priority: Optional[str],
    owner: Optional[str],
    iteration: Optional[str],
    tags: List[str],
    rel_path: str,
    updated: Optional[str],
    sections: Dict[str, str],
    custom_block: Optional[str] = None,
) -> str:
    context = find_section(sections, ["Context"])
    goal = find_section(sections, ["Goal", "Goals"])
    approach = find_section(sections, ["Approach", "Plan", "Implementation Plan"])
    acceptance = find_section(
        sections,
        ["Acceptance Criteria", "Acceptance", "Definition of Done"],
    )
    risks = find_section(
        sections,
        ["Risks / Dependencies", "Risks & Dependencies", "Risks", "Dependencies"],
    )

    lines: List[str] = []
    lines.append(f"# Workset Plan — {item_id} {title}")
    lines.append("")
    lines.append(PLAN_AUTO_BEGIN)
    lines.append(f"> Source: {rel_path}")
    lines.append("")
    lines.append("## Snapshot")
    lines.append(f"- Type: {item_type or 'Unknown'}")
    lines.append(f"- State: {state or 'Unknown'}")
    lines.append(f"- Priority: {priority or 'n/a'}")
    lines.append(f"- Owner: {owner or 'unassigned'}")
    if iteration:
        lines.append(f"- Iteration: {iteration}")
    if tags:
        lines.append(f"- Tags: {', '.join(tags)}")
    lines.append(f"- Last Updated: {updated or 'n/a'}")
    lines.append("")

    lines.append("## Context Highlights")
    lines.extend(_format_block(context, "_No Context section found._"))
    lines.append("")

    lines.append("## Goal")
    lines.extend(_format_block(goal, "_No Goal section found._"))
    lines.append("")

    lines.append("## Approach Checklist")
    lines.extend(_derive_tasks(approach, "Clarify approach steps"))
    lines.append("")

    lines.append("## Acceptance Criteria")
    lines.extend(_derive_tasks(acceptance, "Review acceptance criteria"))
    lines.append("")

    lines.append("## Risks / Dependencies")
    lines.extend(_format_block(risks, "_No risks documented._"))
    lines.append("")
    lines.append(PLAN_AUTO_END)
    lines.append("")

    lines.append("## Custom Checklist")
    lines.append(PLAN_CUSTOM_BEGIN)
    block = (custom_block or DEFAULT_CUSTOM_BLOCK).strip()
    lines.append(block if block else DEFAULT_CUSTOM_BLOCK)
    lines.append(PLAN_CUSTOM_END)
    lines.append("")

    return "\n".join(lines)


def extract_decision_blocks(text: str) -> List[DecisionBlock]:
    if not text:
        return []
    lines = text.splitlines()
    blocks: List[DecisionBlock] = []
    i = 0
    while i < len(lines):
        match = DECISION_RE.match(lines[i])
        if not match:
            i += 1
            continue
        headline = match.group(1).strip()
        collected: List[str] = [headline] if headline else []
        j = i + 1
        while j < len(lines):
            candidate = lines[j]
            if DECISION_RE.match(candidate):
                break
            stripped = candidate.strip()
            if stripped.startswith("#"):
                break
            if stripped:
                collected.append(stripped)
            j += 1
        body = "\n".join(collected).strip()
        if body:
            blocks.append(DecisionBlock(headline=headline or "Decision", body=body))
        i = j
    return blocks
