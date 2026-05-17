"""Tests for the always-sanitize behavior of _try_inject_action_plan_items.

Regression: Gemini 2.5 Flash (and similar mini/flash models) routinely emit a
strategy-inconsistent action_plan_items list — e.g. a stop_loss item alongside
recommended_strategy="wait_and_see", or a single stop_loss when
recommended_strategy="stepped_profit_taking" demands a take_profit ladder.

Before the fix the post-process enforcer skipped sanitization whenever the LLM
had already filled both `recommended_strategy` and `action_plan_items`, so the
bad output flowed straight to the DB. The enforcer now always sanitizes and
recomputes position_outcome_summary from the sanitized list.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_PORTFOLIO_BLOCK_HELD = """
持仓状态：已持有
持股数量：1.1824 股
平均成本：396.81 USD/股
当前价：421.92
账户总权益：3000.00 GBP
"""


def _make_result(*, recommended_strategy, items, strategy_choices=None, outcome=None):
    """Build a minimal AnalysisResult-like stub with a populated dashboard."""
    from src.analyzer import AnalysisResult

    result = AnalysisResult.__new__(AnalysisResult)
    result.name = "Stub"
    result.portfolio_match = "held"
    core = {
        "recommended_strategy": recommended_strategy,
        "action_plan_items": items,
    }
    if strategy_choices is not None:
        core["strategy_choices"] = strategy_choices
    if outcome is not None:
        core["position_outcome_summary"] = outcome
    result.dashboard = {"core_conclusion": core, "battle_plan": {}, "intelligence": {}}
    return result


class EnforcerAlwaysSanitizesTestCase(unittest.TestCase):
    """The enforcer must apply _sanitize_action_plan_items even when the LLM
    already provided both recommended_strategy and action_plan_items."""

    def test_wait_and_see_strips_stop_loss_emitted_by_llm(self):
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        result = _make_result(
            recommended_strategy="wait_and_see",
            items=[
                {
                    "direction": "stop_loss",
                    "trigger_price": 105.0,
                    "shares": 0.15,
                    "pct_of_position": 50.0,
                    "priority": 1,
                }
            ],
        )

        analyzer._try_inject_action_plan_items(result, "CRWV", _PORTFOLIO_BLOCK_HELD)

        core = result.dashboard["core_conclusion"]
        self.assertEqual(
            core["action_plan_items"], [],
            "wait_and_see must produce zero action_plan_items after sanitization",
        )
        self.assertNotIn(
            "position_outcome_summary", core,
            "with no items, position_outcome_summary must be suppressed entirely",
        )

    def test_stepped_profit_taking_keeps_take_profit_items(self):
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        result = _make_result(
            recommended_strategy="stepped_profit_taking",
            items=[
                {"direction": "take_profit", "trigger_price": 440.0, "shares": 0.4, "priority": 1},
                {"direction": "take_profit", "trigger_price": 460.0, "shares": 0.4, "priority": 2},
            ],
        )

        analyzer._try_inject_action_plan_items(result, "MSFT", _PORTFOLIO_BLOCK_HELD)

        core = result.dashboard["core_conclusion"]
        take_profits = [
            it for it in core["action_plan_items"] if it.get("direction") == "take_profit"
        ]
        self.assertEqual(len(take_profits), 2, "both take_profit items must survive")
        # A real cost-based stop_loss must be synthesized at avg_cost * 0.9 ≈ 357.13
        stops = [it for it in core["action_plan_items"] if it.get("direction") == "stop_loss"]
        self.assertTrue(stops, "stepped_profit_taking must always carry a real stop")

    def test_llm_emitted_outcome_with_bogus_numbers_is_replaced(self):
        """Regression: Gemini hallucinated -£2394 worst-case loss for MSFT when the
        real position can lose at most ~£35 against a 10% cost-basis stop."""
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        bogus_outcome = {
            "remaining_shares_after_all_triggers": 0.0,
            "worst_case_loss_amount": -2394.94,
            "worst_case_currency": "GBP",
            "best_case_gain_amount": 718.48,
            "risk_reward_ratio": "1:0.3",
        }
        result = _make_result(
            recommended_strategy="stepped_profit_taking",
            items=[
                {
                    "direction": "stop_loss",
                    "trigger_price": 357.13,
                    "shares": 0,
                    "pct_of_position": 100.0,
                    "priority": 1,
                }
            ],
            outcome=bogus_outcome,
        )

        analyzer._try_inject_action_plan_items(result, "MSFT", _PORTFOLIO_BLOCK_HELD)

        core = result.dashboard["core_conclusion"]
        outcome = core.get("position_outcome_summary")
        self.assertIsNotNone(outcome, "outcome must be recomputed, not removed")
        # Worst case: stop @ 357.13 on 1.1824 shares (derived from 100% pct), cost 396.81
        # = (357.13 - 396.81) * 1.1824 ≈ -46.92 USD — nowhere near -2394 GBP
        self.assertNotAlmostEqual(
            outcome["worst_case_loss_amount"], -2394.94, places=1,
            msg="bogus LLM-emitted figure must be overwritten",
        )
        self.assertLess(
            abs(outcome["worst_case_loss_amount"]), 100.0,
            "recomputed worst-case must reflect a 10% stop on 1.18 shares, not a £2k loss",
        )

    def test_empty_items_after_filtering_also_drops_outcome(self):
        """If wait_and_see drops the only item the LLM gave us, the outcome card
        must be hidden — not shown as 0/0/N/A."""
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        result = _make_result(
            recommended_strategy="wait_and_see",
            items=[{"direction": "stop_loss", "trigger_price": 100.0, "shares": 1.0, "priority": 1}],
            outcome={"worst_case_loss_amount": -50.0, "risk_reward_ratio": "1:2"},
        )

        analyzer._try_inject_action_plan_items(result, "STUB", _PORTFOLIO_BLOCK_HELD)

        core = result.dashboard["core_conclusion"]
        self.assertEqual(core["action_plan_items"], [])
        self.assertNotIn("position_outcome_summary", core)


class ComputeOutcomeSharesDerivationTestCase(unittest.TestCase):
    """Items with shares=0 but pct_of_position>0 must derive shares from pct
    times holding_shares (LLM frequently leaves shares blank)."""

    def test_pct_of_position_derives_shares_when_shares_zero(self):
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        items = [
            {"direction": "stop_loss", "trigger_price": 90.0, "shares": 0, "pct_of_position": 100.0},
        ]
        outcome = analyzer._compute_position_outcome_summary(
            items=items, holding_shares=2.0, avg_cost=100.0,
            current_price=95.0, base_currency="USD",
        )
        self.assertIsNotNone(outcome)
        # (90 - 100) * 2.0 = -20
        self.assertAlmostEqual(outcome["worst_case_loss_amount"], -20.0)
        self.assertAlmostEqual(outcome["remaining_shares_after_all_triggers"], 0.0, places=3)

    def test_pct_over_100_is_capped_to_actual_holding(self):
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        items = [
            {"direction": "stop_loss", "trigger_price": 90.0, "shares": 0, "pct_of_position": 150.0},
        ]
        outcome = analyzer._compute_position_outcome_summary(
            items=items, holding_shares=2.0, avg_cost=100.0,
            current_price=95.0, base_currency="USD",
        )
        # Capped to 2.0 shares: (90 - 100) * 2.0 = -20 (NOT -30)
        self.assertAlmostEqual(outcome["worst_case_loss_amount"], -20.0)

    def test_no_actionable_items_returns_none(self):
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        # All items have shares=0 AND no pct — nothing to compute against
        items = [
            {"direction": "stop_loss", "trigger_price": 90.0, "shares": 0},
        ]
        outcome = analyzer._compute_position_outcome_summary(
            items=items, holding_shares=2.0, avg_cost=100.0,
            current_price=95.0, base_currency="USD",
        )
        self.assertIsNone(outcome)


class WaitAndSeeMaxItemsTestCase(unittest.TestCase):
    """The wait_and_see cap was 1; it must be 0 so the sanitizer drops everything."""

    def test_wait_and_see_cap_is_zero(self):
        from src.analyzer import GeminiAnalyzer

        self.assertEqual(GeminiAnalyzer._STRATEGY_MAX_ITEMS["wait_and_see"], 0)


class SteppedProfitTakingLadderSynthesisTestCase(unittest.TestCase):
    """When Gemini emits `recommended_strategy=stepped_profit_taking` but no
    take_profit items, the post-process must synthesize a 3-step ladder anchored
    on cost basis. Without this, the user sees "AI 推荐分批止盈" with zero
    concrete trigger prices — exactly the screenshot the user flagged.
    """

    def test_synthesizes_three_step_ladder_when_no_tps(self):
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        # Cost 100, 1 share, no take_profit emitted by LLM
        result = analyzer._sanitize_action_plan_items(
            items=[],
            portfolio_context_block=(
                "持仓状态：已持有\n持股数量：1 股\n平均成本：100.0 USD/股\n"
                "当前价：106.0\n账户总权益：500.00 GBP\n"
            ),
            code="STUB",
            strategy="stepped_profit_taking",
        )

        take_profits = [it for it in result if it.get("direction") == "take_profit"]
        self.assertEqual(len(take_profits), 3, "must synth exactly 3 ladder rungs")
        # Triggers should be ascending: +5%, +12%, +20%
        triggers = sorted(it["trigger_price"] for it in take_profits)
        self.assertAlmostEqual(triggers[0], 105.0)
        self.assertAlmostEqual(triggers[1], 112.0)
        self.assertAlmostEqual(triggers[2], 120.0)
        # Allocation should add up to 100%
        total_pct = sum(it["pct_of_position"] for it in take_profits)
        self.assertEqual(total_pct, 100.0)

    def test_does_not_double_synth_when_llm_already_emitted_a_tp(self):
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        llm_tp = {
            "trigger_price": 115.0,
            "direction": "take_profit",
            "shares": 0.5,
            "priority": 1,
        }
        result = analyzer._sanitize_action_plan_items(
            items=[llm_tp],
            portfolio_context_block=(
                "持仓状态：已持有\n持股数量：1 股\n平均成本：100.0 USD/股\n"
                "当前价：110.0\n账户总权益：500.00 GBP\n"
            ),
            code="STUB",
            strategy="stepped_profit_taking",
        )

        take_profits = [it for it in result if it.get("direction") == "take_profit"]
        self.assertEqual(len(take_profits), 1, "must NOT synth when LLM already provided a TP")
        self.assertAlmostEqual(take_profits[0]["trigger_price"], 115.0)

    def test_ladder_synth_includes_real_cost_stop_loss(self):
        """The defensive stop at cost × 0.9 must coexist with the new TP ladder."""
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        result = analyzer._sanitize_action_plan_items(
            items=[],
            portfolio_context_block=(
                "持仓状态：已持有\n持股数量：1 股\n平均成本：100.0 USD/股\n"
                "当前价：106.0\n账户总权益：500.00 GBP\n"
            ),
            code="STUB",
            strategy="stepped_profit_taking",
        )

        stops = [it for it in result if it.get("direction") == "stop_loss"]
        tps = [it for it in result if it.get("direction") == "take_profit"]
        self.assertEqual(len(stops), 1)
        self.assertEqual(len(tps), 3)
        self.assertAlmostEqual(stops[0]["trigger_price"], 90.0)

    def test_no_synth_for_other_strategies(self):
        """long_term_hold + wait_and_see + swing_trade must not get the ladder."""
        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        for s in ("long_term_hold", "swing_trade", "wait_and_see"):
            result = analyzer._sanitize_action_plan_items(
                items=[],
                portfolio_context_block=(
                    "持仓状态：已持有\n持股数量：1 股\n平均成本：100.0 USD/股\n"
                    "当前价：106.0\n账户总权益：500.00 GBP\n"
                ),
                code="STUB",
                strategy=s,
            )
            tps = [it for it in result if it.get("direction") == "take_profit"]
            self.assertEqual(
                len(tps), 0,
                f"strategy={s} must NOT get an auto-synth TP ladder",
            )


if __name__ == "__main__":
    unittest.main()
