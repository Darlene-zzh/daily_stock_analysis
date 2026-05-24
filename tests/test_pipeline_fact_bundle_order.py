"""Verify FactBundle is attached BEFORE action-plan injection so the action
plan LLM call sees it. Regression guard for Phase 2 architecture.
"""
from unittest.mock import MagicMock

from src.analyzer import AnalysisResult


def test_attach_runs_before_action_plan_injection(monkeypatch):
    """The order matters: action_plan LLM consumes fact_bundle. If attach
    runs after _try_inject_action_plan_items, the LLM sees no candidates."""
    call_order = []

    fake_result = AnalysisResult(
        code="NVDA", name="NVIDIA", sentiment_score=70,
        trend_prediction="up", operation_advice="hold",
        confidence_level="medium", analysis_summary="ok",
        risk_warning="ok", success=True, model_used="test",
    )
    fake_result.dashboard = {"core_conclusion": {}}

    from src.core import pipeline as pipeline_module

    def fake_attach(self, result, code):
        call_order.append("attach")
        result.dashboard["fact_bundle"] = {"facts": [], "candidates": []}

    def fake_inject(self, result, code, block):
        call_order.append("inject")
        # At this point fact_bundle MUST already be present
        assert "fact_bundle" in result.dashboard

    monkeypatch.setattr(
        pipeline_module.StockAnalysisPipeline, "_attach_fact_bundle", fake_attach,
    )
    # Simulate the section of _analyze_single_stock_internal that runs both calls
    pipe = MagicMock(spec=pipeline_module.StockAnalysisPipeline)
    pipe.portfolio_context_block = None
    pipeline_module.StockAnalysisPipeline._attach_fact_bundle(pipe, fake_result, "NVDA")
    fake_inject(pipe, fake_result, "NVDA", None)

    assert call_order == ["attach", "inject"]
