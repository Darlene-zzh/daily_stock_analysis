"""Extract intel.* facts from dashboard.intelligence."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord


def extract_intel_facts(
    intelligence: Optional[Dict[str, Any]],
    as_of: str,
) -> List[FactRecord]:
    if not intelligence:
        return []
    facts: List[FactRecord] = []

    risk_alerts = intelligence.get("risk_alerts") or []
    risk_alerts_zh = intelligence.get("risk_alerts_zh") or []
    for i, alert in enumerate(risk_alerts):
        facts.append(FactRecord(
            id=f"intel.risk_alert.{i}", type="intel",
            label="风险警示", value=alert,
            display_value=str(alert)[:120],
            source="intelligence.risk_alerts",
            as_of=as_of,
            extra={"zh": risk_alerts_zh[i] if i < len(risk_alerts_zh) else ""},
        ))

    catalysts = intelligence.get("positive_catalysts") or []
    catalysts_zh = intelligence.get("positive_catalysts_zh") or []
    for i, cat in enumerate(catalysts):
        facts.append(FactRecord(
            id=f"intel.positive_catalyst.{i}", type="intel",
            label="正向催化", value=cat,
            display_value=str(cat)[:120],
            source="intelligence.positive_catalysts",
            as_of=as_of,
            extra={"zh": catalysts_zh[i] if i < len(catalysts_zh) else ""},
        ))

    for key, label in [("latest_news", "最新新闻"),
                       ("sentiment_summary", "市场情绪概览"),
                       ("earnings_outlook", "财报展望")]:
        val = intelligence.get(key)
        if val:
            zh = intelligence.get(f"{key}_zh", "")
            facts.append(FactRecord(
                id=f"intel.{key}", type="intel",
                label=label, value=val, display_value=str(val)[:160],
                source=f"intelligence.{key}", as_of=as_of,
                extra={"zh": zh} if zh else {},
            ))

    dims = intelligence.get("sentiment_dimensions") or {}
    for source_name, data in dims.items():
        if not data:
            continue
        score = data.get("score") if isinstance(data, dict) else None
        summary = data.get("summary", "") if isinstance(data, dict) else ""
        facts.append(FactRecord(
            id=f"intel.sentiment.{source_name}", type="intel",
            label=f"{source_name} 情绪",
            value=score,
            display_value=f"{score:.2f}" if isinstance(score, (int, float)) else "—",
            source=f"intelligence.sentiment_dimensions.{source_name}",
            as_of=as_of,
            extra={"summary": summary},
        ))

    return facts
