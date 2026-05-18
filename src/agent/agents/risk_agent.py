# -*- coding: utf-8 -*-
"""
RiskAgent — dedicated risk screening specialist.

Responsible for:
- Scanning for insider sell-downs, earnings warnings, regulatory actions
- Checking valuation anomalies (PE/PB extremes)
- Evaluating lock-up expiration risks
- Producing risk flags that can override or downgrade signals from other agents
- Sprint 4: emitting a structured :class:`RiskAssessment` (position %,
  tail-risk score, parametric VaR) alongside the legacy soft/hard flag set

Risk flags use a two-level severity system:
- **soft**: downgrades the signal and adds a visible warning
- **hard**: vetoes buy signals entirely when risk override is enabled
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, List, Optional, Sequence

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json
from src.schemas.risk_schema import RiskAssessment

logger = logging.getLogger(__name__)


class RiskAgent(BaseAgent):
    agent_name = "risk"
    max_steps = 4
    tool_names = [
        "search_stock_news",
        "get_realtime_quote",
        "get_stock_info",
    ]

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
You are a **Risk Screening Agent** focused exclusively on identifying \
risks and red flags for the given stock.

Your task: search for and evaluate ALL potential risk factors, then \
output a structured JSON risk assessment.

## Mandatory Risk Checks
1. **Insider / Major Shareholder Activity** — sell-downs (减持), pledges
2. **Earnings Warnings** — pre-loss, downward revisions (业绩预亏, 业绩变脸)
3. **Regulatory** — penalties, investigations, violations (监管处罚, 立案调查)
4. **Industry Policy** — headwinds, sector crackdowns
5. **Lock-up Expirations** — large block unlocks within 30 days (解禁)
6. **Valuation Extremes** — PE > 100 or negative, PB > 10 (flag as anomaly)
7. **Technical Warning Signs** — death crosses, breaking key supports

## Severity Levels
- "high": existential or material risk (lawsuits, fraud, massive insider selling)
- "medium": significant concern (earnings miss, lock-up, sector headwind)
- "low": minor or informational (analyst downgrade, minor insider sale)

## Output Format
Return **only** a JSON object:
{
  "risk_level": "high|medium|low|none",
  "risk_score": 0-100,
  "flags": [
    {
      "category": "insider|earnings|regulatory|industry|lockup|valuation|technical",
      "severity": "high|medium|low",
      "description": "Clear description of the risk",
      "source": "Where this information came from"
    }
  ],
  "veto_buy": true|false,
  "reasoning": "2-3 sentence overall risk assessment",
  "signal_adjustment": "none|downgrade_one|downgrade_two|veto"
}

Important: be thorough but factual. Only flag risks backed by evidence \
from your search results. Do NOT invent risks.
"""

    def build_user_message(self, ctx: AgentContext) -> str:
        parts = [f"Screen stock **{ctx.stock_code}**"]
        if ctx.stock_name:
            parts[0] += f" ({ctx.stock_name})"
        parts.append("for ALL risk factors listed in your instructions.")
        parts.append("Search for latest news if you haven't received intel data yet.")

        # Feed any existing intel data so the risk agent doesn't redo searches
        if ctx.get_data("intel_opinion"):
            parts.append(f"\n[Existing intel data]\n{json.dumps(ctx.get_data('intel_opinion'), ensure_ascii=False, default=str)}")

        return "\n".join(parts)

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning("[RiskAgent] failed to parse risk JSON")
            return None

        # Propagate structured risk flags to context
        for flag in parsed.get("flags", []):
            if isinstance(flag, dict):
                ctx.add_risk_flag(
                    category=flag.get("category", "unknown"),
                    description=flag.get("description", ""),
                    severity=flag.get("severity", "medium"),
                )

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=_risk_to_signal(parsed.get("risk_level", "none")),
            confidence=float(parsed.get("risk_score", 50)) / 100.0,
            reasoning=parsed.get("reasoning", ""),
            raw_data=parsed,
        )

    # ------------------------------------------------------------------ #
    # Sprint 4: structured RiskAssessment derivation
    # ------------------------------------------------------------------ #

    @staticmethod
    def build_structured_assessment(
        ctx: Optional[AgentContext] = None,
        *,
        raw_llm: Optional[Dict[str, Any]] = None,
        recent_closes: Optional[Sequence[float]] = None,
    ) -> RiskAssessment:
        """Derive a structured :class:`RiskAssessment` from the agent's LLM
        output plus any tangible price history.

        This is intentionally **deterministic** and side-effect free so it
        can be called independently of the committee path (Sprint 4
        ``enable_structured_risk=True`` mode) and unit-tested with a stub.

        Parameters
        ----------
        ctx
            Standard :class:`AgentContext` — used only for the risk flag
            log already populated by ``post_process``.
        raw_llm
            The parsed JSON from the LLM (the same dict ``post_process``
            stores on :attr:`AgentOpinion.raw_data`).  Optional; the helper
            degrades gracefully when ``None``.
        recent_closes
            Iterable of daily closing prices, oldest → newest.  When
            supplied (length >= 2) it drives the parametric VaR and the
            annualised volatility figure.  When absent, both fields stay
            ``None`` — never crash, never invent numbers.

        Returns
        -------
        :class:`RiskAssessment`
            All Sprint 1A fields populated for back-compat; the Sprint 4
            extensions (``tail_risk_score``, ``var_estimate_5pct``,
            ``volatility_annualised``) populated when feasible.
        """
        raw = raw_llm or {}
        severity = _llm_to_severity(raw.get("risk_level"), raw.get("signal_adjustment"))
        red_flags = _summarise_flags(raw.get("flags") or [])
        rationale = (raw.get("reasoning") or None) or None

        vol = _annualised_volatility(recent_closes)
        var_5pct = _parametric_var_5pct(vol)
        tail_risk = _tail_risk_score(
            llm_risk_score=_safe_int(raw.get("risk_score")),
            flags=raw.get("flags") or [],
            annualised_vol=vol,
        )
        suggested_pct = _suggested_position_pct(
            severity=severity,
            annualised_vol=vol,
            tail_risk_score=tail_risk,
        )
        veto = bool(raw.get("veto_buy")) or severity == "hard"

        return RiskAssessment(
            severity=severity,
            red_flags=red_flags,
            suggested_position_pct=suggested_pct,
            veto=veto,
            tail_risk_score=tail_risk,
            var_estimate_5pct=var_5pct,
            volatility_annualised=vol,
            rationale=rationale,
        )


# ---------------------------------------------------------------------------- #
# Pure helpers (deterministic, no external state)
# ---------------------------------------------------------------------------- #


def _risk_to_signal(risk_level: str) -> str:
    """Map risk level to a trading signal (inverted)."""
    mapping = {
        "none": "buy",
        "low": "hold",
        "medium": "sell",
        "high": "strong_sell",
    }
    return mapping.get(risk_level, "hold")


def _llm_to_severity(
    risk_level: Any, signal_adjustment: Any
) -> Optional[str]:
    """Map the LLM's risk_level into the Sprint 1A severity tier."""
    rl = (str(risk_level) if risk_level is not None else "").strip().lower()
    sa = (str(signal_adjustment) if signal_adjustment is not None else "").strip().lower()
    if sa == "veto" or rl == "high":
        return "hard"
    if rl in ("medium", "low") or sa.startswith("downgrade"):
        return "soft"
    if rl == "none":
        return "none"
    return None


def _summarise_flags(flags: List[Any]) -> List[str]:
    """Compact ``flags`` into <= 6 human-readable bullets."""
    out: List[str] = []
    for f in flags:
        if not isinstance(f, dict):
            continue
        category = (f.get("category") or "risk").strip()
        description = (f.get("description") or "").strip()
        if description:
            out.append(f"[{category}] {description}"[:200])
        if len(out) >= 6:
            break
    return out


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _annualised_volatility(closes: Optional[Sequence[float]]) -> Optional[float]:
    """sqrt(252) × stdev(close-to-close returns).  None if < 2 prices."""
    if closes is None:
        return None
    prices: List[float] = []
    for p in closes:
        try:
            prices.append(float(p))
        except (TypeError, ValueError):
            continue
    if len(prices) < 2:
        return None
    returns: List[float] = []
    for i in range(1, len(prices)):
        if prices[i - 1] <= 0:
            continue
        returns.append((prices[i] - prices[i - 1]) / prices[i - 1])
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    daily_vol = math.sqrt(max(var, 0.0))
    return daily_vol * math.sqrt(252.0)


def _parametric_var_5pct(annualised_vol: Optional[float]) -> Optional[float]:
    """1-day 5% parametric VaR (z = 1.645).  Returned as a positive fraction."""
    if annualised_vol is None or annualised_vol <= 0:
        return None
    daily_vol = annualised_vol / math.sqrt(252.0)
    return round(1.645 * daily_vol, 6)


def _tail_risk_score(
    *,
    llm_risk_score: Optional[int],
    flags: List[Any],
    annualised_vol: Optional[float],
) -> Optional[float]:
    """Heuristic 0..10 score combining LLM risk_score + flag categories + vol.

    Returns ``None`` when there is no signal to base a score on (no flags,
    no LLM score, no volatility).  Otherwise:

    - Start from ``llm_risk_score / 10`` (LLM emits 0..100).
    - Add 0.5 per high-severity flag (cap at 2.0 from this component).
    - Add another 0..2.0 from annualised volatility (linear 0%..80%).
    """
    has_signal = (
        llm_risk_score is not None
        or any(isinstance(f, dict) for f in flags)
        or annualised_vol is not None
    )
    if not has_signal:
        return None

    base = (llm_risk_score or 0) / 10.0

    high_flag_count = 0
    for f in flags:
        if isinstance(f, dict) and str(f.get("severity") or "").lower() == "high":
            high_flag_count += 1
    flag_component = min(2.0, 0.5 * high_flag_count)

    vol_component = 0.0
    if annualised_vol is not None:
        vol_component = min(2.0, max(0.0, annualised_vol / 0.80 * 2.0))

    score = base + flag_component + vol_component
    return round(min(10.0, max(0.0, score)), 2)


def _suggested_position_pct(
    *,
    severity: Optional[str],
    annualised_vol: Optional[float],
    tail_risk_score: Optional[float],
) -> Optional[float]:
    """Conservative position cap as a fraction (0..1).

    Rules of thumb (locked):

    - severity=hard       → 0  (veto)
    - severity=soft       → start at 0.12
    - severity=none / unknown → start at 0.25
    - Reduce 10% per tail-risk-score point above 5
    - Reduce 50% if annualised volatility > 0.6
    - Clamp to [0, 0.30] so we never recommend > 30%
    """
    if severity == "hard":
        return 0.0
    if severity == "soft":
        base = 0.12
    elif severity == "none":
        base = 0.25
    else:
        base = 0.20  # unknown severity → middle ground
    if tail_risk_score is not None and tail_risk_score > 5:
        base *= max(0.1, 1.0 - 0.10 * (tail_risk_score - 5))
    if annualised_vol is not None and annualised_vol > 0.60:
        base *= 0.5
    return round(max(0.0, min(0.30, base)), 4)
