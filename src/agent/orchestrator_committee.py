# -*- coding: utf-8 -*-
"""LangGraph state machine for the Investment Committee (Sprint 1A).

The orchestrator is intentionally small and **synchronous**. It wires the
nodes prescribed by the design spec §5:

::

    START → bull → bear → (loop N rounds) → [master_buffett ∥ master_burry
            ∥ master_wood ∥ master_taleb] → risk → pm → END

Failure isolation rules (spec §5 node-level + §11 failure modes):

- Every node acquires :meth:`LLMCallBudget.acquire`; if denied, the node
  short-circuits with a ``budget_exhausted`` artefact and the graph moves on.
- Every node has try/except. On exception, the node appends a failure
  artefact (``status='failed'`` with ``error_summary``) and the graph moves
  on rather than raising.
- Strict parse with **1 retry** when a critical field is missing
  (:class:`CommitteeSchemaError`). After the retry, fall back to a failed
  artefact.
- A wall-clock timeout (env ``INVESTMENT_COMMITTEE_TIMEOUT_S``) bounds the
  whole run; on timeout PM still synthesises whatever did complete.
- The PM agent always runs at the end **unless** budget is so depleted it
  also fails — even then the orchestrator returns a ``status='failed'``
  fallback minutes object, never raising.

The ``llm_callable`` parameter abstracts the actual LLM invocation so the
test harness can substitute a deterministic stub. Production wiring of the
real :class:`LLMToolAdapter` lives in
:meth:`src.services.analysis_service.AnalysisService._invoke_committee`.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypedDict

from src.agent.agents.bull_researcher import BearResearcher, BullResearcher
from src.agent.agents.master_personas import DEFAULT_PERSONA_ORDER, get_persona_class
from src.agent.budget import LLMCallBudget, compute_effective_cap, resolve_timeout_s
from src.agent.protocols import AgentContext
from src.schemas.committee_schema import (
    COMMITTEE_MINUTES_PM_SCHEMA_EXAMPLE,
    CommitteeMinutes,
    CommitteeSchemaError,
    DEBATE_EXCHANGE_SCHEMA_EXAMPLE,
    DebateExchange,
    MASTER_OPINION_SCHEMA_EXAMPLE,
    MasterOpinion,
    RISK_ASSESSMENT_SCHEMA_EXAMPLE,
    RiskAssessment,
    failed_committee_minutes,
    failed_debate_exchange,
    failed_master_opinion,
    failed_risk_assessment,
    parse_committee_minutes_strict,
    parse_debate_exchange_strict,
    parse_master_opinion_strict,
    parse_risk_assessment_strict,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------- #
# LLM callable contract
# ---------------------------------------------------------------------------- #


LLMCallable = Callable[[str, str], str]
"""Signature: (system_prompt, user_message) -> raw_text_response.

Production wires this to :meth:`LLMToolAdapter.complete` (or equivalent).
Tests pass a deterministic stub that consumes the (system, user) pair and
returns canned JSON strings.

The callable MUST be synchronous and MUST NOT raise on non-critical
failures (e.g. quota throttle) — return an error sentinel string and let
the orchestrator's strict parser convert it into a failed artefact.
"""


# ---------------------------------------------------------------------------- #
# State type — TypedDict so LangGraph's StateGraph can use it
# ---------------------------------------------------------------------------- #


class CommitteeState(TypedDict, total=False):
    stock_code: str
    stock_name: str
    market: Optional[str]
    report_json: Dict[str, Any]
    debate_rounds: int
    current_round: int  # 1-based; incremented after each bear

    debate: List[Dict[str, Any]]
    masters: List[Dict[str, Any]]
    risk: Optional[Dict[str, Any]]
    minutes: Optional[Dict[str, Any]]

    missing_agents: List[str]
    started_at: float
    deadline: float
    timed_out: bool


# ---------------------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------------------- #


@dataclass
class CommitteeRunResult:
    """Wrapper returned by :class:`InvestmentCommitteeOrchestrator.run`."""

    minutes: CommitteeMinutes
    raw_state: Dict[str, Any]
    duration_s: float

    def to_dict(self) -> Dict[str, Any]:
        return self.minutes.model_dump()


class InvestmentCommitteeOrchestrator:
    """LangGraph-style state machine driver.

    Parameters
    ----------
    ctx
        Standard :class:`AgentContext` carrying ``stock_code`` / ``stock_name``.
    report_json
        The pre-analysis report (the dashboard / summary the masters
        critique).  Truncated downstream when fed to weak models.
    budget
        :class:`LLMCallBudget` controlling LLM call cap.
    debate_rounds
        Number of bull↔bear exchanges (each round = 1 bull + 1 bear).
    llm_callable
        Synchronous (system, user) → text callable; see :data:`LLMCallable`.
    timeout_s
        Wall-clock cap for the full run (default = env-driven).
    """

    def __init__(
        self,
        ctx: AgentContext,
        *,
        report_json: Dict[str, Any],
        budget: LLMCallBudget,
        llm_callable: LLMCallable,
        debate_rounds: int = 2,
        timeout_s: Optional[int] = None,
    ) -> None:
        self.ctx = ctx
        self.report_json = report_json or {}
        self.budget = budget
        self.llm = llm_callable
        self.debate_rounds = max(1, min(3, int(debate_rounds or 2)))
        self.timeout_s = int(timeout_s) if timeout_s is not None else resolve_timeout_s()

    # ----------------------------------------------------------------- #
    # Entry point
    # ----------------------------------------------------------------- #

    def run(self) -> CommitteeRunResult:
        t0 = time.time()
        state: CommitteeState = {
            "stock_code": self.ctx.stock_code,
            "stock_name": self.ctx.stock_name,
            "market": (self.ctx.meta or {}).get("market"),
            "report_json": self.report_json,
            "debate_rounds": self.debate_rounds,
            "current_round": 1,
            "debate": [],
            "masters": [],
            "risk": None,
            "minutes": None,
            "missing_agents": [],
            "started_at": t0,
            "deadline": t0 + self.timeout_s,
            "timed_out": False,
        }

        # We build the LangGraph for spec-fidelity, but the production
        # execution is driven by the explicit Python sequence below — this
        # keeps tests deterministic and avoids LangGraph runtime quirks
        # (e.g. checkpointer requirements in older versions).
        try:
            self._build_langgraph()  # validates wiring at construction time
        except Exception as exc:  # pragma: no cover — safety net only
            logger.debug("[committee] langgraph build skipped: %s", exc)

        # Debate phase
        for round_idx in range(1, self.debate_rounds + 1):
            state["current_round"] = round_idx
            if self._past_deadline(state):
                break
            self._bull_node(state)
            if self._past_deadline(state):
                break
            self._bear_node(state)

        # Master fan-out (deterministic order = serial for now;
        # parallelisation hook can plug into LangGraph later)
        for persona_id in DEFAULT_PERSONA_ORDER:
            if self._past_deadline(state):
                break
            self._master_node(state, persona_id)

        # Risk node
        if not self._past_deadline(state):
            self._risk_node(state)
        else:
            state["missing_agents"].append("risk")

        # PM node (always run unless we genuinely cannot synthesise)
        self._pm_node(state)

        if not state.get("minutes"):
            # Defensive fallback — PM didn't even produce a failed minutes object
            fb = failed_committee_minutes(
                debate_rounds=self.debate_rounds,
                budget_used=self.budget.used,
                budget_cap=self.budget.cap,
                error_summary="PM node failed to emit minutes",
                missing_agents=list(state.get("missing_agents") or []),
                debate=[DebateExchange(**e) for e in (state.get("debate") or [])],
                masters=[MasterOpinion(**m) for m in (state.get("masters") or [])],
                risk=RiskAssessment(**state["risk"]) if state.get("risk") else None,
                latency_ms=int((time.time() - t0) * 1000),
            )
            state["minutes"] = fb.model_dump()

        minutes_obj = CommitteeMinutes(**state["minutes"])
        duration = round(time.time() - t0, 3)
        return CommitteeRunResult(minutes=minutes_obj, raw_state=dict(state), duration_s=duration)

    # ----------------------------------------------------------------- #
    # LangGraph wiring (constructed for spec-fidelity; not executed)
    # ----------------------------------------------------------------- #

    def _build_langgraph(self) -> Any:
        """Construct the LangGraph StateGraph (spec §5).

        The graph is built at orchestrator construction time so any wiring
        bug surfaces immediately rather than during a debate run.  Actual
        execution is driven by the Python sequence in :meth:`run`; once
        Sprint 4 lands the checkpointer this method's output will replace
        the imperative driver.
        """
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError:  # pragma: no cover — Sprint 1 dep is pinned
            return None

        graph = StateGraph(CommitteeState)
        # NOTE: LangGraph 0.4.x reserves node names that clash with state
        # keys. Our state has 'risk' / 'minutes' keys, so the corresponding
        # nodes are prefixed with `node_` to avoid collisions.
        graph.add_node("bull_node", lambda s: self._bull_node(dict(s)) or s)  # noqa: ARG005
        graph.add_node("bear_node", lambda s: self._bear_node(dict(s)) or s)  # noqa: ARG005
        for persona_id in DEFAULT_PERSONA_ORDER:
            pid = persona_id  # closure capture
            graph.add_node(
                f"master_{pid}",
                lambda s, _pid=pid: self._master_node(dict(s), _pid) or s,  # noqa: ARG005
            )
        graph.add_node("risk_node", lambda s: self._risk_node(dict(s)) or s)  # noqa: ARG005
        graph.add_node("pm_node", lambda s: self._pm_node(dict(s)) or s)  # noqa: ARG005

        graph.add_edge(START, "bull_node")
        graph.add_edge("bull_node", "bear_node")
        # We model the debate loop as a single bull→bear edge; the Python
        # driver in :meth:`run` advances through ``current_round`` rounds.
        for pid in DEFAULT_PERSONA_ORDER:
            graph.add_edge("bear_node", f"master_{pid}")
            graph.add_edge(f"master_{pid}", "risk_node")
        graph.add_edge("risk_node", "pm_node")
        graph.add_edge("pm_node", END)
        return graph

    # ----------------------------------------------------------------- #
    # Helper — deadline & retry contract
    # ----------------------------------------------------------------- #

    def _past_deadline(self, state: CommitteeState) -> bool:
        if state.get("timed_out"):
            return True
        if time.time() >= state.get("deadline", 0.0):
            state["timed_out"] = True
            return True
        return False

    def _call_llm_with_retry(
        self,
        *,
        node_name: str,
        system_prompt: str,
        user_message: str,
        parse: Callable[[str], Any],
        schema_example: str,
    ) -> Any:
        """Acquire a slot, run the LLM, parse strictly, retry once on schema miss.

        Returns the parsed object on success.
        Raises :class:`CommitteeSchemaError` if both attempts fail, OR
        :class:`BudgetExhausted` if no slot is available.
        """
        if not self.budget.acquire(node_name):
            raise BudgetExhausted(node_name)
        raw_first = self.llm(system_prompt, user_message)
        try:
            return parse(raw_first)
        except CommitteeSchemaError as first_err:
            logger.info(
                "[committee:%s] first-parse failed, retrying once with schema example: %s",
                node_name, str(first_err)[:200],
            )
            if not self.budget.acquire(f"{node_name}.retry"):
                raise CommitteeSchemaError(
                    "budget exhausted before retry",
                    schema=schema_example,
                    raw=raw_first,
                ) from first_err
            retry_user = (
                "Your previous response failed strict parsing. Below is the "
                "exact JSON schema you must follow — emit ONLY a single JSON "
                "object matching it, no markdown fence, no commentary:\n\n"
                f"{schema_example}\n\n"
                "Now retry with the original task:\n\n"
                f"{user_message}"
            )
            raw_retry = self.llm(system_prompt, retry_user)
            return parse(raw_retry)  # may raise CommitteeSchemaError → handled by caller

    # ----------------------------------------------------------------- #
    # Nodes
    # ----------------------------------------------------------------- #

    def _bull_node(self, state: CommitteeState) -> Optional[CommitteeState]:
        round_idx = state.get("current_round", 1)
        node = f"bull_round_{round_idx}"
        try:
            parsed: DebateExchange = self._call_llm_with_retry(
                node_name=node,
                system_prompt=BullResearcher.system_prompt(),
                user_message=BullResearcher.build_user_message(
                    self.ctx,
                    round_index=round_idx,
                    report_json=self.report_json,
                    prior_exchanges=state.get("debate") or [],
                ),
                parse=lambda raw: parse_debate_exchange_strict(
                    raw, expected_side="bull", expected_round=round_idx,
                ),
                schema_example=DEBATE_EXCHANGE_SCHEMA_EXAMPLE,
            )
            state["debate"].append(parsed.model_dump())
        except BudgetExhausted as exc:
            logger.info("[committee] bull node skipped — budget exhausted")
            state["debate"].append(
                DebateExchange(
                    side="bull", round_index=round_idx, status="failed",
                    error_summary=f"budget exhausted at {exc.node}",
                ).model_dump()
            )
            state["missing_agents"].append(node)
        except CommitteeSchemaError as exc:
            logger.warning("[committee] bull node fell back: %s", str(exc)[:300])
            fb = failed_debate_exchange("bull", round_idx, error_summary=str(exc)[:500])
            state["debate"].append(fb.model_dump())
            state["missing_agents"].append(node)
        except Exception as exc:
            logger.error("[committee] bull node crashed: %s", exc, exc_info=True)
            fb = failed_debate_exchange("bull", round_idx, error_summary=f"unexpected: {exc}")
            state["debate"].append(fb.model_dump())
            state["missing_agents"].append(node)
        return state

    def _bear_node(self, state: CommitteeState) -> Optional[CommitteeState]:
        round_idx = state.get("current_round", 1)
        node = f"bear_round_{round_idx}"
        try:
            parsed: DebateExchange = self._call_llm_with_retry(
                node_name=node,
                system_prompt=BearResearcher.system_prompt(),
                user_message=BearResearcher.build_user_message(
                    self.ctx,
                    round_index=round_idx,
                    report_json=self.report_json,
                    prior_exchanges=state.get("debate") or [],
                ),
                parse=lambda raw: parse_debate_exchange_strict(
                    raw, expected_side="bear", expected_round=round_idx,
                ),
                schema_example=DEBATE_EXCHANGE_SCHEMA_EXAMPLE,
            )
            state["debate"].append(parsed.model_dump())
        except BudgetExhausted as exc:
            state["debate"].append(
                DebateExchange(
                    side="bear", round_index=round_idx, status="failed",
                    error_summary=f"budget exhausted at {exc.node}",
                ).model_dump()
            )
            state["missing_agents"].append(node)
        except CommitteeSchemaError as exc:
            fb = failed_debate_exchange("bear", round_idx, error_summary=str(exc)[:500])
            state["debate"].append(fb.model_dump())
            state["missing_agents"].append(node)
        except Exception as exc:
            logger.error("[committee] bear node crashed: %s", exc, exc_info=True)
            fb = failed_debate_exchange("bear", round_idx, error_summary=f"unexpected: {exc}")
            state["debate"].append(fb.model_dump())
            state["missing_agents"].append(node)
        return state

    def _master_node(self, state: CommitteeState, persona_id: str) -> Optional[CommitteeState]:
        try:
            persona_cls = get_persona_class(persona_id)
        except KeyError:
            logger.error("[committee] unknown persona %s — skipping", persona_id)
            state["missing_agents"].append(f"master_{persona_id}")
            return state

        try:
            parsed: MasterOpinion = self._call_llm_with_retry(
                node_name=f"master_{persona_id}",
                system_prompt=persona_cls.system_prompt(self.ctx),
                user_message=persona_cls.build_user_message(
                    self.ctx,
                    report_json=self.report_json,
                ),
                parse=parse_master_opinion_strict,
                schema_example=MASTER_OPINION_SCHEMA_EXAMPLE,
            )
            state["masters"].append(parsed.model_dump())
        except BudgetExhausted as exc:
            fb = failed_master_opinion(persona_id, error_summary=f"budget exhausted at {exc.node}")
            # Tag the budget_exhausted status explicitly
            fb_dict = fb.model_dump()
            fb_dict["status"] = "budget_exhausted"
            state["masters"].append(fb_dict)
            state["missing_agents"].append(f"master_{persona_id}")
        except CommitteeSchemaError as exc:
            fb = failed_master_opinion(persona_id, error_summary=str(exc)[:500])
            state["masters"].append(fb.model_dump())
            state["missing_agents"].append(f"master_{persona_id}")
        except Exception as exc:
            logger.error("[committee] master %s crashed: %s", persona_id, exc, exc_info=True)
            fb = failed_master_opinion(persona_id, error_summary=f"unexpected: {exc}")
            state["masters"].append(fb.model_dump())
            state["missing_agents"].append(f"master_{persona_id}")
        return state

    def _risk_node(self, state: CommitteeState) -> Optional[CommitteeState]:
        risk_sys = (
            "You are the Risk Manager for an Investment Committee. Based on "
            "the supplied pre-analysis report, debate exchanges, and master "
            "opinions, emit a structured JSON risk assessment. Do not invent "
            "risks; cite tangible signals.\n\n"
            "Severity scale:\n"
            "- none — no material risks identified\n"
            "- soft — material concerns; downgrade the verdict one notch\n"
            "- hard — existential / regulatory / liquidity issue; veto buy\n\n"
            "Output a SINGLE JSON object — no markdown fence, no prose outside JSON:\n"
            "{\n"
            '  "severity": "none" | "soft" | "hard",\n'
            '  "red_flags": ["<flag 1>", "<flag 2>"],\n'
            '  "suggested_position_pct": <0..1>,\n'
            '  "veto": <bool — true only when severity=="hard">\n'
            "}\n"
        )
        risk_user = json.dumps(
            {
                "stock_code": state.get("stock_code"),
                "stock_name": state.get("stock_name"),
                "report": _truncate_for_prompt(state.get("report_json")),
                "debate": state.get("debate"),
                "masters": state.get("masters"),
            },
            ensure_ascii=False, default=str,
        )
        if len(risk_user) > 8000:
            risk_user = risk_user[:8000] + "...(truncated)"
        try:
            parsed: RiskAssessment = self._call_llm_with_retry(
                node_name="risk",
                system_prompt=risk_sys,
                user_message=risk_user,
                parse=parse_risk_assessment_strict,
                schema_example=RISK_ASSESSMENT_SCHEMA_EXAMPLE,
            )
            state["risk"] = parsed.model_dump()
        except BudgetExhausted:
            state["missing_agents"].append("risk")
            state["risk"] = failed_risk_assessment("budget exhausted").model_dump()
        except CommitteeSchemaError as exc:
            state["missing_agents"].append("risk")
            state["risk"] = failed_risk_assessment(str(exc)[:500]).model_dump()
        except Exception as exc:
            logger.error("[committee] risk node crashed: %s", exc, exc_info=True)
            state["missing_agents"].append("risk")
            state["risk"] = failed_risk_assessment(f"unexpected: {exc}").model_dump()
        return state

    def _pm_node(self, state: CommitteeState) -> Optional[CommitteeState]:
        """Committee Portfolio Manager: synthesises the final verdict.

        The PM prompt explicitly enumerates which agents are missing so the
        verdict can acknowledge gaps (spec §6 retry contract item 4).
        """
        # Build a compact summary of what did complete
        completed_masters = [m for m in state.get("masters") or [] if m.get("status") == "ok"]
        failed_master_personas = [
            m.get("persona") or "<unknown>"
            for m in state.get("masters") or []
            if m.get("status") != "ok"
        ]
        debate_summary = state.get("debate") or []

        pm_sys = (
            "You are the Investment Committee Portfolio Manager. Synthesise "
            "the bull / bear debate, the master-lens opinions, and the risk "
            "assessment into a SINGLE final verdict for one stock.\n"
            "\n"
            "Rules:\n"
            "- If risk.veto == true OR risk.severity == 'hard', the PM verdict "
            "MUST be at most 'hold'.\n"
            "- If `missing_agents` is non-empty, you MUST acknowledge the gaps "
            "in `pm_rationale` AND set `status` = 'partial'.\n"
            "- When ALL lenses + risk completed, set `status` = 'ok'.\n"
            "- `pm_dissents` lists masters whose verdict you overrule (e.g. "
            "you go 'buy' but Burry said 'avoid').\n"
            "- `budget_used` and `budget_cap` are supplied below; copy them "
            "verbatim into the output.\n"
            "\n"
            "Output a SINGLE JSON object — no markdown fence, no prose outside JSON:\n"
            f"{COMMITTEE_MINUTES_PM_SCHEMA_EXAMPLE}\n"
        )

        pm_user = json.dumps(
            {
                "stock_code": state.get("stock_code"),
                "stock_name": state.get("stock_name"),
                "report": _truncate_for_prompt(state.get("report_json")),
                "debate_history": debate_summary,
                "master_opinions": completed_masters,
                "missing_master_personas": failed_master_personas,
                "missing_agents": state.get("missing_agents") or [],
                "risk_assessment": state.get("risk"),
                "budget_used": self.budget.used,
                "budget_cap": self.budget.cap,
                "debate_rounds": self.debate_rounds,
            },
            ensure_ascii=False, default=str,
        )
        if len(pm_user) > 12000:
            pm_user = pm_user[:12000] + "...(truncated)"

        latency_ms = int((time.time() - state.get("started_at", time.time())) * 1000)
        try:
            parsed: CommitteeMinutes = self._call_llm_with_retry(
                node_name="pm",
                system_prompt=pm_sys,
                user_message=pm_user,
                parse=parse_committee_minutes_strict,
                schema_example=COMMITTEE_MINUTES_PM_SCHEMA_EXAMPLE,
            )
            # Stitch in the orchestrator-side fields the LLM cannot know
            parsed.debate_rounds = self.debate_rounds
            parsed.debate = [DebateExchange(**e) for e in (state.get("debate") or [])]
            parsed.masters = [MasterOpinion(**m) for m in (state.get("masters") or [])]
            parsed.risk = RiskAssessment(**state["risk"]) if state.get("risk") else None
            parsed.missing_agents = list(state.get("missing_agents") or [])
            parsed.budget_used = self.budget.used
            parsed.budget_cap = self.budget.cap
            parsed.latency_ms = latency_ms

            # Authoritative status override — the LLM is *not* the source of
            # truth on which agents succeeded; we are.  Force the correct
            # ok/partial/failed signal based on what actually completed.
            parsed.status = _resolve_top_status(state, parsed)
            state["minutes"] = parsed.model_dump()
        except BudgetExhausted:
            state["minutes"] = failed_committee_minutes(
                debate_rounds=self.debate_rounds,
                budget_used=self.budget.used,
                budget_cap=self.budget.cap,
                error_summary="PM node could not run — budget exhausted",
                missing_agents=list(state.get("missing_agents") or []) + ["pm"],
                debate=[DebateExchange(**e) for e in (state.get("debate") or [])],
                masters=[MasterOpinion(**m) for m in (state.get("masters") or [])],
                risk=RiskAssessment(**state["risk"]) if state.get("risk") else None,
                latency_ms=latency_ms,
            ).model_dump()
        except CommitteeSchemaError as exc:
            state["minutes"] = failed_committee_minutes(
                debate_rounds=self.debate_rounds,
                budget_used=self.budget.used,
                budget_cap=self.budget.cap,
                error_summary=str(exc)[:500],
                missing_agents=list(state.get("missing_agents") or []) + ["pm"],
                debate=[DebateExchange(**e) for e in (state.get("debate") or [])],
                masters=[MasterOpinion(**m) for m in (state.get("masters") or [])],
                risk=RiskAssessment(**state["risk"]) if state.get("risk") else None,
                latency_ms=latency_ms,
            ).model_dump()
        except Exception as exc:
            logger.error("[committee] pm node crashed: %s", exc, exc_info=True)
            state["minutes"] = failed_committee_minutes(
                debate_rounds=self.debate_rounds,
                budget_used=self.budget.used,
                budget_cap=self.budget.cap,
                error_summary=f"unexpected: {exc}",
                missing_agents=list(state.get("missing_agents") or []) + ["pm"],
                debate=[DebateExchange(**e) for e in (state.get("debate") or [])],
                masters=[MasterOpinion(**m) for m in (state.get("masters") or [])],
                risk=RiskAssessment(**state["risk"]) if state.get("risk") else None,
                latency_ms=latency_ms,
            ).model_dump()
        return state


# ---------------------------------------------------------------------------- #
# Internal helpers
# ---------------------------------------------------------------------------- #


class BudgetExhausted(RuntimeError):
    """Raised internally to signal that an acquire was denied.

    The node that raised this is captured in :attr:`node`.
    """

    def __init__(self, node: str) -> None:
        super().__init__(f"LLM budget exhausted at node {node!r}")
        self.node = node


def _truncate_for_prompt(report_json: Any) -> Any:
    """Cap each top-level value of the report JSON when injected into prompts."""
    if not isinstance(report_json, dict):
        return report_json
    out: Dict[str, Any] = {}
    for k, v in report_json.items():
        if isinstance(v, str) and len(v) > 800:
            out[k] = v[:800] + "...(truncated)"
        else:
            out[k] = v
    return out


def _resolve_top_status(state: CommitteeState, minutes: CommitteeMinutes) -> str:
    """Compute the authoritative top-level ``status`` from orchestration state.

    Rules (spec §6 status semantics):
    - ``ok``      — all 4 masters + risk + PM ok AND no missing agents
    - ``partial`` — PM produced a verdict but some agents missing/failed
    - ``failed``  — only reached via the fallback minutes paths
    """
    missing = list(state.get("missing_agents") or [])
    if missing:
        return "partial"
    master_states = [m.get("status") for m in state.get("masters") or []]
    if any(s != "ok" for s in master_states):
        return "partial"
    if len(master_states) < len(DEFAULT_PERSONA_ORDER):
        return "partial"
    risk = state.get("risk") or {}
    if risk.get("status") not in (None, "ok"):
        return "partial"
    if not minutes.pm_verdict:
        return "failed"
    return "ok"
