"""Tests for _build_portfolio_context_block tuple return."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.v1.endpoints.analysis import _build_portfolio_context_block


class _FakeContextResult:
    def __init__(self, is_held: bool) -> None:
        self.is_held = is_held


class BuildPortfolioContextBlockTestCase(unittest.TestCase):
    def test_no_account_returns_none_none(self) -> None:
        block, match = _build_portfolio_context_block(stock_code="AMD", account_id=None)
        self.assertIsNone(block)
        self.assertIsNone(match)

    def test_held_account_returns_block_and_held(self) -> None:
        with patch(
            "src.services.portfolio_context_service.PortfolioContextService.get_context",
            return_value=_FakeContextResult(is_held=True),
        ), patch(
            "src.services.portfolio_context_service.render_portfolio_context_block",
            return_value="[持仓上下文] held",
        ):
            block, match = _build_portfolio_context_block(stock_code="AMD", account_id=1)
        self.assertEqual(block, "[持仓上下文] held")
        self.assertEqual(match, "held")

    def test_not_held_account_returns_block_and_not_held(self) -> None:
        with patch(
            "src.services.portfolio_context_service.PortfolioContextService.get_context",
            return_value=_FakeContextResult(is_held=False),
        ), patch(
            "src.services.portfolio_context_service.render_portfolio_context_block",
            return_value="[持仓上下文] not held",
        ):
            block, match = _build_portfolio_context_block(stock_code="AMD", account_id=1)
        self.assertEqual(block, "[持仓上下文] not held")
        self.assertEqual(match, "not_held")

    def test_service_exception_returns_none_none(self) -> None:
        with patch(
            "src.services.portfolio_context_service.PortfolioContextService.get_context",
            side_effect=RuntimeError("db down"),
        ):
            block, match = _build_portfolio_context_block(stock_code="AMD", account_id=1)
        self.assertIsNone(block)
        self.assertIsNone(match)

    def test_unknown_account_returns_none_none(self) -> None:
        with patch(
            "src.services.portfolio_context_service.PortfolioContextService.get_context",
            return_value=None,
        ):
            block, match = _build_portfolio_context_block(stock_code="AMD", account_id=9999)
        self.assertIsNone(block)
        self.assertIsNone(match)


if __name__ == "__main__":
    unittest.main()
