"""Tests that action_plan_items flows through API response schema."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class ActionPlanAPIResponseTestCase(unittest.TestCase):
    def test_analysis_report_schema_has_dashboard_field(self) -> None:
        from api.v1.schemas.history import AnalysisReport
        import inspect
        fields = AnalysisReport.model_fields
        self.assertIn("dashboard", fields)

    def test_build_analysis_response_includes_action_plan_items(self) -> None:
        from src.services.analysis_service import AnalysisService
        from src.analyzer import AnalysisResult

        result = AnalysisResult(
            code="MCD",
            name="McDonald's",
            sentiment_score=50,
            trend_prediction="震荡",
            operation_advice="持有",
            dashboard={
                "core_conclusion": {
                    "one_sentence": "短线回调。",
                    "signal_type": "🟡",
                    "time_sensitivity": "本周内",
                    "position_advice": {"no_position": "观望", "has_position": "持有"},
                    "action_plan_items": [
                        {
                            "trigger_price": 421.0,
                            "trigger_condition": "回踩 MA5",
                            "direction": "sell",
                            "shares": 30,
                            "pct_of_position": 20.0,
                            "pct_of_equity": 3.5,
                            "technical_basis": "RSI=74",
                            "fundamental_basis": "诉讼风险",
                            "quant_signal": "量比 1.8",
                            "invalidation_rule": "站稳 428 作废",
                            "priority": 1,
                        }
                    ],
                }
            },
        )

        svc = AnalysisService.__new__(AnalysisService)
        response = svc._build_analysis_response(result, query_id="test123")
        report = response["report"]
        self.assertIn("dashboard", report)
        self.assertIn("core_conclusion", report["dashboard"])
        items = report["dashboard"]["core_conclusion"].get("action_plan_items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["trigger_price"], 421.0)
        self.assertEqual(items[0]["shares"], 30)

    def test_action_plan_item_schema_accepts_fractional_shares(self) -> None:
        """Trading 212 / Robinhood / etc. let users hold fractional shares (e.g. 0.7597).
        If shares is typed as int, Pydantic silently truncates 0.25 → 0, the renderer
        skips items where `not shares` is true, and entire action plans disappear from
        the API response. shares MUST be float.
        """
        from api.v1.schemas.history import ActionPlanItemSchema

        for fractional in (0.25, 0.05, 0.7597, 1.5):
            item = ActionPlanItemSchema(
                trigger_price=200.0,
                direction="sell",
                shares=fractional,
                priority=1,
            )
            self.assertEqual(item.shares, fractional, f"shares={fractional} must round-trip")

    def test_action_plan_item_schema_accepts_integer_shares(self) -> None:
        """Integer holdings still work."""
        from api.v1.schemas.history import ActionPlanItemSchema
        item = ActionPlanItemSchema(
            trigger_price=200.0, direction="sell", shares=30, priority=1,
        )
        self.assertEqual(item.shares, 30.0)


if __name__ == "__main__":
    unittest.main()
