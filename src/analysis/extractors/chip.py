"""Extract chip.* facts from AkshareFetcher.get_chip_distribution (A-share only)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord


def extract_chip_facts(
    chip: Optional[Dict[str, Any]],
    market: str,
    as_of: str,
) -> List[FactRecord]:
    if not chip or market != "a":
        return []
    facts: List[FactRecord] = []
    src = "akshare/chip_distribution"
    chip_as_of = chip.get("date") or as_of

    if chip.get("profit_ratio") is not None:
        v = float(chip["profit_ratio"])
        facts.append(FactRecord(
            id="chip.profit_ratio", type="chip",
            label="获利比例", value=v,
            display_value=f"{v * 100:.1f}%", unit="%",
            source=src, as_of=chip_as_of,
        ))

    if chip.get("avg_cost") is not None:
        v = float(chip["avg_cost"])
        facts.append(FactRecord(
            id="chip.avg_cost", type="chip",
            label="市场平均成本", value=v,
            display_value=f"¥{v:.2f}", unit="CNY",
            source=src, as_of=chip_as_of,
        ))

    for key, label in [("concentration_70", "70% 集中度"),
                       ("concentration_90", "90% 集中度")]:
        if chip.get(key) is not None:
            v = float(chip[key])
            facts.append(FactRecord(
                id=f"chip.{key}", type="chip",
                label=label, value=v,
                display_value=f"{v * 100:.2f}%", unit="%",
                source=src, as_of=chip_as_of,
            ))

    return facts
