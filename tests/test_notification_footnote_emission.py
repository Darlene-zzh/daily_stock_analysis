"""End-to-end: feed a single-stock AnalysisResult with dashboard.fact_bundle +
action_plan_items[].evidence_refs through NotificationService.generate_dashboard_report
and assert the footnote block appears at the end of the action plan section.
"""
import pytest

from src.analyzer import AnalysisResult
from src.notification import NotificationService


def _result_with_evidence():
    r = AnalysisResult(
        code="NVDA",
        name="NVIDIA",
        sentiment_score=65,
        trend_prediction="up",
        operation_advice="hold",
        confidence_level="medium",
        analysis_summary="ok",
        risk_warning="ok",
        success=True,
        model_used="test",
        report_language="zh",
    )
    r.dashboard = {
        "core_conclusion": {
            "recommended_strategy": "swing_trade",
            "strategy_thesis": "thesis",
            "strategy_choices": [],
            "action_plan_items": [
                {
                    "candidate_id": "candidate.exit.1",
                    "trigger_price": 226.13,
                    "trigger_condition": "阻力位触及",
                    "direction": "take_profit",
                    "shares": 0,
                    "pct_of_position": 30.0,
                    "technical_basis": "RSI 71.1 超买",
                    "fundamental_basis": "PM hold (5.8/10)",
                    "evidence_refs": ["technical.resistance", "technical.rsi_12",
                                       "committee.pm_verdict"],
                    "tier": "primary",
                    "provenance": "llm",
                    "priority": 1,
                },
            ],
        },
        "fact_bundle": {
            "as_of": "x", "market": "us", "stock_code": "NVDA",
            "facts": [
                {"id": "technical.resistance", "type": "technical",
                 "label": "阻力位", "value": 226.13, "display_value": "$226.13",
                 "unit": None, "source": "", "confidence": None,
                 "as_of": None, "extra": {"role": "阻力"}},
                {"id": "technical.rsi_12", "type": "technical",
                 "label": "RSI(12)", "value": 71.1, "display_value": "71.1",
                 "unit": None, "source": "", "confidence": None,
                 "as_of": None, "extra": {"zone": "超买"}},
                {"id": "committee.pm_verdict", "type": "committee",
                 "label": "PM 裁决", "value": "hold", "display_value": "Hold",
                 "unit": None, "source": "", "confidence": None,
                 "as_of": None, "extra": {}},
            ],
            "candidates": [],
        },
    }
    return r


def test_notification_emits_footnote_section_after_action_plan():
    svc = NotificationService()
    md = svc.generate_dashboard_report([_result_with_evidence()])
    assert "📋 持仓操作计划" in md
    assert "**证据脚注**" in md
    plan_idx = md.index("📋 持仓操作计划")
    footnote_idx = md.index("**证据脚注**")
    assert plan_idx < footnote_idx


def test_notification_no_footnote_section_when_bundle_missing():
    result = _result_with_evidence()
    result.dashboard.pop("fact_bundle", None)
    svc = NotificationService()
    md = svc.generate_dashboard_report([result])
    assert "📋 持仓操作计划" in md
    assert "**证据脚注**" not in md
