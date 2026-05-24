"""When fact_bundle is on dashboard, _try_inject_action_plan_items must:
  1. Pass the bundle into the prompt builder
  2. Stash bundle + current_price on self for the sanitizer
  3. Fall back to synthesize_from_candidates when sanitizer empties
"""
import json
from unittest.mock import MagicMock

from src.analyzer import GeminiAnalyzer, AnalysisResult


def _result_with_bundle():
    r = AnalysisResult(
        code="NVDA", name="NVIDIA", sentiment_score=70,
        trend_prediction="up", operation_advice="hold",
        confidence_level="medium", analysis_summary="ok",
        risk_warning="ok", success=True, model_used="test",
    )
    r.dashboard = {
        "core_conclusion": {},
        "data_perspective": {"price_position": {"current_price": 223.47}},
        "intelligence": {},
        "fact_bundle": {
            "as_of": "x", "market": "us", "stock_code": "NVDA",
            "facts": [
                {"id": "technical.current_price", "type": "technical", "label": "现价",
                 "value": 223.47, "display_value": "$223.47", "unit": None,
                 "source": "", "confidence": None, "as_of": None, "extra": {}},
                {"id": "technical.resistance", "type": "technical", "label": "阻力",
                 "value": 226.13, "display_value": "$226.13", "unit": None,
                 "source": "", "confidence": None, "as_of": None, "extra": {}},
                {"id": "committee.pm_verdict", "type": "committee", "label": "PM",
                 "value": "hold", "display_value": "Hold", "unit": None,
                 "source": "", "confidence": None, "as_of": None, "extra": {}},
            ],
            "candidates": [
                {"id": "candidate.exit.1", "type": "candidate", "label": "阻力",
                 "value": 226.13, "display_value": "$226.13", "unit": None,
                 "source": "", "confidence": None, "as_of": None, "extra": {},
                 "direction": "take_profit", "price": 226.13,
                 "basis_fact_id": "technical.resistance",
                 "basis_rule": "resistance_touch",
                 "applicable_strategies": ["swing_trade"],
                 "tier": "primary", "distance_pct_from_current": 1.2},
                {"id": "candidate.stop.1", "type": "candidate", "label": "MA20",
                 "value": 213.39, "display_value": "$213.39", "unit": None,
                 "source": "", "confidence": None, "as_of": None, "extra": {},
                 "direction": "stop_loss", "price": 213.39,
                 "basis_fact_id": "technical.ma20",
                 "basis_rule": "ma20_breakdown",
                 "applicable_strategies": ["swing_trade"],
                 "tier": "primary", "distance_pct_from_current": -4.5},
            ],
        },
    }
    r.portfolio_match = None
    return r


def test_inject_passes_bundle_to_prompt_builder():
    """The prompt sent to the LLM must include the [事实数据库] block."""
    agent = GeminiAnalyzer.__new__(GeminiAnalyzer)
    agent.generate_text = MagicMock(return_value=json.dumps({
        "recommended_strategy": "swing_trade",
        "strategy_thesis": "thesis",
        "strategy_choices": [],
        "action_plan_items": [{
            "candidate_id": "candidate.exit.1", "trigger_price": 226.13,
            "direction": "take_profit", "priority": 1,
            "evidence_refs": ["technical.resistance", "committee.pm_verdict"],
            "tier": "primary",
        }],
    }))
    agent._sanitize_strategy_choices = lambda x, **k: x
    agent._recompute_position_outcome_summary = lambda *a, **k: None

    result = _result_with_bundle()
    GeminiAnalyzer._try_inject_action_plan_items(
        agent, result, "NVDA", portfolio_context_block=None,
    )
    sent_prompt = agent.generate_text.call_args[0][0]
    assert "[事实数据库]" in sent_prompt
    assert "[候选触发价位]" in sent_prompt
    assert "candidate.exit.1" in sent_prompt


def test_inject_falls_back_to_synthesizer_when_sanitizer_empties():
    """LLM emits all-invalid candidate_ids → sanitizer drops everything →
    synthesizer fills the gap with candidate-based items."""
    agent = GeminiAnalyzer.__new__(GeminiAnalyzer)
    agent.generate_text = MagicMock(return_value=json.dumps({
        "recommended_strategy": "swing_trade",
        "strategy_thesis": "thesis",
        "strategy_choices": [],
        "action_plan_items": [
            # All candidate_ids are bogus → sanitizer drops them
            {"candidate_id": "candidate.fake.1", "trigger_price": 999,
             "direction": "take_profit", "priority": 1,
             "evidence_refs": ["a", "b"], "tier": "primary"},
        ],
    }))
    agent._sanitize_strategy_choices = lambda x, **k: x
    agent._recompute_position_outcome_summary = lambda *a, **k: None

    result = _result_with_bundle()
    GeminiAnalyzer._try_inject_action_plan_items(
        agent, result, "NVDA", portfolio_context_block=None,
    )
    items = result.dashboard["core_conclusion"]["action_plan_items"]
    assert len(items) >= 1
    assert all(it.get("provenance") == "synthesized" for it in items)
    # Real candidate.exit.1 / candidate.stop.1 should now be the synthesized basis
    cids = [it["candidate_id"] for it in items]
    assert any(cid in ("candidate.exit.1", "candidate.stop.1") for cid in cids)
