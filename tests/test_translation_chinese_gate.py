"""Tests for the Chinese-content gate that suppresses redundant `_zh`
translation when the source intelligence field is already Chinese.

Background: when Gemini's daily cap is hit and the Router falls through to
Cerebras Qwen3-235B / OpenRouter DeepSeek-V4 (both Chinese-native), the
analysis comes back with Chinese in the base `risk_alerts` / `latest_news`
fields. The old `_try_inject_zh_translations` fired unconditionally and
re-translated Chinese→Chinese, producing two paraphrased copies on the
dashboard. The gate now skips the LLM call AND leaves the `*_zh` slot
absent when the content is already CJK — the renderers fall back to the
original field, so a single Chinese copy is shown instead of a duplicate.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FieldIsPredominantlyChineseTestCase(unittest.TestCase):

    def test_pure_english_string_is_not_chinese(self):
        from src.analyzer import _field_is_predominantly_chinese
        self.assertFalse(_field_is_predominantly_chinese(
            "AMD beat Q2 earnings expectations on data center revenue."
        ))

    def test_pure_chinese_string_is_chinese(self):
        from src.analyzer import _field_is_predominantly_chinese
        self.assertTrue(_field_is_predominantly_chinese(
            "AMD 数据中心业务收入超预期，二季度业绩明显改善。"
        ))

    def test_chinese_with_english_tickers_still_chinese(self):
        from src.analyzer import _field_is_predominantly_chinese
        # Common pattern: Chinese sentence with English ticker / company name
        self.assertTrue(_field_is_predominantly_chinese(
            "NVDA 维持多头排列，价格回踩 MA5，乖离率 -4.76% 安全。"
        ))

    def test_english_mentioning_chinese_company_is_not_chinese(self):
        from src.analyzer import _field_is_predominantly_chinese
        self.assertFalse(_field_is_predominantly_chinese(
            "Tencent (TCEHY) reported strong gaming revenue this quarter."
        ))

    def test_list_of_chinese_strings(self):
        from src.analyzer import _field_is_predominantly_chinese
        self.assertTrue(_field_is_predominantly_chinese([
            "估值偏高，PE 远超历史均值",
            "DC GPU 需求面临结构性放缓风险",
        ]))

    def test_list_of_english_strings(self):
        from src.analyzer import _field_is_predominantly_chinese
        self.assertFalse(_field_is_predominantly_chinese([
            "Valuation stretched vs historical average.",
            "DC GPU demand may slow structurally.",
        ]))

    def test_list_of_dicts_with_text_field(self):
        from src.analyzer import _field_is_predominantly_chinese
        # latest_news commonly comes as list of dicts
        self.assertTrue(_field_is_predominantly_chinese([
            {"title": "英伟达 Q3 数据中心营收创纪录", "summary": "受 H200 出货推动"},
            {"title": "微软扩大 AI 数据中心投资规模", "summary": "全年资本支出预期上调"},
        ]))

    def test_empty_value_returns_false(self):
        from src.analyzer import _field_is_predominantly_chinese
        self.assertFalse(_field_is_predominantly_chinese(""))
        self.assertFalse(_field_is_predominantly_chinese([]))
        self.assertFalse(_field_is_predominantly_chinese(None))


class TranslationGateTestCase(unittest.TestCase):
    """End-to-end: _try_inject_zh_translations should NOT call the LLM when
    the source fields are already Chinese."""

    def _make_result(self, intel_fields: dict):
        from src.analyzer import AnalysisResult
        r = AnalysisResult.__new__(AnalysisResult)
        r.code = "NVDA"
        r.name = "NVIDIA"
        r.report_language = "zh"
        r.dashboard = {"intelligence": dict(intel_fields)}
        return r

    def test_skips_llm_call_when_source_is_chinese(self):
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        result = self._make_result({
            "risk_alerts": ["估值偏高，PE 远超历史均值"],
            "positive_catalysts": ["数据中心业务持续放量"],
            "sentiment_summary": "市场情绪积极，但有分歧",
        })

        with patch.object(analyzer, "generate_text", return_value="{}") as mock_llm:
            analyzer._try_inject_zh_translations(result, "NVDA")

        mock_llm.assert_not_called()
        # Chinese source is left as-is: no `*_zh` mirror, so the renderer shows
        # the original field once instead of printing the same Chinese twice.
        intel = result.dashboard["intelligence"]
        self.assertNotIn("risk_alerts_zh", intel)
        self.assertNotIn("positive_catalysts_zh", intel)
        self.assertNotIn("sentiment_summary_zh", intel)

    def test_does_translate_english_source(self):
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        result = self._make_result({
            "risk_alerts": ["Valuation stretched vs peers."],
            "positive_catalysts": ["Data center revenue accelerating."],
        })

        fake_response = (
            '{"risk_alerts_zh": ["估值高于同业"], '
            '"positive_catalysts_zh": ["数据中心营收加速"]}'
        )
        with patch.object(analyzer, "generate_text", return_value=fake_response) as mock_llm:
            analyzer._try_inject_zh_translations(result, "NVDA")

        mock_llm.assert_called_once()
        intel = result.dashboard["intelligence"]
        self.assertEqual(intel["risk_alerts_zh"], ["估值高于同业"])
        self.assertEqual(intel["positive_catalysts_zh"], ["数据中心营收加速"])

    def test_mixed_source_translates_only_english_fields(self):
        """Some fields English, some Chinese — translate only the English ones."""
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        result = self._make_result({
            "risk_alerts": ["Concentration risk in DC segment."],          # English
            "positive_catalysts": ["AI 推理需求强劲，订单饱满"],            # Chinese
        })

        fake_response = '{"risk_alerts_zh": ["DC 业务集中度风险"]}'
        with patch.object(analyzer, "generate_text", return_value=fake_response) as mock_llm:
            analyzer._try_inject_zh_translations(result, "NVDA")

        # LLM was called once (for the English field). The Chinese field is
        # neither sent to the LLM nor mirrored into a `*_zh` slot.
        mock_llm.assert_called_once()
        # The prompt sent to the LLM must NOT include the Chinese-source field.
        sent_prompt = mock_llm.call_args[0][0]
        self.assertIn("Concentration risk", sent_prompt)
        self.assertNotIn("AI 推理需求强劲", sent_prompt)
        # Only the English field gets a `*_zh` translation; the Chinese field
        # keeps its original value with no `*_zh` mirror.
        intel = result.dashboard["intelligence"]
        self.assertEqual(intel["risk_alerts_zh"], ["DC 业务集中度风险"])
        self.assertNotIn("positive_catalysts_zh", intel)


if __name__ == "__main__":
    unittest.main()
