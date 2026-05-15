"""Tests for PortfolioRealtimePriceService cache + lookup."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.portfolio_realtime_service import (
    PortfolioRealtimePriceService,
    _PriceCache,
)


class PortfolioRealtimePriceServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.cache = _PriceCache(ttl_seconds=30.0)
        self.service = PortfolioRealtimePriceService(cache=self.cache)

    def _stub_prices(self, mapping):
        """Patch `_fetch_realtime_position_price` to return values from `mapping`.

        mapping is `{(symbol, currency_hint): (price, provider) or None}`.
        """
        def _fake(symbol, *, currency_hint=None):
            key = (symbol, currency_hint or None)
            value = mapping.get(key)
            if value is None:
                return None, None
            return value
        return patch(
            "src.services.portfolio_realtime_service.PortfolioService._fetch_realtime_position_price",
            side_effect=_fake,
        )

    def test_lookup_returns_price_per_position(self) -> None:
        with self._stub_prices({("AMD", "USD"): (200.0, "yfinance")}):
            result = self.service.lookup([{"symbol": "AMD", "currency": "USD"}])
        self.assertEqual(result["cache_misses"], 1)
        self.assertEqual(result["cache_hits"], 0)
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["symbol"], "AMD")
        self.assertEqual(item["currency_hint"], "USD")
        self.assertAlmostEqual(item["last_price"], 200.0)
        self.assertEqual(item["price_provider"], "yfinance")
        self.assertEqual(item["price_source"], "realtime_quote")
        self.assertTrue(item["price_available"])

    def test_missing_symbol_marked_unavailable(self) -> None:
        with self._stub_prices({}):
            result = self.service.lookup([{"symbol": "ZZZ", "currency": "USD"}])
        item = result["items"][0]
        self.assertFalse(item["price_available"])
        self.assertEqual(item["price_source"], "missing")
        self.assertEqual(item["last_price"], 0.0)

    def test_cache_hits_skip_fetcher_within_ttl(self) -> None:
        with self._stub_prices({("AMD", "USD"): (200.0, "yfinance")}) as stub:
            first = self.service.lookup([{"symbol": "AMD", "currency": "USD"}])
            second = self.service.lookup([{"symbol": "AMD", "currency": "USD"}])
        self.assertEqual(first["cache_misses"], 1)
        self.assertEqual(second["cache_misses"], 0)
        self.assertEqual(second["cache_hits"], 1)
        self.assertEqual(stub.call_count, 1)

    def test_distinct_currency_hints_bypass_each_others_cache(self) -> None:
        # Same ticker queried with different currency hints (e.g. EQGB vs EQGB.L)
        # produces different prices, so the cache keys must include the hint.
        with self._stub_prices({
            ("EQGB", "USD"): None,
            ("EQGB", "GBP"): (554.20, "fallback"),
        }) as stub:
            result = self.service.lookup([
                {"symbol": "EQGB", "currency": "USD"},
                {"symbol": "EQGB", "currency": "GBP"},
            ])
        self.assertEqual(result["cache_misses"], 2)
        self.assertEqual(stub.call_count, 2)
        # Distinct entries returned in request order.
        self.assertEqual(result["items"][0]["currency_hint"], "USD")
        self.assertEqual(result["items"][1]["currency_hint"], "GBP")
        self.assertAlmostEqual(result["items"][1]["last_price"], 554.20)

    def test_empty_payload_returns_empty_items(self) -> None:
        result = self.service.lookup([])
        self.assertEqual(result["items"], [])

    def test_duplicate_positions_are_deduplicated(self) -> None:
        with self._stub_prices({("AMD", "USD"): (200.0, "yfinance")}) as stub:
            result = self.service.lookup([
                {"symbol": "AMD", "currency": "USD"},
                {"symbol": "AMD", "currency": "USD"},
                {"symbol": "AMD", "currency": "USD"},
            ])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(stub.call_count, 1)

    def test_blank_symbols_are_dropped(self) -> None:
        with self._stub_prices({("AMD", "USD"): (200.0, "yfinance")}):
            result = self.service.lookup([
                {"symbol": "", "currency": "USD"},
                {"symbol": "AMD", "currency": "USD"},
            ])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["symbol"], "AMD")

    def test_cache_expires_after_ttl(self) -> None:
        cache = _PriceCache(ttl_seconds=10.0)
        service = PortfolioRealtimePriceService(cache=cache)
        # Manually seed at t=0; query at t=20 misses (expired); t=22 hits if re-cached.
        cache.put(("AMD", "USD"), {"symbol": "AMD", "last_price": 200.0}, now=0.0)
        self.assertIsNone(cache.get(("AMD", "USD"), now=20.0))
        self.assertIsNotNone(cache.get(("AMD", "USD"), now=5.0))


if __name__ == "__main__":
    unittest.main()
