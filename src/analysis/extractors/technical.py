"""Extract technical.* facts from dashboard.data_perspective + RSI."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord


def _format_price(value: float, market: str = "us") -> str:
    if market == "a":
        return f"¥{value:.2f}"
    return f"${value:.2f}"


def _rsi_zone(rsi: float) -> str:
    if rsi >= 70:
        return "超买"
    if rsi <= 30:
        return "超卖"
    return "中性"


def compute_atr_14(ohlc: list) -> Optional[float]:
    """Wilder ATR(14). Requires >= 15 bars (need 1 for prior close).

    True Range = max(high-low, |high-prev_close|, |low-prev_close|).
    Simple-average flavor; sufficient for candidate-level computation.
    """
    if not ohlc or len(ohlc) < 15:
        return None
    trs = []
    for i in range(1, len(ohlc)):
        h, l = float(ohlc[i]["high"]), float(ohlc[i]["low"])
        prev_c = float(ohlc[i - 1]["close"])
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    last14 = trs[-14:]
    return sum(last14) / len(last14)


def extract_technical_facts(
    data_perspective: Dict[str, Any],
    rsi_12: Optional[float],
    as_of: str,
    market: str = "us",
    source_hint: str = "data_perspective",
    ohlc: Optional[list] = None,
) -> List[FactRecord]:
    facts: List[FactRecord] = []
    pp = data_perspective.get("price_position") or {}
    ts = data_perspective.get("trend_status") or {}

    if "current_price" in pp and pp["current_price"] is not None:
        facts.append(FactRecord(
            id="technical.current_price", type="technical",
            label="现价", value=float(pp["current_price"]),
            display_value=_format_price(float(pp["current_price"]), market),
            unit="USD" if market != "a" else "CNY",
            source=source_hint, as_of=as_of,
        ))

    for ma_key, ma_label in [("ma5", "MA5 (5日均线)"), ("ma10", "MA10 (10日均线)"),
                              ("ma20", "MA20 (20日均线)")]:
        if pp.get(ma_key) is not None:
            facts.append(FactRecord(
                id=f"technical.{ma_key}", type="technical",
                label=ma_label, value=float(pp[ma_key]),
                display_value=_format_price(float(pp[ma_key]), market),
                source=source_hint, as_of=as_of,
            ))

    if pp.get("support_level") is not None:
        facts.append(FactRecord(
            id="technical.support", type="technical",
            label="支撑位", value=float(pp["support_level"]),
            display_value=_format_price(float(pp["support_level"]), market),
            source=source_hint, as_of=as_of,
            extra={"role": "支撑"},
        ))

    if pp.get("resistance_level") is not None:
        facts.append(FactRecord(
            id="technical.resistance", type="technical",
            label="阻力位", value=float(pp["resistance_level"]),
            display_value=_format_price(float(pp["resistance_level"]), market),
            source=source_hint, as_of=as_of,
            extra={"role": "阻力"},
        ))

    if rsi_12 is not None:
        facts.append(FactRecord(
            id="technical.rsi_12", type="technical",
            label="RSI(12)", value=float(rsi_12),
            display_value=f"{rsi_12:.1f}",
            source=source_hint, as_of=as_of,
            extra={"zone": _rsi_zone(float(rsi_12)), "threshold_overbought": 70, "threshold_oversold": 30},
        ))

    if ts.get("trend_score") is not None:
        facts.append(FactRecord(
            id="technical.trend_score", type="technical",
            label="趋势分", value=int(ts["trend_score"]),
            display_value=str(ts["trend_score"]),
            source=source_hint, as_of=as_of,
            extra={"ma_alignment": ts.get("ma_alignment"), "is_bullish": ts.get("is_bullish")},
        ))

    if ohlc is not None:
        atr = compute_atr_14(ohlc)
        if atr is not None:
            facts.append(FactRecord(
                id="technical.atr_14", type="technical",
                label="ATR(14)", value=round(atr, 4),
                display_value=f"{atr:.2f}",
                source="data_provider/daily_data:atr_14",
                as_of=as_of,
            ))

    return facts
