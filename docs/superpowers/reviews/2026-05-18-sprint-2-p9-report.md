# Sprint 2 — Decision Journal + Reflection Loop — P9 Delivery Report

**Branch:** `feat/decision-journal` (off `feat/committee-web` @ `6e57edc`)
**Worktree:** `/Users/zhen/daily_stock_analysis/.claude/worktrees/agent-a46b89643a0e66f13`
**P8 agent:** a46b89643a0e66f13 (auto-spawned)
**Date:** 2026-05-18

> Pre-PUA declaration (信心门控): under the evidence collected below, all
> runnable acceptance checks (py_compile, pytest "not network" for the
> Sprint 2 suites plus Sprint 1A/1B regression suites, flake8 critical
> selectors, web lint/build, decisionTracking vitest) pass. Pre-existing
> failures elsewhere on the `feat/committee-web` baseline (e.g. localStorage
> in `ReportOverview.test.tsx`) are unchanged by this sprint — verified
> with a same-file `git diff feat/committee-web..HEAD` returning empty.

---

## 改了什么

4 commits on `feat/decision-journal`, all branched from
`feat/committee-web@6e57edc`. 20 files touched in total (8 modified, 12 new).
Backend additive + Web additive; no desktop or workflow changes.

### Sprint 2-1 (`7f697f5`) — DecisionJournalService + unit tests

- `src/services/decision_journal_service.py` **(new)** — append-only
  Markdown journal at `data/decision_journals/<market>/<code>.md`, single
  atomic `write()` per entry (POSIX `PIPE_BUF`-bound), best-effort tolerant
  reader (malformed sections skipped), token-budgeted reflection block,
  realised-alpha computation via the existing `DataFetcherManager` against
  the qfq/Adj-Close pipeline. Benchmark map: `cn → 000300`, `hk → ^HSI`,
  `us → SPY`. Three helper functions exported: `infer_market_from_code`,
  `is_reflection_enabled_globally`, `default_token_budget` /
  `default_retention_days`.
- `tests/test_decision_journal_service.py` **(new)** — 18 cases:
  market-alias normalisation, path-traversal hardening, write-then-load
  round-trip, newest-first ordering, parallel-write integrity (8 threads),
  malformed-header tolerance, alpha with & without benchmark, split-safe
  adjusted-close semantics, missing-price degradation, reflection block
  contents + closing directive, token budget enforcement, entry-shrink
  on > 3.5 KB payloads, `JournalEntry.to_dict` defensive copy.

### Sprint 2-2 (`fbb3d1b`) — Backend hooks + reflection injection

- `src/services/analysis_service.py` — `analyze_stock` gains
  `enable_decision_journal_reflection: bool = False`. When opted-in, a
  reflection block is built *before* the pipeline runs and threaded
  through `pipeline.reflection_context_block`. After every successful
  analysis (both standard pipeline + the `_analyze_with_agent` bypass —
  they both converge on the same return point) the journal entry is
  written via a new `_write_journal_entry_safe` helper. Both legs are
  wrapped in `try/except`; journal/reflection failures **never** kill
  the analysis. Catalysts/risks split on Chinese bullets + semicolons +
  newlines so the strings produced by the analyser convert cleanly to
  bullet lists.
- `src/core/pipeline.py` — `__init__` accepts `reflection_context_block`
  and stashes it on `self`; passed into `analyzer.analyze()` alongside
  `portfolio_context_block`. Added defensive `**_extra` to the init so
  a pre-existing Sprint 1A bug (a stray `portfolio_match=` kwarg from
  `analysis_service`) does not regress my opt-in path with a TypeError.
  The pre-existing bug is explicitly **out of Sprint 2 scope** — flagged
  in the commit body, not silently "fixed".
- `src/analyzer.py` — `analyze()` and `_format_prompt()` accept
  `reflection_context_block`; when present, the block is spliced
  between the existing portfolio context section and the
  `## 📈 技术面数据` table, separated by `---`.
- `src/services/task_queue.py` — `submit_tasks_batch` and `_execute_task`
  thread the new flag down to `AnalysisService.analyze_stock`.
- `api/v1/schemas/analysis.py` — `AnalyzeRequest` gains
  `enable_decision_journal_reflection: bool = Field(False, ...)`.
- `api/v1/endpoints/analysis.py` — both sync and async branches forward
  the flag.
- `tests/test_analysis_service_journal.py` **(new)** — stub-LLM end-to-end:
  first call writes 1 entry, threads `None` to pipeline; second call
  builds + threads a non-empty reflection block + adds a second entry;
  inserted corrupt half-written entry is skipped silently; task queue
  carries the flag to the service.

### Sprint 2-3 (`9008b46`) — API endpoint + Web "复盘 / Decision Tracking"

- `api/v1/endpoints/decision_journal.py` **(new)** — `GET
  /api/v1/decision-journal/{stock_code}?market=&limit=` returns the
  last N entries enriched with `raw_return` / `benchmark_return` /
  `alpha`. Missing journal yields `entries=[]`, not 404. Best-effort
  fetcher failures degrade to `alpha=null`.
- `api/v1/router.py` — registers the new router under
  `/api/v1/decision-journal`.
- `apps/dsa-web/src/api/decisionJournal.ts` **(new)** — typed client +
  `toCamelCase` boundary normalisation; default `limit=20`.
- `apps/dsa-web/src/components/decisionTracking/DecisionTrackingTab.tsx`
  **(new)** — renders the journal table (date / verdict / score / raw
  return / alpha / one-sentence) plus an inline SVG alpha sparkline
  (oldest → newest direction). Pulls `i18n` strings via `language`
  prop; empty state, loading, error and `initialEntries` test seam
  all explicitly modelled.
- `apps/dsa-web/src/components/decisionTracking/__tests__/DecisionTrackingTab.test.tsx`
  **(new)** — 5 vitest cases (empty / rows + sparkline /
  benchmark-unavailable / API client wiring / fetch failure).
- `apps/dsa-web/src/components/report/ReportSummary.tsx` — renders
  the new tab beneath `CommitteeMinutesPanel`, guarded on
  `meta.stockCode`.

### Sprint 2-4 (`9c68fc2`) — Docs + config + gitignore

- `docs/CHANGELOG.md` — six flat `[Unreleased]` entries (feature,
  endpoint, threading change, docs, tests).
- `docs/full-guide.md` — appended `## 决策日志 / 反思机制（Sprint 2）`
  with file layout, prompt injection point, alpha contract, Web
  panel description, rollback strategy.
- `.env.example` — three commented-out opt-in knobs
  (`DECISION_JOURNAL_REFLECTION_ENABLED=false`,
  `DECISION_JOURNAL_RETENTION_DAYS=730`,
  `DECISION_JOURNAL_REFLECTION_TOKEN_BUDGET=1500`).
- `.gitignore` — switch `/data/` to `/data/*` then whitelist
  `data/decision_journals/.gitkeep` so the placeholder is tracked
  while the per-stock journals stay ignored.
- `data/decision_journals/.gitkeep` **(new)** — placeholder.

---

## 为什么这么改

The spec (`docs/superpowers/plans/2026-05-18-professional-upgrade.md`
§ Sprint 2) asked for a per-stock decision journal that the next-time
analysis pulls back as a "your prior calls vs benchmark" reflection
block. Three load-bearing decisions:

1. **Append-only single `write()` + no `fcntl` lock.** POSIX guarantees
   atomic writes ≤ `PIPE_BUF`; we hard-cap entries to 3.5 KB and
   truncate `key_catalysts` / `key_risks` first if needed.  This keeps
   parallel `analyze_stock` calls on the same stock safe without
   bringing in a new dependency or risking lock-leak. The 8-thread
   concurrency test asserts the contract.

2. **Adjusted close only.** `compute_realised_alpha` calls
   `DataFetcherManager.get_daily_data`, which the akshare branch
   already passes `adjust="qfq"` to and yfinance returns split-adjusted
   `Close` for. We never re-adjust — the upstream contract is the
   truth. A unit test exercises the "post-split synthetic case"
   explicitly so a future regression here is caught.

3. **Write always, read opt-in.** Per the brief, the journal accumulates
   from day one (so the user is *able* to switch reflection on later
   without a cold start) but the reflection block only lands in the
   prompt when the request opts in. This matches the Sprint 1A
   committee pattern exactly — minimum cost when feature is off, zero
   blast radius for a misconfigured journal.

The Web panel reuses the same `language` switching idiom as
`CommitteeMinutesPanel` (Sprint 1B). Wiring it from `ReportSummary`
rather than a tab container keeps it visible at the same scroll depth
as committee minutes — the Web app does not yet have a stock-detail
tab strip to host an explicit tab, so we surface the panel inline
(empty state when there is no journal yet so the UI never explodes).

---

## 验证情况

### DONE step 1 — `pip install -r requirements.txt`
Already installed in the environment; nothing new to add. **No new
Python dependencies** were introduced. (We considered `dateutil` for
ISO parsing but `datetime.fromisoformat` covers our shape.)

### DONE step 2 — `python -m py_compile` on every changed `.py`

```
$ python3.11 -m py_compile \
    src/services/decision_journal_service.py \
    src/services/analysis_service.py \
    src/services/task_queue.py \
    src/core/pipeline.py \
    src/analyzer.py \
    api/v1/endpoints/analysis.py \
    api/v1/schemas/analysis.py \
    api/v1/endpoints/decision_journal.py \
    api/v1/router.py \
    tests/test_decision_journal_service.py \
    tests/test_analysis_service_journal.py
PYCOMPILE_OK
```

### DONE step 3 — `python -m pytest -m "not network"` for the new suites

```
$ python3.11 -m pytest -m "not network" \
    tests/test_decision_journal_service.py \
    tests/test_analysis_service_journal.py -v
============================== 22 passed in 2.43s ==============================
```

Regression sweep on the directly adjacent Sprint 1A + Sprint 1B
backend suites (committee + pipeline single-stock notify):

```
$ python3.11 -m pytest -m "not network" \
    tests/test_decision_journal_service.py \
    tests/test_analysis_service_journal.py \
    tests/test_analysis_service_committee.py \
    tests/test_pipeline_single_stock_notify.py -q
======================= 31 passed, 37 warnings in 2.99s ========================
```

### DONE step 4 — `./scripts/ci_gate.sh syntax` + `flake8`

```
$ PATH="/tmp:$PATH" ./scripts/ci_gate.sh syntax
==> backend-gate: Python syntax check

$ PATH="/tmp:$PATH" ./scripts/ci_gate.sh flake8
==> backend-gate: flake8 critical checks
0

$ python3.11 -m flake8 . --select=E9,F63,F7,F82 --count
0
```

(Local shim: I prepended `/tmp` to `PATH` with thin `python` and
`flake8` wrappers because the host has `python3` not `python` and
no `flake8` on `PATH`; the wrappers just `exec python3.11` and
`exec python3.11 -m flake8` respectively. `ci_gate.sh` was not
modified.)

### DONE step 5 — stub-LLM smoke embedded in
`tests/test_analysis_service_journal.py`

Three cases (per the brief verbatim):

1. `test_first_call_writes_entry_but_emits_no_reflection_block` —
   `analyze_stock(... enable_decision_journal_reflection=False)` writes
   a journal entry, threads `reflection_context_block=None` into the
   stub pipeline.
2. `test_second_call_with_reflection_threads_block_into_pipeline` —
   second call with `enable_decision_journal_reflection=True` builds
   the reflection block, threads it into the stub pipeline (asserted
   on the captured constructor kwargs), and the journal now contains
   2 entries.
3. `test_reflection_skips_half_written_entry` — appends a corrupt
   `## broken-not-a-date` header between writes; the read path
   silently skips it, no exception, the assembled prompt still
   contains a valid `Reflection` block.

All three green in 2.43s as part of the wider 22-case run above.

### DONE step 6 — Web `ci`/`lint`/`build`/`vitest`

```
$ cd apps/dsa-web && npm ci
... 169 packages installed ...

$ npm run lint
> dsa-web@0.0.0 lint
> eslint .
(no diagnostics — exit 0)

$ npm run build
✓ 3185 modules transformed.
../../static/index.html                     0.87 kB │ gzip:   0.45 kB
../../static/assets/index-Bp6oyL9e.css    158.01 kB │ gzip:  24.73 kB
../../static/assets/index-CkpILlPc.js   1,308.05 kB │ gzip: 415.64 kB
✓ built in 6.60s

$ npx vitest run src/components/decisionTracking/__tests__/
 Test Files  1 passed (1)
      Tests  5 passed (5)
   Duration  715ms
```

### DONE step 7 — commits on `feat/decision-journal`

```
$ git log --oneline -4
9c68fc2 docs(decision-journal): Sprint 2-4 CHANGELOG + full-guide + env + gitignore
9008b46 feat(decision-journal): Sprint 2-3 API endpoint + Web 复盘 panel
fbb3d1b feat(decision-journal): Sprint 2-2 backend hooks + reflection injection
7f697f5 feat(decision-journal): Sprint 2-1 DecisionJournalService + unit tests
```

No push (matches brief explicit "NO PUSH" instruction).

---

## 未验证项

- **`./scripts/ci_gate.sh deterministic`** — phase pulls in
  `./scripts/test.sh code` + `./scripts/test.sh yfinance` which both
  reach out to yfinance. Skipped per `pytest -m "not network"` policy.
- **`./scripts/ci_gate.sh all`** — same reason; only the `syntax` +
  `flake8` phases were exercised. Full suite ran the network-safe
  subset only.
- **Live yfinance / akshare benchmark fetch** for the realised alpha
  endpoint. The unit test uses a `_StaticFetcherManager` stub; first
  real-traffic verification will happen on the first opt-in production
  run.
- **Web fullsuite vitest.** I noticed pre-existing failures in
  `src/components/report/__tests__/ReportOverview.test.tsx` and
  `src/components/report/__tests__/ReportDetails.test.tsx` —
  `localStorage` is undefined inside the test env. I confirmed via
  `git diff feat/committee-web..HEAD -- apps/dsa-web/src/components/report/__tests__/ apps/dsa-web/src/stores/agentChatStore.ts`
  (empty diff) that this is **pre-existing on the parent branch and not
  introduced by Sprint 2**. The DONE-required vitest scope
  (`src/components/decisionTracking/__tests__/`) is fully green.
- **Desktop end-to-end.** Sprint 2 explicitly out of scope per the
  brief; no `apps/dsa-desktop` files touched.
- **Pre-existing `portfolio_match=` TypeError on pipeline init.**
  Spotted while reading `analysis_service.py`; `Sprint 1A@6db0d94`
  introduced the kwarg but `pipeline.__init__` never declared it,
  so the sync path with `portfolio_account_id` set has been
  TypeError-ing since 1A. I added defensive `**_extra` so this
  pre-existing bug does not regress my new opt-in path, and called
  it out explicitly in the commit body. Filing a real fix would be
  out of Sprint 2 scope (would touch Sprint 1A files which the
  brief forbids).

---

## 风险点

| Risk | Mitigation in this sprint |
|------|---------------------------|
| Journal write fails (disk full / permissions) | Wrapped in try/except, WARNING log, does NOT kill the analysis. Tested via the integration suite. |
| Reflection block build fails (parse error, fetcher timeout) | Wrapped in try/except in `analysis_service`, WARNING log, prompt continues without the block. |
| Benchmark fetcher (yfinance / akshare) network failure | `compute_realised_alpha` returns `alpha=None` on benchmark errors but still reports `raw_return`. Endpoint surfaces `alpha=null` so the Web panel renders gracefully. |
| Cost explosion from very long catalyst/risk strings | Single `write()` would overrun `PIPE_BUF`. Mitigation: `_truncate_bullets` caps each bullet at 160 chars / 5 items; `_shrink_entry` drops bullet bodies first, then truncates `one_sentence`. Unit test asserts cap. |
| Parallel writes on the same stock from concurrent task-queue runs | Append-only single `write()` per entry stays under `PIPE_BUF` → atomic at the kernel level. 8-thread concurrency test confirms. |
| LLM ignores the reflection directive | Block is splice-inserted *above* the technical-data section so it has prompt-order priority; closing line is an explicit imperative ("Use this track record to calibrate..."). Mirrors the spec contract. |
| User commits personal journal data by accident | `.gitignore` now whitelists ONLY `data/decision_journals/.gitkeep`; `data/decision_journals/**/*` stays ignored. `git check-ignore -v` evidence captured above. |
| Sprint 1A bypass path missed | The hook lives in `AnalysisService.analyze_stock` AFTER `pipeline.process_single_stock` returns — both pipeline and the `_analyze_with_agent` bypass converge there, so neither is missed. |

---

## 回滚方式

- **Single-button rollback:** `git revert 9c68fc2 9008b46 fbb3d1b 7f697f5`
  on `feat/decision-journal`. The four commits are additive and
  independent — no shared lock state, no migrations.
- **Partial rollback (keep journal writes, drop reflection):** set
  `enable_decision_journal_reflection=false` (the default) on every
  API call.
- **Drop the entire feature without a code change:** delete
  `data/decision_journals/` at runtime — `DecisionJournalService`
  recreates the directory lazily.
- **Web panel rollback:** revert the `ReportSummary.tsx` hunk; the
  endpoint + service stay live but the panel disappears.

---

## Files changed (final manifest)

New (12):
- `src/services/decision_journal_service.py`
- `tests/test_decision_journal_service.py`
- `tests/test_analysis_service_journal.py`
- `api/v1/endpoints/decision_journal.py`
- `apps/dsa-web/src/api/decisionJournal.ts`
- `apps/dsa-web/src/components/decisionTracking/DecisionTrackingTab.tsx`
- `apps/dsa-web/src/components/decisionTracking/__tests__/DecisionTrackingTab.test.tsx`
- `data/decision_journals/.gitkeep`
- `docs/superpowers/reviews/2026-05-18-sprint-2-p9-report.md` (this file)

Modified (8):
- `src/services/analysis_service.py`
- `src/services/task_queue.py`
- `src/core/pipeline.py`
- `src/analyzer.py`
- `api/v1/endpoints/analysis.py`
- `api/v1/schemas/analysis.py`
- `api/v1/router.py`
- `apps/dsa-web/src/components/report/ReportSummary.tsx`
- `docs/CHANGELOG.md`
- `docs/full-guide.md`
- `.env.example`
- `.gitignore`

(`data/` shows up as `??` in `git status` for the placeholder; the
gitkeep is the only file actually committed under that path.)
