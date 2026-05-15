"""Tests for the portfolio_match field on AnalysisResult."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer import AnalysisResult


class AnalysisResultPortfolioMatchTestCase(unittest.TestCase):
    def _make(self, **overrides):
        defaults = dict(
            code="AMD",
            name="AMD",
            sentiment_score=70,
            trend_prediction="看多",
            operation_advice="持有",
        )
        defaults.update(overrides)
        return AnalysisResult(**defaults)

    def test_portfolio_match_defaults_to_none(self) -> None:
        result = self._make()
        self.assertIsNone(result.portfolio_match)

    def test_portfolio_match_held_round_trip(self) -> None:
        result = self._make(portfolio_match="held")
        self.assertEqual(result.portfolio_match, "held")
        self.assertEqual(result.to_dict().get("portfolio_match"), "held")

    def test_portfolio_match_not_held_round_trip(self) -> None:
        result = self._make(portfolio_match="not_held")
        self.assertEqual(result.to_dict().get("portfolio_match"), "not_held")

    def test_portfolio_match_none_serialises_as_none(self) -> None:
        result = self._make()
        self.assertIsNone(result.to_dict().get("portfolio_match"))


if __name__ == "__main__":
    unittest.main()
