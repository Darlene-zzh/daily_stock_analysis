# -*- coding: utf-8 -*-
"""Build a "user portfolio context" payload for the per-stock LLM analyzer.

The homepage analysis form lets a user tag the call with an ``account_id``.
When set, this module produces a compact dict the analyzer can render into
the prompt so the LLM tailors its advice to the actual holding (or
explicit lack of holding) instead of giving generic textbook output.

Design notes
------------

* Reuses the existing ``PortfolioService.get_portfolio_snapshot`` for
  per-position cost basis / market value / FX-converted P&L. That keeps the
  fields here consistent with what the holdings page shows.
* Trade statistics (buy/sell counts, last trade, first buy date) come from
  the repository directly so we don't reimplement them.
* When the account holds *no* position in the symbol we still emit a
  context block so the LLM knows "user does not hold this; if a buy entry
  makes sense, propose specific levels and size". That way the homepage
  flow degrades gracefully for stocks the user is *researching* but has
  not bought yet.
* Symbol matching is canonicalised through ``canonical_stock_code`` so
  ``amd`` / ``AMD`` / ``AMD.US`` resolve to the same record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

from data_provider.base import canonical_stock_code
from src.repositories.portfolio_repo import PortfolioRepository
from src.services.portfolio_service import PortfolioService

logger = logging.getLogger(__name__)


@dataclass
class PortfolioContextResult:
    """Either ``is_held=True`` with full numbers or ``False`` with bare account info."""

    account_id: int
    account_name: str
    base_currency: str
    symbol: str
    is_held: bool
    # Position fields (populated when is_held=True)
    quantity: float = 0.0
    avg_cost: float = 0.0
    position_currency: Optional[str] = None
    last_price: float = 0.0
    market_value_base: float = 0.0
    unrealized_pnl_base: float = 0.0
    unrealized_pnl_pct: Optional[float] = None
    # Trade activity (always populated if any historical trade exists)
    first_buy_date: Optional[str] = None
    holding_days: Optional[int] = None
    buy_count: int = 0
    sell_count: int = 0
    last_trade_date: Optional[str] = None
    last_trade_side: Optional[str] = None
    last_trade_price: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "account_name": self.account_name,
            "base_currency": self.base_currency,
            "symbol": self.symbol,
            "is_held": self.is_held,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "position_currency": self.position_currency,
            "last_price": self.last_price,
            "market_value_base": self.market_value_base,
            "unrealized_pnl_base": self.unrealized_pnl_base,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "first_buy_date": self.first_buy_date,
            "holding_days": self.holding_days,
            "buy_count": self.buy_count,
            "sell_count": self.sell_count,
            "last_trade_date": self.last_trade_date,
            "last_trade_side": self.last_trade_side,
            "last_trade_price": self.last_trade_price,
        }


class PortfolioContextService:
    """Compose a per-(account, symbol) context block for the LLM analyzer."""

    def __init__(
        self,
        *,
        portfolio_service: Optional[PortfolioService] = None,
        repo: Optional[PortfolioRepository] = None,
    ) -> None:
        self._service = portfolio_service or PortfolioService()
        self._repo = repo or PortfolioRepository()

    def get_context(
        self,
        *,
        account_id: int,
        symbol: str,
        as_of: Optional[date] = None,
    ) -> Optional[PortfolioContextResult]:
        symbol_norm = canonical_stock_code(str(symbol or "").strip())
        if not symbol_norm:
            return None

        target_date = as_of or date.today()

        try:
            snapshot = self._service.get_portfolio_snapshot(
                account_id=account_id,
                as_of=target_date,
            )
        except ValueError:
            # Account does not exist / inactive — nothing to compose.
            return None

        accounts = snapshot.get("accounts") or []
        if not accounts:
            return None
        account_payload = accounts[0]

        position = self._find_position(account_payload.get("positions") or [], symbol_norm)

        trades = self._repo.list_trades(account_id, as_of=target_date)
        symbol_trades = [
            t for t in trades
            if canonical_stock_code(str(getattr(t, "symbol", "") or "")) == symbol_norm
        ]
        stats = self._aggregate_trade_stats(symbol_trades, as_of=target_date)

        if position is None and not symbol_trades:
            # Account exists but the user has never touched this symbol.
            return PortfolioContextResult(
                account_id=account_id,
                account_name=str(account_payload.get("account_name", f"#{account_id}")),
                base_currency=str(account_payload.get("base_currency", "")),
                symbol=symbol_norm,
                is_held=False,
            )

        if position is None:
            # Trades exist but the position has been fully closed.
            return PortfolioContextResult(
                account_id=account_id,
                account_name=str(account_payload.get("account_name", f"#{account_id}")),
                base_currency=str(account_payload.get("base_currency", "")),
                symbol=symbol_norm,
                is_held=False,
                **stats,
            )

        return PortfolioContextResult(
            account_id=account_id,
            account_name=str(account_payload.get("account_name", f"#{account_id}")),
            base_currency=str(account_payload.get("base_currency", "")),
            symbol=symbol_norm,
            is_held=True,
            quantity=float(position.get("quantity") or 0.0),
            avg_cost=float(position.get("avg_cost") or 0.0),
            position_currency=str(position.get("currency") or ""),
            last_price=float(position.get("last_price") or 0.0),
            market_value_base=float(position.get("market_value_base") or 0.0),
            unrealized_pnl_base=float(position.get("unrealized_pnl_base") or 0.0),
            unrealized_pnl_pct=(
                float(position["unrealized_pnl_pct"])
                if position.get("unrealized_pnl_pct") is not None
                else None
            ),
            **stats,
        )

    @staticmethod
    def _find_position(positions: List[Dict[str, Any]], symbol_norm: str) -> Optional[Dict[str, Any]]:
        for row in positions:
            row_symbol = canonical_stock_code(str(row.get("symbol", "") or ""))
            if row_symbol == symbol_norm:
                return row
        return None

    @staticmethod
    def _aggregate_trade_stats(trades: List[Any], *, as_of: date) -> Dict[str, Any]:
        if not trades:
            return {
                "first_buy_date": None,
                "holding_days": None,
                "buy_count": 0,
                "sell_count": 0,
                "last_trade_date": None,
                "last_trade_side": None,
                "last_trade_price": None,
            }

        buys = [t for t in trades if str(getattr(t, "side", "")).lower() == "buy"]
        sells = [t for t in trades if str(getattr(t, "side", "")).lower() == "sell"]

        first_buy = min((t.trade_date for t in buys), default=None)
        holding_days = (
            (as_of - first_buy).days
            if first_buy is not None
            else None
        )
        last_trade = trades[-1]  # repo returns ordered by trade_date asc, id asc

        return {
            "first_buy_date": first_buy.isoformat() if first_buy else None,
            "holding_days": holding_days,
            "buy_count": len(buys),
            "sell_count": len(sells),
            "last_trade_date": (
                last_trade.trade_date.isoformat() if getattr(last_trade, "trade_date", None) else None
            ),
            "last_trade_side": str(getattr(last_trade, "side", "")).lower() or None,
            "last_trade_price": (
                float(last_trade.price) if getattr(last_trade, "price", None) is not None else None
            ),
        }


def render_portfolio_context_block(
    result: PortfolioContextResult,
    *,
    language: str = "zh",
) -> str:
    """Turn the context dataclass into a Markdown block for the LLM prompt.

    ``language`` controls the wording. ``"zh"`` produces a Chinese block.
    ``"en"`` produces an English block. ``"bi"`` is treated as ``"en"``
    here — the analyzer downstream still adds the bilingual instruction,
    no need to dupe the context block.
    """
    lang = (language or "zh").strip().lower()
    if lang not in {"zh", "en"}:
        lang = "en" if lang == "bi" else "zh"

    if result.is_held:
        if lang == "en":
            lines = [
                "## [User Portfolio Context]",
                f"- Account: {result.account_name}",
                f"- Position: {result.quantity:.4f} shares at avg cost "
                f"{result.avg_cost:.4f} {result.position_currency or ''}/share",
                f"- Current price: {result.last_price:.4f} {result.position_currency or ''}",
                f"- Unrealized P&L: {result.unrealized_pnl_base:+.2f} {result.base_currency}"
                + (
                    f" ({result.unrealized_pnl_pct:+.2f}%)"
                    if result.unrealized_pnl_pct is not None
                    else ""
                ),
            ]
            if result.first_buy_date:
                holding = f" ({result.holding_days} days held)" if result.holding_days is not None else ""
                lines.append(f"- First buy: {result.first_buy_date}{holding}")
            if result.buy_count or result.sell_count:
                last = ""
                if result.last_trade_date and result.last_trade_side and result.last_trade_price is not None:
                    last = (
                        f"; last trade was a {result.last_trade_side} at "
                        f"{result.last_trade_price:.4f} on {result.last_trade_date}"
                    )
                lines.append(
                    f"- Activity: {result.buy_count} buys, {result.sell_count} sells{last}"
                )
            lines.append(
                "\n[Provide personalised advice given this holding — add / trim / take profit / "
                "stop / hold — with explicit trigger price levels and invalidation rules.]"
            )
            return "\n".join(lines)

        # zh
        lines = [
            "## [持仓上下文]",
            f"- 账户：{result.account_name}",
            f"- 持股数量：{result.quantity:.4f} 股 / 平均成本：{result.avg_cost:.4f} "
            f"{result.position_currency or ''}/股",
            f"- 当前价：{result.last_price:.4f} {result.position_currency or ''}",
            f"- 浮动盈亏：{result.unrealized_pnl_base:+.2f} {result.base_currency}"
            + (
                f"（{result.unrealized_pnl_pct:+.2f}%）"
                if result.unrealized_pnl_pct is not None
                else ""
            ),
        ]
        if result.first_buy_date:
            holding = f"（已持有 {result.holding_days} 天）" if result.holding_days is not None else ""
            lines.append(f"- 首次买入：{result.first_buy_date}{holding}")
        if result.buy_count or result.sell_count:
            last = ""
            if result.last_trade_date and result.last_trade_side and result.last_trade_price is not None:
                side_zh = "买入" if result.last_trade_side == "buy" else "卖出"
                last = (
                    f"，最后一笔为 {result.last_trade_date} 以 {result.last_trade_price:.4f} {side_zh}"
                )
            lines.append(
                f"- 交易活动：{result.buy_count} 笔买入 / {result.sell_count} 笔卖出{last}"
            )
        lines.append(
            "\n[请结合上述持仓情况给出针对该用户的个性化操作建议（加仓 / 减仓 / 止盈 / 止损 / 继续持有），"
            "明确分批执行价位与失效触发条件。]"
        )
        return "\n".join(lines)

    # Not held — explicit "you do not own this" branch
    if lang == "en":
        return (
            "## [User Portfolio Context]\n"
            f"- Account: {result.account_name}\n"
            "- The user does not currently hold this symbol in this account.\n"
            "\n[If technicals / news provide a clear entry case, propose specific buy price"
            " levels, initial position size as % of equity, and the invalidation rule; otherwise"
            " recommend staying flat.]"
        )
    return (
        "## [持仓上下文]\n"
        f"- 账户：{result.account_name}\n"
        "- 用户当前未持有该标的。\n"
        "\n[若技术面 / 新闻给出明确进场理由，请提出建仓价位、初始仓位规模（占权益的比例）和无效条件；"
        "否则建议观望，不强行给买点。]"
    )
