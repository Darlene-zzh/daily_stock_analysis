# Professional Upgrade — Investment Committee, Decision Journal, Qlib Quant Anchor (4-Sprint Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan sprint-by-sprint. Each sprint is a **separate commit gate** — do not proceed to the next sprint without user approval.

**Goal:** Upgrade the LLM-driven decision push system into an institutional-grade product by integrating the best ideas from three open-source repos (microsoft/qlib, virattt/ai-hedge-fund, TauricResearch/TradingAgents) on top of the existing agent framework already shipped under `src/agent/`.

**Architecture (cross-sprint):**

- **Sprint 1 (P0)** — *Investment Committee on LangGraph.* Bull ↔ Bear debate + 4 master personas (Buffett/Burry/Cathie Wood/Taleb) + Risk Manager + Portfolio Manager. Web opt-in only; default path unchanged.
- **Sprint 2 (P1)** — *Decision Journal + Reflection.* Every report writes to a per-stock markdown journal; next-time analysis computes realised alpha vs benchmark (HS300/HSI/SPY) and injects a one-paragraph reflection into the prompt.
- **Sprint 3 (P2)** — *Qlib Alpha158 + LightGBM Quant Anchor.* Offline cron trains a rolling LightGBM on Alpha158, exposes per-stock factor quantiles + N-day excess-return forecast + IC as a "second opinion" embedded in the report.
- **Sprint 4 (P3)** — *Infrastructure polish.* LangGraph checkpoint resume in `task_queue.py`; structured-output upgrade for the already-existing `RiskAgent` (it ships today — Sprint 4 is scoped down).

**Tech Stack:** Python 3.11 / pytest / FastAPI / Pydantic v2 / LangGraph (new) / React 18 + TypeScript / Tailwind / LightGBM + qlib (Sprint 3).

**Rules (from AGENTS.md):** English commit messages, no `Co-Authored-By`, **no `git commit` / `git push` / `git tag` without explicit user confirmation**. Phase-by-phase gating — user reviews and commits each sprint before the next starts. CHANGELOG entries go in `[Unreleased]` using flat format `- [类型] 描述`. Sync `src/notification.py` + `src/services/history_service.py` whenever the report markdown changes. Async param threading: `_handle_async_analysis_batch` (`api/v1/endpoints/analysis.py:349`) → `submit_tasks_batch` (`src/services/task_queue.py:345`) → `_execute_task` (`src/services/task_queue.py:576`) → `AnalysisService.analyze_stock` (`src/services/analysis_service.py:42`).

**Decisions confirmed with user (2026-05-18):**

| # | Decision |
|---|---------|
| 1 | LLM call budget **scales with debate rounds**: `cap = 6 + 2N + 2` → 10 / 12 / 14 for 1 / 2 / 3 rounds. Env `INVESTMENT_COMMITTEE_BUDGET_BASE=12` controls baseline; effective cap is computed at runtime |
| 2 | Bull ↔ Bear debate rounds: **user-selectable in Web UI** (1 / 2 / 3, default 2). Web UI shows live cost estimate next to selector |
| 3 | Existing strategies act as **LLM tools the masters call on demand** — Sprint 1 curates to **5**: `ma` / `macd` / `boll` / `sentiment_aggregator` / `fundamentals_snapshot` |
| 4 | Agent timeout / garbage output: **skip and let PM annotate absence** (graceful degradation) |
| 5 | Web opt-in entry points: **both task-creation form AND single-stock page** (Sprint 1B) |
| 6 | Inter-agent schema strictness: **tiered** (see §"Schema strictness rules" below) |
| 7 | Language: **prompts in English**, output follows user's `report_language`. Display layer uses **"inspired lens" framing** (e.g. `Buffett-inspired value lens`) to avoid implying endorsement |
| 8 | Personas: internal id stays snake_case English (`warren_buffett` etc.); display strings localised (English first + Chinese parenthetical on first mention in `zh` mode) |
| 9 | Committee minutes persist to history DB via `history_service` (alongside the existing report) — enables Sprint 2 reflection on past committee verdicts |
| 10 | LangGraph **Sprint 1 adds only `langgraph==0.4.8`**. `langgraph-checkpoint-sqlite>=3.0.1` deferred to Sprint 4 (when it's actually used) |

### Schema strictness rules (applies to every LLM-produced schema in this project)

To prevent LLM JSON drift from quietly degrading into "everything Optional, schema is just decoration", every schema declares:

- **Critical fields** — `verdict`, `score`, `rationale`, `key_evidence` (`len >= 1`). Pydantic `strict` validation. If missing on first LLM response → **retry once** with the schema embedded as a JSON example in the user message
- **Non-critical fields** — `tools_used`, `counter_view`, `citations`, `style_notes`, etc. → `Optional[…] = None` or `default_factory=list`
- **Retry-exhausted** — return a **fallback object** with `status="failed"` + `error_summary`, do NOT raise. The PM prompt receives `missing_agents` and explicitly annotates gaps
- **Top-level status** — every aggregate schema (`CommitteeMinutes`, `RiskAssessment`, …) carries a `status: Literal["ok","partial","failed"]` so callers can branch without inspecting nested fields

**Masters selected:** Warren Buffett (value), Michael Burry (contrarian/short), Cathie Wood (growth/disruption), Nassim Taleb (tail-risk/antifragility). Covers the four quadrants — value × growth × contrarian × risk.

**Benchmark mapping (Sprint 2):** A-share → 沪深 300 (`000300.SH`); HK → 恒生指数 (`HSI`); US → SPY.

---

## Reference implementations (clone-once at `~/reference_repos/`)

Two MIT-licensed reference repos are cloned locally — **every P8 must read its assigned reference file before writing**, not after. This avoids re-inventing inferior prompts. Always cite-and-adapt; do not copy verbatim (license attribution is enough for adaptation).

| Sprint / Task | Reference file | Why |
|---------------|----------------|-----|
| S1 Task 1-2 (Buffett persona) | `~/reference_repos/ai-hedge-fund/src/agents/warren_buffett.py` | Canonical Buffett system prompt + decision schema |
| S1 Task 1-2 (Burry persona) | `~/reference_repos/ai-hedge-fund/src/agents/michael_burry.py` | Contrarian / deep-value framework |
| S1 Task 1-2 (Cathie Wood) | `~/reference_repos/ai-hedge-fund/src/agents/cathie_wood.py` | Disruptive-innovation thesis structure |
| S1 Task 1-2 (Taleb) | `~/reference_repos/ai-hedge-fund/src/agents/nassim_taleb.py` | Tail-risk / antifragility prompt |
| S1 Task 1-3 (Bull / Bear) | `~/reference_repos/TradingAgents/tradingagents/agents/researchers/{bull,bear}_researcher.py` | Debate prompt structure, evidence-citation discipline |
| S1 Task 1-3 (alt. debate pattern) | `~/reference_repos/TradingAgents/tradingagents/agents/risk_mgmt/{conservative,aggressive,neutral}_debator.py` | Three-way debate pattern (we use Bull/Bear only, but the framing is useful) |
| S1 Task 1-3 (LangGraph) | `~/reference_repos/TradingAgents/tradingagents/graph/{trading_graph,setup,propagation}.py` | Modern LangGraph (≥ 0.4.8) state machine patterns |
| S1 Task 1-3 (structured output) | `~/reference_repos/TradingAgents/tradingagents/agents/schemas.py` + `agents/utils/structured.py` | Pydantic-based forced structured output, what we standardise on |
| S1 Task 1-4 (PM) | `~/reference_repos/TradingAgents/tradingagents/agents/managers/portfolio_manager.py` AND `ai-hedge-fund/src/agents/portfolio_manager.py` | Two different PM aggregation styles — pick the one that better fits our verdict-with-evidence output |
| S1 Task 1-4 (Risk Manager) | `~/reference_repos/ai-hedge-fund/src/agents/risk_manager.py` | Position-limit calculation framework — extend our existing `src/agent/agents/risk_agent.py` toward this |
| S2 (Reflection) | `~/reference_repos/TradingAgents/tradingagents/graph/reflection.py` + `agents/utils/memory.py` + `tests/test_memory_log.py` | Direct blueprint for decision journal + reflection injection |
| S3 (Quant signal) | `~/reference_repos/qlib/examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml` | Baseline LightGBM Alpha158 config |
| S3 (HK/US data) | `~/reference_repos/qlib/scripts/data_collector/yahoo/collector.py` | Yahoo data collector (qlib official data is A-share + US; HK requires custom collector) |
| S4 (Checkpoint resume) | `~/reference_repos/TradingAgents/tradingagents/graph/checkpointer.py` + `tests/test_checkpoint_resume.py` | Direct blueprint |

**Dependency note:** Our project currently has **no langchain / langgraph** in `requirements.txt`. Sprint 1 introduces minimal additions:
- `langgraph==0.4.8` (pin exact — TradingAgents-tested version; modern API needed for parallel master fan-out)
- `langchain-core>=0.3.81` (minimum transitive needed by langgraph)
- **Sprint 4 (later)** adds `langgraph-checkpoint-sqlite>=3.0.1` when checkpoint resume actually ships
- We do NOT add `langchain-openai`/`-anthropic`/etc — our existing `src/agent/llm_adapter.py` is the LLM abstraction; LangGraph nodes call through it, not through LangChain providers

---

## Sprint 0 — Pre-work (branching & baseline)

### Task 0-1: Confirm current branch and create feature branch

**Files:** git only.

- [ ] **Step 1: Show working tree state**

Run: `git status --short && git log -5 --oneline`

Expected: branch `feat/action-plan-items` with the pending changes already listed in the gitStatus snapshot.

- [ ] **Step 2: Ask user how to handle pending changes**

Two options to present:
1. Commit pending changes on the current branch first, then branch off `main` for the upgrade.
2. Create the upgrade branch from the current tip (carrying pending changes forward).

**Wait for explicit user choice. Do not commit autonomously.**

- [ ] **Step 3: Create branch (after user confirms)**

`git checkout -b feat/investment-committee-and-reflection`

Expected: `Switched to a new branch 'feat/investment-committee-and-reflection'`

- [ ] **Step 4: Baseline `./scripts/ci_gate.sh`**

Run and capture output. If it fails on `main`'s baseline, file the failures as a blocker and stop. Do not "fix while you're in there" — that violates the stability-over-cleanup rule.

---

## Sprint 1A — Backend Committee Closure (P0a)

> **Why split:** Sprint 1 is split into 1A (backend minimal closure) and 1B (Web UI). Backend lands first as a self-contained, API-testable feature. Web wraps it afterwards. This isolates bug surface — if a regression appears later, we can localise it to one side without unwinding both.

**Goal:** Ship the committee multi-agent pipeline as a backend-only feature, invokable via the API param `enable_investment_committee=true`. No Web UI in 1A; verification is via pytest + curl against the API.

**Detailed task spec:** see `docs/superpowers/specs/2026-05-18-investment-committee-and-reflection-design.md`.

**File-domain map (for parallel P8 spawning):**

| Domain | Owner | Files |
|--------|-------|-------|
| A — Schema + protocol | P8-schema | `src/schemas/committee_schema.py` (new), `src/agent/protocols.py` (extend `AgentOpinion` if needed) |
| B — Master persona agents | P8-personas | `src/agent/agents/master_personas/` (new dir, 4 files + `__init__.py` with display-string mapping) |
| C — Debate orchestrator | P8-debate | `src/agent/agents/bull_researcher.py`, `bear_researcher.py`, `src/agent/orchestrator_committee.py` |
| D — Integration + budget | P8-integration | `src/services/analysis_service.py` (committee hook on both default and bypass paths), `src/services/task_queue.py` (param threading), `api/v1/endpoints/analysis.py` (param), `src/agent/budget.py` (new) |
| E — Renderers + persistence | P8-renderer | `src/notification.py` (`_render_committee_minutes`), `src/services/history_service.py` (same + persistence column for minutes) |

P8s in domains A-D can run in parallel inside a worktree each (B/C/D depend on A's schema being declared; in practice they import from a stub schema first then refine after A finishes its tests). E depends on A.

### Task 1A-1: Schema + protocol (domain A)

- [ ] Define `MasterOpinion`, `DebateExchange`, `RiskAssessment`, `CommitteeMinutes`, `InvestmentCommitteeReport` (Pydantic v2, Optional-lenient like `AnalysisReportSchema`)
- [ ] Add `committee` optional field to a new wrapper around `AnalysisReportSchema` (do not mutate the existing schema — additive only)
- [ ] Tests: 3 fixture LLM responses (perfect / missing fields / outright garbage) must round-trip through strict validation, retry, and graceful fallback
- [ ] DONE: `pytest tests/test_committee_schema.py -q` green; `python -m py_compile src/schemas/committee_schema.py`

### Task 1A-2: Master persona agents (domain B)

- [ ] Subclass existing `BaseAgent`. Each persona is a class with `agent_name`, `tool_names`, `system_prompt(ctx)`
- [ ] **Persona prompt skeleton** (spec doc has the full template) embeds: persona biographical anchor, decision framework (e.g., Buffett: economic moat + intrinsic value + circle of competence), preferred tools, output JSON shape (`MasterOpinion`)
- [ ] All four masters must share the same `MasterOpinion` output schema so the PM agent can iterate them uniformly
- [ ] DONE: each persona's `system_prompt()` ≤ 2 000 tokens; `pytest tests/test_master_personas.py` green (snapshot tests against frozen fixtures)

### Task 1A-3: Debate orchestrator + LangGraph (domain C)

- [ ] Add `langgraph` to `requirements.txt` (pin to a Python-3.11-compatible version)
- [ ] `BullResearcherAgent` / `BearResearcherAgent` subclass `BaseAgent` — each can call the existing strategies-as-tools (via `src/agent/tools/registry.py`)
- [ ] LangGraph state schema in `committee_schema.py`: `{stock_code, ctx, debate_history: list[DebateExchange], master_opinions: dict, risk_assessment, pm_decision, budget_used, errors}`
- [ ] Graph nodes: `bull → bear → [loop N rounds based on user setting] → master_buffett ∥ master_burry ∥ master_wood ∥ master_taleb → risk → pm → end`
- [ ] **Budget enforcement** lives in a wrapper around the LLM call counter (see Task 1-4) — the graph reads remaining budget at each node and short-circuits if budget exhausted (PM gets `budget_exhausted=true` flag in state)
- [ ] **Timeout / garbage handling**: every node has an `on_failure → log + mark missing + continue` policy. PM prompt explicitly enumerates which agents are missing
- [ ] DONE: `pytest tests/test_committee_graph.py` exercises (a) happy path 12-call run; (b) Bear timeout → graph completes with PM annotation; (c) two masters return invalid JSON → graph retries once then degrades

### Task 1A-4: Integration + budget + param threading (domain D)

- [ ] `src/agent/budget.py` — `LLMCallBudget` class with `acquire() / release() / remaining()`. Cap is computed at runtime: `effective_cap = base + 2 * (debate_rounds - 1)` where `base = int(os.getenv("INVESTMENT_COMMITTEE_BUDGET_BASE", "12"))`, yielding 10/12/14 for 1/2/3 rounds
- [ ] Thread `enable_investment_committee: bool = False` and `committee_debate_rounds: int = 2` through the **entire** async chain (memory rule — must not stop halfway):
  - `AnalyzeRequest` (Pydantic model in API endpoints) — add fields
  - `_handle_async_analysis_batch` at `api/v1/endpoints/analysis.py:349` — pass through `submit_kwargs`
  - `submit_tasks_batch` at `src/services/task_queue.py:345` — add kwargs
  - `_execute_task` at `src/services/task_queue.py:576` — add kwargs, persist on `TaskInfo`
  - `AnalysisService.analyze_stock` at `src/services/analysis_service.py:42` — add kwargs
- [ ] In `analyze_stock`, after the existing LLM report is produced, if `enable_investment_committee=True`: invoke `InvestmentCommitteeOrchestrator(report, ctx, budget=…).run()`, attach result to the response dict under `committee` key
- [ ] **Critical**: the agent-bypass path (`_analyze_with_agent` early-return path referenced in `docs/superpowers/plans/2026-05-16-action-plan-items.md:55`) must ALSO call the committee hook — confirm via grep before claiming done
- [ ] `.env.example` documents `INVESTMENT_COMMITTEE_BUDGET=12` and `INVESTMENT_COMMITTEE_ENABLED_BY_DEFAULT=false`
- [ ] DONE: end-to-end smoke — `pytest tests/test_analysis_service_committee.py` exercises async path with `enable_investment_committee=True` and asserts `committee` field is populated

### Task 1A-5: Renderers + language plumbing (domain E)

- [ ] In both renderers, add `_render_committee_minutes(committee: dict, labels: dict) -> list` that emits a `## 投委会会议纪要 / Investment Committee Minutes` section: PM verdict → debate summary → each master's one-paragraph view + score → risk flags
- [ ] Section is only rendered when `committee` field exists in the report (graceful when feature is opt-out)
- [ ] Discord empty-chunk guard (memory rule) — when committee block is large, ensure chunker doesn't emit empty trailing chunks
- [ ] Bilingual support: respect `report_language` from existing `src/report_language.py`. Prompt templates stay English (decision #7), outputs translated downstream as today
- [ ] DONE: `pytest tests/test_notification_committee.py tests/test_history_markdown_committee.py -q` green

### Task 1A-6: Backend documentation + CHANGELOG

- [ ] `docs/CHANGELOG.md` `[Unreleased]` — add (flat format):
  - `- [新功能] 后端投委会 multi-agent pipeline（Bull/Bear 辩论 + 4 大师视角 + Risk/PM）API opt-in，默认关闭`
  - `- [新功能] 报告新增「投委会会议纪要」段落，opt-in 时通过 enable_investment_committee=true 触发`
  - `- [改进] 异步任务参数链路新增 enable_investment_committee / committee_debate_rounds 透传`
- [ ] `.env.example` — `INVESTMENT_COMMITTEE_BUDGET_BASE=12`, `INVESTMENT_COMMITTEE_ENABLED_BY_DEFAULT=false`, `INVESTMENT_COMMITTEE_TIMEOUT_S=90`
- [ ] `requirements.txt` — add `langgraph==0.4.8` (pin exact)
- [ ] Backend docs in `docs/full-guide.md` 中文 — append "投委会模式（API 预览）" subsection
- [ ] Sprint 1B will follow with Web UI; do NOT update README feature list until 1B lands

### Task 1A-7: Sprint 1A acceptance gate

- [ ] `pip install -r requirements.txt` succeeds (new langgraph dep installs cleanly on Python 3.11)
- [ ] `./scripts/ci_gate.sh` green
- [ ] `python -m pytest -m "not network"` green — including all new committee tests
- [ ] **Backend smoke (manual curl or pytest)** on **one A-share + one US stock**:
  - Default analysis unaffected (no `committee` field in response)
  - With `enable_investment_committee=true`: budget respected (10/12/14 by rounds); minutes appear in markdown; PM verdict present; `status="ok"` when all agents complete
  - Forced timeout on one master → `status="partial"`; report still rendered; missing agent annotated
- [ ] HK stock smoke is **best-effort** in 1A (committee works language-agnostically; HK data fetch is orthogonal)
- [ ] Commit on `feat/investment-committee` branch, English message, do not push
- [ ] **Stop. Deliver to user with the 6-point structure. Wait for user approval before Sprint 1B starts.**

---

## Sprint 1B — Web UI opt-in (P0b)

**Goal:** Wrap Sprint 1A's API in a Web UI: toggle on both task-creation form and single-stock page, rounds selector, live cost estimate, and a CommitteeMinutesPanel rendering the response.

### Task 1B-1: Web type plumbing

- [ ] `apps/dsa-web/src/types/analysis.ts` — add `enable_investment_committee?: boolean` and `committee_debate_rounds?: 1|2|3` on `AnalyzeRequest`; default `false` / `2`
- [ ] `apps/dsa-web/src/api/analysis.ts` — forward new params
- [ ] `apps/dsa-web/src/stores/stockPoolStore.ts` — same defaults (memory: defaults live in TWO places — keep them in sync)

### Task 1B-2: CommitteeOptIn component

- [ ] New: `apps/dsa-web/src/components/committee/CommitteeOptIn.tsx`
  - Disclosure (collapsed by default) labelled "Advanced — Investment Committee (preview)"
  - Switch + radio group (1 / 2 / 3 rounds)
  - Live cost hint: `~{6 + 2*N + 2} extra LLM calls per stock` (matches backend formula)
- [ ] Wired into the single-stock analyze form AND the batch task-creation form
- [ ] Component tests (snapshot + interaction)

### Task 1B-3: CommitteeMinutesPanel component

- [ ] New: `apps/dsa-web/src/components/committee/CommitteeMinutesPanel.tsx`
  - Sections: PM verdict card → debate timeline → masters grid (4 cards using initials-in-coloured-circles per the locked decision) → risk strip
  - Each master card uses **"inspired lens" naming**: e.g. `Buffett-inspired value lens (巴菲特式价值视角)` on first render; subsequent cards use English-only
  - Missing personas → greyed-out card with "absent (timeout)" badge
  - Renders nothing when `report.committee` is undefined (graceful)
- [ ] Component tests + integration into `ReportSummary`

### Task 1B-4: Sprint 1B documentation + CHANGELOG

- [ ] `docs/CHANGELOG.md` `[Unreleased]` add:
  - `- [新功能] Web 端「召开投委会」opt-in 开关 + 辩论轮次选择器（个股页 + 批量任务表单）`
  - `- [新功能] 报告页新增「投委会会议纪要」面板（PM 决议 / 辩论时间线 / 大师视角网格 / 风险条）`
- [ ] `docs/README_EN.md` + `docs/README_CHT.md` + `README.md` — update feature table to mention committee mode (now that the user-visible UI is live)
- [ ] `docs/full-guide.md` — expand "投委会模式" section with screenshot + cost guidance

### Task 1B-5: Sprint 1B acceptance gate

- [ ] `cd apps/dsa-web && npm ci && npm run lint && npm run build` green
- [ ] Component tests green
- [ ] Manual UX smoke: toggle on, run analysis on one A-share + one US stock, screenshots attached to PR
- [ ] **Stop. Deliver to user with 6-point structure. Wait for user approval before Sprint 2.**

---

## Sprint 2 — Decision Journal + Reflection Loop (P1)

**Scope skeleton (will be expanded after Sprint 1 gate is approved):**

- New `src/services/decision_journal_service.py` — append-only markdown journal per stock under `data/decision_journals/<MARKET>/<STOCK_CODE>.md`
- After each `analyze_stock` success, write a journal entry: timestamp + summary verdict + score + key catalysts/risks + PM committee verdict if present
- On next analysis of the same stock: load last N entries, fetch price-at-decision and current price, compute raw return + alpha vs benchmark (`000300.SH` / `HSI` / `SPY` lookup via existing fetchers), inject a one-paragraph reflection into the LLM prompt
- New Web tab "复盘 / Decision Tracking" on stock detail page — renders journal entries with realised P&L

**Concurrency:** the task queue can run multiple `analyze_stock` calls in parallel; two parallel runs on the **same stock** would race the journal file. Sprint 2 must:
- Use a per-stock file lock (`fcntl.LOCK_EX` on POSIX) around journal read-modify-write
- Or use append-only writes with line-level atomicity guaranteed by the kernel (single `write()` of a complete entry) — preferred for resilience to crashes mid-write
- Decision: append-only with a fixed per-entry serialisation; reflection-time read is best-effort and tolerates a half-written entry by skipping it

**Other Sprint 2 traps:**
- Alpha computation must use adjusted close to handle splits/dividends; otherwise a 10:1 split makes a +200% raw return look like +2000%
- Journal files can grow unbounded — add a rotation policy (e.g. archive entries older than 2 years to `archive/<year>/`) before Sprint 2 closes
- Reflection prompt must respect token budget — if journal has 30+ entries, summarise older ones first

**Acceptance gate:** deliver, await user approval, commit.

## Sprint 3 — Qlib Alpha158 + LightGBM (P2)

**Required decisions before Sprint 3 spec writing (P9 recommends; confirm at Sprint 3 kickoff):**

| # | Question | P9 recommendation |
|---|----------|-------------------|
| Q1 | **Universe** — which stocks get quant signals? | A-share = CSI 300 components; US = S&P 500 components. HK = no quant (qlib doesn't ship HK data). Stocks outside the universe → silent no-op |
| Q2 | **Training window** | Rolling 3-year window, retrained **weekly** (Saturday GitHub Action). Walk-forward: train through `today - 7d`, predict on `today` |
| Q3 | **Forecast horizon** | Default `10 trading days` (~2 weeks; swing-trade horizon, balances signal-to-noise). Multi-horizon (5/10/20) is a Sprint 3.5 nice-to-have |
| Q4 | **IC computation** | Rank IC (Spearman) over a rolling 20-day window; report current IC + 60-day moving average |
| Q5 | **Low-IC gating** | If 4-week moving IC < 0.02 (essentially random) → hide forecast, show only factor quantiles with a "model currently uncertain" tag |
| Q6 | **No-artifact behaviour** | Silent no-op: log warning, omit the quant section. Default committee/LLM analysis unaffected |
| Q7 | **Role of forecast in report** | **Auxiliary observation only** — explicit caveat "statistical signal, not a recommendation". Forecast cannot raise PM verdict above what fundamentals/technicals justify; can lower a verdict when consistently bearish |

**Scope skeleton (post-decisions):**

- `data_provider/qlib_fetcher.py` — wraps qlib's data loader, materialises Alpha158 factors per stock
- `data/qlib/` — **gitignored** (GB-scale binary data); a `scripts/setup_qlib_data.sh` script downloads via `qlib_data --target_dir data/qlib --region cn` and again for `--region us`
- Weekly retrain GitHub Action — model artifact uploaded to a GitHub Release artifact (not committed); keeps last 8 weekly versions
- New `src/services/quant_signal_service.py` — exposes `get_factor_quantiles(stock_code) -> dict[str, float]` and `get_forecast(stock_code, horizon=10) -> Optional[dict]` (returns None for outside-universe stocks)
- Prompt injection: factor quantiles + forecast snapshot prepended to existing LLM analysis prompt as **"Quant Context (auxiliary)"** — explicit "auxiliary" framing enforced by prompt template
- Report additions: IC decay chart + grouped cumulative return chart (rendered via existing `md2img.py` pipeline)
- HK gap: documented limitation, keep HK on existing fetchers; HK stocks see no Quant Context section
- Acceptance gate: deliver, await user approval, commit

## Sprint 4 — Infrastructure polish (P3, SCOPED DOWN)

**Scope skeleton (revised based on recon — `RiskAgent` already exists):**

- LangGraph checkpoint resume integrated into `task_queue.py` so a crashed/restarted run resumes from the last successful agent node (only meaningful once the committee from Sprint 1 ships)
- Upgrade existing `RiskAgent` output to a structured `RiskAssessment` schema (position-limit %, tail-risk score, VaR estimate) — was previously soft/hard flags only
- Wire `RiskAgent` as a standalone callable from the orchestrator (independent of the committee flow) so default reports can also surface structured risk
- Acceptance gate: deliver, await user approval, commit, tag release as `vNEXT` candidate

---

## Cross-sprint risk register

| Risk | Mitigation |
|------|-----------|
| Weak-model (e.g. `gpt-5.4-mini`) ignores end-of-prompt instructions (memory) | All committee prompts embed schema into the JSON example block + Pydantic strict + 1-retry |
| Discord chunker emits empty trailing chunks on long committee output | Existing fix in `discord_sender.py` filters empty chunks — verify with a fixture |
| Bypass path (`_analyze_with_agent` early return) skips committee hook | Grep + dual-path test (already in user memory as a known footgun) |
| Param threading miss in async chain | Dedicated Task 1-4 step; smoke test asserts param reaches `analyze_stock` |
| Cost explosion | 12-call hard cap + opt-in default-off |
| Bull/Bear produce vacuous parallel arguments under weak models | Each prompt mandates "≥ 3 specific evidence items, citing tool outputs or data" before scoring |
| HK / non-US universe unsupported by qlib | Sprint 3 explicitly limits qlib coverage to A+US; HK keeps existing fetchers + skips ML forecast |
| LangGraph version pin breaks Python 3.11 wheel | Pin tested version; CI baseline verifies install |

---

## Rollback strategy (per-sprint)

| Sprint | Rollback |
|--------|---------|
| Sprint 1 | Feature is opt-in; revert by setting `INVESTMENT_COMMITTEE_ENABLED_BY_DEFAULT=false` and not exposing the Web toggle. Code is additive — `git revert` of the merge commit is safe |
| Sprint 2 | Journal is append-only; reflection injection is guarded by a feature flag `DECISION_JOURNAL_REFLECTION_ENABLED` |
| Sprint 3 | Quant signals injected into prompt only when `QUANT_SIGNAL_ENABLED=true` and the model artifact exists; missing artifact → silent no-op |
| Sprint 4 | Checkpoint resume is opt-in via `TASK_QUEUE_CHECKPOINT_ENABLED`; RiskAgent structured output is additive — old fields preserved |
