"""Tests that the analyzer system prompt adds a bilingual section for US + zh."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer import GeminiAnalyzer


class UsBilingualPromptTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # Bypass __init__ to avoid touching LLM SDK / config.
        self.analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)

    def test_us_zh_appends_bilingual_section(self) -> None:
        prompt = self.analyzer._get_analysis_system_prompt(
            report_language="zh", stock_code="AMD"
        )
        self.assertIn("双语速览", prompt)
        self.assertIn("risk_alerts_zh", prompt)
        self.assertIn("positive_catalysts_zh", prompt)
        self.assertIn("latest_news_zh", prompt)
        self.assertIn("sentiment_summary_zh", prompt)
        self.assertIn("earnings_outlook_zh", prompt)

    def test_cn_zh_does_not_append_bilingual_section(self) -> None:
        prompt = self.analyzer._get_analysis_system_prompt(
            report_language="zh", stock_code="600519"
        )
        self.assertNotIn("双语速览", prompt)
        self.assertNotIn("risk_alerts_zh", prompt)

    def test_hk_zh_does_not_append_bilingual_section(self) -> None:
        prompt = self.analyzer._get_analysis_system_prompt(
            report_language="zh", stock_code="HK00700"
        )
        self.assertNotIn("双语速览", prompt)
        self.assertNotIn("risk_alerts_zh", prompt)

    def test_us_en_does_not_append_bilingual_section(self) -> None:
        # When the user asked for an English report we don't need ZH duplicates.
        prompt = self.analyzer._get_analysis_system_prompt(
            report_language="en", stock_code="AMD"
        )
        self.assertNotIn("双语速览", prompt)
        self.assertNotIn("risk_alerts_zh", prompt)


if __name__ == "__main__":
    unittest.main()
