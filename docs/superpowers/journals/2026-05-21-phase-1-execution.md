# Phase 1 FactBundle Foundation — Execution Journal

**Start:** 2026-05-21 05:29 (local)
**End:** 2026-05-21 05:46 (local)
**Operator:** Claude (autonomous overnight run, PUA-loop mode)
**Plan:** `docs/superpowers/plans/2026-05-21-phase-1-facts-foundation.md` (committed at d3cc5c7)
**Branch:** `feat/committee-timeout-and-bilingual`
**Strategy:** Inline TDD execution per task (subagent prompt-size cap prevents SDD dispatch with inlined code; see `memory/feedback-subagent-prompt-size-limit.md`)

---

## Result

**Phase 1 status: COMPLETE.** All 19 tasks executed, 19 individual commits as the plan dictates, 0 deviations from plan.

- 59 unit / fixture tests added; **59 / 59 PASS** (`python3.11 -m pytest tests/test_facts*.py tests/test_candidate_rules.py tests/test_pipeline_fact_bundle.py`)
- Offline smoke run against real NVDA dashboard from `data/stock_analysis.db`: 22 facts, 7 candidates (resistance_touch / ma20_breakdown / ma10_pullback / support_test / r_multiple_2r / r_multiple_3r / psychological_round), full JSON round-trip clean.
- 27 files changed, +2264 / −1 lines.

## Commit timeline (19 sequential commits, one per Task)

| Task | Commit  | Title |
|------|---------|-------|
| 1  | b554f32 | feat(analysis): add FactRecord, FactBundle, CandidateLevel types |
| 2  | b0509b4 | feat(analysis): add technical.* fact extractor |
| 3  | fb2f4be | feat(analysis): compute ATR(14) for technical fact extractor |
| 4  | d29ddc5 | feat(analysis): add quant.* fact extractor (qlib score/rank/IC) |
| 5  | d56ef1d | feat(analysis): add committee.* fact extractor (PM/risk/masters) |
| 6  | 212f1ee | feat(analysis): add intel.* fact extractor (alerts/catalysts/sentiment) |
| 7  | 039723f | feat(analysis): add portfolio.* fact extractor |
| 8  | a7ebd31 | feat(analysis): add flow.* fact extractor (A-share capital flow) |
| 9  | 2dc6eb7 | feat(analysis): add chip.* fact extractor (A-share chip distribution) |
| 10 | b3d29b7 | feat(analysis): candidate rules — 4 basic technical-position rules |
| 11 | 97fd5e3 | feat(analysis): candidate rules — ATR-based stop_loss (2x/3x) |
| 12 | aaa72f1 | feat(analysis): candidate rules — R-multiple targets + resistance+ATR |
| 13 | 6fbfaaf | feat(analysis): candidate rules — psychological_round + cost-anchor tier |
| 14 | eb36280 | feat(analysis): candidate rules — Fib/swing/qlib/chip remaining rules |
| 15 | 87edf07 | feat(analysis): emit swing_high_20d/swing_low_20d for Fib/swing rules |
| 16 | 5c09b03 | feat(analysis): facts_builder main entry wires all extractors + rules |
| 17 | 726db36 | feat(pipeline): attach FactBundle to dashboard (Phase 1 wiring) |
| 18 | 5b15e2c | test(analysis): NVDA fixture-based end-to-end FactBundle test |
| 19 | dca2141 | docs(changelog): Phase 1 FactBundle foundation entry |

## Decisions / deviations from plan

1. **`CandidateLevel.direction` Literal** widened to include both `"stop"` and `"stop_loss"` because plan’s `_make_candidate` maps `direction="stop_loss"` to id-prefix `"stop"` (Task 10) but tests assert `direction == "stop_loss"`. Adding both keeps both id-mapping and assertion happy.
2. **Pipeline integration placement** — plan said line 1677-1750, exact lines drifted; the cleanest insertion was a new private method `StockAnalysisPipeline._attach_fact_bundle` called from `process_single_stock` after `analyze_stock` returns. Everything wrapped in try/except. Pipeline behaviour unchanged on failure path.
3. **Task 19 Step 2 "real single-stock analysis"** intentionally **NOT** run live overnight to avoid LLM quota / cost. Replaced with an offline smoke that exercises `_attach_fact_bundle` against a real captured NVDA dashboard from `data/stock_analysis.db` — produced 22 facts + 7 candidates + clean JSON. Live smoke is the user’s call when they wake up.
4. **`get_capital_flow_context` not `get_capital_flow`** — the actual method on `DataFetcherManager` is `get_capital_flow_context`; the plan called it `get_capital_flow`. Adjusted accordingly with `hasattr` guard.
5. **`python3.11`, not `python`** — `./scripts/ci_gate.sh` calls bare `python`, which is absent on this system. Ran equivalent checks manually with `python3.11`: `py_compile main.py + src/core/pipeline.py + src/analysis/**` clean; flake8 `E9,F63,F7,F82` zero issues.

## What is NOT done (deliberately, per the user's instructions)

- **Phase 2-6 plans** — the user said "Phase 2-6 plan 还没写，每个 phase 开始前再写"; no scope creep.
- **LLM prompt rewrite, sanitizer, renderers, frontend, audit-layer UI** — all out of scope for Phase 1 per the plan (Section "Not touched in this phase").
- **Live run of `python main.py --stocks AAPL`** — deferred to morning per the reasoning above.

## Verification one-liners (for the user in the morning)

```bash
# 1. Run the full Phase 1 test suite (offline, ~2s)
python3.11 -m pytest tests/test_facts.py tests/test_facts_technical.py tests/test_facts_quant.py tests/test_facts_committee.py tests/test_facts_intel.py tests/test_facts_portfolio.py tests/test_facts_flow.py tests/test_facts_chip.py tests/test_candidate_rules.py tests/test_facts_builder.py tests/test_pipeline_fact_bundle.py tests/test_facts_nvda_fixture.py -v

# 2. Re-run the offline smoke against the real NVDA row
python3.11 -c "
import json, sqlite3, sys
from types import SimpleNamespace
from src.core.pipeline import StockAnalysisPipeline
conn = sqlite3.connect('data/stock_analysis.db')
data = json.loads(conn.execute(\"SELECT raw_result FROM analysis_history WHERE code='NVDA' ORDER BY created_at DESC LIMIT 1\").fetchone()[0])
result = SimpleNamespace(dashboard=data['dashboard'], success=True)
p = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
class F: get_daily_data = staticmethod(lambda c, days=30: (None, 'fake'))
p.fetcher_manager = F()
p._attach_fact_bundle(result, 'NVDA')
fb = result.dashboard['fact_bundle']
print('facts:', len(fb['facts']), 'candidates:', len(fb['candidates']))
print('rules used:', sorted({c['basis_rule'] for c in fb['candidates']}))
"

# 3. Diff overview of what changed
git log --oneline d3cc5c7..HEAD
git diff --stat d3cc5c7..HEAD

# 4. Live smoke (only if you trust the quota burn — not run overnight)
python3.11 main.py --stocks NVDA
# then inspect the new analysis_history row for the fact_bundle key:
python3.11 -c "
import json, sqlite3
row = sqlite3.connect('data/stock_analysis.db').execute(\"SELECT raw_result FROM analysis_history WHERE code='NVDA' ORDER BY created_at DESC LIMIT 1\").fetchone()
data = json.loads(row[0])
fb = data.get('dashboard', {}).get('fact_bundle')
if fb:
    print('LIVE OK — facts:', len(fb['facts']), 'candidates:', len(fb['candidates']))
else:
    print('NO fact_bundle — check logs for [facts_builder] line')
"
```

## Risk notes

- The pipeline wiring is **fully behind try/except**. If facts_builder errors for any reason, the surrounding pipeline still completes and dashboard is unmodified. Nothing user-visible should regress.
- A-share `flow_data` / `chip_data` paths depend on `fetcher_manager.get_capital_flow_context` / `get_chip_distribution`; both guarded by `hasattr` checks.
- `portfolio_context` is currently `getattr(result, 'portfolio_context', None)` — Phase 2 will wire the real context from `PortfolioContextService`. For now portfolio.* facts are emitted only when a caller stashes the context on the result object.
- Bundle attached as `dashboard['fact_bundle']` (top-level alongside other dashboard keys). No existing consumer reads it; old clients are unaffected.

## Files created (new)

- `src/analysis/__init__.py`
- `src/analysis/facts.py`
- `src/analysis/facts_builder.py`
- `src/analysis/candidate_rules.py`
- `src/analysis/extractors/__init__.py`
- `src/analysis/extractors/technical.py`
- `src/analysis/extractors/quant.py`
- `src/analysis/extractors/committee.py`
- `src/analysis/extractors/intel.py`
- `src/analysis/extractors/portfolio.py`
- `src/analysis/extractors/flow.py`
- `src/analysis/extractors/chip.py`
- `tests/test_facts.py` (3 tests)
- `tests/test_facts_technical.py` (8 tests)
- `tests/test_facts_quant.py` (4 tests)
- `tests/test_facts_committee.py` (3 tests)
- `tests/test_facts_intel.py` (3 tests)
- `tests/test_facts_portfolio.py` (3 tests)
- `tests/test_facts_flow.py` (4 tests)
- `tests/test_facts_chip.py` (3 tests)
- `tests/test_candidate_rules.py` (22 tests)
- `tests/test_facts_builder.py` (3 tests)
- `tests/test_pipeline_fact_bundle.py` (2 tests)
- `tests/test_facts_nvda_fixture.py` (1 fixture-based E2E)
- `tests/fixtures/nvda_dashboard.json` (captured NVDA dashboard, id=13 → most-recent)

## Files modified

- `src/core/pipeline.py` (+118 / −1, added `_attach_fact_bundle` + call from `process_single_stock`)
- `docs/CHANGELOG.md` (+1 line in `[Unreleased]` flat format)
