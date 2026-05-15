"""Tests that history_service single-stock markdown filters position rows by portfolio_match."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer import AnalysisResult
from src.services.history_service import HistoryService


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
            "intelligence": {"risk_alerts": []},
        },
        portfolio_match=portfolio_match,
    )


def _fake_record() -> SimpleNamespace:
    return SimpleNamespace(
        code="AMD",
        name="AMD",
        sentiment_score=70,
        trend_prediction="看多",
        operation_advice="持有",
        analysis_summary="",
        news_content="",
        created_at=datetime(2026, 5, 15, 12, 0, 0),
    )


class HistoryMarkdownPositionFilterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HistoryService.__new__(HistoryService)

    def test_held_only_renders_has_position_row(self) -> None:
        md = self.service._generate_single_stock_markdown(_make_result("held"), _fake_record())
        self.assertIn("持仓者", md)
        self.assertNotIn("空仓者", md)

    def test_not_held_only_renders_no_position_row(self) -> None:
        md = self.service._generate_single_stock_markdown(_make_result("not_held"), _fake_record())
        self.assertIn("空仓者", md)
        self.assertNotIn("持仓者", md)

    def test_none_renders_both_rows_unchanged(self) -> None:
        md = self.service._generate_single_stock_markdown(_make_result(None), _fake_record())
        self.assertIn("空仓者", md)
        self.assertIn("持仓者", md)


if __name__ == "__main__":
    unittest.main()
