"""Tests for net_contributed / total_pnl in portfolio snapshots."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config
from src.services.portfolio_service import PortfolioService
from src.storage import DatabaseManager


class PortfolioNetContributedTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.env_path = data_dir / ".env"
        self.db_path = data_dir / "net_contrib.db"
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

    def _make_account(self, base_currency: str = "GBP") -> int:
        account = self.service.create_account(
            name="Test",
            broker="trading212",
            market="us",
            base_currency=base_currency,
        )
        return account["id"]

    def test_single_deposit_is_full_contribution(self) -> None:
        aid = self._make_account()
        self.service.record_cash_ledger(
            account_id=aid,
            event_date=date(2026, 2, 1),
            direction="in",
            amount=1000.0,
            currency="GBP",
            note="csv_import:trading212:deposit:uid-1",
        )
        snap = self.service.get_portfolio_snapshot(account_id=aid)
        self.assertAlmostEqual(snap["net_contributed"], 1000.0, places=4)
        self.assertAlmostEqual(snap["total_pnl"], 0.0, places=4)

    def test_card_debit_reduces_contribution(self) -> None:
        aid = self._make_account()
        self.service.record_cash_ledger(
            account_id=aid,
            event_date=date(2026, 2, 1),
            direction="in",
            amount=1000.0,
            currency="GBP",
            note="csv_import:trading212:deposit:uid-1",
        )
        self.service.record_cash_ledger(
            account_id=aid,
            event_date=date(2026, 4, 23),
            direction="out",
            amount=48.98,
            currency="GBP",
            note="csv_import:trading212:card_debit:uid-2",
        )
        snap = self.service.get_portfolio_snapshot(account_id=aid)
        self.assertAlmostEqual(snap["net_contributed"], 951.02, places=4)

    def test_interest_and_dividend_are_gains_not_contributions(self) -> None:
        aid = self._make_account()
        self.service.record_cash_ledger(
            account_id=aid,
            event_date=date(2026, 2, 1),
            direction="in",
            amount=1000.0,
            currency="GBP",
            note="csv_import:trading212:deposit:uid-1",
        )
        # These inflows are portfolio gains, not new money contributed.
        self.service.record_cash_ledger(
            account_id=aid,
            event_date=date(2026, 3, 1),
            direction="in",
            amount=0.50,
            currency="GBP",
            note="csv_import:trading212:interest:uid-2",
        )
        self.service.record_cash_ledger(
            account_id=aid,
            event_date=date(2026, 3, 5),
            direction="in",
            amount=0.36,
            currency="GBP",
            note="csv_import:trading212:dividend:META:uid-3",
        )
        self.service.record_cash_ledger(
            account_id=aid,
            event_date=date(2026, 3, 8),
            direction="in",
            amount=0.24,
            currency="GBP",
            note="csv_import:trading212:cashback:uid-4",
        )
        snap = self.service.get_portfolio_snapshot(account_id=aid)
        # Net contribution is just the deposit — gains do not increase it.
        self.assertAlmostEqual(snap["net_contributed"], 1000.0, places=4)
        # Total cash reflects the 1.10 GBP of gains on top of the deposit.
        self.assertAlmostEqual(snap["total_cash"], 1001.10, places=4)
        # Total P&L = equity - net_contributed = 1001.10 - 1000 = 1.10.
        self.assertAlmostEqual(snap["total_pnl"], 1.10, places=4)

    def test_manually_recorded_event_without_marker_is_contribution(self) -> None:
        aid = self._make_account()
        # No `csv_import:` prefix: treated as a real contribution by default.
        self.service.record_cash_ledger(
            account_id=aid,
            event_date=date(2026, 2, 1),
            direction="in",
            amount=500.0,
            currency="GBP",
            note="manually entered",
        )
        snap = self.service.get_portfolio_snapshot(account_id=aid)
        self.assertAlmostEqual(snap["net_contributed"], 500.0, places=4)

    def test_total_pnl_equals_equity_minus_contributed(self) -> None:
        aid = self._make_account()
        self.service.record_cash_ledger(
            account_id=aid,
            event_date=date(2026, 2, 1),
            direction="in",
            amount=2000.0,
            currency="GBP",
            note="csv_import:trading212:deposit:uid-1",
        )
        snap = self.service.get_portfolio_snapshot(account_id=aid)
        expected_pnl = snap["total_equity"] - snap["net_contributed"]
        self.assertAlmostEqual(snap["total_pnl"], expected_pnl, places=4)
        self.assertAlmostEqual(snap["total_pnl"], 0.0, places=4)  # no positions yet

    def test_account_payload_includes_per_account_fields(self) -> None:
        aid = self._make_account()
        self.service.record_cash_ledger(
            account_id=aid,
            event_date=date(2026, 2, 1),
            direction="in",
            amount=100.0,
            currency="GBP",
            note="csv_import:trading212:deposit:uid-1",
        )
        snap = self.service.get_portfolio_snapshot(account_id=aid)
        self.assertEqual(len(snap["accounts"]), 1)
        account_view = snap["accounts"][0]
        self.assertIn("net_contributed", account_view)
        self.assertIn("total_pnl", account_view)
        self.assertAlmostEqual(account_view["net_contributed"], 100.0, places=4)

    def test_no_cash_events_yields_zero(self) -> None:
        aid = self._make_account()
        snap = self.service.get_portfolio_snapshot(account_id=aid)
        self.assertAlmostEqual(snap["net_contributed"], 0.0, places=4)
        self.assertAlmostEqual(snap["total_pnl"], 0.0, places=4)


if __name__ == "__main__":
    unittest.main()
