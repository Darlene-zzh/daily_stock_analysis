"""Extract flow.* facts from FundamentalAdapter.get_capital_flow (A-share only)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord


def _format_yuan(value: float) -> str:
    abs_v = abs(value)
    sign = "+" if value >= 0 else "-"
    if abs_v >= 1e8:
        return f"{sign}{abs_v / 1e8:.2f} 亿元"
    if abs_v >= 1e4:
        return f"{sign}{abs_v / 1e4:.2f} 万元"
    return f"{sign}{abs_v:.0f} 元"


def extract_flow_facts(
    flow: Optional[Dict[str, Any]],
    market: str,
    as_of: str,
) -> List[FactRecord]:
    if not flow or market != "a":
        return []
    if flow.get("status") != "ok":
        return []
    facts: List[FactRecord] = []
    stock_flow = flow.get("stock_flow") or {}

    for key, label in [
        ("main_net_inflow", "主力净流入"),
        ("inflow_5d", "5 日累计净流入"),
        ("inflow_10d", "10 日累计净流入"),
    ]:
        val = stock_flow.get(key)
        if val is None:
            continue
        v = float(val)
        facts.append(FactRecord(
            id=f"flow.{key}", type="flow",
            label=label, value=v,
            display_value=_format_yuan(v), unit="CNY",
            source="akshare/capital_flow", as_of=as_of,
        ))

    return facts
