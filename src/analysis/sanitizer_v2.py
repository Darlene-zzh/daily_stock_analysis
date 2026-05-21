"""Phase 2 evidence-grounded sanitizer.

Replaces the legacy cost-basis sanitizer when a FactBundle is available.
Pure function — no I/O, no logging side-effects beyond the logger.

Spec: docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md
Section B "Sanitizer 新版".
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.analysis.facts import FactBundle, CandidateLevel

logger = logging.getLogger(__name__)


def _candidate_map(bundle: FactBundle) -> Dict[str, CandidateLevel]:
    return {c.id: c for c in bundle.candidates}


def sanitize_with_candidates(
    items: List[Dict[str, Any]],
    bundle: FactBundle,
    *,
    strategy: Optional[str],
    current_price: Optional[float],
) -> List[Dict[str, Any]]:
    """Run the 9-check sanitizer against the candidate pool.

    Returns the filtered + corrected items list, with `priority` renumbered
    1..N. May return [] if all items fail — caller falls back to synthesizer.
    """
    cmap = _candidate_map(bundle)
    survivors: List[Dict[str, Any]] = []

    for it in items:
        if not isinstance(it, dict):
            continue
        cid = it.get("candidate_id")

        # Check #1 — candidate_id must exist
        if not cid or cid not in cmap:
            logger.info(
                "[sanitizer_v2] drop item: candidate_id=%r not in bundle.candidates",
                cid,
            )
            continue
        cand = cmap[cid]

        # Check #2 — trigger_price must equal candidate.price (force override)
        candidate_price = float(cand.price)
        llm_price = it.get("trigger_price")
        if llm_price is None or abs(float(llm_price) - candidate_price) > 1e-6:
            logger.info(
                "[sanitizer_v2] override trigger_price: candidate=%s "
                "llm=%s -> candidate.price=%s",
                cid, llm_price, candidate_price,
            )
            it = dict(it)
            it["trigger_price"] = candidate_price

        # Check #3 — recommended_strategy must be in candidate.applicable_strategies
        if strategy and strategy not in cand.applicable_strategies:
            logger.info(
                "[sanitizer_v2] drop item: candidate=%s applies to %s, "
                "recommended=%s",
                cid, cand.applicable_strategies, strategy,
            )
            continue

        # Check #4 — candidate must not be in `filtered` tier
        if cand.tier == "filtered":
            logger.info(
                "[sanitizer_v2] drop item: candidate=%s is in filtered tier", cid,
            )
            continue

        # Check #5 — direction logic vs current price
        if current_price is not None:
            cp = float(current_price)
            if cand.direction == "take_profit" and candidate_price <= cp:
                logger.info(
                    "[sanitizer_v2] drop item: take_profit @ %s ≤ current %s",
                    candidate_price, cp,
                )
                continue
            if cand.direction == "stop_loss" and candidate_price >= cp:
                logger.info(
                    "[sanitizer_v2] drop item: stop_loss @ %s ≥ current %s",
                    candidate_price, cp,
                )
                continue

        survivors.append(it)

    # Renumber priority 1..N (final step shared with later checks)
    for new_pri, it in enumerate(survivors, start=1):
        it["priority"] = new_pri

    return survivors
