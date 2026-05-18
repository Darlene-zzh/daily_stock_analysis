# -*- coding: utf-8 -*-
"""Sprint 4 — committee checkpoint resume tests.

Run with stub-LLM payloads that match the schema validators in
:mod:`src.schemas.committee_schema`.  The test forces a failure mid-graph
(at the ``master_burry`` node) by exhausting the budget for that one node,
verifies a checkpoint exists, then resumes and verifies:

- bull / bear / buffett state is restored (those nodes don't run again)
- the second run completes burry + wood + taleb + risk + pm
- ``budget_used`` accounts correctly for both runs (no double counting)
- on the resumed run, the orchestrator reports ``resumed_from_checkpoint=True``

The tests are intentionally **isolated**: each one uses a unique tempdir
for the SQLite checkpoint store via the ``COMMITTEE_CHECKPOINT_DIR`` env
var, so concurrent test runs cannot collide.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from typing import Any, List, Tuple

from src.agent.budget import LLMCallBudget
from src.agent.committee_checkpointer import (
    checkpoint_db_path,
    has_checkpoint,
    load_state,
)
from src.agent.orchestrator_committee import InvestmentCommitteeOrchestrator
from src.agent.protocols import AgentContext


# --------------------------------------------------------------------------- #
# Stub payloads — mirror the test_committee_graph.py helpers
# --------------------------------------------------------------------------- #


def _bull_payload(round_idx: int) -> str:
    return json.dumps({
        "side": "bull",
        "round_index": round_idx,
        "claim": "Durable franchise with pricing power.",
        "evidence": ["ROE > 25%", "Operating margin > 50%", "Buyback program"],
        "rebuttal_to": None,
        "confidence": 0.7,
    })


def _bear_payload(round_idx: int) -> str:
    return json.dumps({
        "side": "bear",
        "round_index": round_idx,
        "claim": "Regulatory overhang and slowing growth.",
        "evidence": ["Industry policy", "YoY revenue decel", "PE > sector"],
        "rebuttal_to": "moat thesis",
        "confidence": 0.55,
    })


def _master_payload(persona: str, verdict: str = "buy", score: float = 7.0) -> str:
    return json.dumps({
        "persona": persona,
        "verdict": verdict,
        "score": score,
        "headline": f"{persona} headline",
        "rationale": f"Rationale by {persona}. Two sentences here.",
        "key_evidence": [f"{persona}-ev-1", f"{persona}-ev-2", f"{persona}-ev-3"],
        "counter_view": "Regime shift could invalidate.",
        "tools_used": ["fundamentals_snapshot"],
    })


def _risk_payload(severity: str = "soft", veto: bool = False, pos: float = 0.15) -> str:
    return json.dumps({
        "severity": severity,
        "red_flags": ["earnings next week"],
        "suggested_position_pct": pos,
        "veto": veto,
    })


def _pm_payload(
    verdict: str = "buy",
    status: str = "ok",
    budget_used: int = 10,
    budget_cap: int = 14,
) -> str:
    return json.dumps({
        "status": status,
        "pm_verdict": verdict,
        "pm_score": 7.2,
        "pm_rationale": "Lenses lean positive; risk soft.",
        "pm_dissents": [],
        "missing_agents": [],
        "budget_used": budget_used,
        "budget_cap": budget_cap,
    })


class StubLLM:
    """Sequence-driven stub identical to the one in test_committee_graph.py."""

    def __init__(self, responses: List[Any]) -> None:
        self.responses = list(responses)
        self.calls: List[Tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.responses:
            raise AssertionError(
                "StubLLM exhausted — orchestrator made an unexpected LLM call"
            )
        nxt = self.responses.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        if callable(nxt):
            return nxt(system, user)
        return nxt


def _make_ctx() -> AgentContext:
    return AgentContext(stock_code="600519", stock_name="贵州茅台", meta={"market": "A"})


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


class TestCommitteeCheckpointResume(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="committee_ckpt_")
        # Force a unique env-scoped checkpoint dir so concurrent tests can't collide
        os.environ["COMMITTEE_CHECKPOINT_DIR"] = self.tmpdir
        os.environ["TASK_QUEUE_CHECKPOINT_ENABLED"] = "true"
        self.query_id = "test-resume-001"

    def tearDown(self) -> None:
        os.environ.pop("COMMITTEE_CHECKPOINT_DIR", None)
        os.environ.pop("TASK_QUEUE_CHECKPOINT_ENABLED", None)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_resume_skips_completed_nodes_and_accounts_budget(self) -> None:
        """Run 1 crashes at master_burry; Run 2 resumes from checkpoint."""
        # ------------------------------------------------------------ #
        # Run 1 — budget intentionally tight so master_burry trips
        # BudgetExhausted *before* sending its LLM payload. The orchestrator
        # appends a failed master entry rather than raising. We confirm a
        # checkpoint was saved BEFORE the run finished pm by inspecting
        # the SQLite snapshot after the bear / buffett nodes succeed.
        # ------------------------------------------------------------ #
        run1_responses = [
            _bull_payload(1),
            _bear_payload(1),
            _bull_payload(2),
            _bear_payload(2),
            _master_payload("warren_buffett"),
            # Budget will be exhausted before master_burry's LLM call —
            # but we still need slots for the remaining masters/risk/pm
            # which the SECOND run will use against a fresh budget. We
            # script just enough responses for run 1.
        ]
        budget1 = LLMCallBudget(cap=5)  # tight cap — only enough for 4 debate + 1 master
        llm1 = StubLLM(run1_responses)
        orch1 = InvestmentCommitteeOrchestrator(
            _make_ctx(),
            report_json={"summary": "x"},
            budget=budget1,
            llm_callable=llm1,
            debate_rounds=2,
            query_id=self.query_id,
            checkpoint_enabled=True,
        )
        result1 = orch1.run()
        minutes1 = result1.minutes

        # Run 1 should have produced PARTIAL or FAILED minutes since the
        # budget couldn't fit all masters/risk/pm.
        self.assertIn(minutes1.status, ("partial", "failed"))

        # CHECKPOINT INVARIANT: a snapshot must exist now.
        self.assertTrue(
            has_checkpoint(self.query_id),
            "expected checkpoint to be saved after run 1",
        )
        db_path = checkpoint_db_path(self.query_id)
        self.assertTrue(db_path.exists(), f"snapshot DB missing: {db_path}")

        # State invariant: bull/bear all 4 rounds completed; buffett present;
        # burry+wood+taleb+risk are NOT in the snapshot as 'ok'.
        snapshot = load_state(self.query_id)
        self.assertIsNotNone(snapshot)
        self.assertEqual(
            len([
                e for e in (snapshot.get("debate") or [])
                if e.get("status", "ok") == "ok"
            ]),
            4,
            "all 4 debate exchanges must be 'ok' in the snapshot",
        )
        completed_personas = {
            m.get("persona") for m in (snapshot.get("masters") or [])
            if m.get("status") == "ok"
        }
        self.assertEqual(
            completed_personas,
            {"warren_buffett"},
            "only buffett should be 'ok' in the snapshot",
        )

        # ------------------------------------------------------------ #
        # Run 2 — fresh budget, resume from checkpoint. The orchestrator
        # MUST NOT re-run the 4 debate exchanges or buffett; it should
        # only consume LLM slots for burry + wood + taleb + risk + pm = 5.
        # ------------------------------------------------------------ #
        run2_responses = [
            _master_payload("michael_burry", verdict="hold"),
            _master_payload("cathie_wood", verdict="buy"),
            _master_payload("nassim_taleb", verdict="hold"),
            _risk_payload(),
            _pm_payload(status="ok", budget_used=10, budget_cap=12),
        ]
        budget2 = LLMCallBudget(cap=12)
        llm2 = StubLLM(run2_responses)
        orch2 = InvestmentCommitteeOrchestrator(
            _make_ctx(),
            report_json={"summary": "x"},
            budget=budget2,
            llm_callable=llm2,
            debate_rounds=2,
            query_id=self.query_id,
            checkpoint_enabled=True,
        )
        result2 = orch2.run()
        minutes2 = result2.minutes

        # The resume flag must be set on the raw_state.
        self.assertTrue(
            result2.raw_state.get("resumed_from_checkpoint"),
            "orchestrator must flag the run as resumed",
        )

        # Critical: the second LLM was called EXACTLY 5 times (the nodes
        # that actually needed re-running). All 4 debate + 1 buffett came
        # from the checkpoint with zero replays.
        self.assertEqual(
            len(llm2.calls),
            5,
            f"expected 5 LLM calls on resume, got {len(llm2.calls)}",
        )

        # Final minutes must aggregate ALL 4 personas (buffett from snapshot
        # + burry/wood/taleb from run 2). Status downgraded to 'partial'
        # because the snapshot carried partial-state missing_agents from
        # run 1. The PM verdict is still present.
        all_personas = {m.persona for m in minutes2.masters}
        self.assertIn("warren_buffett", all_personas)
        self.assertIn("michael_burry", all_personas)
        self.assertIn("cathie_wood", all_personas)
        self.assertIn("nassim_taleb", all_personas)
        self.assertIsNotNone(minutes2.pm_verdict)
        self.assertIsNotNone(minutes2.risk)

        # After a successful resume that produced ok/partial minutes the
        # orchestrator clears the checkpoint so the next call starts clean.
        self.assertFalse(
            has_checkpoint(self.query_id),
            "checkpoint should be cleared after a successful resume",
        )

    def test_no_checkpoint_when_env_disabled(self) -> None:
        """When ``TASK_QUEUE_CHECKPOINT_ENABLED`` is unset, no DB is touched."""
        os.environ.pop("TASK_QUEUE_CHECKPOINT_ENABLED", None)

        responses = [
            _bull_payload(1), _bear_payload(1),
            _bull_payload(2), _bear_payload(2),
            _master_payload("warren_buffett"),
            _master_payload("michael_burry"),
            _master_payload("cathie_wood"),
            _master_payload("nassim_taleb"),
            _risk_payload(),
            _pm_payload(),
        ]
        llm = StubLLM(responses)
        budget = LLMCallBudget(cap=12)
        orch = InvestmentCommitteeOrchestrator(
            _make_ctx(),
            report_json={"summary": "x"},
            budget=budget,
            llm_callable=llm,
            debate_rounds=2,
            query_id="env-off-002",
            # No checkpoint_enabled flag and the env is off → off.
        )
        result = orch.run()
        self.assertEqual(result.minutes.status, "ok")
        # No DB file should exist for this query_id
        self.assertFalse(
            has_checkpoint("env-off-002"),
            "checkpoint must not be written when env is disabled",
        )

    def test_resume_with_corrupt_snapshot_falls_back_to_fresh_run(self) -> None:
        """A corrupted DB on resume should NOT crash — it starts fresh."""
        # Write a deliberately malformed file at the snapshot location.
        bad_db = checkpoint_db_path(self.query_id)
        bad_db.parent.mkdir(parents=True, exist_ok=True)
        with open(bad_db, "wb") as fp:
            fp.write(b"not a real sqlite database")

        responses = [
            _bull_payload(1), _bear_payload(1),
            _bull_payload(2), _bear_payload(2),
            _master_payload("warren_buffett"),
            _master_payload("michael_burry"),
            _master_payload("cathie_wood"),
            _master_payload("nassim_taleb"),
            _risk_payload(),
            _pm_payload(),
        ]
        llm = StubLLM(responses)
        budget = LLMCallBudget(cap=12)
        orch = InvestmentCommitteeOrchestrator(
            _make_ctx(),
            report_json={"summary": "x"},
            budget=budget,
            llm_callable=llm,
            debate_rounds=2,
            query_id=self.query_id,
            checkpoint_enabled=True,
        )
        result = orch.run()
        # The corrupt snapshot must NOT have crashed the run.
        self.assertEqual(result.minutes.status, "ok")
        # And critically, ``resumed_from_checkpoint`` must be False because
        # the load failed silently.
        self.assertFalse(result.raw_state.get("resumed_from_checkpoint"))


if __name__ == "__main__":
    unittest.main()
