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
    # Account-level aggregate (always populated when account_payload is available)
    total_equity: float = 0.0  # account total equity in base currency

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
            "total_equity": self.total_equity,
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
                total_equity=float(account_payload.get("total_equity", 0.0)),
            )

        if position is None:
            # Trades exist but the position has been fully closed.
            return PortfolioContextResult(
                account_id=account_id,
                account_name=str(account_payload.get("account_name", f"#{account_id}")),
                base_currency=str(account_payload.get("base_currency", "")),
                symbol=symbol_norm,
                is_held=False,
                total_equity=float(account_payload.get("total_equity", 0.0)),
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
            total_equity=float(account_payload.get("total_equity", 0.0)),
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
            ]
            if result.total_equity > 0:
                lines.append(f"- Account equity: {result.total_equity:.2f} {result.base_currency}")
            lines += [
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

        # zh held
        lines = [
            "## [持仓上下文]",
            f"- 账户：{result.account_name}",
        ]
        if result.total_equity > 0:
            lines.append(f"- 账户总权益：{result.total_equity:.2f} {result.base_currency}")
        lines += [
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
        lines = [
            "## [User Portfolio Context]",
            f"- Account: {result.account_name}",
        ]
        if result.total_equity > 0:
            lines.append(f"- Account equity: {result.total_equity:.2f} {result.base_currency}")
        lines.append("- The user does not currently hold this symbol in this account.")
        lines.append(
            "\n[If technicals / news provide a clear entry case, propose specific buy price"
            " levels, initial position size as % of equity, and the invalidation rule; otherwise"
            " recommend staying flat.]"
        )
        return "\n".join(lines)
    # zh not-held
    lines = [
        "## [持仓上下文]",
        f"- 账户：{result.account_name}",
    ]
    if result.total_equity > 0:
        lines.append(f"- 账户总权益：{result.total_equity:.2f} {result.base_currency}")
    lines.append("- 用户当前未持有该标的。")
    lines.append(
        "\n[若技术面 / 新闻给出明确进场理由，请提出建仓价位、初始仓位规模（占权益的比例）和无效条件；"
        "否则建议观望，不强行给买点。]"
    )
    return "\n".join(lines)


ACTION_PLAN_INSTRUCTION_ZH = """
## [操作计划指令]
必须在 action_plan_items 字段输出 2-4 条操作建议，按 priority 排序（1=最优先）。
所有操作建议须与你在同一 JSON 输出中的 time_sensitivity 字段的时间窗口一致，不得给出时间窗口内明显无法成立的价位。
每条必须包含全部 11 个字段：
- trigger_price: 精确触发价（数值，如 421.0）
- trigger_condition: 触发条件（含价量/时间要求，1 句话）
- direction: buy / sell / stop_loss / take_profit
- shares: 具体股数（参考上方持仓上下文中的持股数量；未持有时给合理初始仓数量）
- pct_of_position: 占当前持仓 %（未持有时填 null）
- pct_of_equity: 参考上方持仓上下文中的账户总权益，计算本次操作占权益的 %
- technical_basis: 技术面依据（必须引用具体指标数值，如 RSI=74、MA5=421.8）
- fundamental_basis: 基本面/新闻依据（引用最新消息或财报关键数据）
- quant_signal: 量化信号（量比/换手率/筹码分布/资金流向中至少 2 项）
- invalidation_rule: 何时计划失效（1 句话，含具体价位）
- priority: 1-3（1=首要）

未持有时规则：无论进场信号强弱，priority=1 的第一条建议必须给出具体等待建仓价位
（可以是「等回踩至 $X 建仓」），不得输出空列表。
"""


def build_action_plan_instruction(portfolio_context_block: Optional[str]) -> str:
    """Return the structured-action-plan instruction string when a portfolio context block is present.

    Both the legacy analyzer prompt assembly and the agent executor path call this so the
    instruction text stays in one place — see [[repo-async-task-queue]] for the same parallel
    plumbing pattern.
    """
    if portfolio_context_block and portfolio_context_block.strip():
        return ACTION_PLAN_INSTRUCTION_ZH
    return ""


STRATEGY_CLASSIFY_INSTRUCTION_ZH = """
## [策略分类与操作计划指令]

你必须按两步输出：先分类，后生成 items。

### 第一步：策略分类

阅读以下输入：
- 用户持仓上下文（成本价、浮盈浮亏、持有天数）
- 技术摘要（趋势、MA 排列、支撑/压力位）
- 基本面与新闻摘要
- 市场情绪 (Reddit / X / Polymarket / News)

按以下规则在 4 个固定策略里挑选 applicable 状态，并输出 1-4 个 strategy_choices 条目：

| 触发条件 | 推荐 / 适用 |
|---|---|
| 持仓盈利 > +5% + 技术结构未坏 + buzz falling 或 sentiment 降温 | 推荐 `stepped_profit_taking` |
| 持仓盈利 > +5% + 技术结构强 + buzz rising + bullish sentiment | 推荐 `swing_trade` 或 `long_term_hold` |
| 持仓亏损 -3% ~ -15% + 基本面叙事完好 | 推荐 `long_term_hold` 或 `wait_and_see` |
| 持仓亏损 > -15% + 基本面恶化 / sentiment 转负 | 推荐 `wait_and_see` |
| 未持有 + 趋势强 | 推荐 `swing_trade` |
| 未持有 + 趋势弱 + 估值偏高 | 推荐 `wait_and_see` |
| 财报 / 政策事件 < 14 天 + 持仓 | 推荐 `wait_and_see` |

applicable=false 的策略也要列出并填 `inapplicable_reason`。
recommended_strategy 字段填一个 id（long_term_hold / swing_trade / stepped_profit_taking / wait_and_see）。

### 第二步：写 strategy_thesis (100-200 字)

必须显式引用：
- 用户持仓状态（成本、浮盈/亏、持有天数）—— 未持有时引用现价与权益规模
- 至少 1 条技术依据（具体指标数值）
- 至少 1 条情绪依据（buzz 数值或 trend）
- 该策略的优势 + 劣势

### 第三步：生成 action_plan_items

严格遵循推荐策略的模板：

- `long_term_hold` → 必含 1 条 stop_loss（持有时 ≤ current_price × 0.85；未持有时同）；
  可选 1 条 buy on dip；禁止短线 trigger（距现价 < 5%）。共 2-3 条。
- `swing_trade` → 必含 1 条 entry (buy/sell)、1 条 stop_loss（chart-based）、
  1 条 take_profit（chart-based）。共 3-4 条。
- `stepped_profit_taking` → 必含 2-3 条 take_profit（阶梯价位）+ 1 条 cost-based stop_loss；
  禁止 buy。共 3-4 条。
- `wait_and_see` → 至多 1 条 item，须为事件类提醒（无价格 trigger）。共 0-1 条。

任何违反模板的 item 会在 post-process 阶段被丢弃。

通用规则（贯穿四策略）：
- take_profit 触发价必须高于买入成本（持仓时）
- stop_loss 触发价应当不高于成本价的 102%（持仓时；介于成本上方的 chart support 用 sell 标）
- trigger_price 距 current_price 应当 ≥ 2.5%
- 所有 items 的 shares 总和 ≈ 持仓数（容差 ±5%）；未持有时按权益 5%-10% 折算建仓数

### 第四步：填 position_outcome_summary（持仓时）

```json
"position_outcome_summary": {
  "remaining_shares_after_all_triggers": 数值,
  "worst_case_loss_pct": -10.0,
  "worst_case_loss_amount": -12.0,
  "worst_case_currency": "GBP",
  "best_case_gain_pct": 30.0,
  "best_case_gain_amount": 36.0,
  "risk_reward_ratio": "1:3"
}
```

未持有时该字段可省略或全部填 null。
"""

# Additional template rules that reference cost-basis math — only injected when the user
# holds a position, so the no-portfolio path stays free of "avg_cost ×" wording.
_STRATEGY_HELD_COST_BASIS_ADDENDUM = """
### 持仓成本规则补充（有持仓时适用）

- `long_term_hold` stop_loss: trigger_price ≤ avg_cost × 0.9
- `stepped_profit_taking` stop_loss: trigger_price = avg_cost × 0.95
- `swing_trade` stop_loss: chart-based，但不得高于 avg_cost × 1.02
"""


def build_strategy_classify_prompt(
    portfolio_context_block: Optional[str],
    sentiment_dimensions: Optional[Dict[str, Any]],
    compact_dashboard: Dict[str, Any],
) -> str:
    """Compose the strategy-classification + action-plan-generation prompt.

    Universal: runs for all stocks (with or without portfolio). When portfolio is
    absent, cost-based rules switch to current-price relative rules. When sentiment
    is absent (e.g. A/HK stocks), the sentiment section degrades to text-only signal.
    """
    has_portfolio = bool(portfolio_context_block and portfolio_context_block.strip())
    parts = [STRATEGY_CLASSIFY_INSTRUCTION_ZH]

    if has_portfolio:
        parts.append(_STRATEGY_HELD_COST_BASIS_ADDENDUM)
        parts.append("\n## 持仓上下文\n" + portfolio_context_block)
    else:
        parts.append("\n## 持仓上下文\n用户未持有该股票，按建仓视角分析（cost-based 规则换为现价相对规则）。")

    if sentiment_dimensions:
        import json as _json
        parts.append("\n## 市场情绪\n" + _json.dumps(
            sentiment_dimensions, ensure_ascii=False, indent=2,
        ))

    import json as _json2
    parts.append("\n## 分析摘要\n" + _json2.dumps(
        compact_dashboard, ensure_ascii=False, indent=2, default=str,
    ))

    parts.append(
        "\n## 输出\n仅输出合法 JSON，顶层结构：\n"
        "{\n"
        '  "strategy_choices": [...],\n'
        '  "recommended_strategy": "<id>",\n'
        '  "strategy_thesis": "<100-200 字>",\n'
        '  "action_plan_items": [...],\n'
        '  "position_outcome_summary": {...}\n'
        "}\n"
        "不输出任何注释或代码块标记。"
    )

    return "\n".join(parts)


import re as _re


def _parse_portfolio_facts(block: str) -> Dict[str, Optional[float]]:
    """Extract shares + equity from a rendered portfolio_context_block.

    The renderer formats persisted fields with stable wording — we parse those back out
    so a synthesis fallback knows the user's actual share count and total equity. Returns
    floats (or None) for: shares, equity, avg_cost, last_price, base_currency, position_currency.

    NB: parsing rendered text is brittle — if [[repo-dual-renderers]] semantics change in
    render_portfolio_context_block, this regex must move too.
    """
    out: Dict[str, Any] = {
        "shares": None,
        "equity": None,
        "avg_cost": None,
        "last_price": None,
        "base_currency": None,
        "position_currency": None,
    }
    if not block:
        return out
    # zh: 持股数量：N 股 / 平均成本：M CCY/股
    m = _re.search(r"持股数量[：:]\s*([\d.]+)\s*股", block)
    if m:
        try:
            out["shares"] = float(m.group(1))
        except ValueError:
            pass
    m = _re.search(r"平均成本[：:]\s*([\d.]+)\s*([A-Za-z]{3})/股", block)
    if m:
        try:
            out["avg_cost"] = float(m.group(1))
            out["position_currency"] = m.group(2)
        except ValueError:
            pass
    m = _re.search(r"当前价[：:]\s*([\d.]+)", block)
    if m:
        try:
            out["last_price"] = float(m.group(1))
        except ValueError:
            pass
    # zh: 账户总权益：N CCY
    m = _re.search(r"账户总权益[：:]\s*([\d.]+)\s*([A-Za-z]{3})", block)
    if m:
        try:
            out["equity"] = float(m.group(1))
            out["base_currency"] = m.group(2)
        except ValueError:
            pass
    # en: Position: N shares at avg cost M CCY/share
    m = _re.search(r"Position:\s*([\d.]+)\s*shares", block)
    if m and out["shares"] is None:
        try:
            out["shares"] = float(m.group(1))
        except ValueError:
            pass
    m = _re.search(r"avg cost\s*([\d.]+)\s*([A-Za-z]{3})/share", block)
    if m and out["avg_cost"] is None:
        try:
            out["avg_cost"] = float(m.group(1))
            out["position_currency"] = m.group(2)
        except ValueError:
            pass
    m = _re.search(r"Current price:\s*([\d.]+)", block)
    if m and out["last_price"] is None:
        try:
            out["last_price"] = float(m.group(1))
        except ValueError:
            pass
    m = _re.search(r"Account equity:\s*([\d.]+)\s*([A-Za-z]{3})", block)
    if m and out["equity"] is None:
        try:
            out["equity"] = float(m.group(1))
            out["base_currency"] = m.group(2)
        except ValueError:
            pass
    return out


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def synthesize_action_plan_items(
    dashboard: Dict[str, Any],
    portfolio_context_block: Optional[str],
    *,
    is_held: bool,
) -> List[Dict[str, Any]]:
    """Synthesize 1-2 action_plan_items from existing dashboard data + portfolio facts.

    Use as a *fallback* when the LLM refused to emit action_plan_items (gpt-5.4-mini
    ignores schema extensions per [[repo-llm-mini-models-schema]]). Items are coarser
    than what a cooperative LLM would produce, but they keep the UI affordance alive.

    Returns empty list when there is nothing usable to anchor the plan on (e.g. no
    battle_plan price levels) — caller should leave the field empty in that case.
    """
    if not isinstance(dashboard, dict):
        return []
    battle = dashboard.get("battle_plan") or {}
    sniper = battle.get("sniper_points") or {}
    ideal_buy = _safe_float(sniper.get("ideal_buy"))
    stop_loss = _safe_float(sniper.get("stop_loss"))
    take_profit = _safe_float(sniper.get("take_profit"))

    # Need at least one anchor price to be worth synthesizing.
    if ideal_buy is None and stop_loss is None and take_profit is None:
        return []

    facts = _parse_portfolio_facts(portfolio_context_block or "")
    shares = facts["shares"]
    equity = facts["equity"]
    last_price = facts["last_price"]
    avg_cost = facts["avg_cost"]
    position_currency = facts.get("position_currency") or ""

    # Holder semantics: a "take_profit" at a price below the cost basis isn't a profit at
    # all, just a smaller loss. Clamp the anchor up to a sensible level (cost basis + 2%
    # for a small win, or drop the take_profit item entirely if the chart's TP is far below).
    take_profit_anchor = take_profit
    if is_held and avg_cost is not None and take_profit is not None and take_profit <= avg_cost:
        # If the chart's TP is meaningfully below cost (≤ -3%), don't emit a TP item — the
        # user shouldn't be planning to "take profit" when they're actually under water.
        if take_profit < avg_cost * 0.97:
            take_profit_anchor = None
        else:
            # Otherwise nudge to break-even-plus-2% so the item conveys "exit when finally green".
            take_profit_anchor = round(avg_cost * 1.02, 2)

    # Rationale strings reuse dashboard fields so the synthesized items still cite
    # the analysis the user already sees elsewhere on the page.
    persp = dashboard.get("data_perspective") or {}
    trend = persp.get("trend_status") or {}
    price_pos = persp.get("price_position") or {}
    vol = persp.get("volume_analysis") or {}
    chip = persp.get("chip_structure") or {}
    intel = dashboard.get("intelligence") or {}

    tech_bits = []
    if trend.get("ma_alignment"):
        tech_bits.append(f"均线 {trend.get('ma_alignment')}")
    if trend.get("trend_score") is not None:
        tech_bits.append(f"趋势评分 {trend.get('trend_score')}")
    if price_pos.get("bias_status"):
        tech_bits.append(f"MA5 乖离 {price_pos.get('bias_ma5')}% ({price_pos.get('bias_status')})")
    technical_basis = "，".join(tech_bits) or "见上方数据透视"

    fund_bits = []
    if intel.get("earnings_outlook"):
        fund_bits.append(str(intel["earnings_outlook"])[:80])
    elif intel.get("sentiment_summary"):
        fund_bits.append(str(intel["sentiment_summary"])[:80])
    elif intel.get("latest_news"):
        fund_bits.append(str(intel["latest_news"])[:80])
    fundamental_basis = fund_bits[0] if fund_bits else "见上方情报"

    # Quant signal: only emit when we have ACTUAL quant numbers — volume ratio, turnover,
    # chip concentration, fund flows. volume_meaning is just a restatement of the
    # technical narrative and adds nothing here; drop it to "" so the renderer skips
    # the field entirely instead of showing a misleading repeat (Issue: PLTR report).
    quant_parts = []
    vol_ratio = _safe_float(vol.get("volume_ratio"))
    if vol_ratio is not None and vol_ratio > 0:
        quant_parts.append(f"量比 {vol_ratio:.2f}")
    turnover = _safe_float(vol.get("turnover_rate"))
    if turnover is not None and turnover > 0:
        quant_parts.append(f"换手率 {turnover:.2f}%")
    concentration = _safe_float(chip.get("concentration"))
    if concentration is not None:
        quant_parts.append(f"筹码集中度 {concentration}")
    profit_ratio = _safe_float(chip.get("profit_ratio"))
    if profit_ratio is not None:
        quant_parts.append(f"获利盘 {profit_ratio}")
    quant_basis = "，".join(quant_parts)  # "" when no real quant data — renderer will skip

    items: List[Dict[str, Any]] = []

    def _trim_qty(fraction: float, total: Optional[float]) -> Optional[float]:
        """Compute a share quantity for a trim/sell action.

        Fractional-share accounts (e.g. Trading 212) routinely hold < 1 share, so
        we keep the raw float when the holding is sub-integer instead of rounding
        up to 1 (which would exceed the position and emit pct_of_position > 100%).
        """
        if total is None or total <= 0:
            return None
        raw = total * fraction
        if total < 1:
            return round(raw, 4)
        return max(1.0, round(raw))

    def _pct_of_position(qty: float, total: Optional[float]) -> Optional[float]:
        if total is None or total <= 0:
            return None
        return round((qty / total) * 100.0, 1)

    def _pct_of_equity(qty: float, price: Optional[float], eq: Optional[float]) -> float:
        if price is None or eq is None or eq <= 0:
            return 0.0
        return round((qty * price) / eq * 100.0, 1)

    # Helper: a chart-derived "stop_loss" level above cost basis isn't really stopping
    # a loss — it's a defensive trim at a chart support that's still in profit territory.
    # Use the same threshold as the analyzer's LLM-output sanitizer (cost × 1.02).
    def _direction_for_stop_loss(price: float) -> str:
        if avg_cost is not None and price > avg_cost * 1.02:
            return "sell"
        return "stop_loss"

    # ---- Primary item ----
    if is_held:
        # Holder: 1) trim at ideal_buy / support if it breaks (sell), or hold-to-target.
        # Prefer a "減仓 at stop_loss break" trigger because that's the actionable one
        # for an existing position.
        primary_price = stop_loss if stop_loss is not None else ideal_buy
        if primary_price is not None and shares:
            qty = _trim_qty(0.5, shares) or 0
            is_stop_loss_anchor = primary_price == stop_loss
            direction = _direction_for_stop_loss(primary_price) if is_stop_loss_anchor else "sell"
            items.append({
                "trigger_price": primary_price,
                "trigger_condition": (
                    f"收盘有效跌破 {primary_price:.2f} 且无法收回"
                    if direction == "stop_loss"
                    else f"价格回踩 {primary_price:.2f} 后无法企稳，防守性降仓"
                ),
                "direction": direction,
                "shares": qty,
                "pct_of_position": _pct_of_position(qty, shares),
                "pct_of_equity": _pct_of_equity(qty, last_price or primary_price, equity),
                "technical_basis": technical_basis,
                "fundamental_basis": fundamental_basis,
                "quant_signal": quant_basis,
                "invalidation_rule": (
                    f"次日强势收回 {primary_price:.2f} 上方则暂缓减仓"
                ),
                "priority": 1,
            })
    else:
        # Not held: 1) buy at ideal_buy if technicals confirm.
        primary_price = ideal_buy if ideal_buy is not None else (last_price or take_profit)
        if primary_price is not None:
            # Default initial position: 5% of equity at primary_price.
            if equity and primary_price:
                qty = max(1, int(equity * 0.05 / primary_price))
            else:
                qty = 1
            items.append({
                "trigger_price": primary_price,
                "trigger_condition": f"价格回踩 {primary_price:.2f} 企稳并伴随放量",
                "direction": "buy",
                "shares": qty,
                "pct_of_position": None,
                "pct_of_equity": _pct_of_equity(qty, primary_price, equity),
                "technical_basis": technical_basis,
                "fundamental_basis": fundamental_basis,
                "quant_signal": quant_basis,
                "invalidation_rule": (
                    f"跌破 {stop_loss:.2f} 且无回升则取消计划"
                    if stop_loss is not None
                    else "若技术结构破位则取消"
                ),
                "priority": 1,
            })

    # ---- Secondary item: stop_loss (always defensive) ----
    if stop_loss is not None and (not items or items[0]["trigger_price"] != stop_loss):
        if is_held and shares:
            qty = round(shares, 4) if shares < 1 else round(shares)  # full position stop
            direction = _direction_for_stop_loss(stop_loss)
            items.append({
                "trigger_price": stop_loss,
                "trigger_condition": (
                    f"放量跌破 {stop_loss:.2f} 关键支撑"
                    if direction == "stop_loss"
                    else f"跌破 {stop_loss:.2f} 防守位，主动降仓控制回撤"
                ),
                "direction": direction,
                "shares": qty,
                "pct_of_position": _pct_of_position(qty, shares),
                "pct_of_equity": _pct_of_equity(qty, last_price or stop_loss, equity),
                "technical_basis": (
                    f"跌破止损位 {stop_loss:.2f}，趋势确认转弱"
                    if direction == "stop_loss"
                    else f"跌破支撑位 {stop_loss:.2f}，仍处于成本上方，降仓控制风险"
                ),
                "fundamental_basis": fundamental_basis,
                "quant_signal": quant_basis,
                "invalidation_rule": "当日收盘强势收回则可推迟执行",
                "priority": 2,
            })

    # ---- Optional third item: take_profit on holder ----
    if is_held and take_profit_anchor is not None and shares and len(items) < 3:
        qty = _trim_qty(0.3, shares) or 0
        # If we had to clamp to break-even-plus, label the trigger so the user understands
        # this isn't a chart target — it's a "first chance to exit at flat" trigger.
        is_break_even = (
            avg_cost is not None
            and take_profit is not None
            and take_profit <= avg_cost
            and take_profit_anchor > take_profit
        )
        items.append({
            "trigger_price": take_profit_anchor,
            "trigger_condition": (
                f"反弹至成本价上方 {take_profit_anchor:.2f}（持平偏盈）" if is_break_even
                else f"放量突破并站稳 {take_profit_anchor:.2f}"
            ),
            "direction": "take_profit",
            "shares": qty,
            "pct_of_position": _pct_of_position(qty, shares),
            "pct_of_equity": _pct_of_equity(qty, take_profit_anchor, equity),
            "technical_basis": (
                f"反弹至成本价上方，结合压力位 {take_profit:.2f} 减持降低风险" if is_break_even
                else f"上探目标位 {take_profit_anchor:.2f}，达到既定盈利目标"
            ),
            "fundamental_basis": fundamental_basis,
            "quant_signal": quant_basis,
            "invalidation_rule": "若无法站稳目标位则保留仓位",
            "priority": 3,
        })

    return items
