# -*- coding: utf-8 -*-
"""
Investment Committee schemas (Sprint 1A).

These Pydantic v2 models describe the artefacts that the multi-agent
Investment Committee produces:

- :class:`DebateExchange`     — one Bull / Bear utterance
- :class:`MasterOpinion`      — one master-persona lens verdict
- :class:`RiskAssessment`     — Risk Manager output
- :class:`CommitteeMinutes`   — top-level committee record

Strictness tiers (spec §6, locked decision):

- **Critical fields** are enforced via the ``parse_*_strict`` helpers; missing
  or invalid critical fields raise :class:`CommitteeSchemaError` so the
  orchestrator can trigger a 1-retry with the schema embedded as a JSON
  example.
- **Non-critical fields** are optional or default-empty; missing → leave empty,
  do NOT retry.
- After the retry budget is exhausted the orchestrator should emit a fallback
  object via ``failed_*()`` helpers carrying ``status="failed"`` plus an
  ``error_summary`` — callers must never raise from a parse miss in
  production code.

Status semantics on the top-level :class:`CommitteeMinutes`:

- ``ok``       — all 4 masters + risk + PM completed, no missing agents
- ``partial``  — ≥ 1 missing agent OR ≥ 1 master ``status="failed"`` but PM
  still issued a verdict
- ``failed``   — PM itself could not produce a verdict; treat the whole record
  as advisory only.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ============================================================
# Constants
# ============================================================

PERSONA_IDS = ("warren_buffett", "michael_burry", "cathie_wood", "nassim_taleb")
VERDICT_VALUES = ("strong_buy", "buy", "hold", "avoid", "short")
SIDE_VALUES = ("bull", "bear")
MASTER_STATUS_VALUES = ("ok", "failed", "budget_exhausted")
RISK_STATUS_VALUES = ("ok", "failed")
MINUTES_STATUS_VALUES = ("ok", "partial", "failed")
SEVERITY_VALUES = ("none", "soft", "hard")


# ============================================================
# Errors
# ============================================================


class CommitteeSchemaError(ValueError):
    """Raised when a critical field is missing or invalid on first parse.

    The orchestrator catches this exception, embeds the schema as a JSON
    example in the user message, and retries the LLM call once.  If the
    retry also fails the caller must construct a fallback object via the
    matching ``failed_*`` helper — never re-raise into production code.
    """

    def __init__(self, message: str, schema: str, raw: Optional[str] = None) -> None:
        super().__init__(message)
        self.schema = schema
        self.raw = raw


# ============================================================
# DebateExchange
# ============================================================


class DebateExchange(BaseModel):
    """One Bull or Bear utterance during the debate phase."""

    model_config = ConfigDict(extra="ignore")

    side: Optional[Literal["bull", "bear"]] = None
    round_index: Optional[int] = None
    claim: Optional[str] = None
    evidence: List[str] = Field(default_factory=list)
    rebuttal_to: Optional[str] = None
    confidence: Optional[float] = None

    # Top-level status helps downstream code surface failures without
    # inspecting field-by-field.
    status: Literal["ok", "failed"] = "ok"
    error_summary: Optional[str] = None


# ============================================================
# MasterOpinion
# ============================================================


class MasterOpinion(BaseModel):
    """A single master-persona lens verdict."""

    model_config = ConfigDict(extra="ignore")

    persona: Optional[Literal["warren_buffett", "michael_burry", "cathie_wood", "nassim_taleb"]] = None
    verdict: Optional[Literal["strong_buy", "buy", "hold", "avoid", "short"]] = None
    score: Optional[float] = None
    headline: Optional[str] = None
    rationale: Optional[str] = None
    key_evidence: List[str] = Field(default_factory=list)
    counter_view: Optional[str] = None
    tools_used: List[str] = Field(default_factory=list)
    status: Literal["ok", "failed", "budget_exhausted"] = "ok"
    error_summary: Optional[str] = None


# ============================================================
# RiskAssessment
# ============================================================


class RiskAssessment(BaseModel):
    """Risk Manager structured output (wraps existing :class:`RiskAgent`)."""

    model_config = ConfigDict(extra="ignore")

    severity: Optional[Literal["none", "soft", "hard"]] = None
    red_flags: List[str] = Field(default_factory=list)
    suggested_position_pct: Optional[float] = None  # 0..1
    veto: bool = False
    status: Literal["ok", "failed"] = "ok"
    error_summary: Optional[str] = None


# ============================================================
# CommitteeMinutes
# ============================================================


class CommitteeMinutes(BaseModel):
    """Top-level committee minutes; attached as ``report["committee"]``."""

    model_config = ConfigDict(extra="ignore")

    version: Literal["1"] = "1"
    status: Literal["ok", "partial", "failed"] = "ok"
    debate_rounds: int = 0
    debate: List[DebateExchange] = Field(default_factory=list)
    masters: List[MasterOpinion] = Field(default_factory=list)
    risk: Optional[RiskAssessment] = None
    pm_verdict: Optional[Literal["strong_buy", "buy", "hold", "avoid", "short"]] = None
    pm_score: Optional[float] = None
    pm_rationale: Optional[str] = None
    pm_dissents: List[str] = Field(default_factory=list)
    budget_used: int = 0
    budget_cap: int = 12
    missing_agents: List[str] = Field(default_factory=list)
    latency_ms: int = 0
    error_summary: Optional[str] = None


# ============================================================
# Critical-field validators
# ============================================================


def _require(field_name: str, value: Any, allowed: Optional[tuple] = None) -> None:
    if value is None or value == "":
        raise ValueError(f"critical field '{field_name}' is missing")
    if allowed is not None and value not in allowed:
        raise ValueError(
            f"critical field '{field_name}'={value!r} is not one of {allowed!r}"
        )


def _require_score(field_name: str, value: Any, *, lo: float = 0.0, hi: float = 10.0) -> None:
    if value is None:
        raise ValueError(f"critical field '{field_name}' is missing")
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"critical field '{field_name}' is not numeric: {value!r}") from exc
    if not (lo <= n <= hi):
        raise ValueError(
            f"critical field '{field_name}'={n} out of range [{lo}, {hi}]"
        )


def _require_evidence(field_name: str, value: Any, *, min_len: int = 1) -> None:
    if not isinstance(value, list) or len(value) < min_len:
        raise ValueError(
            f"critical field '{field_name}' must be a list of length >= {min_len}"
        )


def _load_json_object(raw: str) -> Dict[str, Any]:
    """Parse ``raw`` into a dict; tolerate markdown fences and stray prose.

    Returns the largest JSON object found in ``raw``.  Raises ValueError on
    no parse.
    """
    if not raw or not isinstance(raw, str):
        raise ValueError("empty LLM response")
    text = raw.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        # remove leading fence line and trailing fence
        text = text.split("\n", 1)[1] if "\n" in text else text
        if "```" in text:
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    # Try direct parse first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Fall back: find the largest curly-brace span
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in response")
    candidate = text[start : end + 1]
    obj = json.loads(candidate)  # may raise JSONDecodeError → ValueError-equivalent
    if not isinstance(obj, dict):
        raise ValueError("parsed JSON is not an object")
    return obj


def parse_master_opinion_strict(raw: str) -> MasterOpinion:
    """Parse a ``MasterOpinion`` enforcing all critical fields.

    Raises :class:`CommitteeSchemaError` if a critical field is missing,
    invalid, or the JSON itself is unparseable.  Non-critical fields are
    accepted as-is (missing → default).
    """
    try:
        obj = _load_json_object(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise CommitteeSchemaError(
            f"failed to parse MasterOpinion JSON: {exc}",
            schema=MASTER_OPINION_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc

    try:
        _require("persona", obj.get("persona"), allowed=PERSONA_IDS)
        _require("verdict", obj.get("verdict"), allowed=VERDICT_VALUES)
        _require_score("score", obj.get("score"))
        _require("headline", obj.get("headline"))
        _require("rationale", obj.get("rationale"))
        _require_evidence("key_evidence", obj.get("key_evidence"))
    except ValueError as exc:
        raise CommitteeSchemaError(
            f"MasterOpinion critical field invalid: {exc}",
            schema=MASTER_OPINION_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc

    try:
        return MasterOpinion(**obj)
    except ValidationError as exc:
        raise CommitteeSchemaError(
            f"MasterOpinion pydantic validation failed: {exc}",
            schema=MASTER_OPINION_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc


def parse_debate_exchange_strict(raw: str, *, expected_side: Optional[str] = None, expected_round: Optional[int] = None) -> DebateExchange:
    """Parse a ``DebateExchange`` enforcing critical fields.

    ``expected_side`` / ``expected_round`` let the orchestrator forcibly
    correct an LLM that mislabels its own utterance.
    """
    try:
        obj = _load_json_object(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise CommitteeSchemaError(
            f"failed to parse DebateExchange JSON: {exc}",
            schema=DEBATE_EXCHANGE_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc

    if expected_side is not None:
        obj.setdefault("side", expected_side)
    if expected_round is not None and obj.get("round_index") is None:
        obj["round_index"] = expected_round

    try:
        _require("side", obj.get("side"), allowed=SIDE_VALUES)
        if obj.get("round_index") is None:
            raise ValueError("critical field 'round_index' is missing")
        _require("claim", obj.get("claim"))
        _require_evidence("evidence", obj.get("evidence"))
    except ValueError as exc:
        raise CommitteeSchemaError(
            f"DebateExchange critical field invalid: {exc}",
            schema=DEBATE_EXCHANGE_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc

    try:
        return DebateExchange(**obj)
    except ValidationError as exc:
        raise CommitteeSchemaError(
            f"DebateExchange pydantic validation failed: {exc}",
            schema=DEBATE_EXCHANGE_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc


def parse_risk_assessment_strict(raw: str) -> RiskAssessment:
    """Parse a ``RiskAssessment`` enforcing critical fields."""
    try:
        obj = _load_json_object(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise CommitteeSchemaError(
            f"failed to parse RiskAssessment JSON: {exc}",
            schema=RISK_ASSESSMENT_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc

    try:
        _require("severity", obj.get("severity"), allowed=SEVERITY_VALUES)
        # suggested_position_pct in [0, 1]
        _require_score(
            "suggested_position_pct",
            obj.get("suggested_position_pct"),
            lo=0.0,
            hi=1.0,
        )
        if "veto" not in obj or not isinstance(obj.get("veto"), bool):
            raise ValueError("critical field 'veto' must be a boolean")
    except ValueError as exc:
        raise CommitteeSchemaError(
            f"RiskAssessment critical field invalid: {exc}",
            schema=RISK_ASSESSMENT_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc

    try:
        return RiskAssessment(**obj)
    except ValidationError as exc:
        raise CommitteeSchemaError(
            f"RiskAssessment pydantic validation failed: {exc}",
            schema=RISK_ASSESSMENT_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc


def parse_committee_minutes_strict(raw: str) -> CommitteeMinutes:
    """Parse top-level :class:`CommitteeMinutes` enforcing critical fields.

    The PM agent emits this; if any critical field is missing the caller is
    expected to retry once, then fall back to ``failed_committee_minutes``.
    """
    try:
        obj = _load_json_object(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise CommitteeSchemaError(
            f"failed to parse CommitteeMinutes JSON: {exc}",
            schema=COMMITTEE_MINUTES_PM_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc

    try:
        _require("status", obj.get("status"), allowed=MINUTES_STATUS_VALUES)
        _require("pm_verdict", obj.get("pm_verdict"), allowed=VERDICT_VALUES)
        _require_score("pm_score", obj.get("pm_score"))
        _require("pm_rationale", obj.get("pm_rationale"))
        if obj.get("budget_used") is None:
            raise ValueError("critical field 'budget_used' is missing")
        if obj.get("budget_cap") is None:
            raise ValueError("critical field 'budget_cap' is missing")
    except ValueError as exc:
        raise CommitteeSchemaError(
            f"CommitteeMinutes critical field invalid: {exc}",
            schema=COMMITTEE_MINUTES_PM_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc

    try:
        return CommitteeMinutes(**obj)
    except ValidationError as exc:
        raise CommitteeSchemaError(
            f"CommitteeMinutes pydantic validation failed: {exc}",
            schema=COMMITTEE_MINUTES_PM_SCHEMA_EXAMPLE,
            raw=raw,
        ) from exc


# ============================================================
# Fallback object factories
# ============================================================


def failed_master_opinion(persona: str, *, error_summary: str) -> MasterOpinion:
    return MasterOpinion(
        persona=persona if persona in PERSONA_IDS else None,
        status="failed",
        error_summary=error_summary[:500] if error_summary else None,
    )


def failed_debate_exchange(side: str, round_index: int, *, error_summary: str) -> DebateExchange:
    return DebateExchange(
        side=side if side in SIDE_VALUES else None,
        round_index=round_index,
        status="failed",
        error_summary=error_summary[:500] if error_summary else None,
    )


def failed_risk_assessment(error_summary: str) -> RiskAssessment:
    return RiskAssessment(
        status="failed",
        error_summary=error_summary[:500] if error_summary else None,
    )


def failed_committee_minutes(
    *,
    debate_rounds: int,
    budget_used: int,
    budget_cap: int,
    error_summary: str,
    missing_agents: Optional[List[str]] = None,
    debate: Optional[List[DebateExchange]] = None,
    masters: Optional[List[MasterOpinion]] = None,
    risk: Optional[RiskAssessment] = None,
    latency_ms: int = 0,
) -> CommitteeMinutes:
    """Construct a ``status='failed'`` minutes object after retry exhaustion.

    The renderer downgrades the verdict card to a "committee inconclusive"
    notice when ``status == 'failed'``.
    """
    return CommitteeMinutes(
        status="failed",
        debate_rounds=debate_rounds,
        debate=list(debate or []),
        masters=list(masters or []),
        risk=risk,
        budget_used=budget_used,
        budget_cap=budget_cap,
        missing_agents=list(missing_agents or []),
        latency_ms=latency_ms,
        error_summary=error_summary[:500] if error_summary else None,
    )


# ============================================================
# JSON schema examples used in retry prompts
# ============================================================


MASTER_OPINION_SCHEMA_EXAMPLE = """{
  "persona": "warren_buffett",
  "verdict": "buy",
  "score": 7.5,
  "headline": "<one analyst-voice sentence>",
  "rationale": "<2-4 analyst-voice sentences>",
  "key_evidence": ["<evidence 1>", "<evidence 2>", "<evidence 3>"],
  "counter_view": "<what would change the verdict>",
  "tools_used": ["ma", "fundamentals_snapshot"]
}"""

DEBATE_EXCHANGE_SCHEMA_EXAMPLE = """{
  "side": "bull",
  "round_index": 1,
  "claim": "<<= 200 char thesis>",
  "evidence": ["<evidence 1>", "<evidence 2>", "<evidence 3>"],
  "rebuttal_to": "<short reference to prior bear claim, or null>",
  "confidence": 0.7
}"""

RISK_ASSESSMENT_SCHEMA_EXAMPLE = """{
  "severity": "soft",
  "red_flags": ["<flag 1>", "<flag 2>"],
  "suggested_position_pct": 0.15,
  "veto": false
}"""

COMMITTEE_MINUTES_PM_SCHEMA_EXAMPLE = """{
  "status": "ok",
  "pm_verdict": "buy",
  "pm_score": 7.2,
  "pm_rationale": "<2-4 sentences explaining the synthesis>",
  "pm_dissents": ["michael_burry"],
  "missing_agents": [],
  "budget_used": 12,
  "budget_cap": 12
}"""
