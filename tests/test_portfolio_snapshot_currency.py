"""Snapshot top-level currency derivation + FX fallback signal tests."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config
from src.services.portfolio_service import PortfolioService
from src.storage import DatabaseManager


class PortfolioSnapshotCurrencyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.env_path = data_dir / ".env"
        self.db_path = data_dir / "snapshot_currency.db"
        self.env_path.write_text(
            f"DATABASE_PATH={self.db_path}\nADMIN_AUTH_ENABLED=false\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        os.environ.pop("PORTFOLIO_REPORT_CURRENCY", None)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.service = PortfolioService()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("PORTFOLIO_REPORT_CURRENCY", None)
        self.temp_dir.cleanup()

    def test_single_account_uses_account_base_currency(self) -> None:
        self.service.create_account(name="GBP", broker="t212", market="us", base_currency="GBP")
        snap = self.service.get_portfolio_snapshot()
        self.assertEqual(snap["currency"], "GBP")

    def test_single_usd_account_uses_usd(self) -> None:
        self.service.create_account(name="US", broker="ibkr", market="us", base_currency="USD")
        snap = self.service.get_portfolio_snapshot()
        self.assertEqual(snap["currency"], "USD")

    def test_multi_account_defaults_to_cny(self) -> None:
        self.service.create_account(name="A", broker="x", market="us", base_currency="GBP")
        self.service.create_account(name="B", broker="y", market="us", base_currency="USD")
        snap = self.service.get_portfolio_snapshot()
        self.assertEqual(snap["currency"], "CNY")

    def test_multi_account_honors_report_currency_env(self) -> None:
        os.environ["PORTFOLIO_REPORT_CURRENCY"] = "USD"
        Config.reset_instance()
        self.service.create_account(name="A", broker="x", market="us", base_currency="GBP")
        self.service.create_account(name="B", broker="y", market="us", base_currency="USD")
        snap = self.service.get_portfolio_snapshot()
        self.assertEqual(snap["currency"], "USD")

    def test_single_account_ignores_report_currency_env(self) -> None:
        # When there is exactly one account the user almost always wants to see
        # that account's currency, so the env override is intentionally not
        # consulted in the single-account case.
        os.environ["PORTFOLIO_REPORT_CURRENCY"] = "USD"
        Config.reset_instance()
        self.service.create_account(name="A", broker="x", market="us", base_currency="GBP")
        snap = self.service.get_portfolio_snapshot()
        self.assertEqual(snap["currency"], "GBP")

    def test_no_accounts_keeps_default_currency(self) -> None:
        snap = self.service.get_portfolio_snapshot()
        self.assertEqual(snap["currency"], "CNY")
        self.assertEqual(snap["account_count"], 0)

    def test_fx_fallback_used_field_present(self) -> None:
        self.service.create_account(name="GBP", broker="t212", market="us", base_currency="GBP")
        snap = self.service.get_portfolio_snapshot()
        self.assertIn("fx_fallback_used", snap)
        self.assertIsInstance(snap["fx_fallback_used"], bool)


if __name__ == "__main__":
    unittest.main()
