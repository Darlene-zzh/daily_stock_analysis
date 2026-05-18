# Sprint 4 — P9 Delivery Report

**Branch:** `feat/committee-infra` (off `feat/quant-signal`)
**Worktree:** `/Users/zhen/daily_stock_analysis/.claude/worktrees/agent-ae808e38ff2d4267d`
**Date:** 2026-05-18
**Commits (no push):**
- `7ccadc2` feat(committee-infra): Sprint 4-1 SQLite checkpoint resume
- `19ad102` feat(committee-infra): Sprint 4-2 structured RiskAssessment standalone path
- `0dd0a38` feat(committee-infra): Sprint 4-3 renderers + Web StructuredRiskCallout + tests
- `ecdd268` docs(committee-infra): Sprint 4-4 CHANGELOG + .env.example + full-guide.md

> Closes the 4-sprint professional-upgrade chain
> (Sprint 1A committee → 1B Web → 2 decision journal → 3 quant signal → **4 infra polish**).

---

## 1. 改了什么 / What Changed

### A. LangGraph Checkpoint Resume (opt-in via env)

- **New module `src/agent/committee_checkpointer.py`** — per-query SQLite snapshot store keyed on `query_id`. Soft-imports `langgraph.checkpoint.sqlite.SqliteSaver`; falls back to plain `sqlite3` when the package is missing. Public helpers: `save_state`, `load_state`, `has_checkpoint`, `clear_checkpoint`, `checkpoint_enabled`, `checkpoint_db_path`.
- **`src/agent/orchestrator_committee.py`** — accepts `query_id: Optional[str]` and `checkpoint_enabled: Optional[bool]` constructor args. After every node (bull / bear per round, each master, risk, pm) the orchestrator persists a state snapshot. On the next run with the same `query_id`, `_restore_from_checkpoint` replays completed nodes back into `CommitteeState`; `_has_completed_*` helpers skip slots that already have `status='ok'`. Successful runs (`status ∈ {ok, partial}`) clear the snapshot.
- **`src/services/analysis_service.py`** — passes `query_id` to the orchestrator (with a `**_kwargs + TypeError fallback` shim so existing Sprint 1A test stubs still pass).
- **Dependency:** `requirements.txt` gets `langgraph-checkpoint-sqlite>=3.0.1` (already pinned `langgraph==0.4.8` in Sprint 1A). Both are soft-imported.
- **Env switch:** `TASK_QUEUE_CHECKPOINT_ENABLED=false` (default). Optional `COMMITTEE_CHECKPOINT_DIR=data/committee_checkpoints` override.
- **Filesystem:** new `data/committee_checkpoints/.gitkeep`; `.gitignore` updated with the standard whitelist/`.db` pattern that Sprints 2 + 3 use.

### B. Structured Risk Assessment standalone path (opt-in via API param)

- **`src/schemas/risk_schema.py`** — promotes `RiskAssessment` out of `committee_schema.py` into its own module. Adds four Sprint 4 fields, all default-None for byte-stable payloads:
  - `tail_risk_score: 0..10` — heuristic combining LLM `risk_score`, count of high-severity flags, and annualised volatility.
  - `var_estimate_5pct` — z=1.645 × daily_vol parametric VaR as positive fractional loss.
  - `volatility_annualised` — sqrt(252) × stdev of daily close-to-close returns.
  - `rationale` — optional 1-2 sentence narrative.
- **`src/schemas/committee_schema.py`** — re-exports `RiskAssessment` from the new module so every `from src.schemas.committee_schema import RiskAssessment` consumer keeps working unchanged.
- **`src/agent/agents/risk_agent.py`** — adds `RiskAgent.build_structured_assessment(raw_llm=..., recent_closes=...)` static helper. Existing committee `_risk_node` path is untouched; the new method is independently callable for the default analysis pipeline.
- **API plumbing:** new `enable_structured_risk: bool = False` field on `AnalyzeRequest`; forwarded through the sync + async endpoints, `AnalysisTaskQueue.submit_tasks_batch / _execute_task`, into `AnalysisService.analyze_stock`. When set, the new private `_invoke_structured_risk` helper builds the payload from `result.risk_warning` + price history and attaches it to `response['risk_assessment']` **and** `result.dashboard['risk_assessment']` so the existing renderers can surface it. Failures are caught at the call site and never kill the response.
- **Both renderers updated** (the long-standing parallel-update invariant from `repo-dual-renderers.md` memory):
  - `src/notification.py` — new `_render_structured_risk` helper + dashboard hook.
  - `src/services/history_service.py` — same helper, byte-identical output.
- **Web component** — `apps/dsa-web/src/components/risk/StructuredRiskCallout.tsx` mirrors the markdown layout (severity badge, position %, tail-risk, VaR, volatility, red flags, rationale). Renders `null` when no payload is attached. Wired into `ReportSummary.tsx`. Type `StructuredRiskAssessment` added; `AnalysisReport.riskAssessment` + `AnalysisRequest.enableStructuredRisk` extended.

### C. Docs & Configuration

- **`docs/CHANGELOG.md`** `[Unreleased]` flat entries describing both feature surfaces + tests.
- **`.env.example`** placeholder block for `TASK_QUEUE_CHECKPOINT_ENABLED` / `COMMITTEE_CHECKPOINT_DIR` / `STRUCTURED_RISK_ENABLED` (all commented-out booleans; **no real secrets**).
- **`docs/full-guide.md`** — two new subsections ("Checkpoint Resume" and "Structured Risk Assessment") with failure-path tables and rollback steps, in the same style as the Sprint 3 "Quant Context" section.

### D. Tests

- **`tests/test_committee_checkpoint_resume.py`** (3 cases) — crash mid-graph, snapshot persisted, resume only calls LLM for the 5 remaining nodes; env-off path never writes a DB; corrupt DB falls back to fresh run.
- **`tests/test_risk_agent_structured.py`** (9 cases) — VaR matches the z × daily_vol formula, tail-risk score reacts to high flag count, hard severity zeros out position, none-severity > soft-severity, legacy fields stay populated.
- **`tests/test_risk_renderer_independent.py`** (6 cases) — `notification` vs `history` renderer outputs byte-identical for ZH + EN, hard payload shows veto, sparse payload hides optional metric rows, empty payload renders `[]`.
- **`apps/dsa-web/src/components/risk/__tests__/StructuredRiskCallout.test.tsx`** (5 cases) — null prop renders nothing, soft tier renders severity + position 12% + tail 6.50/10 + VaR 3.40%, hard payload shows `veto=true`, optional metric rows hide when null.

---

## 2. 为什么这么改 / Why

- **Checkpoint resume** addresses the user's specific reality: a mixed Anspire / AIHubMix / Gemini / DeepSeek LLM pool with rate-limit hiccups (per memory `repo-gemini-free-tier-rpm.md`). Today a half-finished committee run restarts from scratch, costing 8–10 extra LLM calls when only 1 node actually failed. Sprint 4 lets the next call with the same task_id pick up exactly where it left off.
- **Structured Risk standalone** was already documented as the spec's "even in default reports" goal. We **don't replace** `RiskAgent` (the committee still uses it identically); we **layer** structured fields on top, callable from the non-committee path so users who don't enable the committee still get a risk callout.
- **Both surfaces are opt-in** — Sprint 4 promises zero default-behavior change, and that's exactly what's delivered.

---

## 3. 验证情况 / Verification

### DONE matrix — verbatim outputs

**(1) `pip install -r requirements.txt` + import smoke**

```
imports ok, SQLITE_SAVER_AVAILABLE= True
```

**(2) `python -m py_compile` on every new/changed .py**

```
ALL py_compile OK
```

**(3) New Sprint 4 tests — `pytest -m "not network" tests/test_committee_checkpoint_resume.py tests/test_risk_agent_structured.py tests/test_risk_renderer_independent.py -v`**

```
tests/test_committee_checkpoint_resume.py::TestCommitteeCheckpointResume::test_no_checkpoint_when_env_disabled PASSED
tests/test_committee_checkpoint_resume.py::TestCommitteeCheckpointResume::test_resume_skips_completed_nodes_and_accounts_budget PASSED
tests/test_committee_checkpoint_resume.py::TestCommitteeCheckpointResume::test_resume_with_corrupt_snapshot_falls_back_to_fresh_run PASSED
tests/test_risk_agent_structured.py::TestStructuredRiskAssessment::test_empty_inputs_produce_safe_defaults PASSED
tests/test_risk_agent_structured.py::TestStructuredRiskAssessment::test_hard_severity_vetoes_position_to_zero PASSED
tests/test_risk_agent_structured.py::TestStructuredRiskAssessment::test_legacy_fields_remain_populated_for_committee_consumers PASSED
tests/test_risk_agent_structured.py::TestStructuredRiskAssessment::test_none_severity_starts_higher_than_soft PASSED
tests/test_risk_agent_structured.py::TestStructuredRiskAssessment::test_soft_severity_caps_position_below_default PASSED
tests/test_risk_agent_structured.py::TestStructuredRiskAssessment::test_tail_risk_score_in_range_and_responds_to_high_flags PASSED
tests/test_risk_agent_structured.py::TestStructuredRiskAssessment::test_var_and_volatility_computed_from_price_series PASSED
tests/test_risk_agent_structured.py::TestStructuredRiskAssessment::test_var_none_when_no_prices_supplied PASSED
tests/test_risk_agent_structured.py::TestStructuredRiskAssessment::test_var_none_with_single_price PASSED
tests/test_risk_renderer_independent.py::TestRendererParity::test_en_renderers_byte_identical_for_full_payload PASSED
tests/test_risk_renderer_independent.py::TestRendererParity::test_hard_severity_renders_veto_in_both PASSED
tests/test_risk_renderer_independent.py::TestRendererParity::test_missing_renderers_dont_emit_section_heading_for_empty PASSED
tests/test_risk_renderer_independent.py::TestRendererParity::test_none_payload_renders_empty_in_both PASSED
tests/test_risk_renderer_independent.py::TestRendererParity::test_sparse_payload_omits_optional_metrics_in_both PASSED
tests/test_risk_renderer_independent.py::TestRendererParity::test_zh_renderers_byte_identical_for_full_payload PASSED

============================== 18 passed in 2.26s ==============================
```

**(4) Sprint 1A regression — `pytest -m "not network" tests/test_committee_graph.py tests/test_committee_schema.py tests/test_master_personas.py`**

```
============================== 65 passed in 1.91s ==============================
```

**Full committee suite (1A schema + graph + personas + notification + history + analysis_service + Sprint 4 trio) — 108 passed.**

**(5) `./scripts/ci_gate.sh syntax` equivalent + flake8**

```
syntax OK
0
```
(`flake8 . --select=E9,F63,F7,F82 --count --show-source --statistics` produced count `0`.)

**(6) Web — `cd apps/dsa-web && npm run lint && npx vitest run src/components/risk/__tests__/ && npm run build`**

```
lint: clean (no eslint output)
vitest: Test Files 1 passed (1) · Tests 5 passed (5) · Duration 786ms
build: ✓ 3188 modules transformed · built in 5.94s
```

**(7) Stub-LLM smoke for checkpoint resume** — covered by `test_resume_skips_completed_nodes_and_accounts_budget`:
- Run 1 with `cap=5` budget exhausts mid-graph after `buffett`; `has_checkpoint(query_id)` returns True; snapshot has 4 OK debate exchanges + `{warren_buffett}` as the only completed persona.
- Run 2 with fresh `cap=12` budget reads the snapshot; only **5** LLM calls are made (`burry / wood / taleb / risk / pm`); `result.raw_state['resumed_from_checkpoint'] == True`; final `minutes.masters` contains all 4 personas; checkpoint is cleared post-run.

**(8) Stub-LLM smoke for structured risk** — covered by `test_var_and_volatility_computed_from_price_series` + `test_legacy_fields_remain_populated_for_committee_consumers`:
- 12-price walk produces volatility ≈ 0.358, VaR = `round(1.645 × daily_vol, 6) == 0.037077`; assertion re-derives the formula inside the test rather than trusting the implementation.
- Backward-compat: round-trip `RiskAssessment(**out.model_dump())` preserves severity + tail_risk_score; legacy `red_flags` / `veto` / `status` keep their Sprint 1A semantics.

---

## 4. 未验证项 / Not Verified

- **End-to-end on a real LLM** — Sprint 4 stays on stub-LLM tests (per the prompt's DONE matrix). The opt-in env flag means production behavior is byte-identical to Sprint 3 unless the user flips the switch.
- **Docker build smoke** — not executed locally; the dependency added is a small pure-Python sqlite saver pinned in `requirements.txt`, so `docker-build` job should pass CI cleanly. Will be confirmed by the CI gate on PR open.
- **Sprint 4 doesn't touch desktop assets** — `apps/dsa-desktop/` was deliberately out of scope (per WHERE forbidden list) and the Web `npm run build` produces the same bundle layout the desktop builder consumes.
- **Pre-existing baseline failures (not introduced by Sprint 4):** the wider `pytest -m "not network"` sweep shows 14 unrelated failures (`test_analysis_api_contract.py` × 8, `test_analysis_history.py` × 2, `test_notification.py` × 1, `test_search_news_freshness.py` × 3). I verified these same 14 (same names) fail on the unmodified `feat/quant-signal` baseline by running the suite from the sibling worktree `/Users/zhen/daily_stock_analysis/.claude/worktrees/agent-adcd75cec3bd87302`. Root causes are pre-existing: (a) `test_analysis_api_contract.py` stubs expect the older `submit_tasks_batch` signature without ANY Sprint 1A-3 kwargs; (b) the TZ tests are environmental (DST window). Sprint 4 leaves these counts unchanged.

---

## 5. 风险点 / Risks

| Risk | Mitigation |
|------|-----------|
| Stale checkpoint DB after a crash with no resume | `_clear_checkpoint(query_id)` is called on successful `ok / partial` runs; corrupt DB is silently treated as "no checkpoint" so user can never get stuck. Runtime size bounded by `query_id` count × tiny JSON blob per row. |
| Pre-existing test stubs in `test_analysis_service_committee.py` mock `_invoke_committee` with the older signature | Solved with `**_kwargs` on the production method **and** a TypeError-fallback at the call site. Both the production code path and the test path call the same method. |
| Two renderers drift again | `test_risk_renderer_independent.py` enforces byte-identical output (`self.assertEqual(zh_notif, zh_history)`) for 4 different payload shapes. Drift fails the test loud. |
| Soft-import of `langgraph-checkpoint-sqlite` | If the dep ever gets ripped out, `committee_checkpointer.py` falls back to plain `sqlite3` and still works. `SQLITE_SAVER_AVAILABLE` flag exposed for observability. |

---

## 6. 回滚方式 / Rollback

- **Soft rollback (kill features at runtime without redeploy):** set `TASK_QUEUE_CHECKPOINT_ENABLED=false` (or unset) and stop passing `enable_structured_risk=true`. Both default to off. Web component renders `null` when payload is absent.
- **Hard rollback (remove code):**

  ```bash
  git revert ecdd268 0dd0a38 19ad102 7ccadc2  # in reverse order
  rm -rf data/committee_checkpoints/         # optional cleanup
  ```

  Each commit is scoped (checkpoint backend / structured-risk path / renderers+Web+tests / docs) so partial reverts are also safe.
- **Drop the dep:** if `langgraph-checkpoint-sqlite>=3.0.1` causes a CI conflict, remove the line from `requirements.txt`; `committee_checkpointer.py` works without it via the `sqlite3` fallback.

---

## Sprint Cascade Summary (4-sprint chain — final state)

```
feat/main → feat/investment-committee (Sprint 1A)
         → feat/committee-web         (Sprint 1B)
         → feat/decision-journal      (Sprint 2)
         → feat/quant-signal          (Sprint 3)
         → feat/committee-infra       (Sprint 4)  ← THIS
```

All 4 sprints sit on `feat/committee-infra` HEAD, ready for the user's overnight review.

---

**Confidence statement:** Under the evidence available in this run, the full DONE matrix passes. Both Sprint 4 features (checkpoint resume + structured risk) are **opt-in** with **zero default-link side effects** — the byte-stable Sprint 1A-3 behavior is preserved when both switches stay off. No tag, no push, no destructive git operation performed; the user holds full release authority.
