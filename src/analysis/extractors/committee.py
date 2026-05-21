"""Extract committee.* facts from dashboard.committee."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord

VERDICT_LABEL = {
    "strong_buy": "Strong Buy", "buy": "Buy", "hold": "Hold",
    "sell": "Sell", "strong_sell": "Strong Sell",
}


def extract_committee_facts(
    committee: Optional[Dict[str, Any]],
    as_of: str,
) -> List[FactRecord]:
    if not committee:
        return []
    facts: List[FactRecord] = []
    src = "committee"

    if "pm_verdict" in committee and committee["pm_verdict"]:
        facts.append(FactRecord(
            id="committee.pm_verdict", type="committee",
            label="PM 裁决", value=committee["pm_verdict"],
            display_value=VERDICT_LABEL.get(committee["pm_verdict"], committee["pm_verdict"]),
            source=src, as_of=as_of,
            extra={"rationale": committee.get("pm_rationale", "")},
        ))

    if committee.get("pm_score") is not None:
        facts.append(FactRecord(
            id="committee.pm_score", type="committee",
            label="PM 评分", value=float(committee["pm_score"]),
            display_value=f"{committee['pm_score']:.1f} / 10",
            source=src, as_of=as_of,
        ))

    if committee.get("pm_dissents"):
        facts.append(FactRecord(
            id="committee.pm_dissents", type="committee",
            label="PM 异议清单", value=committee["pm_dissents"],
            display_value=", ".join(committee["pm_dissents"]),
            source=src, as_of=as_of,
        ))

    risk = committee.get("risk") or {}
    if risk.get("suggested_position_pct") is not None:
        pct = float(risk["suggested_position_pct"])
        facts.append(FactRecord(
            id="committee.risk.suggested_position_pct", type="committee",
            label="风控建议仓位上限", value=pct,
            display_value=f"≤ {int(pct * 100)}%",
            source=src, as_of=as_of,
            extra={
                "severity": risk.get("severity"),
                "red_flags": risk.get("red_flags", []),
                "veto": risk.get("veto", False),
            },
        ))

    if risk.get("severity"):
        facts.append(FactRecord(
            id="committee.risk.severity", type="committee",
            label="风控严重度", value=risk["severity"],
            display_value=risk["severity"],
            source=src, as_of=as_of,
        ))

    dissents = set(committee.get("pm_dissents") or [])
    for master in committee.get("masters") or []:
        persona = master.get("persona")
        if not persona:
            continue
        is_dissent = persona in dissents
        verdict = master.get("verdict", "")
        score = master.get("score")
        score_str = f" ({score:.1f})" if score is not None else ""
        dissent_mark = " ⚠ 异议" if is_dissent else ""
        facts.append(FactRecord(
            id=f"committee.master.{persona}", type="committee",
            label=f"{persona} 投票", value=verdict,
            display_value=f"{VERDICT_LABEL.get(verdict, verdict)}{score_str}{dissent_mark}",
            source=src, as_of=as_of,
            extra={
                "score": score,
                "headline": master.get("headline", ""),
                "key_evidence": master.get("key_evidence", []),
                "is_dissent": is_dissent,
            },
        ))

    return facts
