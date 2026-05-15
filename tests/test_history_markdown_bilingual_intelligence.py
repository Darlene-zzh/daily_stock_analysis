"""Tests that history_service single-stock markdown appends `中：` sub-lines."""

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


def _make_result(intel) -> AnalysisResult:
    return AnalysisResult(
        code="AMD",
        name="AMD",
        sentiment_score=70,
        trend_prediction="看多",
        operation_advice="持有",
        analysis_summary="震荡走强。",
        report_language="zh",
        dashboard={
            "core_conclusion": {
                "one_sentence": "震荡走强。",
                "signal_type": "🟡持有观望",
                "time_sensitivity": "本周内",
                "position_advice": {
                    "no_position": "暂不追高。",
                    "has_position": "继续持有。",
                },
            },
            "intelligence": intel,
        },
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


class HistoryMarkdownBilingualIntelligenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HistoryService.__new__(HistoryService)

    def test_paired_lists_emit_zh_subline_per_item(self) -> None:
        md = self.service._generate_single_stock_markdown(
            _make_result({
                "risk_alerts": ["OpenAI vs Musk litigation"],
                "risk_alerts_zh": ["OpenAI 与马斯克的诉讼"],
                "positive_catalysts": ["Bill Ackman stake"],
                "positive_catalysts_zh": ["艾克曼建仓"],
                "latest_news": "MSFT news.",
                "latest_news_zh": "微软消息。",
                "sentiment_summary": "Mixed positive.",
                "sentiment_summary_zh": "整体偏正向。",
                "earnings_outlook": "Up 2%.",
                "earnings_outlook_zh": "上调 2%。",
            }),
            _fake_record(),
        )
        self.assertIn("OpenAI vs Musk litigation", md)
        self.assertIn("中：OpenAI 与马斯克的诉讼", md)
        self.assertIn("中：艾克曼建仓", md)
        self.assertIn("中：微软消息。", md)
        self.assertIn("中：整体偏正向。", md)
        self.assertIn("中：上调 2%。", md)

    def test_missing_zh_falls_back_to_english_only(self) -> None:
        md = self.service._generate_single_stock_markdown(
            _make_result({
                "risk_alerts": ["alert"],
                "positive_catalysts": ["catalyst"],
                "latest_news": "news",
                "sentiment_summary": "summary",
                "earnings_outlook": "outlook",
            }),
            _fake_record(),
        )
        self.assertIn("alert", md)
        self.assertNotIn("中：", md)

    def test_short_zh_list_does_per_item_fallback(self) -> None:
        md = self.service._generate_single_stock_markdown(
            _make_result({
                "risk_alerts": ["one", "two", "three"],
                "risk_alerts_zh": ["告警 1"],
            }),
            _fake_record(),
        )
        self.assertIn("中：告警 1", md)
        self.assertEqual(md.count("中："), 1)


if __name__ == "__main__":
    unittest.main()
