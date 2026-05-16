"""Tests for structured sentiment_dimensions payload returned by SocialSentimentService."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.social_sentiment_service import SocialSentimentService


class GetSocialContextStructuredTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = SocialSentimentService(
            api_key="sk_test", api_url="https://api.adanos.org",
        )

    def _patch_endpoints(self, reddit=None, x=None, poly=None, news=None):
        return [
            patch.object(self.svc, "fetch_reddit_report", return_value=reddit),
            patch.object(self.svc, "fetch_x_trending",
                         return_value=[{"ticker": "NVDA", **x}] if x else []),
            patch.object(self.svc, "fetch_polymarket_trending",
                         return_value=[{"ticker": "NVDA", **poly}] if poly else []),
            patch.object(self.svc, "fetch_news_report", return_value=news),
        ]

    def test_get_social_context_returns_tuple(self):
        patches = self._patch_endpoints(
            reddit={"buzz_score": 84.4, "sentiment_score": 0.06, "trend": "rising"},
            x={"buzz_score": 89.0, "sentiment_score": 0.28, "trend": "falling"},
            poly={"buzz_score": 64.7, "sentiment_score": 0.13},
            news={"buzz_score": 61.6, "sentiment_score": 0.48, "trend": "stable"},
        )
        for p in patches:
            p.start()
        try:
            result = self.svc.get_social_context("NVDA")
        finally:
            for p in patches:
                p.stop()

        self.assertIsInstance(result, tuple)
        text, dims = result
        self.assertIsInstance(text, str)
        self.assertIsInstance(dims, dict)
        self.assertIn("reddit", dims)
        self.assertIn("x_twitter", dims)
        self.assertIn("polymarket", dims)
        self.assertIn("news", dims)
        self.assertAlmostEqual(dims["reddit"]["buzz_score"], 84.4)
        self.assertEqual(dims["x_twitter"]["buzz_trend"], "falling")

    def test_partial_data_returns_partial_dims(self):
        patches = self._patch_endpoints(
            reddit=None,  # 404
            x={"buzz_score": 89.0, "sentiment_score": 0.28},
            poly=None,
            news={"buzz_score": 61.6, "sentiment_score": 0.48},
        )
        for p in patches:
            p.start()
        try:
            text, dims = self.svc.get_social_context("NVDA")
        finally:
            for p in patches:
                p.stop()

        self.assertNotIn("reddit", dims)
        self.assertNotIn("polymarket", dims)
        self.assertIn("x_twitter", dims)
        self.assertIn("news", dims)

    def test_returns_none_when_no_data(self):
        patches = self._patch_endpoints(reddit=None, x=None, poly=None, news=None)
        for p in patches:
            p.start()
        try:
            result = self.svc.get_social_context("NVDA")
        finally:
            for p in patches:
                p.stop()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
