"""Extract quant.* facts from data/quant_models/{market}/<week>/predictions.json + ic.json."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord

_WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")


def find_latest_qlib_week(market_dir: Path) -> Optional[str]:
    if not market_dir.exists() or not market_dir.is_dir():
        return None
    weeks = [p.name for p in market_dir.iterdir() if p.is_dir() and _WEEK_RE.match(p.name)]
    if not weeks:
        return None
    return sorted(weeks)[-1]


def extract_quant_facts(
    ticker: str,
    *,
    predictions: Dict[str, Dict[str, float]],
    ic: Dict[str, Any],
    universe_size: int,
    week: str,
    as_of: str,
) -> List[FactRecord]:
    entry = predictions.get(ticker)
    if not entry:
        return []
    facts: List[FactRecord] = []
    score = float(entry.get("score", 0.0))
    rank = float(entry.get("rank", 0.0))
    ic_4w = ic.get("ic_ma_4w")
    ic_current = ic.get("ic_current")
    source = f"data/quant_models/<market>/{week}/predictions.json"

    facts.append(FactRecord(
        id="quant.qlib_score", type="quant",
        label="Qlib 模型打分", value=round(score, 4),
        display_value=f"{score:.3f}",
        confidence=float(ic_4w) if ic_4w is not None else None,
        source=source, as_of=as_of,
        extra={"week": week},
    ))

    top_pct = max(1, math.ceil((1.0 - rank) * 100))
    facts.append(FactRecord(
        id="quant.qlib_rank", type="quant",
        label="Qlib 截面分位", value=round(rank, 4),
        display_value=f"前 {top_pct}%",
        source=source, as_of=as_of,
        extra={
            "universe_size": universe_size,
            "rank_absolute": max(1, math.ceil((1.0 - rank) * universe_size)),
            "week": week,
        },
    ))

    if ic_current is not None:
        facts.append(FactRecord(
            id="quant.qlib_ic_current", type="quant",
            label="Qlib IC 当周", value=float(ic_current),
            display_value=f"{float(ic_current):.3f}",
            source=source, as_of=as_of,
        ))

    if ic_4w is not None:
        facts.append(FactRecord(
            id="quant.qlib_ic_4w", type="quant",
            label="Qlib IC 4周均", value=float(ic_4w),
            display_value=f"{float(ic_4w):.3f}",
            source=source, as_of=as_of,
            extra={"interpretation": "IC>0.1 视为有效"},
        ))

    return facts
