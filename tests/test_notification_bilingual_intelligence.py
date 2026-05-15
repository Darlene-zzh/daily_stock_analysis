"""Tests that the dashboard notification report appends `中：` sub-lines per _zh field."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer import AnalysisResult
from src.notification import NotificationService


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


class NotificationBilingualIntelligenceTestCase(unittest.TestCase):
    def test_paired_lists_emit_zh_subline_per_item(self) -> None:
        result = _make_result({
            "risk_alerts": ["OpenAI vs Musk litigation"],
            "risk_alerts_zh": ["OpenAI 与马斯克的诉讼"],
            "positive_catalysts": ["Bill Ackman revealed a new MSFT stake"],
            "positive_catalysts_zh": ["艾克曼披露新建仓微软"],
            "latest_news": "MSFT announces partnership.",
            "latest_news_zh": "微软宣布新合作。",
            "sentiment_summary": "Mixed but tilting positive.",
            "sentiment_summary_zh": "整体偏正向。",
            "earnings_outlook": "FY26 EPS revised up 2%.",
            "earnings_outlook_zh": "FY26 EPS 上调 2%。",
        })
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("OpenAI vs Musk litigation", md)
        self.assertIn("中：OpenAI 与马斯克的诉讼", md)
        self.assertIn("Bill Ackman revealed a new MSFT stake", md)
        self.assertIn("中：艾克曼披露新建仓微软", md)
        self.assertIn("中：微软宣布新合作。", md)
        self.assertIn("中：整体偏正向。", md)
        self.assertIn("中：FY26 EPS 上调 2%。", md)

    def test_missing_zh_falls_back_to_english_only(self) -> None:
        result = _make_result({
            "risk_alerts": ["OpenAI vs Musk litigation"],
            "positive_catalysts": ["Bill Ackman stake"],
            "latest_news": "MSFT news.",
            "sentiment_summary": "Mixed.",
            "earnings_outlook": "Up.",
        })
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("OpenAI vs Musk litigation", md)
        self.assertNotIn("中：", md)

    def test_short_zh_list_does_per_item_fallback(self) -> None:
        result = _make_result({
            "risk_alerts": ["alert one", "alert two", "alert three"],
            "risk_alerts_zh": ["告警 1"],  # only first item translated
        })
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("中：告警 1", md)
        # second/third items keep English only, no malformed "中：" lines
        zh_count = md.count("中：")
        self.assertEqual(zh_count, 1)

    def test_empty_zh_string_skips_subline(self) -> None:
        result = _make_result({
            "risk_alerts": ["alert one", "alert two"],
            "risk_alerts_zh": ["告警 1", ""],  # second item empty
        })
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("中：告警 1", md)
        # Empty string must not produce a "中：" line
        zh_count = md.count("中：")
        self.assertEqual(zh_count, 1)


if __name__ == "__main__":
    unittest.main()
