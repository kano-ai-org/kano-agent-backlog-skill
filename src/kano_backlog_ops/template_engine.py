"""
template_engine.py - Minimal zero-dependency template engine.

Supports:
- {{ variable }} replacement (nested access via dot notation)
- {{#each list}} ... {{/each}} looping
- {{#if (eq a b)}} conditional (basic) or just {{#if variable}}
- {{#unless variable}} ... {{/unless}} inverse conditional
"""

import re
from collections import ChainMap
from dataclasses import dataclass
from typing import Any, Dict, Match, Optional, Tuple

class TemplateEngine:
    def __init__(self):
        pass

    def render(self, template: str, context: Dict[str, Any]) -> str:
        """Render a template with a Handlebars-like subset (nested blocks supported)."""
        return self._render_segment(template, ChainMap(context), depth=0)

    @dataclass(frozen=True)
    class _Tag:
        raw: str
        start: int
        end: int  # index right after "}}"

    def _render_segment(self, template: str, context: ChainMap[str, Any], *, depth: int) -> str:
        if depth > 50:
            # Prevent runaway recursion on malformed templates.
            return template

        out: list[str] = []
        idx = 0
        while True:
            tag = self._find_next_tag(template, idx)
            if tag is None:
                out.append(template[idx:])
                break

            out.append(template[idx:tag.start])
            raw = tag.raw.strip()

            if raw.startswith("#each "):
                key = raw[len("#each ") :].strip()
                inner, next_idx = self._extract_block(template, tag.end, block_name="each")
                items = self._get_value(context, key)
                if isinstance(items, list):
                    for item in items:
                        overlay: dict[str, Any] = {"this": item}
                        if isinstance(item, dict):
                            overlay.update(item)
                        out.append(self._render_segment(inner, context.new_child(overlay), depth=depth + 1))
                idx = next_idx
                continue

            if raw.startswith("#if "):
                cond = raw[len("#if ") :].strip()
                inner, next_idx = self._extract_block(template, tag.end, block_name="if")
                if self._eval_condition(cond, context):
                    out.append(self._render_segment(inner, context, depth=depth + 1))
                idx = next_idx
                continue

            if raw.startswith("#unless "):
                key = raw[len("#unless ") :].strip()
                inner, next_idx = self._extract_block(template, tag.end, block_name="unless")
                val = self._get_value(context, key)
                if not bool(val):
                    out.append(self._render_segment(inner, context, depth=depth + 1))
                idx = next_idx
                continue

            if raw.startswith("/"):
                # Stray closing tag: omit from output to keep rendered docs clean.
                idx = tag.end
                continue

            out.append(self._render_var(raw, context))
            idx = tag.end

        return "".join(out)

    def _render_var(self, key: str, context: ChainMap[str, Any]) -> str:
        if key == "this":
            return str(context.get("this", ""))
        val = self._get_value(context, key)
        return "" if val is None else str(val)

    def _find_next_tag(self, text: str, start: int) -> Optional[_Tag]:
        open_idx = text.find("{{", start)
        if open_idx == -1:
            return None
        close_idx = text.find("}}", open_idx + 2)
        if close_idx == -1:
            return None
        return self._Tag(raw=text[open_idx + 2 : close_idx], start=open_idx, end=close_idx + 2)

    def _extract_block(self, text: str, start_idx: int, *, block_name: str) -> Tuple[str, int]:
        """
        Return (inner_text, next_idx_after_close) for a block.

        Supports nesting of the same block type (e.g., nested each inside each).
        """
        open_tag = f"#{block_name}"
        close_tag = f"/{block_name}"
        depth = 1
        scan = start_idx
        while True:
            tag = self._find_next_tag(text, scan)
            if tag is None:
                # Malformed template: treat the rest as inner content.
                return text[start_idx:], len(text)

            raw = tag.raw.strip()
            if raw.startswith(open_tag + " "):
                depth += 1
            elif raw == close_tag:
                depth -= 1
                if depth == 0:
                    return text[start_idx:tag.start], tag.end

            scan = tag.end

    _EQ_RE = re.compile(r'^\(eq\s+([\w\.\[\]]+)\s+"([^"]*)"\s*\)$')

    def _eval_condition(self, cond: str, context: ChainMap[str, Any]) -> bool:
        match = self._EQ_RE.match(cond)
        if match:
            key = match.group(1)
            target_val = match.group(2)
            return str(self._get_value(context, key)) == target_val
        val = self._get_value(context, cond)
        return bool(val)

    def _get_value(self, context: ChainMap[str, Any], path: str) -> Any:
        """Get value from context using dot notation."""
        parts = path.split('.')
        curr: Any = context
        try:
            for part in parts:
                # Handle array access [0]
                if part.endswith(']') and '[' in part:
                    p_name = part.split('[')[0]
                    idx = int(part.split('[')[1].rstrip(']'))
                    if p_name:
                         curr = curr[p_name]
                    curr = curr[idx]
                else:
                    if hasattr(curr, "get"):
                        curr = curr.get(part)
                    else:
                        return None
                
                if curr is None:
                    return None
            return curr
        except Exception:
            return None
