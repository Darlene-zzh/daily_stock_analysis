# Sprint 3 P9 Delivery Report — Qlib Alpha158 + LightGBM Quant Anchor (Framework-First)

**Branch:** `feat/quant-signal` off `feat/decision-journal`
**Commits:** 7 (`0141e7b` → `1e22f6a`), English messages, no push
**Worktree:** `/Users/zhen/daily_stock_analysis/.claude/worktrees/agent-adcd75cec3bd87302`

---

## 1. 改了什么 / What changed

Sprint 3 ships the **framework** for the qlib Alpha158 + LightGBM auxiliary signal. The data download and model training are intentionally not run overnight (they are GB-scale / CPU-heavy and the user runs them on-demand); the framework code, tests, scripts, workflow, Web panel, API, docs are all done.

### Backend (Python)

| File | Status | Why |
|---|---|---|
| `data_provider/qlib_fetcher.py` | new | Lazy-import wrapper around `pyqlib`; ensure_initialized / get_alpha158_factors / csi300_universe / sp500_universe / normalize_to_qlib_symbol. All return None / empty cleanly when qlib is missing |
| `src/services/quant_signal_service.py` | new | `QuantSignalService` orchestrator. Public surface: `get_factor_quantiles`, `get_forecast`, `build_quant_context_block`. Carries the 7 P9-locked decisions internally |
| `src/analyzer.py` | edit | `GeminiAnalyzer.analyze()` and `_format_prompt()` accept `quant_context_block`. When non-empty, splice section between reflection block and technical data. When None, no Quant Context section appears |
| `src/core/pipeline.py` | edit | `StockAnalysisPipeline.__init__` and `analyze()` call forward the new kwarg |
| `src/services/analysis_service.py` | edit | `analyze_stock()` gains `enable_quant_signal: bool = False` + `quant_forecast_horizon: Optional[int] = None`. The block is built BEFORE the pipeline runs; failure is caught with try/except so the rest of the analysis is unaffected |
| `src/services/task_queue.py` | edit | `submit_tasks_batch` + `_execute_task` thread the new kwargs through the async batch path |

### API (FastAPI)

| File | Status |
|---|---|
| `api/v1/schemas/analysis.py` | edit — adds `enable_quant_signal` + `quant_forecast_horizon` to `AnalyzeRequest` |
| `api/v1/endpoints/analysis.py` | edit — forwards both fields to async submit and sync paths |
| `api/v1/endpoints/quant_signal.py` | new — `GET /api/v1/quant-signal/{stock_code}?market=&horizon=`; 200 + payload OR 204 No Content |
| `api/v1/router.py` | edit — registers the new endpoint under `/api/v1/quant-signal` |

### Scripts + Workflow

| File | Status |
|---|---|
| `scripts/setup_qlib_data.sh` | new — manual data downloader (cn + us), refuses unsupported regions, exits 1 if pyqlib missing |
| `scripts/train_alpha158_lightgbm.py` | new — rolling weekly trainer; writes `model.pkl`, `predictions.json`, `ic.json` under `data/quant_models/<region>/<YYYY-Wxx>/`. Lazy-imports both qlib + lightgbm, exits 0 with warning when either missing |
| `.github/workflows/qlib-retrain.yml` | new — `workflow_dispatch` only (schedule deliberately commented out per spec). Bundles weekly artifact + uploads to a GitHub Release (pre-release) |

### Web (apps/dsa-web)

| File | Status |
|---|---|
| `apps/dsa-web/src/api/quantSignal.ts` | new — typed API client. Treats 204 the same as null |
| `apps/dsa-web/src/components/quant/QuantContextPanel.tsx` | new — factor strip + forecast banner + auxiliary caveat. Returns null when no signal |
| `apps/dsa-web/src/components/quant/__tests__/QuantContextPanel.test.tsx` | new — 6 vitest cases |
| `apps/dsa-web/src/components/report/ReportSummary.tsx` | edit — mount the panel between the committee and the decision-tracking sections |

### Config + Docs

| File | Status |
|---|---|
| `requirements-quant.txt` | new — `pyqlib>=0.9.0`, `lightgbm>=4.0`. **NOT in main requirements.txt** |
| `.env.example` | edit — `QUANT_SIGNAL_ENABLED`, `QUANT_MODEL_DIR`, `QUANT_FORECAST_HORIZON`, `QUANT_IC_GATING_THRESHOLD`, `QLIB_DATA_DIR`, `QLIB_PROVIDER_URI_CN/US` |
| `.gitignore` | edit — `data/qlib/**` and `data/quant_models/**` ignored; `.gitkeep` whitelisted |
| `data/qlib/.gitkeep`, `data/quant_models/.gitkeep` | new — placeholders |
| `docs/CHANGELOG.md` | edit — Sprint 3 flat entries in `[Unreleased]` |
| `docs/full-guide.md` | edit — new `量化辅助信号 / Quant Context (Sprint 3)` section |
| `docs/quant-signal-setup.md` | new — step-by-step runbook |

### Tests (4 new files, 49 passing)

- `tests/test_qlib_fetcher.py` — 12 cases: lazy-import / supported markets / symbol normalisation / no-data graceful path / inner-exception swallow
- `tests/test_quant_signal_service.py` — 28 cases: env defaults / market inference / HK no-op / outside-universe / no-artifact / IC gating / IC pass / dual-language caveat
- `tests/test_quant_prompt_injection.py` — 4 cases: block omitted vs spliced, zh/en parity, three-block stacking order
- `tests/test_analysis_service_quant.py` — 4 cases: default-off no service instantiation / opt-in build + thread / exception swallow / task_queue param signature

---

## 2. 为什么这么改 / Why

* P9 spec explicitly demanded **framework-first**: the overnight environment can't realistically download GB of qlib data or run a full LightGBM weekly train, so we ship the plumbing such that when the user later runs `scripts/setup_qlib_data.sh` + `scripts/train_alpha158_lightgbm.py`, the system Just Works.
* Every public function is **silent no-op** on failure. Quant context is auxiliary; a broken qlib install must never break the default analysis or look like an API error.
* Lazy import keeps the main `requirements.txt` clean; qlib's C deps and lightgbm wheels would significantly bloat the default Docker image and slow CI.
* Threading the opt-in through the SAME path Sprint 1B/2 used (`portfolio_context_block` / `reflection_context_block`) gives us a uniform mental model and avoids inventing parallel plumbing.
* All seven P9-locked decisions are implemented exactly as documented in `docs/superpowers/plans/2026-05-18-professional-upgrade.md` § Sprint 3.

---

## 3. 验证情况 / Verification

### DONE matrix — verbatim outputs

**(1) requirements.txt unchanged:**
```
$ git diff feat/decision-journal -- requirements.txt | wc -l
       0
```

**(2) py_compile on every new/changed .py:**
```
$ python3.11 -m py_compile data_provider/qlib_fetcher.py src/services/quant_signal_service.py \
    src/services/analysis_service.py src/services/task_queue.py src/core/pipeline.py \
    src/analyzer.py api/v1/schemas/analysis.py api/v1/endpoints/analysis.py \
    api/v1/endpoints/quant_signal.py api/v1/router.py scripts/train_alpha158_lightgbm.py
PYCOMPILE_OK
```

**(3) pytest (without qlib installed):**
```
$ python3.11 -m pytest -m "not network" tests/test_quant_signal_service.py \
    tests/test_qlib_fetcher.py tests/test_quant_prompt_injection.py \
    tests/test_analysis_service_quant.py
============================== 49 passed in 2.38s ==============================
```

**(4) ci_gate.sh syntax + flake8 critical:**
```
$ bash scripts/ci_gate.sh syntax
==> backend-gate: Python syntax check
(clean — no errors)

$ python3.11 -m flake8 . --select=E9,F63,F7,F82 --count
0
```

**(5) Web lint + build + vitest:**
```
$ cd apps/dsa-web && npm run lint
> dsa-web@0.0.0 lint
> eslint .
(clean — 0 errors)

$ npm run build
✓ built in 6.45s

$ npx vitest run src/components/quant/__tests__/
 Test Files  1 passed (1)
      Tests  6 passed (6)
```

**(6) Lazy-import smoke (no qlib → None, no exception):**
```
$ python3.11 -c "from src.services.quant_signal_service import QuantSignalService; \
    s = QuantSignalService(); print(s.get_factor_quantiles('600519', 'cn'))"
None
```

**(7) GitHub workflow YAML parses; only `workflow_dispatch` active:**
```
$ python3.11 -c "import yaml; d = yaml.safe_load(open('.github/workflows/qlib-retrain.yml')); \
    print('triggers active:', list(d.get(True, {}).keys()))"
triggers active: ['workflow_dispatch']
```

*(`actionlint` was not available in the overnight env; fell back to YAML parse + manual review per DONE step 7 fallback.)*

**(8) Commit chain on `feat/quant-signal`:**
```
$ git log --oneline -8
1e22f6a docs(quant-signal): Sprint 3-7 config + CHANGELOG + setup runbook
895ef21 test(quant-signal): Sprint 3-6 unit tests for fetcher / service / prompt / analysis hook
4ae41b2 feat(quant-signal): Sprint 3-5 Web QuantContextPanel + ReportSummary wiring
dfbeb12 feat(quant-signal): Sprint 3-4 setup script + weekly training + GitHub workflow
5dda8ce feat(quant-signal): Sprint 3-3 API schema + GET /api/v1/quant-signal endpoint
e647416 feat(quant-signal): Sprint 3-2 analyzer/pipeline/service hook for quant context
0141e7b feat(quant-signal): Sprint 3-1 qlib_fetcher + QuantSignalService
5843c1e docs(decision-journal): Sprint 2 P9 delivery report
```

All English commit titles, no `Co-Authored-By`, no push.

### What is NOT done overnight (user-manual steps)

These are the **expected manual steps** the spec called out — NOT failures:

1. **Data download** — `bash scripts/setup_qlib_data.sh` (GB-scale per region, several minutes). Documented in `docs/quant-signal-setup.md` step 3.
2. **First model training** — `python scripts/train_alpha158_lightgbm.py` (~20 minutes per region). Documented in step 4.
3. **Cron activation** — `.github/workflows/qlib-retrain.yml` ships with `schedule:` commented out. User should manually `workflow_dispatch` once, confirm the artifact uploads, THEN uncomment the cron. Documented in step 5.
4. **Per-request opt-in** — set `enable_quant_signal: true` on the analysis API request to actually see the Quant Context block. Documented in step 6.

---

## 4. 未验证项 / Not verified

| Item | Why | Mitigation |
|---|---|---|
| Real qlib data download (`setup_qlib_data.sh`) | GB-scale, expected manual step | Script has been bash-syntax-checked (`bash -n`); pyqlib-not-installed branch exits 1 with a clear message |
| Real LightGBM training run | Single region ~20 min CPU; explicit manual step | `python scripts/train_alpha158_lightgbm.py --region cn` smoke-tested with no qlib → exits 0 with warning |
| Live `GET /api/v1/quant-signal` HTTP round-trip | Requires FastAPI startup + trained model | Endpoint handler unit-tested implicitly via service mocks; YAML/Python structure verified |
| `actionlint` on `.github/workflows/qlib-retrain.yml` | `actionlint` not installed in the overnight env | Fell back to `yaml.safe_load` parse — passed (DONE step 7 documented fallback) |
| Whole-pytest sweep | Suite uses optional deps not part of this Sprint's scope; we ran only the Sprint 3 files per the spec's DONE step 3 | All 49 Sprint 3 cases green |
| HK-stock fallthrough at runtime | Service-level test (`test_get_factor_quantiles_returns_none_for_hk`) covers it; pipeline-end-to-end requires the standard analysis path which is untouched | Same try/except guard wraps the call site |

---

## 5. 风险点 / Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `import qlib` triggers C extension compilation on the user's first install | Medium | Documented in `docs/quant-signal-setup.md`; isolated to `requirements-quant.txt`; default app boot unaffected |
| LightGBM training memory usage on 3-year window × 500-stock universe | Medium | GitHub Action sets `timeout-minutes: 90`; user can override `--training-years` to shrink |
| `data/quant_models/<region>/<YYYY-Wxx>/` directory layout assumes ISO week sort works across year transitions | Low | Lexicographic sort of `YYYY-Wxx` IS correct (alphabetical = chronological); if ever wrong, a single `.json` read fails and the service returns None gracefully |
| `factor_quantiles.json` sidecar isn't actually written by the trainer in this build | Low | Trainer documented to produce it as an OPTIONAL future enhancement; service falls back to live factor values when the sidecar is missing |
| `_analyze_with_agent` bypass path doesn't inject quant context | By design | Mirrors Sprint 1B/2 behaviour — agent mode uses its own context-assembly path; documented in the bypass-comment in `pipeline.py` |
| 4-week IC gate at 0.02 may be too lax / strict | Low | Tunable via `QUANT_IC_GATING_THRESHOLD`; gate sits in `quant_signal_service._load_model_artifact` so swapping the rule is a one-liner |
| GitHub Release pre-release artifact accumulation | Low | Action artifact retention is 60 days; Release assets are pre-release so a janitor PR can prune them when desired |

---

## 6. 回滚方式 / Rollback

* **Quick disable**: any consumer passing `enable_quant_signal: false` (the default) gets the unchanged pre-Sprint-3 prompt. Web panel renders nothing because the API returns 204.
* **Disable globally**: remove `data/quant_models/` so the service finds no artifact → silent no-op everywhere.
* **Permanent revert**: `git revert 0141e7b..1e22f6a` removes the entire Sprint 3 stack atomically; nothing in Sprint 1A / 1B / 2 depends on it.
* **Workflow rollback**: delete `.github/workflows/qlib-retrain.yml`; no other workflow file references it.

---

## Locked-decision conformance check

| # | Decision | Lives in |
|---|---|---|
| Q1 | CSI 300 (cn) + S&P 500 (us); HK silent no-op | `QuantSignalService.is_in_universe`, `qlib_fetcher.csi300_universe / sp500_universe`, `QUANT_MARKETS = ("cn", "us")` |
| Q2 | Rolling 3-year, weekly Saturday retrain | `train_alpha158_lightgbm.py`'s `--training-years 3` default + `qlib-retrain.yml` `cron: "0 2 * * 6"` (commented out until user opt-in) |
| Q3 | Default 10-day horizon | `QUANT_FORECAST_HORIZON` env / `default_forecast_horizon() → 10` / API `quant_forecast_horizon` default None |
| Q4 | Rank IC (Spearman) + 4-week MA | `train_alpha158_lightgbm.py` `daily_ic` groupby + `tail(20).mean()` |
| Q5 | IC < 0.02 → forecast hidden, factors keep uncertain tag | `QuantSignalService.get_forecast`'s `ic_ma_4w < ic_gating_threshold()` check + `_render_block`'s uncertain tag branch |
| Q6 | No artifact → silent no-op | `_load_model_artifact` returns None → `get_forecast` returns None → API returns 204 → Web returns null |
| Q7 | Auxiliary, not a recommendation | `build_quant_context_block` always emits the bilingual caveat; Web panel always renders the "Auxiliary" badge + caveat text |

---

**Status:** Sprint 3 framework delivery complete. P9 can chain to Sprint 4. The four user-manual steps above need running before quant context appears in actual reports.
