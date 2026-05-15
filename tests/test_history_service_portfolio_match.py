"""Tests that _rebuild_analysis_result reads portfolio_match back from raw_result."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.history_service import HistoryService


def _fake_record() -> SimpleNamespace:
    return SimpleNamespace(
        code="AMD",
        name="AMD",
        sentiment_score=70,
        trend_prediction="看多",
        operation_advice="持有",
        analysis_summary="",
        news_content="",
        created_at=None,
    )


class HistoryServicePortfolioMatchTestCase(unittest.TestCase):
    def test_rebuild_reads_portfolio_match_held(self) -> None:
        service = HistoryService.__new__(HistoryService)  # bypass __init__
        raw = {"code": "AMD", "name": "AMD", "sentiment_score": 70, "portfolio_match": "held"}
        rebuilt = service._rebuild_analysis_result(raw, _fake_record())
        self.assertIsNotNone(rebuilt)
        self.assertEqual(rebuilt.portfolio_match, "held")

    def test_rebuild_reads_portfolio_match_not_held(self) -> None:
        service = HistoryService.__new__(HistoryService)
        raw = {"code": "AMD", "name": "AMD", "portfolio_match": "not_held"}
        rebuilt = service._rebuild_analysis_result(raw, _fake_record())
        self.assertEqual(rebuilt.portfolio_match, "not_held")

    def test_rebuild_handles_missing_portfolio_match(self) -> None:
        service = HistoryService.__new__(HistoryService)
        raw = {"code": "AMD", "name": "AMD"}
        rebuilt = service._rebuild_analysis_result(raw, _fake_record())
        self.assertIsNone(rebuilt.portfolio_match)


if __name__ == "__main__":
    unittest.main()
