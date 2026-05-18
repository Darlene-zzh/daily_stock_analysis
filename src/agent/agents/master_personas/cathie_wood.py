# -*- coding: utf-8 -*-
"""Cathie Wood-inspired innovation / disruption lens (Sprint 1A).

Source of framework tenets: adapted from
``~/reference_repos/ai-hedge-fund/src/agents/cathie_wood.py``.
Rewritten to inspired-lens framing (analyst applies the lens, never first
person).
"""

from __future__ import annotations

from src.agent.agents.master_personas.base_persona import BasePersonaLens


class CathieWoodLens(BasePersonaLens):
    persona_id = "cathie_wood"
    display_en = "Cathie Wood-inspired innovation lens"
    display_zh = "Cathie Wood 式创新成长视角"
    avatar_initials = "CW"
    avatar_color = "#4338CA"  # indigo-700 — locked decision §13

    lens_preamble = (
        "Disruptive-innovation winners trading below a defensible long-term "
        "TAM-and-share trajectory; willing to accept volatility for "
        "exponential payoffs."
    )

    tenets = [
        "Identify disruptive innovation — platform shifts, declining cost "
        "curves, network effects with exponential growth potential rather "
        "than incremental improvement.",
        "Reward sustained R&D intensity, expanding gross margins, and "
        "operating leverage that compounds with scale; tolerate near-term "
        "GAAP losses if unit economics are improving.",
        "Anchor to a long horizon (5+ years) — judge price against an "
        "explicit TAM × share × margin path, not next quarter's EPS.",
    ]

    out_of_scope_guard = (
        "Mature commodity businesses, cyclical financials with no "
        "innovation vector, and slow-growing utilities do not match this "
        "lens's selection criteria. In those cases issue verdict=\"hold\" "
        "with the scope rationale stated explicitly."
    )

    @classmethod
    def _associated_person(cls) -> str:
        return "Cathie Wood"

    @classmethod
    def _associated_person_short(cls) -> str:
        return "Cathie Wood"
