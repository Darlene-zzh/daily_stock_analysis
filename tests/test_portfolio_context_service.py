"""Tests for PortfolioContextService and the LLM prompt block renderer."""

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
from src.services.portfolio_context_service import (
    PortfolioContextService,
    render_portfolio_context_block,
)
from src.services.portfolio_service import PortfolioService
from src.storage import DatabaseManager


class PortfolioContextServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.env_path = data_dir / ".env"
        self.db_path = data_dir / "portfolio_context.db"
        self.env_path.write_text(
            f"DATABASE_PATH={self.db_path}\nADMIN_AUTH_ENABLED=false\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        # Reset the module-level snapshot TTL cache so a snapshot cached by a
        # previous test (with a different temp DB / account fixture) doesn't
        # bleed into this case and short-circuit `get_portfolio_snapshot`.
        from src.services.portfolio_context_service import clear_portfolio_snapshot_cache
        clear_portfolio_snapshot_cache()
        self.service = PortfolioService()
        self.context_service = PortfolioContextService(portfolio_service=self.service)
        self.account = self.service.create_account(
            name="Test T212", broker="t212", market="us", base_currency="GBP"
        )

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def test_unknown_account_returns_none(self) -> None:
        result = self.context_service.get_context(account_id=9999, symbol="AMD")
        self.assertIsNone(result)

    def test_account_with_no_trades_for_symbol_returns_not_held(self) -> None:
        # Account exists but never traded AMD.
        result = self.context_service.get_context(account_id=self.account["id"], symbol="AMD")
        self.assertIsNotNone(result)
        self.assertFalse(result.is_held)
        self.assertEqual(result.account_name, "Test T212")
        self.assertEqual(result.symbol, "AMD")

    def test_held_position_populates_full_block(self) -> None:
        # Two buys of AMD plus a current price baked into history.
        self.service.record_trade(
            account_id=self.account["id"],
            symbol="AMD",
            trade_date=date(2026, 3, 1),
            side="buy",
            quantity=1.0,
            price=200.0,
            currency="USD",
            market="us",
            trade_uid="T1",
        )
        self.service.record_trade(
            account_id=self.account["id"],
            symbol="AMD",
            trade_date=date(2026, 4, 5),
            side="buy",
            quantity=2.0,
            price=180.0,
            currency="USD",
            market="us",
            trade_uid="T2",
        )

        result = self.context_service.get_context(
            account_id=self.account["id"],
            symbol="AMD",
            as_of=date(2026, 5, 15),
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.is_held)
        # 1*200 + 2*180 = 560 across 3 shares -> avg cost ~ 186.67 USD
        self.assertAlmostEqual(result.quantity, 3.0, places=4)
        self.assertAlmostEqual(result.avg_cost, 186.6667, places=3)
        self.assertEqual(result.position_currency, "USD")
        self.assertEqual(result.first_buy_date, "2026-03-01")
        self.assertEqual(result.holding_days, 75)
        self.assertEqual(result.buy_count, 2)
        self.assertEqual(result.sell_count, 0)
        self.assertEqual(result.last_trade_date, "2026-04-05")
        self.assertEqual(result.last_trade_side, "buy")
        self.assertAlmostEqual(result.last_trade_price, 180.0, places=4)

    def test_position_closed_returns_not_held_with_history(self) -> None:
        # Buy then sell everything -> snapshot has no position, but trade
        # history still exists. We want is_held=False AND activity counts.
        self.service.record_trade(
            account_id=self.account["id"],
            symbol="TSLA",
            trade_date=date(2026, 3, 1),
            side="buy",
            quantity=1.0,
            price=200.0,
            currency="USD",
            market="us",
            trade_uid="T3",
        )
        self.service.record_trade(
            account_id=self.account["id"],
            symbol="TSLA",
            trade_date=date(2026, 4, 1),
            side="sell",
            quantity=1.0,
            price=250.0,
            currency="USD",
            market="us",
            trade_uid="T4",
        )

        result = self.context_service.get_context(
            account_id=self.account["id"],
            symbol="TSLA",
            as_of=date(2026, 5, 15),
        )
        self.assertIsNotNone(result)
        self.assertFalse(result.is_held)
        self.assertEqual(result.buy_count, 1)
        self.assertEqual(result.sell_count, 1)
        self.assertEqual(result.last_trade_side, "sell")
        self.assertAlmostEqual(result.last_trade_price, 250.0, places=4)

    def test_never_traded_includes_total_equity(self) -> None:
        """total_equity is populated even when the user never traded the symbol."""
        result = self.context_service.get_context(account_id=self.account["id"], symbol="AMD")
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.total_equity, 0.0)

    def test_held_position_includes_total_equity(self) -> None:
        """total_equity appears in the held-position branch."""
        self.service.record_trade(
            account_id=self.account["id"],
            symbol="AMD",
            side="buy",
            quantity=10,
            price=185.0,
            trade_date=date(2026, 1, 1),
        )
        result = self.context_service.get_context(account_id=self.account["id"], symbol="AMD")
        self.assertIsNotNone(result)
        self.assertTrue(result.is_held)
        self.assertGreaterEqual(result.total_equity, 0.0)

    def test_render_block_zh_includes_equity_line(self) -> None:
        """render_portfolio_context_block (zh) includes account equity line when > 0."""
        from src.services.portfolio_context_service import (
            PortfolioContextResult,
            render_portfolio_context_block,
        )
        r = PortfolioContextResult(
            account_id=1,
            account_name="Test",
            base_currency="GBP",
            symbol="AMD",
            is_held=False,
            total_equity=2189.0,
        )
        block = render_portfolio_context_block(r, language="zh")
        self.assertIn("账户总权益", block)
        self.assertIn("2189.00", block)
        self.assertIn("GBP", block)

    def test_render_block_zh_omits_equity_line_when_zero(self) -> None:
        """render_portfolio_context_block (zh) omits the equity line when total_equity=0."""
        from src.services.portfolio_context_service import (
            PortfolioContextResult,
            render_portfolio_context_block,
        )
        r = PortfolioContextResult(
            account_id=1,
            account_name="Test",
            base_currency="GBP",
            symbol="AMD",
            is_held=False,
            total_equity=0.0,
        )
        block = render_portfolio_context_block(r, language="zh")
        self.assertNotIn("账户总权益", block)

    def test_render_block_en_includes_equity_line(self) -> None:
        """render_portfolio_context_block (en) includes account equity line when > 0."""
        from src.services.portfolio_context_service import (
            PortfolioContextResult,
            render_portfolio_context_block,
        )
        r = PortfolioContextResult(
            account_id=1,
            account_name="Test",
            base_currency="GBP",
            symbol="AMD",
            is_held=False,
            total_equity=2189.0,
        )
        block = render_portfolio_context_block(r, language="en")
        self.assertIn("Account equity", block)
        self.assertIn("2189.00", block)


class RenderPortfolioContextBlockTestCase(unittest.TestCase):
    def _make_held_result(self):
        from src.services.portfolio_context_service import PortfolioContextResult
        return PortfolioContextResult(
            account_id=1,
            account_name="Darlene Trading212",
            base_currency="GBP",
            symbol="AMD",
            is_held=True,
            quantity=6.0,
            avg_cost=143.96,
            position_currency="USD",
            last_price=133.73,
            market_value_base=602.42,
            unrealized_pnl_base=-46.08,
            unrealized_pnl_pct=-7.11,
            first_buy_date="2026-02-23",
            holding_days=82,
            buy_count=9,
            sell_count=0,
            last_trade_date="2026-04-23",
            last_trade_side="buy",
            last_trade_price=197.99,
        )

    def test_zh_block_contains_all_user_requested_fields(self) -> None:
        result = self._make_held_result()
        block = render_portfolio_context_block(result, language="zh")
        self.assertIn("[持仓上下文]", block)
        self.assertIn("Darlene Trading212", block)
        self.assertIn("6.0000 股", block)
        self.assertIn("143.9600 USD/股", block)
        self.assertIn("133.7300 USD", block)
        self.assertIn("-46.08 GBP", block)
        self.assertIn("-7.11%", block)
        self.assertIn("2026-02-23", block)
        self.assertIn("82 天", block)
        self.assertIn("9 笔买入", block)
        self.assertIn("2026-04-23", block)
        self.assertIn("197.9900", block)
        self.assertIn("买入", block)
        self.assertIn("个性化操作建议", block)

    def test_en_block_uses_english_wording(self) -> None:
        result = self._make_held_result()
        block = render_portfolio_context_block(result, language="en")
        self.assertIn("[User Portfolio Context]", block)
        self.assertIn("Darlene Trading212", block)
        self.assertIn("6.0000 shares", block)
        self.assertIn("Unrealized P&L", block)
        self.assertIn("82 days held", block)
        self.assertIn("9 buys", block)
        self.assertIn("personalised advice", block)

    def test_bi_falls_back_to_english_block(self) -> None:
        result = self._make_held_result()
        block = render_portfolio_context_block(result, language="bi")
        self.assertIn("[User Portfolio Context]", block)

    def test_not_held_block_encourages_entry_proposal(self) -> None:
        from src.services.portfolio_context_service import PortfolioContextResult
        result = PortfolioContextResult(
            account_id=1,
            account_name="Darlene Trading212",
            base_currency="GBP",
            symbol="NVDA",
            is_held=False,
        )
        zh = render_portfolio_context_block(result, language="zh")
        self.assertIn("用户当前未持有", zh)
        self.assertIn("建仓价位", zh)
        en = render_portfolio_context_block(result, language="en")
        self.assertIn("does not currently hold", en)
        self.assertIn("propose specific buy price", en)


if __name__ == "__main__":
    unittest.main()
