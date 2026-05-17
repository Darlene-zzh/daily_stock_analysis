"""Tests for the in-memory snapshot TTL cache in
`src.services.portfolio_context_service`.

Why this matters: `get_portfolio_snapshot` is the slowest step in the analysis
pipeline (10+ sequential realtime quotes per account, ~5-10 min cold). The
cache lets back-to-back single-stock analyses on the same account reuse the
result for `PORTFOLIO_SNAPSHOT_TTL_SECONDS` (default 600s).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _fake_snapshot(account_id: int):
    return {
        "accounts": [
            {
                "account_id": account_id,
                "account_name": "Test",
                "base_currency": "GBP",
                "total_equity": 1000.0,
                "positions": [],
            }
        ]
    }


class PortfolioSnapshotCacheTestCase(unittest.TestCase):

    def setUp(self) -> None:
        from src.services.portfolio_context_service import clear_portfolio_snapshot_cache
        clear_portfolio_snapshot_cache()
        os.environ.pop("PORTFOLIO_SNAPSHOT_TTL_SECONDS", None)

    def tearDown(self) -> None:
        from src.services.portfolio_context_service import clear_portfolio_snapshot_cache
        clear_portfolio_snapshot_cache()
        os.environ.pop("PORTFOLIO_SNAPSHOT_TTL_SECONDS", None)

    def test_second_get_context_call_reuses_cached_snapshot(self):
        from src.services.portfolio_context_service import PortfolioContextService

        mock_service = MagicMock()
        mock_service.get_portfolio_snapshot.return_value = _fake_snapshot(1)
        mock_repo = MagicMock()
        mock_repo.list_trades.return_value = []

        ctx = PortfolioContextService(portfolio_service=mock_service, repo=mock_repo)
        ctx.get_context(account_id=1, symbol="MSFT")
        ctx.get_context(account_id=1, symbol="NVDA")

        # Both calls share the cached snapshot — only ONE actual snapshot fetch.
        self.assertEqual(mock_service.get_portfolio_snapshot.call_count, 1)

    def test_different_account_id_misses_cache(self):
        from src.services.portfolio_context_service import PortfolioContextService

        mock_service = MagicMock()
        mock_service.get_portfolio_snapshot.side_effect = [
            _fake_snapshot(1),
            _fake_snapshot(2),
        ]
        mock_repo = MagicMock()
        mock_repo.list_trades.return_value = []

        ctx = PortfolioContextService(portfolio_service=mock_service, repo=mock_repo)
        ctx.get_context(account_id=1, symbol="MSFT")
        ctx.get_context(account_id=2, symbol="MSFT")

        # Different account_id → independent cache key → 2 fetches.
        self.assertEqual(mock_service.get_portfolio_snapshot.call_count, 2)

    def test_ttl_zero_disables_cache(self):
        from src.services.portfolio_context_service import PortfolioContextService

        os.environ["PORTFOLIO_SNAPSHOT_TTL_SECONDS"] = "0"
        mock_service = MagicMock()
        mock_service.get_portfolio_snapshot.return_value = _fake_snapshot(1)
        mock_repo = MagicMock()
        mock_repo.list_trades.return_value = []

        ctx = PortfolioContextService(portfolio_service=mock_service, repo=mock_repo)
        ctx.get_context(account_id=1, symbol="MSFT")
        ctx.get_context(account_id=1, symbol="NVDA")

        # TTL=0 means every call hits the underlying service.
        self.assertEqual(mock_service.get_portfolio_snapshot.call_count, 2)

    def test_clear_cache_forces_next_call_to_fetch(self):
        from src.services.portfolio_context_service import (
            PortfolioContextService,
            clear_portfolio_snapshot_cache,
        )

        mock_service = MagicMock()
        mock_service.get_portfolio_snapshot.return_value = _fake_snapshot(1)
        mock_repo = MagicMock()
        mock_repo.list_trades.return_value = []

        ctx = PortfolioContextService(portfolio_service=mock_service, repo=mock_repo)
        ctx.get_context(account_id=1, symbol="MSFT")
        self.assertEqual(mock_service.get_portfolio_snapshot.call_count, 1)

        clear_portfolio_snapshot_cache()
        ctx.get_context(account_id=1, symbol="MSFT")
        self.assertEqual(mock_service.get_portfolio_snapshot.call_count, 2)

    def test_invalid_ttl_env_falls_back_to_default(self):
        os.environ["PORTFOLIO_SNAPSHOT_TTL_SECONDS"] = "garbage"
        from src.services.portfolio_context_service import _snapshot_ttl_seconds

        # Falls back to default (600), doesn't crash.
        self.assertEqual(_snapshot_ttl_seconds(), 600.0)


if __name__ == "__main__":
    unittest.main()
