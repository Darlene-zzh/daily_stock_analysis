"""Tests that the dashboard notification report filters position-advice rows by portfolio_match."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer import AnalysisResult
from src.notification import NotificationService


def _make_result(portfolio_match=None) -> AnalysisResult:
    return AnalysisResult(
        code="AMD",
        name="AMD",
        sentiment_score=70,
        trend_prediction="看多",
        operation_advice="持有",
        analysis_summary="震荡走强，等待回踩。",
        report_language="zh",
        dashboard={
            "core_conclusion": {
                "one_sentence": "震荡走强，等待回踩。",
                "signal_type": "🟡持有观望",
                "time_sensitivity": "本周内",
                "position_advice": {
                    "no_position": "暂不追高，等 400 附近回踩企稳。",
                    "has_position": "继续持有观察，跌破 395 减仓，放量站稳 433 加仓。",
                },
            },
            "intelligence": {
                "risk_alerts": ["OpenAI vs Musk litigation"],
            },
        },
        portfolio_match=portfolio_match,
    )


class PositionFilterTestCase(unittest.TestCase):
    def test_held_only_renders_has_position_row(self) -> None:
        result = _make_result(portfolio_match="held")
        markdown = NotificationService().generate_dashboard_report([result])
        self.assertIn("持仓者", markdown)
        self.assertNotIn("空仓者", markdown)
        self.assertIn("继续持有观察", markdown)

    def test_not_held_only_renders_no_position_row(self) -> None:
        result = _make_result(portfolio_match="not_held")
        markdown = NotificationService().generate_dashboard_report([result])
        self.assertIn("空仓者", markdown)
        self.assertNotIn("持仓者", markdown)
        self.assertIn("暂不追高", markdown)

    def test_none_renders_both_rows_unchanged(self) -> None:
        result = _make_result(portfolio_match=None)
        markdown = NotificationService().generate_dashboard_report([result])
        self.assertIn("空仓者", markdown)
        self.assertIn("持仓者", markdown)


if __name__ == "__main__":
    unittest.main()
