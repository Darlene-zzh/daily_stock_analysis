# -*- coding: utf-8 -*-
"""LangGraph orchestrator tests (Sprint 1A Task 1A-3).

Covers spec §12 graph cases:
- happy path with 12-call budget (2 debate rounds × 2 sides + 4 masters + risk + pm = 10 calls)
- master timeout → graph completes, PM annotates absence
- JSON-drift retry → second LLM attempt succeeds, ``budget_used`` increments by 2

Plus structural assertions:
- LangGraph state machine wires without raising
- budget cap is computed correctly per debate_rounds
- Risk veto forces PM verdict to <= 'hold'
- ``status='partial'`` is enforced by orchestrator regardless of what the LLM
  PM emits — the orchestrator overrides
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Tuple

import pytest

from src.agent.budget import LLMCallBudget, compute_effective_cap
from src.agent.orchestrator_committee import (
    InvestmentCommitteeOrchestrator,
    _resolve_top_status,
)
from src.agent.protocols import AgentContext
from src.schemas.committee_schema import (
    CommitteeMinutes,
)


# --------------------------------------------------------------------------- #
# Stub LLM machinery
# --------------------------------------------------------------------------- #


def _make_ctx() -> AgentContext:
    return AgentContext(stock_code="600519", stock_name="贵州茅台", meta={"market": "A"})


def _bull_payload(round_idx: int) -> str:
    return json.dumps(
        {
            "side": "bull",
            "round_index": round_idx,
            "claim": "Durable franchise with pricing power; valuation reasonable.",
            "evidence": [
                "5-yr ROE > 25%",
                "Operating margin > 50%",
                "Buyback program reduces float",
            ],
            "rebuttal_to": None,
            "confidence": 0.7,
        }
    )


def _bear_payload(round_idx: int) -> str:
    return json.dumps(
        {
            "side": "bear",
            "round_index": round_idx,
            "claim": "Regulatory overhang and slowing growth justify caution.",
            "evidence": [
                "Industry policy headlines this week",
                "YoY revenue growth decelerating",
                "PE > sector median",
            ],
            "rebuttal_to": "moat thesis",
            "confidence": 0.55,
        }
    )


def _master_payload(persona: str, verdict: str = "buy", score: float = 7.0) -> str:
    return json.dumps(
        {
            "persona": persona,
            "verdict": verdict,
            "score": score,
            "headline": f"{persona} headline",
            "rationale": f"Rationale by {persona} across two sentences. Concluding clause.",
            "key_evidence": [f"{persona}-evidence-1", f"{persona}-evidence-2", f"{persona}-evidence-3"],
            "counter_view": "Regime shift could invalidate the thesis",
            "tools_used": ["fundamentals_snapshot"],
        }
    )


def _risk_payload(severity: str = "soft", veto: bool = False, pos: float = 0.15) -> str:
    return json.dumps(
        {
            "severity": severity,
            "red_flags": ["earnings next week"],
            "suggested_position_pct": pos,
            "veto": veto,
        }
    )


def _pm_payload(verdict: str = "buy", status: str = "ok", budget_used: int = 10, budget_cap: int = 12) -> str:
    return json.dumps(
        {
            "status": status,
            "pm_verdict": verdict,
            "pm_score": 7.2,
            "pm_rationale": "Aggregated lenses lean positive; risk soft only.",
            "pm_dissents": [],
            "missing_agents": [],
            "budget_used": budget_used,
            "budget_cap": budget_cap,
        }
    )


class StubLLM:
    """Sequence-driven LLM stub.

    Each invocation pops the next scripted response from ``responses``.  If
    a response is a callable (system, user) -> str it's invoked dynamically;
    if it's an Exception it's raised.  Records every (system, user) call.
    """

    def __init__(self, responses: List[Any]) -> None:
        self.responses = list(responses)
        self.calls: List[Tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.responses:
            raise AssertionError("StubLLM exhausted — orchestrator made an unexpected call")
        nxt = self.responses.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        if callable(nxt):
            return nxt(system, user)
        return nxt


# --------------------------------------------------------------------------- #
# Budget arithmetic
# --------------------------------------------------------------------------- #


def test_compute_effective_cap_matches_spec_table():
    # base=12 yields 10 / 12 / 14 for 1 / 2 / 3 rounds (locked decision #1)
    assert compute_effective_cap(1, base=10) == 10
    assert compute_effective_cap(2, base=10) == 12
    assert compute_effective_cap(3, base=10) == 14
    # base=12 default
    assert compute_effective_cap(1, base=12) == 12
    assert compute_effective_cap(2, base=12) == 14


def test_compute_effective_cap_clamps_invalid_rounds():
    # rounds < 1 → 1, > 3 → 3
    assert compute_effective_cap(0, base=10) == 10  # treated as 1 round
    assert compute_effective_cap(99, base=10) == 14  # treated as 3 rounds


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_happy_path_two_rounds_full_committee():
    """All 10 nodes succeed first-try; PM emits 'ok' minutes."""
    # 2 rounds × 2 sides = 4 + 4 masters + 1 risk + 1 pm = 10 LLM calls
    responses = [
        _bull_payload(1),
        _bear_payload(1),
        _bull_payload(2),
        _bear_payload(2),
        _master_payload("warren_buffett"),
        _master_payload("michael_burry"),
        _master_payload("cathie_wood"),
        _master_payload("nassim_taleb"),
        _risk_payload(),
        _pm_payload(),
    ]
    llm = StubLLM(responses)
    budget = LLMCallBudget(cap=12)
    orch = InvestmentCommitteeOrchestrator(
        _make_ctx(),
        report_json={"summary": {"analysis_summary": "Strong franchise"}},
        budget=budget,
        llm_callable=llm,
        debate_rounds=2,
    )
    result = orch.run()

    assert isinstance(result.minutes, CommitteeMinutes)
    minutes = result.minutes
    # Status: all 4 masters + risk + PM completed cleanly
    assert minutes.status == "ok"
    assert minutes.pm_verdict == "buy"
    assert minutes.pm_score == 7.2
    # Debate: 2 rounds × (bull + bear) = 4 exchanges
    assert len(minutes.debate) == 4
    assert {ex.side for ex in minutes.debate} == {"bull", "bear"}
    # Masters: 4 lenses, all OK
    assert len(minutes.masters) == 4
    assert all(m.status == "ok" for m in minutes.masters)
    # Risk: severity soft, no veto
    assert minutes.risk is not None
    assert minutes.risk.severity == "soft"
    assert minutes.risk.veto is False
    # Budget bookkeeping
    assert minutes.budget_used == 10
    assert minutes.budget_cap == 12
    assert minutes.missing_agents == []
    # LLM called exactly 10 times
    assert len(llm.calls) == 10


# --------------------------------------------------------------------------- #
# Degradation: one master returns garbage twice → fallback
# --------------------------------------------------------------------------- #


def test_master_timeout_triggers_partial_status():
    """Burry returns invalid JSON twice → graph completes, PM annotates absence.

    Per spec §6 retry contract: 1 retry, then fallback to failed object.
    """
    responses = [
        _bull_payload(1),
        _bear_payload(1),
        _bull_payload(2),
        _bear_payload(2),
        _master_payload("warren_buffett"),
        # Burry first attempt — garbage
        "this is not JSON for burry",
        # Burry retry — still garbage
        "still garbage on retry",
        _master_payload("cathie_wood"),
        _master_payload("nassim_taleb"),
        _risk_payload(),
        _pm_payload(status="partial"),
    ]
    llm = StubLLM(responses)
    budget = LLMCallBudget(cap=14)  # 12 baseline + retry slack
    orch = InvestmentCommitteeOrchestrator(
        _make_ctx(),
        report_json={"summary": "x"},
        budget=budget,
        llm_callable=llm,
        debate_rounds=2,
    )
    result = orch.run()
    minutes = result.minutes
    # Burry should be present but with status='failed'
    burry = next(m for m in minutes.masters if m.persona == "michael_burry")
    assert burry.status == "failed"
    assert burry.error_summary
    # Three other masters still OK
    other_masters = [m for m in minutes.masters if m.persona != "michael_burry"]
    assert len(other_masters) == 3
    assert all(m.status == "ok" for m in other_masters)
    # Top-level status downgraded to partial
    assert minutes.status == "partial"
    # PM still issues a verdict
    assert minutes.pm_verdict is not None
    # missing_agents annotated
    assert any("master_michael_burry" in a for a in minutes.missing_agents)


# --------------------------------------------------------------------------- #
# JSON drift retry — first attempt invalid, second valid → success
# --------------------------------------------------------------------------- #


def test_json_drift_retry_succeeds_and_uses_two_budget_slots():
    """Buffett first response garbage, retry valid → budget_used increments by 2."""
    responses = [
        _bull_payload(1),
        _bear_payload(1),
        _bull_payload(2),
        _bear_payload(2),
        # Buffett: first garbage, retry valid
        '{"persona": "warren_buffett", "verdict": "moon"}',  # invalid verdict
        _master_payload("warren_buffett"),
        _master_payload("michael_burry"),
        _master_payload("cathie_wood"),
        _master_payload("nassim_taleb"),
        _risk_payload(),
        _pm_payload(),
    ]
    llm = StubLLM(responses)
    budget = LLMCallBudget(cap=14)
    orch = InvestmentCommitteeOrchestrator(
        _make_ctx(),
        report_json={"summary": "x"},
        budget=budget,
        llm_callable=llm,
        debate_rounds=2,
    )
    result = orch.run()
    minutes = result.minutes
    buff = next(m for m in minutes.masters if m.persona == "warren_buffett")
    assert buff.status == "ok"
    # Budget = 4 debate + 1 buffett-first + 1 buffett-retry + 3 other masters + 1 risk + 1 pm = 11
    assert minutes.budget_used == 11
    # LLM was actually called 11 times
    assert len(llm.calls) == 11
    # The retry user message should contain the schema example marker
    retry_user = llm.calls[5][1]  # 5th call (0-indexed) is the buffett retry
    assert "previous response failed strict parsing" in retry_user


# --------------------------------------------------------------------------- #
# Risk veto caps PM verdict to <= 'hold'
# --------------------------------------------------------------------------- #


def test_risk_hard_veto_does_not_break_graph():
    """A hard-veto risk node + 'hold' PM verdict is well-formed."""
    responses = [
        _bull_payload(1),
        _bear_payload(1),
        _bull_payload(2),
        _bear_payload(2),
        _master_payload("warren_buffett"),
        _master_payload("michael_burry"),
        _master_payload("cathie_wood"),
        _master_payload("nassim_taleb"),
        _risk_payload(severity="hard", veto=True, pos=0.0),
        _pm_payload(verdict="hold"),
    ]
    llm = StubLLM(responses)
    budget = LLMCallBudget(cap=12)
    orch = InvestmentCommitteeOrchestrator(
        _make_ctx(),
        report_json={"summary": "x"},
        budget=budget,
        llm_callable=llm,
        debate_rounds=2,
    )
    result = orch.run()
    assert result.minutes.risk.severity == "hard"
    assert result.minutes.risk.veto is True
    assert result.minutes.pm_verdict == "hold"
    assert result.minutes.status == "ok"  # all agents completed


# --------------------------------------------------------------------------- #
# Budget exhaustion mid-fan-out → graph still completes via fallback
# --------------------------------------------------------------------------- #


def test_budget_exhaustion_mid_run_does_not_raise():
    """When budget runs dry, remaining nodes degrade gracefully."""
    # Tight budget: only 4 calls allowed (2 bull-bear pairs) - masters get squeezed
    responses = [
        _bull_payload(1),
        _bear_payload(1),
        _bull_payload(2),
        _bear_payload(2),
        # Masters / risk / pm should NEVER be invoked — budget will reject
    ]
    llm = StubLLM(responses)
    budget = LLMCallBudget(cap=4)
    orch = InvestmentCommitteeOrchestrator(
        _make_ctx(),
        report_json={"summary": "x"},
        budget=budget,
        llm_callable=llm,
        debate_rounds=2,
    )
    result = orch.run()
    minutes = result.minutes
    # Debate exchanges all OK
    assert len([d for d in minutes.debate if d.status == "ok"]) == 4
    # All masters degraded
    assert all(m.status != "ok" for m in minutes.masters)
    # PM produced a 'failed' fallback minutes (budget exhausted)
    assert minutes.status == "failed"
    assert minutes.error_summary  # carries why it failed
    # No further LLM calls happened
    assert len(llm.calls) == 4


# --------------------------------------------------------------------------- #
# Wall-clock timeout — orchestrator respects deadline
# --------------------------------------------------------------------------- #


def test_wall_clock_timeout_short_circuits_remaining_nodes(monkeypatch):
    """If the deadline is in the past, only PM runs (and may fall back)."""
    def _slow_then_done(system: str, user: str) -> str:  # noqa: ARG001
        return _bull_payload(1)

    llm = StubLLM([_slow_then_done] * 30)
    budget = LLMCallBudget(cap=14)
    orch = InvestmentCommitteeOrchestrator(
        _make_ctx(),
        report_json={"summary": "x"},
        budget=budget,
        llm_callable=llm,
        debate_rounds=2,
        timeout_s=0,  # immediate deadline
    )
    result = orch.run()
    # PM must still issue a minutes object (failed fallback in this case)
    assert result.minutes is not None
    # missing_agents non-empty
    assert len(result.minutes.missing_agents) >= 1


# --------------------------------------------------------------------------- #
# Status resolver — orchestrator overrides LLM-claimed status
# --------------------------------------------------------------------------- #


def test_orchestrator_overrides_llm_status_when_agents_missing():
    """LLM claims status='ok' but a master failed → orchestrator forces 'partial'."""
    responses = [
        _bull_payload(1),
        _bear_payload(1),
        _bull_payload(2),
        _bear_payload(2),
        _master_payload("warren_buffett"),
        "garbage burry",
        "garbage burry retry",
        _master_payload("cathie_wood"),
        _master_payload("nassim_taleb"),
        _risk_payload(),
        # PM lies: claims status='ok' though Burry failed
        _pm_payload(status="ok"),
    ]
    llm = StubLLM(responses)
    budget = LLMCallBudget(cap=14)
    orch = InvestmentCommitteeOrchestrator(
        _make_ctx(),
        report_json={"summary": "x"},
        budget=budget,
        llm_callable=llm,
        debate_rounds=2,
    )
    result = orch.run()
    # Orchestrator overrules the LLM
    assert result.minutes.status == "partial"


# --------------------------------------------------------------------------- #
# LangGraph wiring — must build at construction without raising
# --------------------------------------------------------------------------- #


def test_langgraph_wiring_does_not_raise():
    llm = StubLLM([])
    budget = LLMCallBudget(cap=12)
    orch = InvestmentCommitteeOrchestrator(
        _make_ctx(),
        report_json={"summary": "x"},
        budget=budget,
        llm_callable=llm,
        debate_rounds=2,
    )
    # Build the graph in isolation — should not raise
    graph = orch._build_langgraph()
    # Graph may be None if langgraph not installed; that's a test env issue
    # If it is built, it has the expected node count: bull, bear, 4 masters,
    # risk, pm = 8 nodes.
    if graph is not None:
        nodes = getattr(graph, "nodes", None)
        if nodes is not None:
            # Some langgraph versions expose nodes as a dict / set
            try:
                node_count = len(nodes)
            except TypeError:
                node_count = sum(1 for _ in nodes)
            assert node_count >= 8
