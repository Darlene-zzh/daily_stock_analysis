"""Tests that the system prompt JSON example includes action_plan_items."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class SystemPromptActionPlanItemsTestCase(unittest.TestCase):
    def _get_prompts(self):
        from src.analyzer import GeminiAnalyzer
        return GeminiAnalyzer.SYSTEM_PROMPT, GeminiAnalyzer.LEGACY_DEFAULT_SYSTEM_PROMPT

    def test_system_prompt_has_action_plan_items_example(self) -> None:
        sp, _ = self._get_prompts()
        self.assertIn("action_plan_items", sp)
        self.assertIn("trigger_price", sp)
        self.assertIn("trigger_condition", sp)
        self.assertIn("pct_of_equity", sp)
        self.assertIn("technical_basis", sp)
        self.assertIn("fundamental_basis", sp)
        self.assertIn("quant_signal", sp)
        self.assertIn("invalidation_rule", sp)

    def test_legacy_prompt_has_action_plan_items_example(self) -> None:
        _, lp = self._get_prompts()
        self.assertIn("action_plan_items", lp)
        self.assertIn("trigger_price", lp)
        self.assertIn("pct_of_equity", lp)

    def test_format_prompt_injects_action_plan_instruction_when_portfolio_present(self) -> None:
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        prompt = a._format_prompt(
            context={
                "code": "AMD",
                "date": "2026-05-16",
                "today": {},
            },
            name="AMD",
            portfolio_context_block="## [持仓上下文]\n- 账户：Test\n- 账户总权益：2189.00 GBP\n- 持股数量：50.0 股",
        )
        self.assertIn("action_plan_items", prompt)
        self.assertIn("trigger_price", prompt)
        self.assertIn("pct_of_equity", prompt)
        self.assertIn("technical_basis", prompt)

    def test_format_prompt_no_action_plan_without_portfolio(self) -> None:
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        prompt = a._format_prompt(
            context={"code": "600519", "date": "2026-05-16", "today": {}},
            name="贵州茅台",
        )
        # No portfolio context → no action plan instruction
        self.assertNotIn("[操作计划指令]", prompt)


if __name__ == "__main__":
    unittest.main()
