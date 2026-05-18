# -*- coding: utf-8 -*-
"""Master-persona registry for the Investment Committee (Sprint 1A).

Every persona is implemented as a small object exposing:
- ``persona_id``     (snake_case English, also the internal schema value)
- ``display_en``     (English "inspired lens" name)
- ``display_zh``     (Chinese parenthetical for first mention in zh mode)
- ``avatar_initials``  + ``avatar_color`` (Web component palette;
  imported by ``CommitteeMinutesPanel`` via a mirror in
  ``apps/dsa-web/src/utils/personaDisplay.ts``)
- ``system_prompt(ctx)`` and ``build_user_message(ctx, *, report_json, tool_summary)``

The personas DELIBERATELY do not subclass ``BaseAgent`` — the orchestrator
drives the LLM call directly so it can enforce the
:class:`LLMCallBudget` cap and the strict-parse + 1-retry contract.

**Product safety rule (spec §7):** every system prompt uses *inspired-lens*
framing.  The LLM is "an analyst applying the X-inspired lens", NOT the real
person.  First-person impersonation is explicitly forbidden.
"""

from __future__ import annotations

from typing import Dict, List, Type

from src.agent.agents.master_personas.warren_buffett import WarrenBuffettLens
from src.agent.agents.master_personas.michael_burry import MichaelBurryLens
from src.agent.agents.master_personas.cathie_wood import CathieWoodLens
from src.agent.agents.master_personas.nassim_taleb import NassimTalebLens
from src.agent.agents.master_personas.base_persona import BasePersonaLens

__all__ = [
    "BasePersonaLens",
    "WarrenBuffettLens",
    "MichaelBurryLens",
    "CathieWoodLens",
    "NassimTalebLens",
    "PERSONA_REGISTRY",
    "PERSONA_DISPLAY",
    "DEFAULT_PERSONA_ORDER",
    "get_persona_class",
]


PERSONA_REGISTRY: Dict[str, Type[BasePersonaLens]] = {
    WarrenBuffettLens.persona_id: WarrenBuffettLens,
    MichaelBurryLens.persona_id: MichaelBurryLens,
    CathieWoodLens.persona_id: CathieWoodLens,
    NassimTalebLens.persona_id: NassimTalebLens,
}


# Single source of truth — imported by orchestrator, renderer, and (mirror)
# by the Web component to avoid string duplication across layers.
PERSONA_DISPLAY: Dict[str, Dict[str, str]] = {
    cls.persona_id: {
        "display_en": cls.display_en,
        "display_zh": cls.display_zh,
        "avatar_initials": cls.avatar_initials,
        "avatar_color": cls.avatar_color,
    }
    for cls in PERSONA_REGISTRY.values()
}


# Ordered list — orchestrator uses this for deterministic fan-out / test
# snapshot stability.
DEFAULT_PERSONA_ORDER: List[str] = [
    "warren_buffett",
    "michael_burry",
    "cathie_wood",
    "nassim_taleb",
]


def get_persona_class(persona_id: str) -> Type[BasePersonaLens]:
    """Return the persona class registered under ``persona_id``.

    Raises :class:`KeyError` if the id is unknown — keep callers honest;
    unknown ids are a programmer bug, not a runtime fallback case.
    """
    return PERSONA_REGISTRY[persona_id]
