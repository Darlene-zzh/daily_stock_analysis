"""Deterministic code-side synthesizer: build action_plan_items directly from
the FactBundle.candidates pool when the LLM fails or the sanitizer empties.

Each item carries `provenance: "synthesized"` so the UI can badge it as a code
fallback. Spec: docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md
Section B "Synthesizer 重写".
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.analysis.facts import CandidateLevel, FactRecord


_MAX_EXITS_PER_STRATEGY = {
    "long_term_hold": 1,
    "swing_trade": 2,
    "stepped_profit_taking": 3,
    "wait_and_see": 0,
}

_MAX_STOPS_PER_STRATEGY = {
    "long_term_hold": 1,
    "swing_trade": 1,
    "stepped_profit_taking": 1,
    "wait_and_see": 0,
}


def _first_committee_fact_id(facts: List[FactRecord]) -> str:
    for f in facts:
        if f.type == "committee":
            return f.id
    return ""


def _item_from_candidate(
    cand: CandidateLevel,
    facts: List[FactRecord],
    priority: int,
) -> Dict[str, Any]:
    committee_anchor = _first_committee_fact_id(facts)
    evidence_refs: List[str] = [cand.basis_fact_id] if cand.basis_fact_id else []
    if committee_anchor and committee_anchor not in evidence_refs:
        evidence_refs.append(committee_anchor)
    if len(evidence_refs) < 2:
        # Fall back to a technical anchor when committee isn't available
        for f in facts:
            if f.type == "technical" and f.id not in evidence_refs:
                evidence_refs.append(f.id)
                break
    return {
        "candidate_id": cand.id,
        "trigger_price": float(cand.price),
        "trigger_condition": f"{cand.label} ({cand.basis_rule})",
        "direction": cand.direction,
        "shares": 0,
        "pct_of_position": None,
        "pct_of_equity": None,
        "technical_basis": f"{cand.basis_rule}（来自代码合成）",
        "fundamental_basis": "",
        "quant_signal": "",
        "invalidation_rule": f"价格反向穿越 {cand.display_value} 视为失效",
        "priority": priority,
        "evidence_refs": evidence_refs[:3],
        "narrative": (
            f"{cand.label}：{cand.basis_rule}（代码兜底，"
            f"参考 <ref:{cand.basis_fact_id}>）"
        ),
        "tier": cand.tier,
        "provenance": "synthesized",
    }


def synthesize_from_candidates(
    candidates: List[CandidateLevel],
    *,
    strategy: str,
    facts: List[FactRecord],
) -> List[Dict[str, Any]]:
    """Code-side fallback: build action_plan_items directly from candidates.

    Returns an empty list when there's nothing applicable. UI marks each entry
    with `provenance: "synthesized"`.
    """
    if not candidates or not strategy:
        return []
    applicable = [
        c for c in candidates
        if c.tier != "filtered" and strategy in c.applicable_strategies
    ]
    if not applicable:
        return []

    max_exits = _MAX_EXITS_PER_STRATEGY.get(strategy, 2)
    max_stops = _MAX_STOPS_PER_STRATEGY.get(strategy, 1)

    primary_exits = sorted(
        [c for c in applicable
         if c.direction == "take_profit" and c.tier == "primary"],
        key=lambda c: c.distance_pct_from_current,
    )[:max_exits]
    primary_stops = sorted(
        [c for c in applicable
         if c.direction == "stop_loss" and c.tier == "primary"],
        key=lambda c: -c.distance_pct_from_current,
    )[:max_stops]

    chosen: List[CandidateLevel] = primary_exits + primary_stops

    # If we still have no primary picks, fall back to discipline_anchor (cap 1)
    if not chosen:
        anchors = sorted(
            [c for c in applicable if c.tier == "discipline_anchor"],
            key=lambda c: abs(c.distance_pct_from_current),
        )
        chosen = anchors[:1]

    items: List[Dict[str, Any]] = []
    for i, cand in enumerate(chosen, start=1):
        items.append(_item_from_candidate(cand, facts, priority=i))
    return items
