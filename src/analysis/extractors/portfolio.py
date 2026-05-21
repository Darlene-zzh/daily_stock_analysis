"""Extract portfolio.* facts from PortfolioContextService output."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord


def extract_portfolio_facts(
    portfolio_context: Optional[Dict[str, Any]],
    as_of: str,
) -> List[FactRecord]:
    if not portfolio_context:
        return []
    facts: List[FactRecord] = []
    src = "portfolio_context_service"

    match = portfolio_context.get("match_state")
    facts.append(FactRecord(
        id="portfolio.position_match", type="portfolio",
        label="持仓匹配状态", value=match if match else "unknown",
        display_value={"held": "已持有", "not_held": "未持有"}.get(match, "未知"),
        source=src, as_of=as_of,
    ))

    if match != "held":
        return facts

    if portfolio_context.get("holding_shares") is not None:
        shares = float(portfolio_context["holding_shares"])
        facts.append(FactRecord(
            id="portfolio.holding_shares", type="portfolio",
            label="持仓股数", value=shares,
            display_value=f"{shares:.4f} 股", unit="shares",
            source=src, as_of=as_of,
        ))

    if portfolio_context.get("avg_cost") is not None:
        cost = float(portfolio_context["avg_cost"])
        ccy = portfolio_context.get("currency", "USD")
        symbol = {"USD": "$", "CNY": "¥", "HKD": "HK$", "GBP": "£"}.get(ccy, "")
        facts.append(FactRecord(
            id="portfolio.avg_cost", type="portfolio",
            label="成本均价", value=cost,
            display_value=f"{symbol}{cost:.2f}", unit=ccy,
            source=src, as_of=as_of,
        ))

    if portfolio_context.get("unrealized_pnl_pct") is not None:
        pct = float(portfolio_context["unrealized_pnl_pct"])
        sign = "+" if pct >= 0 else ""
        facts.append(FactRecord(
            id="portfolio.unrealized_pnl_pct", type="portfolio",
            label="浮盈率", value=pct,
            display_value=f"{sign}{pct:.2f}%", unit="%",
            source=src, as_of=as_of,
        ))

    if portfolio_context.get("unrealized_pnl_amount") is not None:
        amt = float(portfolio_context["unrealized_pnl_amount"])
        base = portfolio_context.get("base_currency", "USD")
        symbol = {"USD": "$", "CNY": "¥", "HKD": "HK$", "GBP": "£"}.get(base, "")
        sign = "+" if amt >= 0 else ""
        facts.append(FactRecord(
            id="portfolio.unrealized_pnl_amount", type="portfolio",
            label="浮盈金额", value=amt,
            display_value=f"{sign}{symbol}{amt:.2f}", unit=base,
            source=src, as_of=as_of,
        ))

    if portfolio_context.get("total_equity") is not None:
        eq = float(portfolio_context["total_equity"])
        base = portfolio_context.get("base_currency", "USD")
        symbol = {"USD": "$", "CNY": "¥", "HKD": "HK$", "GBP": "£"}.get(base, "")
        facts.append(FactRecord(
            id="portfolio.total_equity", type="portfolio",
            label="账户总权益", value=eq,
            display_value=f"{symbol}{eq:.2f}", unit=base,
            source=src, as_of=as_of,
        ))

    if portfolio_context.get("first_buy_date"):
        facts.append(FactRecord(
            id="portfolio.first_buy_date", type="portfolio",
            label="首次买入日期", value=portfolio_context["first_buy_date"],
            display_value=str(portfolio_context["first_buy_date"]),
            source=src, as_of=as_of,
        ))

    return facts
