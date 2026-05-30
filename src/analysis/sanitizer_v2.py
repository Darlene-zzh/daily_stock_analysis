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
    portfolio_held: bool = True,
) -> List[Dict[str, Any]]:
    """Run the 9-check sanitizer against the candidate pool.

    Returns the filtered + corrected items list, with `priority` renumbered
    1..N. May return [] if all items fail — caller falls back to synthesizer.

    ``portfolio_held``: when False (user does not currently hold this symbol)
    the post-check pass zeroes out ``shares`` / ``pct_of_position`` /
    ``pct_of_equity`` on every survivor — Gemini & Cerebras free-tier models
    routinely hallucinate "持仓 5%" etc. against a non-existent position.
    Trigger prices and evidence are retained so the user still sees the
    informational levels; only the quantitative claims about a non-existent
    position are scrubbed.
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

        # Check #6 — evidence_refs autofill (must have ≥ 2 valid fact_ids)
        raw_refs = it.get("evidence_refs") or []
        if not isinstance(raw_refs, list):
            raw_refs = []
        valid_fact_ids = (
            {f.id for f in bundle.facts}
            | {c.id for c in bundle.candidates}
        )
        refs = [r for r in raw_refs if isinstance(r, str) and r in valid_fact_ids]
        if len(refs) < 2:
            # Auto-fill: basis_fact_id + first available committee fact
            if cand.basis_fact_id and cand.basis_fact_id not in refs:
                refs.append(cand.basis_fact_id)
            committee_facts = [f.id for f in bundle.facts
                                if f.type == "committee" and f.id not in refs]
            if committee_facts and len(refs) < 2:
                refs.append(committee_facts[0])
            if len(refs) < 2:
                # Fall back to a technical anchor when committee isn't available
                for f in bundle.facts:
                    if f.type == "technical" and f.id not in refs:
                        refs.append(f.id)
                        break
        # Strip duplicates while preserving order
        seen: set = set()
        deduped: list = []
        for r in refs:
            if r not in seen:
                seen.add(r)
                deduped.append(r)
        it = dict(it)
        it["evidence_refs"] = deduped

        survivors.append(it)

    # Check #8 — dedup by candidate_id, keeping the lowest-priority-number entry
    by_id: Dict[str, Dict[str, Any]] = {}
    for it in survivors:
        cid = it["candidate_id"]
        existing = by_id.get(cid)
        existing_pri = existing.get("priority", 1e9) if existing else 1e9
        new_pri = it.get("priority", 1e9)
        if existing is None or (
            isinstance(new_pri, (int, float)) and new_pri < existing_pri
        ):
            by_id[cid] = it
    survivors = list(by_id.values())

    # Check #7 — discipline_anchor capped to 1 entry (drop extras)
    def _effective_tier(item: Dict[str, Any]) -> str:
        item_tier = item.get("tier")
        if item_tier:
            return item_tier
        cand_obj = cmap.get(item["candidate_id"])
        return cand_obj.tier if cand_obj else ""

    anchors = [it for it in survivors if _effective_tier(it) == "discipline_anchor"]
    if len(anchors) > 1:
        anchors.sort(key=lambda x: x.get("priority", 99))
        keep_id = anchors[0]["candidate_id"]
        drop_ids = {it["candidate_id"] for it in anchors[1:]}
        survivors = [
            it for it in survivors
            if it["candidate_id"] == keep_id or it["candidate_id"] not in drop_ids
        ]

    # Check #9 — Renumber priority 1..N after dedup/cap
    for new_pri, it in enumerate(survivors, start=1):
        it["priority"] = new_pri

    # Check #10 — when user does not hold the symbol, scrub quantitative
    # position claims. Keep trigger_price + evidence — they remain useful as
    # informational levels for "if you enter, plan to exit here".
    if not portfolio_held:
        for it in survivors:
            had_claim = any(
                it.get(k) not in (None, 0, 0.0)
                for k in ("shares", "pct_of_position", "pct_of_equity")
            )
            it["shares"] = None
            it["pct_of_position"] = None
            it["pct_of_equity"] = None
            if had_claim:
                logger.info(
                    "[sanitizer_v2] scrubbed fabricated position fields on "
                    "candidate=%s (user does not hold)", it.get("candidate_id"),
                )

    return survivors
