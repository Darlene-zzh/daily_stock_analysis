"""Tests for StockTwits public sentiment API client."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.stocktwits_service import StockTwitsService


def _make_message(sentiment: str | None) -> dict:
    return {
        "id": 1,
        "body": "test",
        "entities": {"sentiment": {"basic": sentiment}} if sentiment else {"sentiment": None},
    }


class StockTwitsAggregateTestCase(unittest.TestCase):
    @patch("src.services.stocktwits_service.requests.get")
    def test_aggregates_bullish_bearish_ratios(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "messages": (
                [_make_message("Bullish")] * 6
                + [_make_message("Bearish")] * 2
                + [_make_message(None)] * 2
            ),
        }
        mock_get.return_value = resp

        svc = StockTwitsService()
        out = svc.fetch_sentiment("NVDA")

        self.assertEqual(out["messages_sampled"], 10)
        self.assertAlmostEqual(out["bullish_ratio"], 0.6)
        self.assertAlmostEqual(out["bearish_ratio"], 0.2)
        self.assertAlmostEqual(out["neutral_ratio"], 0.2)
        self.assertEqual(out["source"], "stocktwits_public")

    @patch("src.services.stocktwits_service.requests.get")
    def test_hits_correct_endpoint(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"messages": []}
        mock_get.return_value = resp

        StockTwitsService().fetch_sentiment("aapl")
        called_url = mock_get.call_args[0][0]
        self.assertEqual(
            called_url,
            "https://api.stocktwits.com/api/2/streams/symbol/AAPL.json",
        )

    @patch("src.services.stocktwits_service.requests.get")
    def test_returns_none_on_empty_messages(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"messages": []}
        mock_get.return_value = resp

        out = StockTwitsService().fetch_sentiment("NVDA")
        self.assertIsNone(out)

    @patch("src.services.stocktwits_service.requests.get")
    def test_returns_none_on_http_error(self, mock_get):
        resp = MagicMock()
        resp.status_code = 429
        mock_get.return_value = resp

        out = StockTwitsService().fetch_sentiment("NVDA")
        self.assertIsNone(out)

    @patch("src.services.stocktwits_service.requests.get")
    def test_caches_repeated_requests_within_ttl(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "messages": [_make_message("Bullish")] * 3,
        }
        mock_get.return_value = resp

        svc = StockTwitsService()
        svc.fetch_sentiment("NVDA")
        svc.fetch_sentiment("NVDA")  # second call should hit cache

        self.assertEqual(mock_get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
