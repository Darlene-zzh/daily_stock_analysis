"""Stage 1 orchestrator — wires all 8 extractors + candidate rules into a FactBundle.

Called from src/core/pipeline.py::process_single_stock after committee + dashboard
assembly is complete. Returns a FactBundle attached to dashboard.fact_bundle.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.candidate_rules import compute_candidates
from src.analysis.extractors.chip import extract_chip_facts
from src.analysis.extractors.committee import extract_committee_facts
from src.analysis.extractors.flow import extract_flow_facts
from src.analysis.extractors.intel import extract_intel_facts
from src.analysis.extractors.portfolio import extract_portfolio_facts
from src.analysis.extractors.quant import extract_quant_facts
from src.analysis.extractors.technical import extract_technical_facts
from src.analysis.facts import FactBundle, FactRecord


def build_fact_bundle(
    *,
    stock_code: str,
    market: str,
    dashboard: Dict[str, Any],
    portfolio_context: Optional[Dict[str, Any]],
    ohlc: Optional[List[Dict[str, Any]]],
    rsi_12: Optional[float],
    qlib_predictions: Dict[str, Dict[str, float]],
    qlib_ic: Dict[str, Any],
    qlib_week: str,
    qlib_universe_size: int,
    as_of: str,
    flow: Optional[Dict[str, Any]] = None,
    chip: Optional[Dict[str, Any]] = None,
) -> FactBundle:
    """Assemble the Stage 1 FactBundle. Pure code, no LLM, no I/O.

    Caller is responsible for resolving qlib predictions / flow / chip / ohlc
    upstream and passing them in.
    """
    facts: List[FactRecord] = []

    facts.extend(extract_technical_facts(
        data_perspective=dashboard.get("data_perspective") or {},
        rsi_12=rsi_12, as_of=as_of, market=market, ohlc=ohlc,
    ))
    facts.extend(extract_quant_facts(
        ticker=stock_code,
        predictions=qlib_predictions or {}, ic=qlib_ic or {},
        universe_size=qlib_universe_size, week=qlib_week, as_of=as_of,
    ))
    facts.extend(extract_committee_facts(
        committee=dashboard.get("committee"), as_of=as_of,
    ))
    facts.extend(extract_intel_facts(
        intelligence=dashboard.get("intelligence"), as_of=as_of,
    ))
    facts.extend(extract_portfolio_facts(
        portfolio_context=portfolio_context, as_of=as_of,
    ))
    facts.extend(extract_flow_facts(flow=flow, market=market, as_of=as_of))
    facts.extend(extract_chip_facts(chip=chip, market=market, as_of=as_of))

    candidates = compute_candidates(facts)

    return FactBundle(
        as_of=as_of, market=market, stock_code=stock_code,
        facts=facts, candidates=candidates,
    )
