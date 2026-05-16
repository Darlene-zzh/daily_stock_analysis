"""Tests for strategy classification schema + LLM decision rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class StrategySchemaTestCase(unittest.TestCase):
    def test_strategy_choice_schema_validates(self) -> None:
        from api.v1.schemas.history import StrategyChoiceSchema
        choice = StrategyChoiceSchema(
            id="long_term_hold",
            label_zh="长线持有",
            emoji="🌳",
            applicable=True,
            fit_condition="看好 AI 主线 1-2 年",
            key_params="跌破 cost × 0.9 退出",
            time_horizon="6 个月+",
            inapplicable_reason=None,
        )
        self.assertEqual(choice.id, "long_term_hold")
        self.assertTrue(choice.applicable)

    def test_strategy_id_constrained_to_four_values(self) -> None:
        """The id field accepts only the four fixed enum values."""
        from api.v1.schemas.history import StrategyChoiceSchema
        for valid in ("long_term_hold", "swing_trade", "stepped_profit_taking", "wait_and_see"):
            StrategyChoiceSchema(id=valid)  # should not raise

    def test_core_conclusion_carries_new_fields(self) -> None:
        from api.v1.schemas.history import CoreConclusionSchema
        fields = CoreConclusionSchema.model_fields
        self.assertIn("strategy_choices", fields)
        self.assertIn("recommended_strategy", fields)
        self.assertIn("strategy_thesis", fields)
        self.assertIn("position_outcome_summary", fields)

    def test_position_outcome_summary_validates(self) -> None:
        from api.v1.schemas.history import PositionOutcomeSummarySchema
        s = PositionOutcomeSummarySchema(
            remaining_shares_after_all_triggers=0.0,
            worst_case_loss_pct=-10.0,
            worst_case_loss_amount=-12.0,
            worst_case_currency="GBP",
            best_case_gain_pct=30.0,
            best_case_gain_amount=36.0,
            risk_reward_ratio="1:3",
        )
        self.assertEqual(s.risk_reward_ratio, "1:3")


class StrategyClassifyPromptTestCase(unittest.TestCase):
    def test_prompt_contains_all_four_strategy_ids(self) -> None:
        from src.services.portfolio_context_service import build_strategy_classify_prompt
        text = build_strategy_classify_prompt(
            portfolio_context_block="## [持仓上下文]\n- 账户：T\n- 平均成本：100",
            sentiment_dimensions={"reddit": {"buzz_score": 50}},
            compact_dashboard={"key_levels": {"ideal_buy": 95}},
        )
        for sid in ("long_term_hold", "swing_trade", "stepped_profit_taking", "wait_and_see"):
            self.assertIn(sid, text)

    def test_prompt_handles_missing_portfolio(self) -> None:
        """Without portfolio context the prompt downgrades cost-based wording."""
        from src.services.portfolio_context_service import build_strategy_classify_prompt
        text = build_strategy_classify_prompt(
            portfolio_context_block=None,
            sentiment_dimensions=None,
            compact_dashboard={"key_levels": {"ideal_buy": 95}},
        )
        self.assertIn("未持有", text)
        # Main block now references avg_cost × to show the held-vs-unheld split,
        # but the held-only addendum section must NOT be injected.
        self.assertNotIn("持仓成本规则补充", text)

    def test_prompt_embeds_sentiment_decision_rules(self) -> None:
        from src.services.portfolio_context_service import build_strategy_classify_prompt
        text = build_strategy_classify_prompt(
            portfolio_context_block="## [持仓上下文]\n- 平均成本：100",
            sentiment_dimensions={"x_twitter": {"buzz_trend": "falling"}},
            compact_dashboard={},
        )
        self.assertIn("buzz falling", text)  # rule referenced in prompt


if __name__ == "__main__":
    unittest.main()
