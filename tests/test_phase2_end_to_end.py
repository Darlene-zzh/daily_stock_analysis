"""End-to-end: feed the NVDA dashboard fixture through facts_builder, then
through _try_inject_action_plan_items with a mocked LLM, and verify the final
action_plan_items pass all evidence-grounding invariants.
"""
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.analyzer import GeminiAnalyzer, AnalysisResult
from src.analysis.facts_builder import build_fact_bundle


FIXTURE = Path(__file__).parent / "fixtures" / "nvda_dashboard.json"


@pytest.mark.skipif(not FIXTURE.exists(), reason="NVDA fixture missing")
def test_phase2_nvda_pipeline_with_mocked_llm():
    dashboard = json.loads(FIXTURE.read_text())
    bundle = build_fact_bundle(
        stock_code="NVDA", market="us", dashboard=dashboard,
        portfolio_context=None, ohlc=None, rsi_12=71.1,
        qlib_predictions={"NVDA": {"score": 0.235, "rank": 0.847}},
        qlib_ic={"ic_ma_4w": 0.21},
        qlib_universe_size=503, qlib_week="2026-W21",
        as_of="2026-05-21T00:43:00Z",
    )

    result = AnalysisResult(
        code="NVDA", name="NVIDIA", sentiment_score=65,
        trend_prediction="up", operation_advice="hold",
        confidence_level="medium", analysis_summary="ok",
        risk_warning="ok", success=True, model_used="test",
    )
    result.dashboard = dict(dashboard)
    # Clear the fixture's pre-populated upstream action_plan_items so the test
    # exercises the LLM-branch path (we want to validate that LLM-emitted
    # candidate_ids survive sanitization, not legacy items missing candidate_id).
    if isinstance(result.dashboard.get("core_conclusion"), dict):
        result.dashboard["core_conclusion"] = dict(result.dashboard["core_conclusion"])
        result.dashboard["core_conclusion"].pop("action_plan_items", None)
        result.dashboard["core_conclusion"].pop("recommended_strategy", None)
    result.dashboard["fact_bundle"] = {
        "as_of": bundle.as_of, "market": bundle.market,
        "stock_code": bundle.stock_code,
        "facts": [asdict(f) for f in bundle.facts],
        "candidates": [asdict(c) for c in bundle.candidates],
    }
    result.portfolio_match = None

    # Pick the first 2 real candidate IDs from the bundle for the mocked LLM
    primary_candidates = [c for c in bundle.candidates if c.tier == "primary"]
    if len(primary_candidates) < 2:
        pytest.skip(f"Fixture only yielded {len(primary_candidates)} primary candidates")
    # Choose 2 candidates that share at least one applicable strategy
    chosen = None
    for i, c1 in enumerate(primary_candidates):
        for c2 in primary_candidates[i + 1:]:
            shared = set(c1.applicable_strategies) & set(c2.applicable_strategies)
            if shared:
                chosen = (c1, c2, next(iter(shared)))
                break
        if chosen:
            break
    if not chosen:
        pytest.skip("No two primary candidates share an applicable strategy")
    c1, c2, strategy = chosen

    mock_resp = {
        "recommended_strategy": strategy,
        "strategy_thesis": "..." * 30,
        "strategy_choices": [],
        "action_plan_items": [
            {
                "candidate_id": c1.id,
                "trigger_price": float(c1.price),
                "direction": c1.direction,
                "shares": 0.23, "pct_of_position": 30.0,
                "technical_basis": "x", "fundamental_basis": "y",
                "quant_signal": "z", "invalidation_rule": "w",
                "priority": 1,
                "evidence_refs": ["technical.current_price", "committee.pm_verdict"],
                "tier": "primary", "narrative": "...",
            },
            {
                "candidate_id": c2.id,
                "trigger_price": float(c2.price),
                "direction": c2.direction,
                "shares": 0.23, "pct_of_position": 30.0,
                "technical_basis": "x", "fundamental_basis": "y",
                "quant_signal": "z", "invalidation_rule": "w",
                "priority": 2,
                "evidence_refs": ["technical.current_price"],  # only 1 — autofill
                "tier": "primary", "narrative": "...",
            },
        ],
    }

    agent = GeminiAnalyzer.__new__(GeminiAnalyzer)
    agent.generate_text = MagicMock(return_value=json.dumps(mock_resp))
    agent._sanitize_strategy_choices = lambda x, **k: x
    agent._recompute_position_outcome_summary = lambda *a, **k: None

    GeminiAnalyzer._try_inject_action_plan_items(
        agent, result, "NVDA", portfolio_context_block=None,
    )

    core = result.dashboard["core_conclusion"]
    items = core["action_plan_items"]
    assert len(items) == 2

    # Invariants
    candidate_ids_in_bundle = {c.id for c in bundle.candidates}
    valid_ids = (
        {f.id for f in bundle.facts}
        | {c.id for c in bundle.candidates}
    )
    for it in items:
        # All candidate_ids must exist
        assert it["candidate_id"] in candidate_ids_in_bundle
        # All evidence_refs must be valid + ≥ 2
        assert all(r in valid_ids for r in it["evidence_refs"])
        assert len(it["evidence_refs"]) >= 2
        # provenance tagged
        assert it.get("provenance") == "llm"
    # Priorities renumbered 1..N
    assert sorted(it["priority"] for it in items) == [1, 2]
