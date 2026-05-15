"""Trading 212 CSV import parser tests."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config
from src.services.portfolio_import_service import PortfolioImportService
from src.services.portfolio_service import PortfolioService
from src.storage import DatabaseManager


TRADING212_HEADER = (
    "Action,Time,ISIN,Ticker,Name,Notes,ID,No. of shares,Price / share,"
    "Currency (Price / share),Exchange rate,Result,Currency (Result),"
    "Total,Currency (Total),Withholding tax,Currency (Withholding tax),"
    "Currency conversion fee,Currency (Currency conversion fee),"
    "Merchant name,Merchant category\n"
)


def _t212_row(
    *,
    action: str,
    time: str = "2026-02-23 14:30:03",
    isin: str = "US0079031078",
    ticker: str = "AMD",
    name: str = "Advanced Micro Devices",
    trade_id: str = "EOF47056171308",
    shares: str = "0.3396244900",
    price: str = "198.50",
    price_currency: str = "USD",
    fee: str = "0.08",
    fee_currency: str = "GBP",
) -> str:
    return (
        f"{action},{time},{isin},{ticker},\"{name}\",,{trade_id},{shares},"
        f"{price},{price_currency},1.35046997,,,50.00,GBP,,,"
        f"{fee},{fee_currency},,\n"
    )


class Trading212ParserTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.env_path = data_dir / ".env"
        self.db_path = data_dir / "portfolio_t212_test.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=AAPL",
                    "ADMIN_AUTH_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.service = PortfolioService()
        self.import_service = PortfolioImportService(portfolio_service=self.service)

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def test_broker_registry_includes_trading212_with_aliases(self) -> None:
        items = self.import_service.list_supported_brokers()
        broker_map = {item["broker"]: item for item in items}
        self.assertIn("trading212", broker_map)
        aliases = set(broker_map["trading212"]["aliases"])
        self.assertIn("t212", aliases)
        self.assertIn("trading_212", aliases)

    def test_market_buy_usd_mapped_correctly(self) -> None:
        csv_text = TRADING212_HEADER + _t212_row(action="Market buy")
        parsed = self.import_service.parse_trade_csv(
            broker="trading212",
            content=csv_text.encode("utf-8"),
        )
        self.assertEqual(parsed["record_count"], 1)
        record = parsed["records"][0]
        self.assertEqual(record["symbol"], "AMD")
        self.assertEqual(record["side"], "buy")
        self.assertAlmostEqual(record["quantity"], 0.3396244900, places=10)
        self.assertAlmostEqual(record["price"], 198.50, places=4)
        self.assertEqual(record["currency"], "USD")
        self.assertAlmostEqual(record["fee"], 0.08, places=4)
        self.assertEqual(record["trade_uid"], "EOF47056171308")
        self.assertEqual(record["trade_date"].isoformat(), "2026-02-23")

    def test_limit_sell_usd_mapped_correctly(self) -> None:
        csv_text = TRADING212_HEADER + _t212_row(
            action="Limit sell",
            ticker="TSLA",
            isin="US88160R1014",
            trade_id="EOF47109157439",
            shares="0.1300000000",
            price="405.53",
        )
        parsed = self.import_service.parse_trade_csv(
            broker="trading212",
            content=csv_text.encode("utf-8"),
        )
        self.assertEqual(parsed["record_count"], 1)
        record = parsed["records"][0]
        self.assertEqual(record["symbol"], "TSLA")
        self.assertEqual(record["side"], "sell")

    def test_gbx_price_normalized_to_gbp(self) -> None:
        csv_text = TRADING212_HEADER + _t212_row(
            action="Market buy",
            ticker="EQGB",
            isin="IE00BYVTMW98",
            shares="0.0705467300",
            price="48195.0000000000",
            price_currency="GBX",
            fee="",
        )
        parsed = self.import_service.parse_trade_csv(
            broker="trading212",
            content=csv_text.encode("utf-8"),
        )
        self.assertEqual(parsed["record_count"], 1)
        record = parsed["records"][0]
        self.assertAlmostEqual(record["price"], 481.95, places=4)
        self.assertEqual(record["currency"], "GBP")

    def test_gbp_trade_keeps_price_and_zero_fee(self) -> None:
        csv_text = TRADING212_HEADER + _t212_row(
            action="Market buy",
            ticker="VUAG",
            isin="IE00BFMXXD54",
            shares="0.4923198100",
            price="101.56",
            price_currency="GBP",
            fee="",
        )
        parsed = self.import_service.parse_trade_csv(
            broker="trading212",
            content=csv_text.encode("utf-8"),
        )
        self.assertEqual(parsed["record_count"], 1)
        record = parsed["records"][0]
        self.assertAlmostEqual(record["price"], 101.56, places=4)
        self.assertEqual(record["currency"], "GBP")
        self.assertAlmostEqual(record["fee"], 0.0, places=4)

    def test_non_trade_actions_are_dropped(self) -> None:
        rows = [
            "Deposit,2026-02-22 19:04:12,,,,\"Transaction ID: AAA\","
            "019c86bc-e7cf-7aee-a6ab-00cb264ef791,,,,,,,100.00,GBP,,,,,,\n",
            "Interest on cash,2026-02-23 02:13:01,,,,\"Interest on cash\","
            "019c8845-7f0a-7bd2-a65e-0c8c172e9a54,,,,,,,0.01,GBP,,,,,,\n",
            "Dividend (Dividend),2026-03-26 16:14:07,US30303M1027,META,"
            "\"Meta Platforms\",,,0.2271167800,0.367500,USD,0.74889000,,,"
            "0.06,GBP,0.04,USD,,,,\n",
            "Card debit,2026-04-23 12:01:45,,,,,019dbd80-042d-7baa-bb65-12646ce46d3a,"
            ",,,,,,-48.98,GBP,,,,,\"TESCO STORES 6593\",\"RETAIL_STORES\"\n",
            "Spending cashback,2026-04-25 01:22:54,,,,,019dc23b-8981-7e2a-a94a-bbac34465ee3,"
            ",,,,,,0.24,GBP,,,,,,\n",
        ]
        csv_text = TRADING212_HEADER + "".join(rows)
        parsed = self.import_service.parse_trade_csv(
            broker="trading212",
            content=csv_text.encode("utf-8"),
        )
        self.assertEqual(parsed["record_count"], 0)

    def test_dedup_by_id_column(self) -> None:
        account = self.service.create_account(
            name="T212",
            broker="trading212",
            market="us",
            base_currency="GBP",
        )
        csv_text = TRADING212_HEADER + _t212_row(action="Market buy")
        parsed = self.import_service.parse_trade_csv(
            broker="trading212",
            content=csv_text.encode("utf-8"),
        )
        first = self.import_service.commit_trade_records(
            account_id=account["id"],
            broker="trading212",
            records=parsed["records"],
        )
        second = self.import_service.commit_trade_records(
            account_id=account["id"],
            broker="trading212",
            records=parsed["records"],
        )
        self.assertEqual(first["inserted_count"], 1)
        self.assertEqual(second["duplicate_count"], 1)

    def test_t212_alias_resolves_to_trading212(self) -> None:
        csv_text = TRADING212_HEADER + _t212_row(action="Market buy")
        parsed = self.import_service.parse_trade_csv(
            broker="t212",
            content=csv_text.encode("utf-8"),
        )
        self.assertEqual(parsed["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
