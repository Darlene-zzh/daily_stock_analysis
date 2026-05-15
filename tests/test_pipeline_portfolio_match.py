"""Tests that portfolio_match propagates from service to AnalysisResult."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class PipelinePortfolioMatchTestCase(unittest.TestCase):
    def test_pipeline_init_accepts_portfolio_match(self) -> None:
        import inspect
        from src.core.pipeline import StockAnalysisPipeline

        sig = inspect.signature(StockAnalysisPipeline.__init__)
        self.assertIn("portfolio_match", sig.parameters)

    def test_pipeline_sets_portfolio_match_on_result(self) -> None:
        from src.analyzer import AnalysisResult
        from src.core.pipeline import StockAnalysisPipeline

        # Build a stub pipeline instance bypassing __init__ side effects.
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.portfolio_match = "held"

        fake_result = AnalysisResult(
            code="AMD",
            name="AMD",
            sentiment_score=70,
            trend_prediction="看多",
            operation_advice="持有",
        )

        # Production code applies portfolio_match where it currently sets
        # current_price / change_pct (just after analyzer.analyze returns).
        # We exercise that small helper directly:
        from src.core.pipeline import _apply_portfolio_match  # added in this task
        _apply_portfolio_match(fake_result, pipeline)
        self.assertEqual(fake_result.portfolio_match, "held")

    def test_pipeline_apply_with_none_leaves_field_unchanged(self) -> None:
        from src.analyzer import AnalysisResult
        from src.core.pipeline import StockAnalysisPipeline, _apply_portfolio_match

        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.portfolio_match = None

        fake_result = AnalysisResult(
            code="AMD",
            name="AMD",
            sentiment_score=70,
            trend_prediction="看多",
            operation_advice="持有",
        )
        _apply_portfolio_match(fake_result, pipeline)
        self.assertIsNone(fake_result.portfolio_match)


class AnalysisServicePortfolioMatchSignatureTestCase(unittest.TestCase):
    def test_analyze_stock_signature_accepts_portfolio_match(self) -> None:
        import inspect
        from src.services.analysis_service import AnalysisService

        sig = inspect.signature(AnalysisService.analyze_stock)
        self.assertIn("portfolio_match", sig.parameters)


if __name__ == "__main__":
    unittest.main()
