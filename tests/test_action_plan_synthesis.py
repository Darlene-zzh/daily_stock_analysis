"""Tests for action_plan_items synthesis fallback.

When mini models (gpt-5.4-mini etc.) ignore the schema extension and refuse to
emit action_plan_items, we fall back to deriving 1-3 plausible items from the
dashboard + portfolio facts so the UI section still appears.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.portfolio_context_service import (
    _parse_portfolio_facts,
    synthesize_action_plan_items,
)


_HELD_BLOCK_ZH = """## [持仓上下文]
- 账户：Darlene Trading212
- 账户总权益：2396.50 GBP
- 持股数量：0.7597 股 / 平均成本：196.1767 USD/股
- 当前价：225.3200 USD
- 浮动盈亏：+16.62 GBP（+14.86%）
- 首次买入：2026-03-23（已持有 54 天）
- 交易活动：6 笔买入 / 3 笔卖出
"""

_NOT_HELD_BLOCK_ZH = """## [持仓上下文]
- 账户：Darlene Trading212
- 账户总权益：5000.00 GBP
- 用户当前未持有该标的。
"""

_HELD_BLOCK_EN = """## [User Portfolio Context]
- Account: Darlene Trading212
- Account equity: 2396.50 GBP
- Position: 0.7597 shares at avg cost 196.18 USD/share
- Current price: 225.32 USD
"""


def _sample_dashboard():
    return {
        "core_conclusion": {
            "one_sentence": "短线回踩，结构未破。",
            "signal_type": "🟡持有观望",
            "time_sensitivity": "本周内",
        },
        "data_perspective": {
            "trend_status": {"ma_alignment": "bullish", "trend_score": 86, "is_bullish": True},
            "price_position": {"bias_ma5": -0.05, "bias_status": "中性"},
            "volume_analysis": {
                "volume_meaning": "量能正常，回踩节奏",
                "volume_status": "量能正常",
            },
        },
        "intelligence": {
            "earnings_outlook": "业绩窗口临近，关注 5/20 财报",
            "risk_alerts": ["业绩事件风险"],
        },
        "battle_plan": {
            "sniper_points": {
                "ideal_buy": 223.4,
                "secondary_buy": "N/A",
                "stop_loss": 210.3,
                "take_profit": 236.54,
            }
        },
    }


class ParsePortfolioFactsTestCase(unittest.TestCase):
    def test_parses_zh_block(self) -> None:
        facts = _parse_portfolio_facts(_HELD_BLOCK_ZH)
        self.assertAlmostEqual(facts["shares"], 0.7597)
        self.assertAlmostEqual(facts["equity"], 2396.50)
        self.assertEqual(facts["base_currency"], "GBP")
        self.assertEqual(facts["position_currency"], "USD")
        self.assertAlmostEqual(facts["last_price"], 225.32)

    def test_parses_en_block(self) -> None:
        facts = _parse_portfolio_facts(_HELD_BLOCK_EN)
        self.assertAlmostEqual(facts["shares"], 0.7597)
        self.assertAlmostEqual(facts["equity"], 2396.50)
        self.assertEqual(facts["base_currency"], "GBP")

    def test_returns_blank_on_empty(self) -> None:
        facts = _parse_portfolio_facts("")
        self.assertIsNone(facts["shares"])
        self.assertIsNone(facts["equity"])


class SynthesizeActionPlanItemsHeldTestCase(unittest.TestCase):
    def test_held_emits_sell_when_stop_loss_above_cost_basis(self) -> None:
        """Cost=196.18, chart stop_loss=210.3 (> cost*1.02) → reclassify as defensive
        sell, NOT stop_loss. A stop_loss above cost isn't a loss-prevention exit.
        """
        items = synthesize_action_plan_items(
            _sample_dashboard(), _HELD_BLOCK_ZH, is_held=True
        )
        self.assertGreaterEqual(len(items), 2)
        # Primary anchor was chart stop_loss=210.3, but it's above cost → "sell".
        self.assertEqual(items[0]["direction"], "sell")
        self.assertAlmostEqual(items[0]["trigger_price"], 210.3)
        self.assertEqual(items[0]["priority"], 1)
        # No item should carry direction=stop_loss when no level is at/below cost.
        directions = [it["direction"] for it in items]
        self.assertNotIn("stop_loss", directions)
        self.assertIn("take_profit", directions)

    def test_held_stop_loss_kept_when_level_at_or_below_cost(self) -> None:
        """Cost=196.18, chart stop_loss=190 (below cost) → keep as real stop_loss."""
        block = """## [持仓上下文]
- 账户：Darlene
- 账户总权益：3000.00 GBP
- 持股数量：1 股 / 平均成本：196.18 USD/股
- 当前价：225.00 USD
"""
        dash = _sample_dashboard()
        dash["battle_plan"]["sniper_points"]["stop_loss"] = 190.0
        items = synthesize_action_plan_items(dash, block, is_held=True)
        directions = [it["direction"] for it in items]
        self.assertIn("stop_loss", directions)

    def test_held_items_carry_required_rationale_fields(self) -> None:
        items = synthesize_action_plan_items(
            _sample_dashboard(), _HELD_BLOCK_ZH, is_held=True
        )
        for it in items:
            self.assertTrue(it["technical_basis"])
            self.assertTrue(it["fundamental_basis"])
            self.assertTrue(it["invalidation_rule"])
            # quant_signal intentionally allowed to be "" when no real quant data —
            # see SynthesizeQuantSignalTestCase.
            self.assertIn("quant_signal", it)

    def test_held_share_count_anchored_to_actual_holding(self) -> None:
        items = synthesize_action_plan_items(
            _sample_dashboard(), _HELD_BLOCK_ZH, is_held=True
        )
        # 0.7597 shares → integer rounding produces small share counts. Just check
        # that they are positive integers and pct_of_position is between 0 and 100.
        for it in items:
            self.assertGreater(it["shares"], 0)
            if it["pct_of_position"] is not None:
                self.assertGreater(it["pct_of_position"], 0)
                self.assertLessEqual(it["pct_of_position"], 100)


class SynthesizeActionPlanItemsNotHeldTestCase(unittest.TestCase):
    def test_not_held_emits_buy_primary(self) -> None:
        items = synthesize_action_plan_items(
            _sample_dashboard(), _NOT_HELD_BLOCK_ZH, is_held=False
        )
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]["direction"], "buy")
        self.assertAlmostEqual(items[0]["trigger_price"], 223.4)
        self.assertIsNone(items[0]["pct_of_position"])  # no position to pct against
        self.assertGreater(items[0]["pct_of_equity"], 0)


class SynthesizeQuantSignalTestCase(unittest.TestCase):
    """quant_signal should only carry real quantitative numbers — when none are
    available (typical US stock dashboards), the field must be empty so the
    renderer skips it instead of repeating the volume_meaning narrative.
    """

    def test_quant_signal_empty_when_no_real_quant_data(self) -> None:
        dash = _sample_dashboard()
        # _sample_dashboard sets volume_meaning + volume_status but no numeric volume_ratio
        # / turnover / chip — synthesized items' quant_signal should therefore be "".
        items = synthesize_action_plan_items(dash, _HELD_BLOCK_ZH, is_held=True)
        for it in items:
            self.assertEqual(
                it["quant_signal"], "",
                f"quant_signal must be empty for {it['direction']} item without real metrics",
            )

    def test_quant_signal_populated_when_volume_ratio_present(self) -> None:
        dash = _sample_dashboard()
        dash["data_perspective"]["volume_analysis"] = {
            "volume_ratio": 1.8, "turnover_rate": 2.3, "volume_meaning": "irrelevant",
        }
        items = synthesize_action_plan_items(dash, _HELD_BLOCK_ZH, is_held=True)
        self.assertTrue(any("量比 1.80" in it["quant_signal"] for it in items))
        self.assertTrue(any("换手率 2.30%" in it["quant_signal"] for it in items))


class SynthesizeCostBasisGuardTestCase(unittest.TestCase):
    """For a holder whose cost basis is above the chart's take_profit, the synthesis
    must NOT emit a take_profit at a price below cost (= a loss masquerading as
    a "profit"). Either skip the TP item or clamp to break-even-plus.
    """

    BLOCK_UNDERWATER = """## [持仓上下文]
- 账户：Darlene
- 账户总权益：3000.00 GBP
- 持股数量：5 股 / 平均成本：144.0 USD/股
- 当前价：134.0 USD
"""

    def _dash_with_tp_below_cost(self):
        dash = _sample_dashboard()
        dash["battle_plan"]["sniper_points"] = {
            "ideal_buy": 133.0, "stop_loss": 129.0, "take_profit": 140.0,
        }
        return dash

    def test_tp_below_cost_clamped_to_break_even_plus(self) -> None:
        items = synthesize_action_plan_items(
            self._dash_with_tp_below_cost(), self.BLOCK_UNDERWATER, is_held=True
        )
        tp_items = [it for it in items if it["direction"] == "take_profit"]
        self.assertTrue(tp_items, "synthesis should still produce a TP item when TP is close to cost")
        tp = tp_items[0]
        # avg_cost = 144, so anchor should be 144 * 1.02 = 146.88
        self.assertGreater(tp["trigger_price"], 144.0)
        self.assertAlmostEqual(tp["trigger_price"], 146.88)
        self.assertIn("持平偏盈", tp["trigger_condition"])

    def test_tp_far_below_cost_drops_item(self) -> None:
        dash = self._dash_with_tp_below_cost()
        # TP at 100 is far below cost 144 — break-even-plus would be unrealistic
        dash["battle_plan"]["sniper_points"]["take_profit"] = 100.0
        items = synthesize_action_plan_items(dash, self.BLOCK_UNDERWATER, is_held=True)
        directions = [it["direction"] for it in items]
        self.assertNotIn("take_profit", directions)

    def test_tp_above_cost_unchanged(self) -> None:
        block = """## [持仓上下文]
- 账户：Darlene
- 账户总权益：3000.00 GBP
- 持股数量：5 股 / 平均成本：120.0 USD/股
- 当前价：134.0 USD
"""
        items = synthesize_action_plan_items(
            self._dash_with_tp_below_cost(), block, is_held=True
        )
        tp_items = [it for it in items if it["direction"] == "take_profit"]
        self.assertTrue(tp_items)
        # avg_cost 120 < take_profit 140, so no clamp
        self.assertAlmostEqual(tp_items[0]["trigger_price"], 140.0)


class SynthesizeActionPlanItemsEdgeCasesTestCase(unittest.TestCase):
    def test_no_battle_plan_returns_empty(self) -> None:
        dash = _sample_dashboard()
        dash["battle_plan"] = {}
        items = synthesize_action_plan_items(dash, _HELD_BLOCK_ZH, is_held=True)
        self.assertEqual(items, [])

    def test_empty_dashboard_returns_empty(self) -> None:
        self.assertEqual(synthesize_action_plan_items({}, _HELD_BLOCK_ZH, is_held=True), [])

    def test_invalid_dashboard_returns_empty(self) -> None:
        self.assertEqual(
            synthesize_action_plan_items(None, _HELD_BLOCK_ZH, is_held=True),  # type: ignore[arg-type]
            [],
        )


class PipelineFallbackHookTestCase(unittest.TestCase):
    """The pipeline-level wrapper must:
    - Skip when portfolio_context_block is empty.
    - Skip when action_plan_items already populated.
    - Inject synthesized items when they're missing.
    """

    def _make_result(self, action_plan_items=None, portfolio_match="held"):
        from src.analyzer import AnalysisResult
        dashboard = _sample_dashboard()
        if action_plan_items is not None:
            dashboard["core_conclusion"]["action_plan_items"] = action_plan_items
        return AnalysisResult(
            code="NVDA",
            name="NVIDIA",
            sentiment_score=50,
            trend_prediction="震荡",
            operation_advice="持有",
            analysis_summary="...",
            report_language="zh",
            dashboard=dashboard,
            portfolio_match=portfolio_match,
        )

    def test_fill_skipped_when_block_missing(self) -> None:
        from src.core.pipeline import _fill_action_plan_items_if_missing
        result = self._make_result()
        _fill_action_plan_items_if_missing(result, None)
        self.assertIsNone(result.dashboard["core_conclusion"].get("action_plan_items"))

    def test_fill_skipped_when_already_present(self) -> None:
        from src.core.pipeline import _fill_action_plan_items_if_missing
        existing = [{"trigger_price": 1.0, "direction": "buy", "shares": 1, "priority": 1}]
        result = self._make_result(action_plan_items=existing)
        _fill_action_plan_items_if_missing(result, _HELD_BLOCK_ZH)
        # Untouched
        self.assertEqual(
            result.dashboard["core_conclusion"]["action_plan_items"], existing
        )

    def test_fill_synthesizes_when_missing_and_block_present(self) -> None:
        from src.core.pipeline import _fill_action_plan_items_if_missing
        result = self._make_result()
        _fill_action_plan_items_if_missing(result, _HELD_BLOCK_ZH)
        items = result.dashboard["core_conclusion"].get("action_plan_items")
        self.assertIsInstance(items, list)
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], 1)


class AgentPromptOneSentenceFixTestCase(unittest.TestCase):
    """Both agent system prompts must drop the "30字以内" cap so mini models stop
    self-truncating one_sentence with an ellipsis.
    """

    def test_agent_prompt_no_char_limit(self) -> None:
        from src.agent.executor import AGENT_SYSTEM_PROMPT, LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT
        self.assertNotIn("一句话核心结论（30字以内）", AGENT_SYSTEM_PROMPT)
        self.assertNotIn("一句话核心结论（30字以内）", LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT)
        self.assertIn("无字数硬性上限", AGENT_SYSTEM_PROMPT)
        self.assertIn("无字数硬性上限", LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT)


class OrchestratorOneSentenceFallbackTestCase(unittest.TestCase):
    """When the multi-agent reducer doesn't emit core.one_sentence, the orchestrator
    falls back to truncating analysis_summary. The cap must be generous enough that
    the fallback shows the whole decision sentence rather than a fragment + "…".
    """

    def test_fallback_no_longer_re_truncates(self) -> None:
        """analysis_summary is already capped at 220; orchestrator must not re-truncate."""
        from pathlib import Path
        text = Path("src/agent/orchestrator.py").read_text(encoding="utf-8")
        self.assertNotIn("_truncate_text(analysis_summary, 60)", text)
        self.assertNotIn("_truncate_text(analysis_summary, 200)", text)
        self.assertIn('core["one_sentence"] = analysis_summary', text)


if __name__ == "__main__":
    unittest.main()
