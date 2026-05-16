"""Tests for position_outcome_summary computation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class PositionOutcomeSummaryTestCase(unittest.TestCase):
    def test_computes_remaining_shares_after_all_triggers(self):
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        items = [
            {"direction": "take_profit", "shares": 0.3, "trigger_price": 240},
            {"direction": "take_profit", "shares": 0.2, "trigger_price": 250},
            {"direction": "stop_loss", "shares": 0.2597, "trigger_price": 176},
        ]
        result = a._compute_position_outcome_summary(
            items=items, holding_shares=0.7597,
            avg_cost=196.0, current_price=225.0, base_currency="GBP",
        )
        # 0.7597 - 0.3 - 0.2 - 0.2597 = 0.0
        self.assertAlmostEqual(result["remaining_shares_after_all_triggers"], 0.0, places=3)

    def test_worst_case_is_stop_loss_amount(self):
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        items = [{"direction": "stop_loss", "shares": 1.0, "trigger_price": 90.0}]
        result = a._compute_position_outcome_summary(
            items=items, holding_shares=1.0,
            avg_cost=100.0, current_price=105.0, base_currency="USD",
        )
        # Loss = (90 - 100) * 1.0 = -10
        self.assertAlmostEqual(result["worst_case_loss_amount"], -10.0)
        self.assertAlmostEqual(result["worst_case_loss_pct"], -10.0)
        self.assertEqual(result["worst_case_currency"], "USD")

    def test_best_case_is_take_profit(self):
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        items = [
            {"direction": "take_profit", "shares": 0.5, "trigger_price": 130.0},
            {"direction": "stop_loss", "shares": 0.5, "trigger_price": 90.0},
        ]
        result = a._compute_position_outcome_summary(
            items=items, holding_shares=1.0,
            avg_cost=100.0, current_price=105.0, base_currency="USD",
        )
        # Best: 0.5 * (130 - 100) = +15
        self.assertAlmostEqual(result["best_case_gain_amount"], 15.0)

    def test_risk_reward_ratio_formatted_as_1_to_n(self):
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        items = [
            {"direction": "take_profit", "shares": 1.0, "trigger_price": 130.0},
            {"direction": "stop_loss", "shares": 1.0, "trigger_price": 90.0},
        ]
        result = a._compute_position_outcome_summary(
            items=items, holding_shares=1.0,
            avg_cost=100.0, current_price=105.0, base_currency="USD",
        )
        # Risk = 10, reward = 30, R:R = 1:3
        self.assertEqual(result["risk_reward_ratio"], "1:3.0")

    def test_returns_none_without_holding(self):
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        result = a._compute_position_outcome_summary(
            items=[], holding_shares=None, avg_cost=None,
            current_price=100, base_currency="USD",
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
