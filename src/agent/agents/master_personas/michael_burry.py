# -*- coding: utf-8 -*-
"""Burry-inspired contrarian / deep-value lens (Sprint 1A).

Source of framework tenets: adapted from
``~/reference_repos/ai-hedge-fund/src/agents/michael_burry.py``.
Rewritten to inspired-lens framing (analyst applies the lens, never first
person).
"""

from __future__ import annotations

from src.agent.agents.master_personas.base_persona import BasePersonaLens


class MichaelBurryLens(BasePersonaLens):
    persona_id = "michael_burry"
    display_en = "Burry-inspired contrarian lens"
    display_zh = "Burry 式逆向视角"
    avatar_initials = "MB"
    avatar_color = "#B91C1C"  # red-700 — locked decision §13

    lens_preamble = (
        "Hard-number deep value with downside-first scepticism and a "
        "contrarian read of consensus narrative."
    )

    tenets = [
        "Hunt for deep value via hard cash-flow metrics — free cash flow "
        "yield, EV/EBIT, balance-sheet quality. Tangible numbers outrank "
        "narrative.",
        "Be contrarian about consensus: press hatred can be a tailwind "
        "when fundamentals are intact, and consensus love is a yellow "
        "flag when leverage is rising.",
        "Lead with downside risk — avoid leveraged balance sheets, watch "
        "for dilution and refinancing walls; weigh hard catalysts (insider "
        "buying, buybacks, asset sales) as decisive evidence.",
    ]

    out_of_scope_guard = (
        "Pure narrative / momentum names with no FCF, no asset coverage, "
        "and no measurable catalyst lie outside this lens's evidence "
        "model. In those cases issue verdict=\"hold\" with the scope "
        "rationale stated explicitly."
    )

    @classmethod
    def _associated_person(cls) -> str:
        return "Michael Burry"

    @classmethod
    def _associated_person_short(cls) -> str:
        return "Michael Burry"
