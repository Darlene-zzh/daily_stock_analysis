"""Tests for Adanos /news/stocks/v1/stock/{ticker} endpoint integration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.social_sentiment_service import SocialSentimentService


class FetchNewsReportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = SocialSentimentService(
            api_key="sk_test_dummy",
            api_url="https://api.adanos.org",
        )

    @patch("src.services.social_sentiment_service._get_with_retry")
    def test_fetches_news_report_with_correct_path(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ticker": "NVDA",
            "buzz_score": 61.6,
            "sentiment_score": 0.484,
            "mentions": 285,
            "bullish_pct": 86,
            "bearish_pct": 4,
            "top_sources": [{"source": "yahoo-finance", "count": 68}],
        }
        mock_get.return_value = mock_resp

        result = self.svc.fetch_news_report("NVDA")

        called_url = mock_get.call_args[0][0]
        self.assertEqual(called_url, "https://api.adanos.org/news/stocks/v1/stock/NVDA")
        self.assertEqual(result["buzz_score"], 61.6)
        self.assertEqual(result["sentiment_score"], 0.484)

    @patch("src.services.social_sentiment_service._get_with_retry")
    def test_fetch_news_report_uppercases_ticker(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ticker": "AAPL"}
        mock_get.return_value = mock_resp

        self.svc.fetch_news_report("aapl")

        called_url = mock_get.call_args[0][0]
        self.assertIn("/stock/AAPL", called_url)

    @patch("src.services.social_sentiment_service._get_with_retry")
    def test_fetch_news_report_returns_none_on_404(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = self.svc.fetch_news_report("UNKNOWN")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
