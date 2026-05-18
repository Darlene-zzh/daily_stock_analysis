# -*- coding: utf-8 -*-
"""Bull-side researcher for the Investment Committee debate phase.

Adapted from ``~/reference_repos/TradingAgents/tradingagents/agents/researchers/bull_researcher.py``
but rewritten to:
- emit a structured :class:`DebateExchange` JSON object per round
- accept the existing :class:`AgentContext` and an ordered debate history
- enforce the evidence floor (≥ 3 specific items per claim — spec §11)
- stay neutral on stock-narrative voice (it argues *for* the position, but
  cites the supplied materials, never invents facts)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.agent.protocols import AgentContext


class BullResearcher:
    """Stateless prompt builder + identity for the Bull side of the debate."""

    side = "bull"
    display_en = "Bull Researcher"
    display_zh = "看多研究员"

    # ---------------------------------------------------------------- #
    # Prompts
    # ---------------------------------------------------------------- #

    @classmethod
    def system_prompt(cls) -> str:
        return (
            "You are a Bull Researcher participating in an Investment "
            "Committee debate on a single stock. Your task: build the "
            "strongest evidence-based bull case using ONLY the supplied "
            "materials (pre-analysis report, prior debate exchanges, "
            "available tool outputs). Do not invent facts.\n"
            "\n"
            "Focus areas:\n"
            "1. Growth Potential — TAM expansion, scalability, "
            "compounding revenue/margin trends.\n"
            "2. Competitive Advantages — moats, brand, switching costs, "
            "scale economics.\n"
            "3. Positive Catalysts — recent news, fundamentals, sentiment, "
            "technical confirmations that support a long thesis.\n"
            "4. Bear Counterpoints — engage the prior bear claim directly "
            "if it exists; show why the bull side is stronger.\n"
            "\n"
            "Rules:\n"
            "- Cite at least THREE specific pieces of evidence from the "
            "supplied materials.\n"
            "- Tone is conversational debate, but evidence-anchored.\n"
            "- Keep `claim` to <= 200 characters.\n"
            "- Output a SINGLE JSON object — no markdown fence, no prose "
            "outside JSON:\n"
            "{\n"
            '  "side": "bull",\n'
            '  "round_index": <int>,\n'
            '  "claim": "<<= 200 char thesis>",\n'
            '  "evidence": ["<evidence 1>", "<evidence 2>", "<evidence 3>"],\n'
            '  "rebuttal_to": "<short reference to prior bear claim, or null>",\n'
            '  "confidence": <0..1>\n'
            "}\n"
        )

    @classmethod
    def build_user_message(
        cls,
        ctx: AgentContext,
        *,
        round_index: int,
        report_json: Dict[str, Any],
        prior_exchanges: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        prior_exchanges = prior_exchanges or []
        last_bear = next(
            (e for e in reversed(prior_exchanges) if e.get("side") == "bear"),
            None,
        )
        stock_label = ctx.stock_code
        if ctx.stock_name:
            stock_label += f" ({ctx.stock_name})"

        try:
            report_blob = json.dumps(report_json, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            report_blob = str(report_json)
        if len(report_blob) > 7000:
            report_blob = report_blob[:7000] + "...(truncated)"

        lines: List[str] = [
            f"Stock: {stock_label}",
            f"Round: {round_index}",
            "Pre-analysis report (JSON):",
            report_blob,
        ]
        if last_bear:
            lines.extend(
                [
                    "",
                    "Most recent bear claim to rebut:",
                    json.dumps(last_bear, ensure_ascii=False, default=str)[:1500],
                ]
            )
        lines.append(
            "\nReturn the JSON object now — bull side, round_index="
            f"{round_index}, with >= 3 evidence items."
        )
        return "\n".join(lines)


class BearResearcher:
    """Stateless prompt builder + identity for the Bear side of the debate."""

    side = "bear"
    display_en = "Bear Researcher"
    display_zh = "看空研究员"

    @classmethod
    def system_prompt(cls) -> str:
        return (
            "You are a Bear Researcher participating in an Investment "
            "Committee debate on a single stock. Your task: build the "
            "strongest evidence-based bear case using ONLY the supplied "
            "materials. Do not invent risks; cite tangible signals.\n"
            "\n"
            "Focus areas:\n"
            "1. Downside Risks — leverage, dilution, refinancing, "
            "regulatory, single-customer concentration.\n"
            "2. Competitive Erosion — share losses, gross-margin compression, "
            "disruptor encroachment.\n"
            "3. Negative Catalysts — recent earnings miss, guidance cuts, "
            "insider selling, deteriorating sentiment.\n"
            "4. Bull Counterpoints — engage the prior bull claim directly "
            "if it exists; show why the bear side is stronger.\n"
            "\n"
            "Rules:\n"
            "- Cite at least THREE specific pieces of evidence from the "
            "supplied materials.\n"
            "- Tone is conversational debate, but evidence-anchored.\n"
            "- Keep `claim` to <= 200 characters.\n"
            "- Output a SINGLE JSON object — no markdown fence, no prose "
            "outside JSON:\n"
            "{\n"
            '  "side": "bear",\n'
            '  "round_index": <int>,\n'
            '  "claim": "<<= 200 char thesis>",\n'
            '  "evidence": ["<evidence 1>", "<evidence 2>", "<evidence 3>"],\n'
            '  "rebuttal_to": "<short reference to prior bull claim, or null>",\n'
            '  "confidence": <0..1>\n'
            "}\n"
        )

    @classmethod
    def build_user_message(
        cls,
        ctx: AgentContext,
        *,
        round_index: int,
        report_json: Dict[str, Any],
        prior_exchanges: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        prior_exchanges = prior_exchanges or []
        last_bull = next(
            (e for e in reversed(prior_exchanges) if e.get("side") == "bull"),
            None,
        )
        stock_label = ctx.stock_code
        if ctx.stock_name:
            stock_label += f" ({ctx.stock_name})"

        try:
            report_blob = json.dumps(report_json, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            report_blob = str(report_json)
        if len(report_blob) > 7000:
            report_blob = report_blob[:7000] + "...(truncated)"

        lines: List[str] = [
            f"Stock: {stock_label}",
            f"Round: {round_index}",
            "Pre-analysis report (JSON):",
            report_blob,
        ]
        if last_bull:
            lines.extend(
                [
                    "",
                    "Most recent bull claim to rebut:",
                    json.dumps(last_bull, ensure_ascii=False, default=str)[:1500],
                ]
            )
        lines.append(
            "\nReturn the JSON object now — bear side, round_index="
            f"{round_index}, with >= 3 evidence items."
        )
        return "\n".join(lines)
