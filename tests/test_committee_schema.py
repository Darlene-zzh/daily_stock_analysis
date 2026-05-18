# -*- coding: utf-8 -*-
"""Unit tests for src.schemas.committee_schema (Sprint 1A Task 1A-1).

Covers:
- happy-path strict parsing for MasterOpinion, DebateExchange,
  RiskAssessment, CommitteeMinutes
- missing critical fields → CommitteeSchemaError (triggers orchestrator retry)
- malformed / garbage JSON → CommitteeSchemaError
- failed_* fallback constructors yield status='failed' objects without raising
- markdown-fenced JSON is tolerated
- top-level CommitteeMinutes.status semantics (ok / partial / failed)
"""
from __future__ import annotations

import json
import pytest

from src.schemas.committee_schema import (
    CommitteeMinutes,
    CommitteeSchemaError,
    DebateExchange,
    MasterOpinion,
    RiskAssessment,
    failed_committee_minutes,
    failed_debate_exchange,
    failed_master_opinion,
    failed_risk_assessment,
    parse_committee_minutes_strict,
    parse_debate_exchange_strict,
    parse_master_opinion_strict,
    parse_risk_assessment_strict,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def perfect_master_opinion_json() -> str:
    return json.dumps(
        {
            "persona": "warren_buffett",
            "verdict": "buy",
            "score": 7.5,
            "headline": "Durable moat with modest entry margin",
            "rationale": "The franchise economics remain compelling. Pricing power compounds free cash flow.",
            "key_evidence": [
                "ROE 25% over 5 years",
                "Net margin > 30%",
                "Buybacks reduced share count 4%/yr",
            ],
            "counter_view": "A regulatory shock to category economics",
            "tools_used": ["fundamentals_snapshot"],
        }
    )


@pytest.fixture
def garbage_json() -> str:
    return "this is not JSON and never will be"


# --------------------------------------------------------------------------- #
# MasterOpinion
# --------------------------------------------------------------------------- #


def test_master_opinion_happy_path(perfect_master_opinion_json):
    opinion = parse_master_opinion_strict(perfect_master_opinion_json)
    assert isinstance(opinion, MasterOpinion)
    assert opinion.persona == "warren_buffett"
    assert opinion.verdict == "buy"
    assert opinion.score == 7.5
    assert len(opinion.key_evidence) == 3
    assert opinion.status == "ok"


def test_master_opinion_missing_persona():
    bad = json.dumps(
        {
            "verdict": "buy",
            "score": 7.5,
            "headline": "x",
            "rationale": "x",
            "key_evidence": ["a", "b", "c"],
        }
    )
    with pytest.raises(CommitteeSchemaError) as exc:
        parse_master_opinion_strict(bad)
    assert "persona" in str(exc.value)
    # The error must carry a schema example so the orchestrator can embed it.
    assert exc.value.schema and "persona" in exc.value.schema


def test_master_opinion_invalid_verdict():
    bad = json.dumps(
        {
            "persona": "warren_buffett",
            "verdict": "moon",
            "score": 5,
            "headline": "x",
            "rationale": "x",
            "key_evidence": ["a"],
        }
    )
    with pytest.raises(CommitteeSchemaError):
        parse_master_opinion_strict(bad)


def test_master_opinion_score_out_of_range():
    bad = json.dumps(
        {
            "persona": "warren_buffett",
            "verdict": "buy",
            "score": 99.0,
            "headline": "x",
            "rationale": "x",
            "key_evidence": ["a"],
        }
    )
    with pytest.raises(CommitteeSchemaError):
        parse_master_opinion_strict(bad)


def test_master_opinion_empty_evidence():
    bad = json.dumps(
        {
            "persona": "warren_buffett",
            "verdict": "buy",
            "score": 7,
            "headline": "x",
            "rationale": "x",
            "key_evidence": [],
        }
    )
    with pytest.raises(CommitteeSchemaError) as exc:
        parse_master_opinion_strict(bad)
    assert "key_evidence" in str(exc.value)


def test_master_opinion_garbage_raises(garbage_json):
    with pytest.raises(CommitteeSchemaError):
        parse_master_opinion_strict(garbage_json)


def test_master_opinion_markdown_fenced_json_is_accepted(perfect_master_opinion_json):
    fenced = "```json\n" + perfect_master_opinion_json + "\n```"
    opinion = parse_master_opinion_strict(fenced)
    assert opinion.persona == "warren_buffett"


def test_master_opinion_with_surrounding_prose(perfect_master_opinion_json):
    # Some weak models emit chatter outside the JSON block; we must still
    # find the largest brace-span and parse it.
    polluted = "Sure, here's my verdict:\n\n" + perfect_master_opinion_json + "\n\nLet me know if you need more."
    opinion = parse_master_opinion_strict(polluted)
    assert opinion.persona == "warren_buffett"


def test_failed_master_opinion_constructs_without_raising():
    fallback = failed_master_opinion("warren_buffett", error_summary="timeout after 30s")
    assert fallback.status == "failed"
    assert fallback.persona == "warren_buffett"
    assert "timeout" in (fallback.error_summary or "")


def test_failed_master_opinion_clamps_long_error():
    long_err = "x" * 1000
    fallback = failed_master_opinion("warren_buffett", error_summary=long_err)
    # error_summary length clamped to 500 chars
    assert len(fallback.error_summary or "") <= 500


# --------------------------------------------------------------------------- #
# DebateExchange
# --------------------------------------------------------------------------- #


def test_debate_exchange_happy_path():
    payload = json.dumps(
        {
            "side": "bull",
            "round_index": 1,
            "claim": "Revenue growth is accelerating into a high-margin SaaS mix",
            "evidence": ["YoY growth 30%", "Gross margin expansion 200bps", "Net retention 120%"],
            "rebuttal_to": None,
            "confidence": 0.7,
        }
    )
    exch = parse_debate_exchange_strict(payload)
    assert exch.side == "bull"
    assert exch.round_index == 1
    assert len(exch.evidence) == 3


def test_debate_exchange_missing_side_filled_by_expected():
    payload = json.dumps(
        {
            "round_index": 1,
            "claim": "x",
            "evidence": ["a", "b"],
        }
    )
    # Orchestrator passes expected_side to repair the missing field
    exch = parse_debate_exchange_strict(payload, expected_side="bear")
    assert exch.side == "bear"


def test_debate_exchange_invalid_side_raises():
    payload = json.dumps(
        {
            "side": "centrist",
            "round_index": 1,
            "claim": "x",
            "evidence": ["a"],
        }
    )
    with pytest.raises(CommitteeSchemaError):
        parse_debate_exchange_strict(payload)


def test_debate_exchange_empty_evidence_raises():
    payload = json.dumps(
        {
            "side": "bull",
            "round_index": 1,
            "claim": "x",
            "evidence": [],
        }
    )
    with pytest.raises(CommitteeSchemaError):
        parse_debate_exchange_strict(payload)


def test_failed_debate_exchange_constructs_without_raising():
    fallback = failed_debate_exchange("bull", 2, error_summary="LLM timeout")
    assert fallback.status == "failed"
    assert fallback.side == "bull"
    assert fallback.round_index == 2


# --------------------------------------------------------------------------- #
# RiskAssessment
# --------------------------------------------------------------------------- #


def test_risk_assessment_happy_path():
    payload = json.dumps(
        {
            "severity": "soft",
            "red_flags": ["High beta", "Earnings next week"],
            "suggested_position_pct": 0.15,
            "veto": False,
        }
    )
    ra = parse_risk_assessment_strict(payload)
    assert ra.severity == "soft"
    assert ra.suggested_position_pct == 0.15
    assert ra.veto is False


def test_risk_assessment_invalid_position_pct():
    payload = json.dumps(
        {
            "severity": "soft",
            "red_flags": [],
            "suggested_position_pct": 1.5,
            "veto": False,
        }
    )
    with pytest.raises(CommitteeSchemaError):
        parse_risk_assessment_strict(payload)


def test_risk_assessment_missing_veto_raises():
    payload = json.dumps(
        {
            "severity": "soft",
            "suggested_position_pct": 0.1,
        }
    )
    with pytest.raises(CommitteeSchemaError):
        parse_risk_assessment_strict(payload)


def test_failed_risk_assessment_constructs():
    fb = failed_risk_assessment("risk node crashed")
    assert fb.status == "failed"
    assert fb.veto is False


# --------------------------------------------------------------------------- #
# CommitteeMinutes
# --------------------------------------------------------------------------- #


def test_committee_minutes_pm_happy_path():
    payload = json.dumps(
        {
            "status": "ok",
            "pm_verdict": "buy",
            "pm_score": 7.0,
            "pm_rationale": "Synthesis favours moat and reasonable valuation.",
            "pm_dissents": [],
            "missing_agents": [],
            "budget_used": 12,
            "budget_cap": 12,
        }
    )
    minutes = parse_committee_minutes_strict(payload)
    assert minutes.status == "ok"
    assert minutes.pm_verdict == "buy"


def test_committee_minutes_missing_pm_verdict_raises():
    payload = json.dumps(
        {
            "status": "ok",
            "pm_score": 7,
            "pm_rationale": "x",
            "budget_used": 1,
            "budget_cap": 12,
        }
    )
    with pytest.raises(CommitteeSchemaError):
        parse_committee_minutes_strict(payload)


def test_failed_committee_minutes_carries_partial_state():
    one_master = MasterOpinion(
        persona="warren_buffett",
        verdict="hold",
        score=5.0,
        headline="x",
        rationale="x",
        key_evidence=["a"],
    )
    fb = failed_committee_minutes(
        debate_rounds=2,
        budget_used=8,
        budget_cap=12,
        error_summary="PM agent timed out",
        missing_agents=["michael_burry", "nassim_taleb"],
        masters=[one_master],
    )
    assert fb.status == "failed"
    assert fb.budget_used == 8
    assert fb.missing_agents == ["michael_burry", "nassim_taleb"]
    assert len(fb.masters) == 1
    # Round-trip — fallback object must serialise so it can be persisted
    dumped = fb.model_dump()
    assert dumped["status"] == "failed"
    rehydrated = CommitteeMinutes(**dumped)
    assert rehydrated.status == "failed"


def test_committee_minutes_status_partial_when_master_missing():
    # We don't enforce orchestrator semantics inside the schema — but the
    # status field must accept 'partial' as a Literal value.
    minutes = CommitteeMinutes(
        status="partial",
        debate_rounds=2,
        pm_verdict="hold",
        pm_score=5,
        pm_rationale="One lens absent",
        missing_agents=["nassim_taleb"],
        budget_used=10,
        budget_cap=12,
    )
    assert minutes.status == "partial"


# --------------------------------------------------------------------------- #
# Retry contract simulation
# --------------------------------------------------------------------------- #


def test_retry_contract_first_garbage_then_valid(perfect_master_opinion_json, garbage_json):
    """First call → CommitteeSchemaError. Retry with valid payload → success.

    This simulates the orchestrator's 1-retry policy: catch
    CommitteeSchemaError on first attempt, embed the schema example, and
    retry. We assert both branches behave as documented.
    """
    with pytest.raises(CommitteeSchemaError) as exc1:
        parse_master_opinion_strict(garbage_json)
    # Schema example available to the orchestrator for retry prompt
    assert "persona" in exc1.value.schema
    # Retry succeeds
    opinion = parse_master_opinion_strict(perfect_master_opinion_json)
    assert opinion.status == "ok"


def test_retry_contract_double_failure_falls_back(garbage_json):
    """Both attempts garbage → caller MUST construct fallback, not raise."""
    with pytest.raises(CommitteeSchemaError):
        parse_master_opinion_strict(garbage_json)
    with pytest.raises(CommitteeSchemaError):
        parse_master_opinion_strict(garbage_json)
    # Orchestrator falls back — must succeed without raising
    fb = failed_master_opinion("warren_buffett", error_summary="two retry attempts failed")
    assert fb.status == "failed"
    assert fb.persona == "warren_buffett"
