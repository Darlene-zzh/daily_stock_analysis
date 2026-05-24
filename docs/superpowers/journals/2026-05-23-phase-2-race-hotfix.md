# Phase 2 Sanitizer Race — Debug + Hotfix Journal

**Window:** 2026-05-23 BST (afternoon, post-Phase-3-ship)
**Branch:** `feat/committee-timeout-and-bilingual` (PR #10) + rebase `feat/phase-3-renderers` (PR #11)
**Trigger:** User asked "what to do next" after Phase 3 shipped; I recommended fixing the (then-thought-to-be) NVDA pre-split price ghost.
**Outcome:** Discovered the bug was NOT a Phase 1 data-source issue — it was a Phase 2 thread-safety race. Fixed and pushed in a single session, both PRs rebased.
**Author:** Claude Opus 4.7 (1M context), paired with user `zihanzhang641@gmail.com`

---

## Iron law: no fix before root cause

Started with `superpowers:systematic-debugging` (user added `ultrathink`). My initial hypothesis came from memory `repo-nvda-presplit-ghost.md`: "NVDA candidate.entry.1=$414.95 is a stale pre-split price from Phase 1 data source bug." That memory was written by me 6 hours earlier based on the smoke log alone.

## Investigation

### Step 1 — Read the smoke log carefully (Phase 1: gather evidence)

```
820: 2026-05-23 04:55:55 | [facts_builder] MSFT bundle attached: 17 facts, 14 candidates
821: 2026-05-23 04:55:56 | [sanitizer_v2] override trigger_price: candidate=candidate.entry.1 llm=214.75 -> candidate.price=414.95
822: 2026-05-23 04:55:56 | [sanitizer_v2] drop item: candidate=candidate.entry.1 applies to ['swing_trade', 'stepped_profit_taking'], recommended=wait_and_see
823: 2026-05-23 04:55:56 | [action_plan] sanitizer empty -> synthesized 0 items from candidates for NVDA/wait_and_see
```

Three observations:
- MSFT was attached at 04:55:55, NVDA's sanitizer fired at 04:55:56 (1 second apart)
- The `$414.95` value matches MSFT's price range, not NVDA's (~$215)
- Line 823 logged the stock as "NVDA" — so the `code` parameter was correct, but the bundle wasn't

### Step 2 — Check concurrency assumption

```bash
grep -n "ThreadPoolExecutor\|self.analyzer\s*=" src/core/pipeline.py
```

Found:
- `self.analyzer = GeminiAnalyzer(...)` — single instance (line 138)
- `ThreadPoolExecutor(max_workers=self.max_workers)` — multiple workers (line 1966)
- All workers call `self.analyzer.*` — shared singleton

This was sufficient to suspect the bug was concurrency, not data source.

### Step 3 — Verify against persisted state (Phase 2: compare working examples)

The decisive evidence: query the DB directly to see what was actually persisted for NVDA and MSFT.

```python
SELECT id, code, created_at, raw_result FROM analysis_history
WHERE code IN ('NVDA','MSFT') AND created_at >= '2026-05-23 04:00:00'
ORDER BY created_at DESC LIMIT 4
```

Result:
- NVDA id=50: `candidate.entry.1 @ $214.75` ✅ correct
- MSFT id=51: `candidate.entry.1 @ $414.95` ✅ correct for MSFT

**Both bundles were correctly built per-stock**. The corruption was happening AFTER bundle attach, INSIDE the sanitizer. Phase 1 data source is fine.

### Step 4 — Form hypothesis (Phase 3)

Phase 2 Task 13 stashed bundle on `self.analyzer._fact_bundle_for_sanitize`. Under concurrent execution:
1. NVDA thread calls `_try_inject_action_plan_items`, sets `self._fact_bundle_for_sanitize = NVDA_bundle`
2. NVDA's LLM call begins (~30 seconds)
3. MSFT thread enters the same method, sets `self._fact_bundle_for_sanitize = MSFT_bundle` (OVERWRITES)
4. NVDA's LLM returns
5. NVDA's sanitizer reads `self._fact_bundle_for_sanitize` → MSFT's bundle
6. NVDA's `candidate.entry.1` ID exists in MSFT's bundle → "force-aligned" to MSFT's $414.95

The damage was masked in NVDA's case by `wait_and_see` strategy dropping the entry, but for `swing_trade` / `long_term_hold` stocks, the user would have seen visibly wrong trigger_prices.

### Step 5 — Write deterministic failing test (Phase 4)

3 tests in `tests/test_sanitizer_thread_safety.py`:
1. `test_sanitize_accepts_fact_bundle_and_current_price_kwargs` — pin the explicit-kwarg signature
2. `test_no_instance_attribute_stash_after_inject` — guard against future re-introduction
3. `test_explicit_fact_bundle_kwarg_wins_over_any_instance_stash` — set stale stash to MSFT bundle, call sanitizer with explicit NVDA kwarg, assert NVDA wins

Initial run: 2/3 failed (signature + explicit-kwarg-wins). The `no-stash` test passed by accident because cleanup at end of `_try_inject_action_plan_items` nulled the stash; I left that test as a forward guard.

### Step 6 — Fix (Phase 4, single change)

`src/analyzer.py`:
- `_sanitize_action_plan_items` signature now `(self, items, portfolio_context_block, code, strategy=None, *, fact_bundle=None, current_price=None)`
- Removed `bundle_dict = getattr(self, "_fact_bundle_for_sanitize", None)`; uses the `fact_bundle` kwarg directly
- `_try_inject_action_plan_items`:
  - Bundle + current_price become local variables, NEVER assigned to `self`
  - Both call sites (upstream-strategy branch + LLM branch) pass them explicitly via `fact_bundle=fact_bundle, current_price=current_price`
  - Deleted both `self._fact_bundle_for_sanitize = None` cleanup lines (no longer needed — local vars die with stack frame)

Also updated existing test `tests/test_analyzer_sanitizer_v2_dispatch.py` to use the new explicit-kwarg API.

### Step 7 — Verify

- 3 new race tests: all green
- 22-test Phase 2 + sanitizer suite: all green
- Full offline regression: 2506 passed, 1 known pre-existing failure
- flake8 critical / py_compile: clean
- Committed `d703a37` to PR #10
- Rebased PR #11 (`feat/phase-3-renderers`) cleanly onto new PR #10 head, force-pushed

---

## Lessons learned

### 1. Memory can be wrong — verify before relying on it
I wrote `repo-nvda-presplit-ghost.md` 6 hours earlier confidently asserting the bug was a Phase 1 data-source ghost. Today's investigation proved that wrong. The original analysis was based on log lines alone, without checking the persisted state. **Rule: when a memo asserts the cause of a multi-component bug, the verification step (DB query, code grep) should be IN the memo itself, not just in the writing-window context.** Now both memos cross-reference each other so the wrong analysis is visibly superseded.

### 2. Instance attributes on shared singletons are ALWAYS racy
The Phase 2 design used `self._fact_bundle_for_sanitize` to avoid changing a method signature. That works in single-threaded tests, fails silently in multi-threaded production. **Rule for this codebase: any singleton that's used by `ThreadPoolExecutor` workers (`self.analyzer`, `self.db`, `self.fetcher_manager`, etc.) must not carry per-call state. Always thread per-call state through method parameters.** Added to memory.

### 3. The "ultrathink" tag was load-bearing here
User added `ultrathink` to the message that triggered this debugging. Without it I might have rushed to "fix" the candidate_rules data source — a non-existent bug, which would have wasted hours and not solved the real problem. Ultrathink → forced me to actually verify hypotheses against DB state before proposing a fix.

### 4. Sanitizer's value just got higher
The sanitizer's `trigger_price` force-align was originally framed as "catch LLM hallucinations." Today's incident shows it ALSO catches our own concurrency bugs — when bundles cross-leak, the override fires loudly in the log, making the bug visible. Without sanitizer logging, this race could have persisted silently for months.

### 5. Stacked PRs survived a force-push cleanly
PR #11 (Phase 3) was stacked on PR #10. The hotfix went onto #10, then `git rebase feat/committee-timeout-and-bilingual feat/phase-3-renderers` rebased Phase 3's 9 commits onto the new #10 head with zero conflicts (Phase 3 only touches renderers; the hotfix only touches analyzer). Force-pushed Phase 3 with `--force-with-lease`. GitHub auto-updated #11's diff. Stacked-PR pattern proved robust.

---

## Stats

- **Commits this session**: 1 (`d703a37` fix on PR #10) + 9 rebased Phase 3 commits (`015d250` ... etc.) on PR #11
- **Files touched**: 1 source (`src/analyzer.py`) + 2 tests (1 new + 1 modified)
- **Lines added**: ~140 (mostly new race tests)
- **Lines deleted**: ~25 (removed instance-stash plumbing)
- **Time to diagnose**: ~10 min (log inspection + grep + DB query)
- **Time to fix**: ~15 min (test → fix → verify → rebase → push)
- **User-visible damage prevented**: this bug, if shipped to production with multi-stock parallel analysis, would have produced cross-stock corrupted trigger_prices in `action_plan_items` for any stock recommended `swing_trade` / `long_term_hold`
