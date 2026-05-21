"""FactRecord / FactBundle / CandidateLevel — typed data classes for Stage 1 outputs.

See docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md
Section A for full schema design.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


@dataclass
class FactRecord:
    id: str
    type: str
    label: str
    value: Any
    display_value: str
    unit: Optional[str] = None
    source: str = ""
    confidence: Optional[float] = None
    as_of: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateLevel(FactRecord):
    """Candidate trigger price level produced by candidate_rules.

    Inherits all FactRecord fields. Subclass-specific fields below.
    """
    direction: Literal["entry", "exit", "stop", "take_profit", "stop_loss"] = "entry"
    price: float = 0.0
    basis_fact_id: str = ""
    basis_rule: str = ""
    applicable_strategies: List[str] = field(default_factory=list)
    tier: Literal["primary", "secondary", "discipline_anchor", "filtered"] = "primary"
    distance_pct_from_current: float = 0.0


@dataclass
class FactBundle:
    as_of: str
    market: Literal["a", "hk", "us"]
    stock_code: str
    facts: List[FactRecord]
    candidates: List[CandidateLevel]

    def get(self, fact_id: str) -> Optional[FactRecord]:
        for f in self.facts:
            if f.id == fact_id:
                return f
        for c in self.candidates:
            if c.id == fact_id:
                return c
        return None

    def by_type(self, type_prefix: str) -> List[FactRecord]:
        return [f for f in self.facts if f.type == type_prefix]
