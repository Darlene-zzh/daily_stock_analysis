"""Candidate price-level computation rules.

23 rules across entry / exit / take_profit / stop_loss directions.
Each rule produces 0 or 1 CandidateLevel from the FactBundle.

See docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md
Section A "Candidate 生成规则".
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from src.analysis.facts import CandidateLevel, FactRecord


def _get_fact(facts: List[FactRecord], fact_id: str) -> Optional[FactRecord]:
    for f in facts:
        if f.id == fact_id:
            return f
    return None


def _get_value(facts: List[FactRecord], fact_id: str) -> Optional[float]:
    f = _get_fact(facts, fact_id)
    if f is None or f.value is None:
        return None
    try:
        return float(f.value)
    except (TypeError, ValueError):
        return None


_ID_PREFIX = {
    "take_profit": "exit",
    "stop_loss": "stop",
    "entry": "entry",
    "exit": "exit",
}


def _make_candidate(
    idx: int, *, direction: str, price: float, current: float,
    label: str, basis_fact_id: str, basis_rule: str,
    applicable_strategies: List[str], tier: str = "primary",
) -> CandidateLevel:
    id_prefix = _ID_PREFIX[direction]
    distance = ((price - current) / current * 100) if current else 0.0
    return CandidateLevel(
        id=f"candidate.{id_prefix}.{idx}",
        type="candidate",
        label=label,
        value=price,
        display_value=f"${price:.2f}",
        direction=direction,
        price=price,
        basis_fact_id=basis_fact_id,
        basis_rule=basis_rule,
        applicable_strategies=applicable_strategies,
        tier=tier,
        distance_pct_from_current=round(distance, 4),
    )


def compute_candidates(facts: List[FactRecord]) -> List[CandidateLevel]:
    """Run all rules over facts; return all candidates that survive filtering."""
    current = _get_value(facts, "technical.current_price")
    if current is None:
        return []
    candidates: List[CandidateLevel] = []
    counters = {"exit": 0, "stop": 0, "entry": 0}

    def add(c: CandidateLevel) -> None:
        candidates.append(c)

    def next_idx(kind: str) -> int:
        counters[kind] += 1
        return counters[kind]

    # ---- Rule: resistance_touch (take_profit) ----
    r = _get_value(facts, "technical.resistance")
    if r is not None and r > current:
        add(_make_candidate(
            next_idx("exit"),
            direction="take_profit", price=r, current=current,
            label="阻力位触及减仓",
            basis_fact_id="technical.resistance",
            basis_rule="resistance_touch",
            applicable_strategies=["swing_trade", "stepped_profit_taking"],
        ))

    # ---- Rule: ma20_breakdown (stop_loss) ----
    ma20 = _get_value(facts, "technical.ma20")
    if ma20 is not None and ma20 < current:
        add(_make_candidate(
            next_idx("stop"),
            direction="stop_loss", price=ma20, current=current,
            label="MA20 跌破止损",
            basis_fact_id="technical.ma20",
            basis_rule="ma20_breakdown",
            applicable_strategies=["swing_trade", "stepped_profit_taking"],
        ))

    # ---- Rule: ma10_pullback (entry) ----
    ma10 = _get_value(facts, "technical.ma10")
    if ma10 is not None and ma10 <= current:
        add(_make_candidate(
            next_idx("entry"),
            direction="entry", price=ma10, current=current,
            label="MA10 回踩入场",
            basis_fact_id="technical.ma10",
            basis_rule="ma10_pullback",
            applicable_strategies=["swing_trade", "stepped_profit_taking"],
        ))

    # ---- Rule: support_test (entry) ----
    sup = _get_value(facts, "technical.support")
    if sup is not None and sup <= current:
        add(_make_candidate(
            next_idx("entry"),
            direction="entry", price=sup, current=current,
            label="支撑位反抽入场",
            basis_fact_id="technical.support",
            basis_rule="support_test",
            applicable_strategies=["swing_trade"],
        ))

    # ---- Rule: atr_2x_below_current (stop_loss) ----
    atr = _get_value(facts, "technical.atr_14")
    if atr is not None:
        price_2x = current - 2 * atr
        add(_make_candidate(
            next_idx("stop"),
            direction="stop_loss", price=round(price_2x, 2), current=current,
            label="ATR(14)×2 止损",
            basis_fact_id="technical.atr_14",
            basis_rule="atr_2x_below_current",
            applicable_strategies=["swing_trade"],
        ))

    # ---- Rule: atr_3x_below_current (stop_loss) ----
    if atr is not None:
        price_3x = current - 3 * atr
        add(_make_candidate(
            next_idx("stop"),
            direction="stop_loss", price=round(price_3x, 2), current=current,
            label="ATR(14)×3 止损",
            basis_fact_id="technical.atr_14",
            basis_rule="atr_3x_below_current",
            applicable_strategies=["stepped_profit_taking", "long_term_hold"],
        ))

    return candidates
