# Phase 3 Execution Journal — Evidence-Grounded Renderers

**Window:** 2026-05-23 BST (single session, post-Phase-2-ship)
**Branch:** `feat/phase-3-renderers` (stacked on `feat/committee-timeout-and-bilingual`)
**Spec:** `docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md` Section C
**Plan:** `docs/superpowers/plans/2026-05-23-phase-3-evidence-renderers.md`
**Shipped:** PR #11 — https://github.com/Darlene-zzh/daily_stock_analysis/pull/11
**Author:** Claude Opus 4.7 (1M context), paired with user `zihanzhang641@gmail.com`

---

## Outcome

Phase 3 (Wikipedia-style footnote renderers + 🤖 代码兜底 badge + parity guard) shipped to PR #11 stacked on PR #10. 8 TDD tasks delivered as 8 atomic commits. Full-suite regression +28 tests vs Phase 2 baseline. **One critical guard installed**: a parity test that catches any future drift between `notification.py` and `history_service.py`.

---

## Timeline

### Pre-execution — Phase 3 plan written in parallel with Phase 2 smoke

Phase 3 plan was authored on 2026-05-23 morning while the Phase 2 smoke was running in the background (~67 min). This is the "parallel preparation" pattern — the smoke needed wall-clock time anyway, and Phase 3 is renderer-only (zero file-level conflict with Phase 2 in the analyzer/sanitizer surface). Plan was saved to `docs/superpowers/plans/2026-05-23-phase-3-evidence-renderers.md` and reviewed before execution.

### Branch creation

After PR #10 opened (Phase 1+2+hotfix), branched `feat/phase-3-renderers` directly from `feat/committee-timeout-and-bilingual` HEAD. This sets up the stacked-PR pattern: Phase 3 base will be #10's branch until #10 merges, then auto-retargets to main.

### Task 1 — `_render_evidence_footnotes` helper in notification.py

**Commit:** [47d1932](https://github.com/Darlene-zzh/daily_stock_analysis/commit/47d1932)

Added 5 pure helpers above `_render_action_plan_items`:
- `_SUPERSCRIPT_DIGITS` — `str.maketrans` for `0-9 → ⁰¹²³⁴⁵⁶⁷⁸⁹`
- `_to_superscript(n)` — int → Unicode superscript string
- `_resolve_fact(fact_id, fact_bundle)` — look up by id in `facts` + `candidates`
- `_format_fact_footnote(fact)` — formats `\`[id]\` <label> = <display> (<extra>)`
- `_render_evidence_footnotes(refs, fact_bundle)` — orchestrator: dedup refs preserving first-occurrence order, number 1..N, render block

5 tests covered: input order, dedup, missing-fact fallback, empty refs short-circuit, None bundle short-circuit.

### Task 2 — Mirror helpers to history_service.py

**Commit:** [8d23c59](https://github.com/Darlene-zzh/daily_stock_analysis/commit/8d23c59)

Inserted the EXACT same block of code above `_render_action_plan_items` in `src/services/history_service.py`. This is the intentional duplication that `[[repo-dual-renderers]]` describes. Added 2 parity-style tests: `notification` vs `history` byte-equal output, history version handles empty inputs.

### Task 3 — Extend `_render_action_plan_items` in notification.py

**Commit:** [5ed53cb](https://github.com/Darlene-zzh/daily_stock_analysis/commit/5ed53cb)

Changed signature to `(items: list, fact_bundle=None) -> list`. Inside the loop:
- Introduced `ref_to_num` dict + `_num_for(ref_id)` closure for stable 1..N numbering across all items
- `_pick_ref(refs, prefix, used)` picks the first unused ref whose `fact_id` starts with `prefix`
- Per-item slot mapping:
  - `**触发**：` ← first evidence_ref
  - `**技术面**：` ← next ref starting with `technical.`
  - `**基本面**：` ← next ref starting with `intel.`
  - `**量化**：` ← next ref starting with `quant.` OR `committee.` (fallback)
- Remaining refs still get numbered (so they appear in the footnote block) even without inline superscript
- Append `🤖 *代码兜底*` line when `provenance == "synthesized"`

6 tests: superscript attach, badge present, badge absent for LLM, no superscripts without bundle, no superscripts without refs, legacy positional-arg signature still works.

### Task 4 — Mirror extension to history_service.py

**Commit:** [eb8c1f1](https://github.com/Darlene-zzh/daily_stock_analysis/commit/eb8c1f1)

Verbatim mirror of Task 3 function. Same signature, same closures, same line emissions. Added docstring note pointing to `[[repo-dual-renderers]]` and the parity test (Task 7). 4 mirror tests passed.

### Task 5 — Wire `fact_bundle` into notification main loop

**Commit:** [3e2a7d6](https://github.com/Darlene-zzh/daily_stock_analysis/commit/3e2a7d6)

Modified `NotificationService.generate_dashboard_report` around the action_plan_items rendering. Changes:
1. Fetched `fact_bundle = dashboard.get("fact_bundle")` (dashboard was already in scope)
2. Passed it through: `_render_action_plan_items(action_plan_items, fact_bundle=fact_bundle)`
3. After the renderer returns, collected unique `evidence_refs` across items, called `_render_evidence_footnotes`, appended `---` + footnote lines + blank trailing line

Wrote integration test that builds an `AnalysisResult` with a 3-fact bundle + one item with 3 evidence_refs, calls `svc.generate_dashboard_report([result])`, asserts:
- `📋 持仓操作计划` appears in output (action plan section rendered)
- `**证据脚注**` appears later (footnote block emitted)
- Footnote index > action plan index (ordering correct)

Second test: drop `fact_bundle` from the result → footnote block must NOT appear (backward compat).

Ran all 256 notification-themed tests — all green, no regression.

### Task 6 — Mirror wiring to history_service main loop

**Commit:** [b0a84bb](https://github.com/Darlene-zzh/daily_stock_analysis/commit/b0a84bb)

Same wiring at `HistoryService._generate_single_stock_markdown`. The history service takes both `result: AnalysisResult` and `record` (ORM row); for the test I constructed a `SimpleNamespace(created_at=datetime(...), report_type="full")` to stub the record.

Ran all 89 history-themed tests — all green.

### Task 7 — Parity test (THE critical guard)

**Commit:** [169072c](https://github.com/Darlene-zzh/daily_stock_analysis/commit/169072c)

Created `tests/fixtures/nvda_dashboard_phase3.json` — 3-item action plan covering:
- Item 1: LLM provenance, 4 evidence_refs spanning 3 type prefixes (technical, committee, quant)
- Item 2: synthesized provenance, 2 refs (to trigger badge + reuse of `committee.pm_verdict`)
- Item 3: legacy item with no `evidence_refs` (no superscripts attached, but trigger line still renders)

Plus a 5-fact bundle (resistance, rsi_12, ma20, pm_verdict, qlib_rank) and 2 candidates.

Created `tests/test_renderer_parity_phase3.py` — 4 assertions:
1. `notif_render(items, bundle) == hist_render(items, bundle)` — byte-equal action plan section
2. `notif_footnotes(refs, bundle) == hist_footnotes(refs, bundle)` — byte-equal footnote section
3. 🤖 badge appears in BOTH outputs
4. Legacy item still renders trigger price in BOTH

All 4 passed first run — confirming the verbatim duplication in Tasks 1-6 was actually verbatim.

### Task 8 — Full-suite regression + CHANGELOG

**Commit:** [d8ce086](https://github.com/Darlene-zzh/daily_stock_analysis/commit/d8ce086)

- `python3.11 -m pytest -m "not network"` → **2528 passed**, 1 pre-existing failure (`test_max_steps_exceeded` per [[repo-agent-salvage-v2]]) → +28 net vs Phase 2 baseline of 2500
- `flake8 src/notification.py src/services/history_service.py --select=E9,F63,F7,F82` → 0 errors
- `py_compile` on both renderers → clean
- CHANGELOG anchor appended (flat format per CLAUDE.md)

### PR #11 opened (stacked)

User chose stacked PR strategy. Created via the same osxkeychain-token + curl pattern as PR #10 (token used exactly once, never echoed, body file deleted after). PR body explicitly notes the dependency on #10 and the merge sequence:
- Don't merge #11 directly to main — base is `feat/committee-timeout-and-bilingual`
- After #10 merges to main, GitHub will offer to retarget #11's base to main; or user can do it manually

---

## Lessons learned

### 1. Parity tests are cheap and catch real classes of bug
The parity test (`tests/test_renderer_parity_phase3.py`) is 4 simple assertions on the same fixture. It cost ~5 minutes to write. It now permanently prevents any future change to one renderer without the same change to the other — closing the [[repo-dual-renderers]] failure mode at source. **Generalize this pattern**: any time the codebase has intentional duplicates (renderer pairs, two API versions, mirror configs), a fixture-driven byte-equal test is the right guard.

### 2. Parallel planning during long-running smoke is high-leverage
While Phase 2 smoke was burning ~67 minutes of wall clock, I wrote the Phase 3 plan instead of idling. When smoke finished, Phase 3 was ready to execute. This dropped Phase 3's total wall-clock cost from ~3 hours to ~1.5 hours.

### 3. Verbatim duplication > shared helper module — for this case
Initially I considered extracting `_render_evidence_footnotes` to a new `src/render/evidence.py` module to eliminate duplication. Decided against it because:
- Existing pattern in the codebase is duplicate renderers ([[repo-dual-renderers]])
- A shared module adds an import + indirection cost
- The parity test makes the duplication safe enough
- Phase 3 plan said "follow existing pattern"

Outcome: cleaner diff, smaller PR, no architectural change snuck in alongside a feature change.

### 4. Stacked PRs reduce reviewer cognitive load
PR #10 was 47 commits across 3 logical buckets — a lot to absorb. PR #11 is 9 commits, all about one thing (renderers). When user opens #11, they see exactly the Phase 3 diff, not Phase 1+2 noise. The cost: explicit merge sequencing (#10 first, then #11) and rebase if #10 changes.

### 5. The plan-first discipline pays compounding interest
The Phase 3 plan was already 100% complete before any code was written. Every task had exact files, exact code, exact commands, exact expected output. Execution was just "follow the plan, commit, next." This is the third spec-driven feature in a row (Phase 1, Phase 2, Phase 3) where planning eliminated mid-execution rework.

---

## Stats

- **Commits**: 9 (8 task + 1 CHANGELOG anchor)
- **Source files touched**: 2 (`src/notification.py`, `src/services/history_service.py`)
- **New tests**: 23 across 5 new test files + 1 new fixture
- **Lines added**: ~700 (mostly tests + new helpers)
- **Lines deleted**: ~25 (legacy `_render_action_plan_items` body replaced)
- **Wall-clock duration**: ~1.5 hours (excluding the Phase 2 smoke that ran in parallel)
- **Pre-existing failure carried forward**: 1 (`test_agent_executor::test_max_steps_exceeded`)
