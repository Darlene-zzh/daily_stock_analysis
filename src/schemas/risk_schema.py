# -*- coding: utf-8 -*-
"""Sprint 4 — :class:`RiskAssessment` promoted out of ``committee_schema``.

This module is the single source of truth for the Risk Manager's structured
output.  Sprint 1A introduced a smaller version inline in
:mod:`src.schemas.committee_schema` for the Investment Committee; Sprint 4
extends it with quant-style fields (suggested position %, tail-risk score,
parametric VaR) and exposes the schema for **independent** use outside the
committee (e.g. the default-pipeline ``risk_assessment`` attached to a stock
report when ``enable_structured_risk=True``).

Backward compatibility:

- The legacy field set (``severity / red_flags / suggested_position_pct /
  veto / status / error_summary``) is preserved unchanged so committee code
  paths and existing renderers keep working.
- The new fields default to ``None`` when not computable so old payloads
  parse cleanly.
- :mod:`src.schemas.committee_schema` re-exports the symbol so its public
  surface (``from src.schemas.committee_schema import RiskAssessment``)
  continues to resolve.

Severity contract (unchanged from Sprint 1A):

- ``none``  — no material risks identified
- ``soft``  — material concerns; downstream may downgrade verdict one notch
- ``hard``  — existential / regulatory / liquidity issue; veto buy
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SEVERITY_VALUES = ("none", "soft", "hard")
"""Allowed values for :attr:`RiskAssessment.severity`.  Re-exported by
:mod:`src.schemas.committee_schema` for back-compat."""


class RiskAssessment(BaseModel):
    """Structured Risk Manager output.

    Used in two contexts:

    1. **Committee mode** — wired into ``CommitteeMinutes.risk`` by the
       LangGraph orchestrator.  Severity drives the PM verdict cap.
    2. **Standalone mode** (Sprint 4) — when ``enable_structured_risk=True``
       the default analysis pipeline runs the existing :class:`RiskAgent`
       and exposes its structured fields on ``response['risk_assessment']``
       without engaging the full committee.  Severity is informational
       only in this mode.

    The legacy fields (``severity``, ``red_flags``, ``suggested_position_pct``,
    ``veto``, ``status``, ``error_summary``) keep their Sprint 1A semantics
    so committee code and the existing renderers continue to work.
    """

    model_config = ConfigDict(extra="ignore")

    # ----- legacy Sprint 1A fields (unchanged) ----- #
    severity: Optional[Literal["none", "soft", "hard"]] = None
    red_flags: List[str] = Field(default_factory=list)
    suggested_position_pct: Optional[float] = None  # 0..1
    veto: bool = False
    status: Literal["ok", "failed"] = "ok"
    error_summary: Optional[str] = None

    # ----- Sprint 4 extensions ----- #
    tail_risk_score: Optional[float] = Field(
        default=None,
        description=(
            "0..10 — heuristic ranking of how exposed the position is to a "
            "single low-probability / high-impact event (lock-up expiry, "
            "earnings miss, regulatory crackdown). Higher = more fragile."
        ),
    )
    var_estimate_5pct: Optional[float] = Field(
        default=None,
        description=(
            "5%% 1-day parametric Value-at-Risk expressed as a positive "
            "fractional loss (e.g. 0.038 = a 3.8%% drop). Computed from a "
            "60-day rolling close-to-close return when price history is "
            "available; ``None`` otherwise."
        ),
    )
    volatility_annualised: Optional[float] = Field(
        default=None,
        description=(
            "Annualised 60-day volatility (sqrt(252) × daily std). Surfaced "
            "for transparency: the ``suggested_position_pct`` should react "
            "to this number, so making it visible defends the verdict."
        ),
    )
    rationale: Optional[str] = Field(
        default=None,
        description=(
            "One- to two-sentence narrative explaining how the structured "
            "fields were derived. Optional — defaults to None when the "
            "Risk Agent could not produce one."
        ),
    )


# Default object used when the structured-risk path fails — keeps callers
# defensive against ``None`` shapes.
def empty_risk_assessment(error_summary: Optional[str] = None) -> RiskAssessment:
    return RiskAssessment(
        status="failed" if error_summary else "ok",
        error_summary=(error_summary or None),
    )


__all__ = [
    "RiskAssessment",
    "SEVERITY_VALUES",
    "empty_risk_assessment",
]
