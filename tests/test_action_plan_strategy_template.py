"""Tests for per-strategy action_plan_items template enforcement (post-process)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer import AnalysisResult, GeminiAnalyzer


_BLOCK_HELD = """## [持仓上下文]
- 账户：T
- 账户总权益：3000.00 GBP
- 持股数量：5 股 / 平均成本：144.0 USD/股
- 当前价：135.0 USD
"""


def _stub_llm(payload: str):
    a = GeminiAnalyzer.__new__(GeminiAnalyzer)
    a.generate_text = lambda *args, **kwargs: payload  # type: ignore[method-assign]
    return a


def _make_result():
    return AnalysisResult(
        code="PLTR", name="Palantir", sentiment_score=50,
        trend_prediction="震荡", operation_advice="减仓",
        analysis_summary="", report_language="zh",
        dashboard={"core_conclusion": {"one_sentence": "x"}},
        portfolio_match="held",
    )


class StrategyTemplateEnforcementTestCase(unittest.TestCase):
    def test_stepped_profit_taking_rejects_buy_items(self):
        """stepped_profit_taking forbids direction=buy (you have profit, don't add more)."""
        payload = json.dumps({
            "recommended_strategy": "stepped_profit_taking",
            "action_plan_items": [
                {"trigger_price": 140.0, "direction": "take_profit",
                 "shares": 1.0, "priority": 1},
                {"trigger_price": 130.0, "direction": "buy",
                 "shares": 1.0, "priority": 2},  # MUST be dropped
                {"trigger_price": 145.0, "direction": "stop_loss",
                 "shares": 2.0, "priority": 3},
            ],
        }, ensure_ascii=False)
        a = _stub_llm(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        directions = [it["direction"] for it in items]
        self.assertNotIn("buy", directions)

    def test_wait_and_see_caps_at_one_item(self):
        payload = json.dumps({
            "recommended_strategy": "wait_and_see",
            "action_plan_items": [
                {"trigger_price": 140.0, "direction": "take_profit",
                 "shares": 1.0, "priority": 1},
                {"trigger_price": 130.0, "direction": "buy",
                 "shares": 1.0, "priority": 2},
                {"trigger_price": 145.0, "direction": "stop_loss",
                 "shares": 2.0, "priority": 3},
            ],
        }, ensure_ascii=False)
        a = _stub_llm(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"].get("action_plan_items", [])
        # wait_and_see accepts at most 1 item (event reminders only)
        self.assertLessEqual(len(items), 1)

    def test_long_term_hold_appends_cost_based_stop_when_missing(self):
        """long_term_hold MUST have a real stop_loss at cost*0.9 or below."""
        payload = json.dumps({
            "recommended_strategy": "long_term_hold",
            "action_plan_items": [
                # LLM forgot the stop_loss
                {"trigger_price": 120.0, "direction": "buy",
                 "shares": 1.0, "priority": 1},
            ],
        }, ensure_ascii=False)
        a = _stub_llm(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        stops = [it for it in items
                 if it["direction"] == "stop_loss"
                 and isinstance(it["trigger_price"], (int, float))
                 and it["trigger_price"] <= 144.0 * 0.91]
        self.assertGreaterEqual(len(stops), 1)


if __name__ == "__main__":
    unittest.main()
