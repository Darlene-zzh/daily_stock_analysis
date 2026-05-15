"""Tests for the LSE (.L) realtime price fallback in portfolio snapshots."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config
from src.services.portfolio_service import PortfolioService
from src.storage import DatabaseManager


class _FakeQuote:
    def __init__(self, price: float, provider: str = "yfinance") -> None:
        self.price = price
        self.source = provider


class _FakeFetcherManager:
    """Return a price for some symbols, None for others."""

    def __init__(self, prices: dict) -> None:
        self._prices = prices
        self.calls: list = []

    def get_realtime_quote(self, symbol: str, log_final_failure: bool = False):  # noqa: ARG002
        self.calls.append(symbol)
        if symbol in self._prices:
            return _FakeQuote(self._prices[symbol])
        return None


def _patched_manager(prices: dict):
    """Patch DataFetcherManager to return a deterministic FakeFetcherManager."""
    fake = _FakeFetcherManager(prices)
    return patch("data_provider.base.DataFetcherManager", return_value=fake), fake


class PortfolioLseFallbackTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.env_path = data_dir / ".env"
        self.db_path = data_dir / "lse_fallback.db"
        self.env_path.write_text(
            f"DATABASE_PATH={self.db_path}\nADMIN_AUTH_ENABLED=false\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.service = PortfolioService()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def test_primary_lookup_hit_uses_returned_price(self) -> None:
        mgr_patch, fake = _patched_manager({"AAPL": 195.20})
        with mgr_patch:
            price, provider = PortfolioService._fetch_realtime_position_price("AAPL")
        self.assertAlmostEqual(price, 195.20, places=4)
        self.assertEqual(provider, "yfinance")
        self.assertEqual(fake.calls, ["AAPL"])

    def test_primary_miss_with_gbp_hint_tries_dot_l(self) -> None:
        # Plain VUAG misses on Yahoo (US source returns nothing); .L returns GBP-quoted price.
        mgr_patch, fake = _patched_manager({"VUAG.L": 107.58})
        with mgr_patch:
            price, _ = PortfolioService._fetch_realtime_position_price(
                "VUAG", currency_hint="GBP"
            )
        self.assertAlmostEqual(price, 107.58, places=4)
        self.assertEqual(fake.calls, ["VUAG", "VUAG.L"])

    def test_primary_miss_with_gbx_hint_normalizes_pence(self) -> None:
        # EQGB.L reported in pence (55420 GBX) should be normalized to GBP (554.20).
        mgr_patch, fake = _patched_manager({"EQGB.L": 55420.0})
        with mgr_patch:
            price, _ = PortfolioService._fetch_realtime_position_price(
                "EQGB", currency_hint="GBX"
            )
        self.assertAlmostEqual(price, 554.20, places=4)
        self.assertEqual(fake.calls, ["EQGB", "EQGB.L"])

    def test_primary_miss_without_currency_hint_returns_none(self) -> None:
        # Without a GBP/GBX hint we must not silently switch markets.
        mgr_patch, fake = _patched_manager({"EQGB.L": 55420.0})
        with mgr_patch:
            price, _ = PortfolioService._fetch_realtime_position_price("EQGB")
        self.assertIsNone(price)
        self.assertEqual(fake.calls, ["EQGB"])

    def test_primary_miss_with_usd_hint_does_not_try_lse(self) -> None:
        mgr_patch, fake = _patched_manager({"AMD.L": 999.0})
        with mgr_patch:
            price, _ = PortfolioService._fetch_realtime_position_price(
                "AMD", currency_hint="USD"
            )
        self.assertIsNone(price)
        self.assertEqual(fake.calls, ["AMD"])

    def test_symbol_with_dot_skips_lse_fallback(self) -> None:
        # Codes that already carry a suffix (e.g. 600519.SS, BRK.B) must not get
        # an extra ".L" suffix tacked on.
        mgr_patch, fake = _patched_manager({})
        with mgr_patch:
            price, _ = PortfolioService._fetch_realtime_position_price(
                "BRK.B", currency_hint="GBP"
            )
        self.assertIsNone(price)
        self.assertEqual(fake.calls, ["BRK.B"])

    def test_gbp_share_below_threshold_kept_as_is(self) -> None:
        # Below the GBX heuristic threshold (1000), the price is treated as GBP.
        mgr_patch, _ = _patched_manager({"VUAG.L": 850.0})
        with mgr_patch:
            price, _ = PortfolioService._fetch_realtime_position_price(
                "VUAG", currency_hint="GBP"
            )
        self.assertAlmostEqual(price, 850.0, places=4)


if __name__ == "__main__":
    unittest.main()
