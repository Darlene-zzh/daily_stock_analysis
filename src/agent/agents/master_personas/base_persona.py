# -*- coding: utf-8 -*-
"""Base class for master-persona lenses (Sprint 1A).

Subclasses provide the lens-specific tenets (3 bullet points) and a one-line
preamble.  The shared ``system_prompt`` and ``build_user_message`` enforce the
**inspired-lens framing** product safety rule:

- The LLM is an *analyst applying the X-inspired lens*, never the real person.
- Output is third-person analyst voice, e.g. "The position appears…",
  NOT "I, Buffett, see…".
- The persona MUST cite >= 3 specific evidence items.
- Out-of-scope cases return ``verdict="hold"`` with a documented rationale.

Tool exposure for Sprint 1 is the curated five
(``ma`` / ``macd`` / ``boll`` / ``sentiment_aggregator`` / ``fundamentals_snapshot``)
declared in the locked decisions table.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from src.agent.protocols import AgentContext

# Locked decision §13: curated 5 strategy tools for every persona
TOOL_NAMES_SPRINT1: List[str] = [
    "ma",
    "macd",
    "boll",
    "sentiment_aggregator",
    "fundamentals_snapshot",
]


class BasePersonaLens:
    """Shared system-prompt template for the four master lenses."""

    # Subclass overrides ---------------------------------------------------- #

    persona_id: str = "base"
    display_en: str = "Base lens"
    display_zh: str = "基础视角"
    avatar_initials: str = "??"
    avatar_color: str = "#888888"

    # One-line preamble (e.g. "Buffett-inspired value lens — durable
    # franchises bought at a discount to intrinsic value")
    lens_preamble: str = "Lens preamble"

    # Three concise lens tenets
    tenets: List[str] = []

    # Optional out-of-scope guard description, e.g. "Pre-revenue biotech is
    # outside the Buffett-inspired lens's analytical scope."
    out_of_scope_guard: str = ""

    # Tool exposure
    tool_names: List[str] = list(TOOL_NAMES_SPRINT1)

    # ----------------------------------------------------------------- #
    # Prompt construction
    # ----------------------------------------------------------------- #

    @classmethod
    def system_prompt(cls, ctx: AgentContext) -> str:  # noqa: ARG003 — ctx reserved for future contextual tweaks
        tenets_block = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(cls.tenets))
        scope_note = ""
        if cls.out_of_scope_guard:
            scope_note = f"\n\nScope guard:\n{cls.out_of_scope_guard}"

        return (
            "You are a senior equity analyst applying the "
            f"**{cls.display_en}** — the decision framework canonically "
            f"associated with {cls._associated_person()}. You speak as an "
            f"analyst, not as {cls._associated_person_short()} personally; "
            "never use first-person voice impersonating the real person. "
            "Output is in third-person analyst voice "
            "(e.g. \"The position appears…\", NOT \"I, Buffett, see…\").\n"
            "\n"
            "The lens you apply:\n"
            f"{tenets_block}\n"
            f"{scope_note}\n"
            "\n"
            "You will receive: (a) a structured pre-analysis report on the "
            "stock, (b) optionally one or more strategy-tool outputs from "
            "this curated toolbox: "
            "`ma`, `macd`, `boll`, `sentiment_aggregator`, "
            "`fundamentals_snapshot`.\n"
            "\n"
            "You MUST:\n"
            "- Cite at least three concrete pieces of evidence from the "
            "materials provided\n"
            "- Refuse to invent fundamentals you cannot verify in the "
            "supplied context\n"
            "- If the case is outside this lens's analytical scope, return "
            "verdict=\"hold\" and explicitly say so in `rationale`\n"
            "- Output third-person analyst voice; do not impersonate the "
            "real person\n"
            "\n"
            "Output a SINGLE JSON object matching this schema "
            "(no markdown, no commentary outside JSON):\n"
            "{\n"
            f'  "persona": "{cls.persona_id}",\n'
            '  "verdict": "strong_buy" | "buy" | "hold" | "avoid" | "short",\n'
            '  "score": <number 0..10>,\n'
            '  "headline": "<one analyst-voice sentence>",\n'
            '  "rationale": "<2-4 analyst-voice sentences>",\n'
            '  "key_evidence": ["<bullet 1>", "<bullet 2>", "<bullet 3>"],\n'
            '  "counter_view": "<what would change the verdict>",\n'
            '  "tools_used": []\n'
            "}\n"
        )

    @classmethod
    def build_user_message(
        cls,
        ctx: AgentContext,
        *,
        report_json: Dict[str, Any],
        tool_summary: str = "",
    ) -> str:
        """Construct the per-stock user message for the persona LLM call."""
        stock_label = f"{ctx.stock_code}"
        if ctx.stock_name:
            stock_label += f" ({ctx.stock_name})"

        # Truncate report_json — weak models choke on very large contexts
        try:
            report_blob = json.dumps(report_json, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            report_blob = str(report_json)
        if len(report_blob) > 8000:
            report_blob = report_blob[:8000] + "...(truncated)"

        market = (ctx.meta or {}).get("market") or ""

        return (
            f"Stock: {stock_label}\n"
            f"Market: {market}\n"
            "Pre-analysis report (JSON):\n"
            f"{report_blob}\n"
            f"Available tools: {tool_summary or ', '.join(cls.tool_names)}\n"
        )

    # ----------------------------------------------------------------- #
    # Hooks for subclasses (avoid hard-coding names in shared prompt)
    # ----------------------------------------------------------------- #

    @classmethod
    def _associated_person(cls) -> str:
        return "the canonical practitioner of this framework"

    @classmethod
    def _associated_person_short(cls) -> str:
        return "the practitioner"
