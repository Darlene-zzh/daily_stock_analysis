"""Tests for the dedicated post-process LLM call that fills action_plan_items.

Mirrors the pattern of _try_inject_zh_translations — a focused, low-token LLM call
that runs after main analysis when mini models drop the action_plan_items field.

We mock generate_text to avoid real LLM traffic.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer import AnalysisResult, GeminiAnalyzer


_BLOCK_HELD = """## [持仓上下文]
- 账户：Darlene
- 账户总权益：3000.00 GBP
- 持股数量：5 股 / 平均成本：144.0 USD/股
- 当前价：134.0 USD
"""


def _dashboard():
    return {
        "core_conclusion": {
            "one_sentence": "PLTR 短线偏弱，等放量确认。",
            "time_sensitivity": "本周内",
        },
        "data_perspective": {
            "trend_status": {"ma_alignment": "bearish", "trend_score": 43},
            "price_position": {"current_price": 134.0, "ma5": 134.13, "support_level": 133.73},
        },
        "intelligence": {
            "risk_alerts": ["高估值风险", "散户情绪降温"],
            "positive_catalysts": ["SAP/Accenture 合作"],
            "earnings_outlook": "短期业绩窗口风险",
        },
        "battle_plan": {
            "sniper_points": {"ideal_buy": 133.73, "stop_loss": 129.45, "take_profit": 140.0},
        },
    }


def _make_result(action_plan_items=None):
    dash = _dashboard()
    if action_plan_items is not None:
        dash["core_conclusion"]["action_plan_items"] = action_plan_items
    return AnalysisResult(
        code="PLTR",
        name="Palantir",
        sentiment_score=43,
        trend_prediction="震荡",
        operation_advice="减仓",
        analysis_summary="",
        report_language="zh",
        dashboard=dash,
        portfolio_match="held",
    )


def _make_analyzer(stubbed_response: str | None):
    """Build an analyzer instance bypassing __init__, with generate_text stubbed."""
    a = GeminiAnalyzer.__new__(GeminiAnalyzer)
    a.generate_text = lambda *args, **kwargs: stubbed_response  # type: ignore[method-assign]
    return a


_LLM_GOOD_RESPONSE = json.dumps({
    "action_plan_items": [
        {
            "trigger_price": 146.88,
            "trigger_condition": "反弹至成本价上方 146.88 持平偏盈",
            "direction": "take_profit",
            "shares": 2,
            "pct_of_position": 40.0,
            "pct_of_equity": 9.8,
            "technical_basis": "突破 MA20 压力，趋势短期修复",
            "fundamental_basis": "SAP/Accenture 合作短期催化",
            "quant_signal": "",
            "invalidation_rule": "无法站稳 144 以上则保留仓位",
            "priority": 1,
        },
        {
            "trigger_price": 129.45,
            "trigger_condition": "收盘有效跌破 129.45 关键支撑",
            "direction": "stop_loss",
            "shares": 5,
            "pct_of_position": 100.0,
            "pct_of_equity": 24.6,
            "technical_basis": "跌破止损位，空头排列确认",
            "fundamental_basis": "估值与情绪双重压力",
            "quant_signal": "",
            "invalidation_rule": "次日强势收回则暂缓",
            "priority": 2,
        },
    ]
}, ensure_ascii=False)


class TryInjectActionPlanItemsTestCase(unittest.TestCase):
    def test_runs_universally_without_portfolio_block(self) -> None:
        """Method is now universal — runs even without a portfolio context block.
        Without portfolio context there is no avg_cost, so cost-basis filtering is
        skipped and valid items are injected.  _LLM_GOOD_RESPONSE only carries
        action_plan_items (no strategy fields), so items should still land in core.
        """
        a = _make_analyzer(_LLM_GOOD_RESPONSE)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", None)
        # Universal: items ARE injected even without portfolio context
        self.assertIsNotNone(result.dashboard["core_conclusion"].get("action_plan_items"))

    def test_skips_when_both_strategy_and_items_already_populated(self) -> None:
        """Skip guard now requires BOTH recommended_strategy (str) AND action_plan_items
        (list) to be filled — a prior layer completed the full strategy classification.
        """
        a = _make_analyzer(_LLM_GOOD_RESPONSE)
        existing = [{"trigger_price": 1, "direction": "buy", "priority": 1}]
        result = _make_result(action_plan_items=existing)
        result.dashboard["core_conclusion"]["recommended_strategy"] = "swing_trade"
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        self.assertEqual(
            result.dashboard["core_conclusion"]["action_plan_items"], existing,
        )
        self.assertEqual(
            result.dashboard["core_conclusion"]["recommended_strategy"], "swing_trade",
        )

    def test_injects_parsed_items_on_success(self) -> None:
        a = _make_analyzer(_LLM_GOOD_RESPONSE)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        self.assertEqual(len(items), 2)
        # Cost-basis respected: take_profit is above 144
        tp = next(it for it in items if it["direction"] == "take_profit")
        self.assertGreater(tp["trigger_price"], 144.0)

    def test_strips_code_fences(self) -> None:
        fenced = f"```json\n{_LLM_GOOD_RESPONSE}\n```"
        a = _make_analyzer(fenced)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        self.assertEqual(len(result.dashboard["core_conclusion"]["action_plan_items"]), 2)

    def test_silent_on_invalid_json(self) -> None:
        a = _make_analyzer("not json at all {{{")
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        self.assertIsNone(result.dashboard["core_conclusion"].get("action_plan_items"))

    def test_silent_on_none_response(self) -> None:
        a = _make_analyzer(None)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        self.assertIsNone(result.dashboard["core_conclusion"].get("action_plan_items"))

    def test_filters_items_missing_required_keys(self) -> None:
        bad = json.dumps({
            "action_plan_items": [
                {"direction": "buy", "priority": 1},  # missing trigger_price
                {"trigger_price": 100.0, "priority": 1},  # missing direction
                {"trigger_price": 130.0, "direction": "stop_loss", "priority": 2},  # ok
            ]
        }, ensure_ascii=False)
        a = _make_analyzer(bad)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["direction"], "stop_loss")

    def test_take_profit_below_cost_basis_dropped(self) -> None:
        """LLM ignores the 'TP > cost basis' instruction sometimes; the post-process
        must drop those mislabeled exits regardless of what the LLM emitted.
        """
        bad = json.dumps({
            "action_plan_items": [
                # cost basis is 144 (per _BLOCK_HELD) — this TP is below cost
                {"trigger_price": 140.86, "direction": "take_profit",
                 "shares": 1, "priority": 1},
                # stop_loss is fine even below cost
                {"trigger_price": 128.47, "direction": "stop_loss",
                 "shares": 5, "priority": 2},
                # TP comfortably above cost — kept
                {"trigger_price": 155.0, "direction": "take_profit",
                 "shares": 2, "priority": 3},
            ]
        }, ensure_ascii=False)
        a = _make_analyzer(bad)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        prices = [it["trigger_price"] for it in items]
        self.assertNotIn(140.86, prices, "TP below cost must be dropped")
        self.assertIn(128.47, prices, "stop_loss kept regardless of cost")
        self.assertIn(155.0, prices, "TP above cost kept")

    def test_take_profit_within_half_pct_of_cost_dropped(self) -> None:
        """TP at exactly cost basis (or within 0.5%) is also not a real profit."""
        bad = json.dumps({
            "action_plan_items": [
                {"trigger_price": 144.50, "direction": "take_profit",
                 "shares": 1, "priority": 1},  # cost=144 → only +0.35%
                {"trigger_price": 200.0, "direction": "stop_loss",
                 "shares": 1, "priority": 2},  # filler so result is non-empty
            ]
        }, ensure_ascii=False)
        a = _make_analyzer(bad)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        prices = [it["trigger_price"] for it in items]
        self.assertNotIn(144.50, prices)

    def test_stop_loss_above_cost_reclassified_as_sell(self) -> None:
        """LLM emits direction=stop_loss for a chart support level that's actually
        above the user's cost basis (defensive trim, not loss prevention). Sanitizer
        must rename to direction=sell so the user doesn't read it as a loss exit.
        """
        bad = json.dumps({
            "action_plan_items": [
                # cost basis is 144 — 200 is +39% in profit, clearly not a "loss"
                {"trigger_price": 200.0, "direction": "stop_loss",
                 "shares": 1, "priority": 1},
                # real stop_loss below cost — keep as is
                {"trigger_price": 130.0, "direction": "stop_loss",
                 "shares": 5, "priority": 2},
            ]
        }, ensure_ascii=False)
        a = _make_analyzer(bad)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        by_price = {it["trigger_price"]: it["direction"] for it in items}
        self.assertEqual(by_price[200.0], "sell", "200 > cost*1.02 → reclassify to sell")
        self.assertEqual(by_price[130.0], "stop_loss", "130 < cost → keep as real stop_loss")

    def test_priorities_renumbered_contiguously_after_filter(self) -> None:
        """After dropping items, surviving items should have priorities 1..N
        (not 1, 3 with a gap where item 2 was filtered out).
        """
        bad = json.dumps({
            "action_plan_items": [
                {"trigger_price": 130.0, "direction": "buy",
                 "shares": 1, "priority": 1},
                # Will be dropped (TP below cost)
                {"trigger_price": 140.0, "direction": "take_profit",
                 "shares": 1, "priority": 2},
                {"trigger_price": 128.0, "direction": "stop_loss",
                 "shares": 5, "priority": 3},
            ]
        }, ensure_ascii=False)
        a = _make_analyzer(bad)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        priorities = [it["priority"] for it in items]
        self.assertEqual(priorities, [1, 2], "post-filter priorities must be contiguous")

    def test_prompt_includes_cost_basis_guidance(self) -> None:
        captured: dict = {}

        def capture(prompt, max_tokens=None, temperature=None):  # noqa: D401
            captured["prompt"] = prompt
            return _LLM_GOOD_RESPONSE

        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        a.generate_text = capture  # type: ignore[method-assign]
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        # Verify the prompt actually surfaces the cost-basis constraint.
        # New prompt uses build_strategy_classify_prompt — check its actual content.
        self.assertIn("成本价", captured["prompt"])
        self.assertIn("持仓上下文", captured["prompt"])
        self.assertIn("144.0 USD/股", captured["prompt"])


class StrategyClassificationInjectionTestCase(unittest.TestCase):
    def _make_result_no_strategy(self):
        from src.analyzer import AnalysisResult
        dash = _dashboard()
        return AnalysisResult(
            code="PLTR", name="Palantir", sentiment_score=43,
            trend_prediction="震荡", operation_advice="减仓",
            analysis_summary="", report_language="zh",
            dashboard=dash, portfolio_match="held",
        )

    def test_runs_without_portfolio_context_too(self):
        """Strategy classification must run for non-portfolio analyses (universal)."""
        payload = json.dumps({
            "strategy_choices": [
                {"id": "swing_trade", "label_zh": "短线波段",
                 "applicable": True, "fit_condition": "趋势强", "key_params": "MA20 防守"},
            ],
            "recommended_strategy": "swing_trade",
            "strategy_thesis": "技术结构健康...",
            "action_plan_items": [
                {"trigger_price": 130.0, "direction": "buy", "shares": 1.0, "priority": 1},
                {"trigger_price": 128.0, "direction": "stop_loss", "shares": 1.0, "priority": 2},
                {"trigger_price": 140.0, "direction": "take_profit", "shares": 1.0, "priority": 3},
            ],
        }, ensure_ascii=False)
        a = _make_analyzer(payload)
        result = self._make_result_no_strategy()
        a._try_inject_action_plan_items(result, "PLTR", portfolio_context_block=None)
        core = result.dashboard["core_conclusion"]
        self.assertEqual(core.get("recommended_strategy"), "swing_trade")
        self.assertEqual(len(core.get("action_plan_items", [])), 3)

    def test_injects_strategy_fields_when_present(self):
        """LLM-provided strategy fields are injected, but position_outcome_summary
        is always recomputed from the sanitized items + real portfolio facts.
        The LLM's self-reported R:R is intentionally ignored (Gemini 2.5 Flash
        routinely emits hallucinated outcome numbers — see commit history)."""
        payload = json.dumps({
            "strategy_choices": [
                {"id": "stepped_profit_taking", "label_zh": "阶梯式止盈",
                 "applicable": True},
                {"id": "swing_trade", "label_zh": "短线波段",
                 "applicable": False, "inapplicable_reason": "已有浮盈"},
            ],
            "recommended_strategy": "stepped_profit_taking",
            "strategy_thesis": "NVDA 当前已 +15% 浮盈...",
            "action_plan_items": [
                {"trigger_price": 236.0, "direction": "take_profit",
                 "shares": 0.25, "priority": 1},
                {"trigger_price": 145.0, "direction": "stop_loss",
                 "shares": 0.5, "priority": 2},
            ],
            "position_outcome_summary": {
                "remaining_shares_after_all_triggers": 0.25,
                "risk_reward_ratio": "1:3",
            },
        }, ensure_ascii=False)
        a = _make_analyzer(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "NVDA", _BLOCK_HELD)
        core = result.dashboard["core_conclusion"]
        self.assertEqual(len(core["strategy_choices"]), 2)
        self.assertEqual(core["strategy_choices"][1]["applicable"], False)
        self.assertIsNotNone(core["position_outcome_summary"])
        # The LLM's "1:3" is replaced by the computed ratio. With a synthesized
        # real cost-based stop at avg_cost × 0.9 dominating the worst-case math,
        # the computed R:R for this scenario is well under 1:1 — exact match
        # would over-specify; just assert it is NOT the LLM's claim.
        self.assertNotEqual(core["position_outcome_summary"]["risk_reward_ratio"], "1:3")
        self.assertIn(":", core["position_outcome_summary"]["risk_reward_ratio"])


class StrategyChoicesSanitizationTestCase(unittest.TestCase):
    def test_positional_id_recovery_when_all_ids_missing(self):
        """LLM emits 4 entries with no id — we recover positionally."""
        payload = json.dumps({
            "recommended_strategy": "stepped_profit_taking",
            "strategy_choices": [
                {"applicable": True, "fit_condition": "x1"},
                {"applicable": False, "inapplicable_reason": "x2"},
                {"applicable": False, "inapplicable_reason": "x3"},
                {"applicable": False, "inapplicable_reason": "x4"},
            ],
            "action_plan_items": [],
        }, ensure_ascii=False)
        a = _make_analyzer(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        choices = result.dashboard["core_conclusion"]["strategy_choices"]
        ids = [c["id"] for c in choices]
        self.assertEqual(ids, ["long_term_hold", "swing_trade",
                                "stepped_profit_taking", "wait_and_see"])

    def test_label_zh_backfilled_from_id(self):
        payload = json.dumps({
            "recommended_strategy": "swing_trade",
            "strategy_choices": [
                {"id": "swing_trade", "applicable": True, "fit_condition": "x"},
            ],
            "action_plan_items": [],
        }, ensure_ascii=False)
        a = _make_analyzer(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        choices = result.dashboard["core_conclusion"]["strategy_choices"]
        self.assertEqual(choices[0]["label_zh"], "短线波段")
        self.assertEqual(choices[0]["emoji"], "⚡")

    def test_empty_entries_dropped(self):
        payload = json.dumps({
            "recommended_strategy": "swing_trade",
            "strategy_choices": [
                {"id": "swing_trade", "applicable": True, "fit_condition": "x"},
                {},  # empty — drop
                {"id": None, "label_zh": None, "applicable": False},  # all none — drop
            ],
            "action_plan_items": [],
        }, ensure_ascii=False)
        a = _make_analyzer(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        choices = result.dashboard["core_conclusion"]["strategy_choices"]
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0]["id"], "swing_trade")

    def test_dedup_by_id(self):
        payload = json.dumps({
            "recommended_strategy": "swing_trade",
            "strategy_choices": [
                {"id": "swing_trade", "applicable": True, "fit_condition": "first"},
                {"id": "swing_trade", "applicable": True, "fit_condition": "duplicate"},
            ],
            "action_plan_items": [],
        }, ensure_ascii=False)
        a = _make_analyzer(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        choices = result.dashboard["core_conclusion"]["strategy_choices"]
        self.assertEqual(len(choices), 1)
        self.assertIn("first", choices[0]["fit_condition"])


if __name__ == "__main__":
    unittest.main()
