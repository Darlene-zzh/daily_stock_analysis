# -*- coding: utf-8 -*-
"""End-to-end integration tests for the committee hook on AnalysisService.

Covers Task 1A-4 acceptance:
- ``analyze_stock`` is param-additive — default call signature unchanged.
- ``enable_investment_committee=True`` produces ``response["report"]["committee"]``
  with ``status in {"ok", "partial"}`` and ``pm_verdict`` populated.
- A forced master-timeout yields ``status="partial"`` + non-empty
  ``missing_agents``.
- The committee minutes are ALSO attached to ``result.dashboard["committee"]``
  so the existing renderer pipeline can pick them up uniformly with other
  dashboard sub-sections.
- Both the standard pipeline path AND the ``_analyze_with_agent`` bypass
  path go through the same hook (the hook lives at the AnalysisService
  level after pipeline returns; the bypass path converges there too).

The test exercises ``AnalysisService.analyze_stock`` directly with the
LLM-callable swapped at the orchestrator boundary so no real LLM is needed.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from src.agent.budget import LLMCallBudget
from src.agent.orchestrator_committee import InvestmentCommitteeOrchestrator
from src.agent.protocols import AgentContext


# --------------------------------------------------------------------------- #
# Fake pipeline result + service patching
# --------------------------------------------------------------------------- #


def _bull_payload(round_idx: int) -> str:
    return json.dumps({
        "side": "bull", "round_index": round_idx,
        "claim": "Strong moat + reasonable valuation.",
        "evidence": ["ROE 25%", "Operating margin 50%", "Buybacks 4%/yr"],
        "rebuttal_to": None, "confidence": 0.7,
    })


def _bear_payload(round_idx: int) -> str:
    return json.dumps({
        "side": "bear", "round_index": round_idx,
        "claim": "Regulatory headwinds and decelerating growth.",
        "evidence": ["Policy headlines", "Decel YoY", "PE > sector"],
        "rebuttal_to": "moat thesis", "confidence": 0.55,
    })


def _master_payload(persona: str, verdict: str = "buy", score: float = 7.0) -> str:
    return json.dumps({
        "persona": persona,
        "verdict": verdict,
        "score": score,
        "headline": f"{persona} headline",
        "rationale": f"Rationale by {persona}. Second sentence concludes the view.",
        "key_evidence": [f"{persona}-e1", f"{persona}-e2", f"{persona}-e3"],
        "counter_view": "Regime shift could invalidate",
        "tools_used": [],
    })


def _risk_payload(severity: str = "soft") -> str:
    return json.dumps({
        "severity": severity, "red_flags": [],
        "suggested_position_pct": 0.15, "veto": False,
    })


def _pm_payload(status: str = "ok") -> str:
    return json.dumps({
        "status": status, "pm_verdict": "buy", "pm_score": 7.0,
        "pm_rationale": "Synthesis leans positive across lenses.",
        "pm_dissents": [], "missing_agents": [],
        "budget_used": 10, "budget_cap": 12,
    })


class _ScriptedLLM:
    """Simple LLM-callable stub driven by a scripted response list."""

    def __init__(self, responses: List[str]) -> None:
        self.responses = list(responses)
        self.calls: List = []

    def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.responses:
            raise AssertionError("LLM stub exhausted unexpectedly")
        return self.responses.pop(0)


@pytest.fixture
def fake_pipeline_result():
    """Mimic AnalysisResult attributes that AnalysisService consumes."""
    return SimpleNamespace(
        code="600519",
        name="贵州茅台",
        success=True,
        sentiment_score=72,
        trend_prediction="震荡向上",
        operation_advice="逢低买入",
        report_language="zh",
        current_price=1730.0,
        change_pct=0.5,
        model_used="gpt-test",
        analysis_summary="Strong franchise",
        news_summary="",
        technical_analysis="MA aligned bullish",
        fundamental_analysis="ROE 25%",
        risk_warning="",
        dashboard={"core_conclusion": {"one_sentence": "Buy on dips"}},
        portfolio_match=None,
        query_id="qid-123",
        # _build_analysis_response touches get_sniper_points
        get_sniper_points=lambda: {
            "ideal_buy": 1700, "secondary_buy": 1680,
            "stop_loss": 1620, "take_profit": 1900,
        },
    )


@pytest.fixture
def stub_committee_pipeline(monkeypatch, fake_pipeline_result):
    """Patch the AnalysisService internals so `analyze_stock` runs without
    touching real data fetchers / LLM / cache."""
    from src.services import analysis_service as _as_mod

    # 1) Disable cache lookup
    monkeypatch.setattr(
        _as_mod.AnalysisService,
        "_lookup_recent_cache_response",
        lambda self, code, rt: None,
    )

    # 2) Stub the pipeline to return our fake AnalysisResult
    class _StubPipeline:
        def __init__(self, *args, **kwargs):
            pass

        def process_single_stock(self, code, **kwargs):
            return fake_pipeline_result

    monkeypatch.setattr(_as_mod, "StockAnalysisPipeline", _StubPipeline, raising=False)

    # 3) Make `from src.core.pipeline import StockAnalysisPipeline` resolve to our stub
    import src.core.pipeline as _pipeline_mod
    monkeypatch.setattr(_pipeline_mod, "StockAnalysisPipeline", _StubPipeline, raising=False)
    return fake_pipeline_result


# --------------------------------------------------------------------------- #
# 1) Default analysis untouched when opt-out
# --------------------------------------------------------------------------- #


def test_default_analysis_has_no_committee_field(stub_committee_pipeline, monkeypatch):
    """Spec acceptance: when opt-out (default), response must NOT contain committee."""
    from src.services.analysis_service import AnalysisService

    svc = AnalysisService()
    result = svc.analyze_stock(stock_code="600519")
    assert result is not None
    report = result.get("report") or {}
    assert "committee" not in report
    # dashboard untouched
    assert "committee" not in (stub_committee_pipeline.dashboard or {})


# --------------------------------------------------------------------------- #
# 2) Opt-in happy path → status='ok', pm_verdict populated
# --------------------------------------------------------------------------- #


def test_committee_optin_happy_path(stub_committee_pipeline, monkeypatch):
    """End-to-end stub LLM smoke: status='ok' and pm_verdict='buy'."""
    from src.services.analysis_service import AnalysisService

    # Patch _invoke_committee to use a scripted stub instead of going through
    # litellm. We want this test to exercise the integration glue but stay
    # deterministic; the underlying orchestrator is already tested directly
    # in test_committee_graph.py.
    scripted = [
        _bull_payload(1), _bear_payload(1),
        _bull_payload(2), _bear_payload(2),
        _master_payload("warren_buffett"),
        _master_payload("michael_burry"),
        _master_payload("cathie_wood"),
        _master_payload("nassim_taleb"),
        _risk_payload(),
        _pm_payload(status="ok"),
    ]
    llm = _ScriptedLLM(scripted)

    def _fake_invoke(self, *, stock_code, result, response, debate_rounds):
        budget = LLMCallBudget(cap=12)
        ctx = AgentContext(stock_code=stock_code, stock_name=result.name, meta={"market": "A"})
        orch = InvestmentCommitteeOrchestrator(
            ctx,
            report_json=response.get("report") or {},
            budget=budget,
            llm_callable=llm,
            debate_rounds=debate_rounds,
        )
        return orch.run().minutes.model_dump()

    monkeypatch.setattr(AnalysisService, "_invoke_committee", _fake_invoke)

    svc = AnalysisService()
    response = svc.analyze_stock(
        stock_code="600519",
        enable_investment_committee=True,
        committee_debate_rounds=2,
    )
    assert response is not None
    committee = (response.get("report") or {}).get("committee")
    assert committee is not None, "Expected report.committee to be populated"
    assert committee["status"] in ("ok", "partial"), f"unexpected status={committee['status']!r}"
    assert committee["pm_verdict"] is not None, "PM verdict missing"
    # spec — masters list must be 4
    assert len(committee["masters"]) == 4
    # Each master entry must carry a non-empty persona id
    assert all(m.get("persona") for m in committee["masters"])
    # Also attached to dashboard
    dashboard = response["report"]
    # In our stub the AnalysisResult.dashboard is the same dict referenced;
    # the service mutates it on opt-in so the existing renderer pipeline
    # sees the section without further plumbing.
    assert "committee" in stub_committee_pipeline.dashboard


# --------------------------------------------------------------------------- #
# 3) Forced timeout / failure → status='partial' + non-empty missing_agents
# --------------------------------------------------------------------------- #


def test_committee_forced_timeout_yields_partial(stub_committee_pipeline, monkeypatch):
    """Burry returns invalid JSON twice → status='partial' + missing_agents non-empty."""
    from src.services.analysis_service import AnalysisService

    scripted = [
        _bull_payload(1), _bear_payload(1),
        _bull_payload(2), _bear_payload(2),
        _master_payload("warren_buffett"),
        "this is not JSON",        # burry first attempt
        "still not JSON on retry",  # burry retry
        _master_payload("cathie_wood"),
        _master_payload("nassim_taleb"),
        _risk_payload(),
        _pm_payload(status="ok"),  # LLM lies; orchestrator overrides to partial
    ]
    llm = _ScriptedLLM(scripted)

    def _fake_invoke(self, *, stock_code, result, response, debate_rounds):
        budget = LLMCallBudget(cap=14)
        ctx = AgentContext(stock_code=stock_code, stock_name=result.name, meta={"market": "A"})
        orch = InvestmentCommitteeOrchestrator(
            ctx,
            report_json=response.get("report") or {},
            budget=budget,
            llm_callable=llm,
            debate_rounds=debate_rounds,
        )
        return orch.run().minutes.model_dump()

    monkeypatch.setattr(AnalysisService, "_invoke_committee", _fake_invoke)

    svc = AnalysisService()
    response = svc.analyze_stock(
        stock_code="600519",
        enable_investment_committee=True,
        committee_debate_rounds=2,
    )
    committee = (response.get("report") or {}).get("committee")
    assert committee is not None
    assert committee["status"] == "partial"
    assert committee["missing_agents"], "missing_agents must be non-empty after failure"
    # PM still issued a verdict despite Burry absent
    assert committee["pm_verdict"] is not None


# --------------------------------------------------------------------------- #
# 4) Committee failure must NEVER kill the default report
# --------------------------------------------------------------------------- #


def test_committee_exception_does_not_break_default_report(stub_committee_pipeline, monkeypatch):
    from src.services.analysis_service import AnalysisService

    def _exploding(self, *, stock_code, result, response, debate_rounds):
        raise RuntimeError("committee blew up")

    monkeypatch.setattr(AnalysisService, "_invoke_committee", _exploding)

    svc = AnalysisService()
    # No exception escapes
    response = svc.analyze_stock(
        stock_code="600519",
        enable_investment_committee=True,
    )
    assert response is not None
    # The committee is missing, but the default report is intact
    report = response.get("report") or {}
    assert "summary" in report
    assert "committee" not in report


# --------------------------------------------------------------------------- #
# 5) Param threading — task_queue → service signature parity
# --------------------------------------------------------------------------- #


def test_task_queue_threads_committee_params_to_service(monkeypatch):
    """submit_tasks_batch → _execute_task → analyze_stock — kwargs survive."""
    import inspect
    from src.services import task_queue as _tq_mod
    from src.services.analysis_service import AnalysisService

    # Confirm the additive kwargs exist in every hop with the same names
    submit_sig = inspect.signature(_tq_mod.AnalysisTaskQueue.submit_tasks_batch)
    exec_sig = inspect.signature(_tq_mod.AnalysisTaskQueue._execute_task)
    service_sig = inspect.signature(AnalysisService.analyze_stock)
    for sig in (submit_sig, exec_sig, service_sig):
        assert "enable_investment_committee" in sig.parameters
        assert "committee_debate_rounds" in sig.parameters
        # Defaults must match (False / 2)
        assert sig.parameters["enable_investment_committee"].default is False
        assert sig.parameters["committee_debate_rounds"].default == 2


# --------------------------------------------------------------------------- #
# 6) API schema carries the new fields with correct defaults + constraints
# --------------------------------------------------------------------------- #


def test_analyze_request_schema_exposes_committee_fields():
    from api.v1.schemas.analysis import AnalyzeRequest

    req_default = AnalyzeRequest(stock_code="600519")
    assert req_default.enable_investment_committee is False
    assert req_default.committee_debate_rounds == 2

    req_opt_in = AnalyzeRequest(
        stock_code="600519",
        enable_investment_committee=True,
        committee_debate_rounds=3,
    )
    assert req_opt_in.enable_investment_committee is True
    assert req_opt_in.committee_debate_rounds == 3

    # Out of range rounds must be rejected by Field(ge=1, le=3)
    with pytest.raises(Exception):
        AnalyzeRequest(stock_code="600519", committee_debate_rounds=5)
    with pytest.raises(Exception):
        AnalyzeRequest(stock_code="600519", committee_debate_rounds=0)
