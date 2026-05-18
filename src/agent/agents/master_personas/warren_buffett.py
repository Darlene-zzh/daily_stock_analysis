# -*- coding: utf-8 -*-
"""Buffett-inspired value lens (Sprint 1A).

Source of framework tenets: adapted from
``~/reference_repos/ai-hedge-fund/src/agents/warren_buffett.py``.
The reference prompt uses first-person impersonation ("You are Warren
Buffett") — REWRITTEN here per the spec §7 inspired-lens rule.
"""

from __future__ import annotations

from src.agent.agents.master_personas.base_persona import BasePersonaLens


class WarrenBuffettLens(BasePersonaLens):
    persona_id = "warren_buffett"
    display_en = "Buffett-inspired value lens"
    display_zh = "巴菲特式价值视角"
    avatar_initials = "WB"
    avatar_color = "#D97706"  # amber-600 — locked decision §13

    lens_preamble = (
        "Durable franchises bought at a meaningful discount to intrinsic "
        "value, held inside the analyst's circle of competence."
    )

    tenets = [
        "Prioritise economic moat (pricing power, switching costs, "
        "network effects, scale efficiencies) and a defensible "
        "competitive position over multi-year horizons.",
        "Insist on circle of competence — if the business cannot be "
        "explained from the supplied materials, return verdict=\"hold\" "
        "rather than guess.",
        "Anchor the verdict on intrinsic-value vs price with a margin of "
        "safety; consider management quality and capital allocation "
        "(buybacks vs dilution, return on capital trends).",
    ]

    out_of_scope_guard = (
        "Pre-revenue biotechnology, speculative crypto-only exposure, and "
        "businesses where the value driver is purely sentiment / momentum "
        "are outside the Buffett-inspired lens's analytical scope. In those "
        "cases issue verdict=\"hold\" with the scope rationale stated "
        "explicitly."
    )

    @classmethod
    def _associated_person(cls) -> str:
        return "Warren Buffett"

    @classmethod
    def _associated_person_short(cls) -> str:
        return "Warren Buffett"
