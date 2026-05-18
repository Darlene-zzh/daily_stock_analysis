# Sprint 1 Design Spec — Investment Committee & Master Personas (P0)

> Sprint 1 of the 4-sprint Professional Upgrade. See `docs/superpowers/plans/2026-05-18-professional-upgrade.md` for the master plan covering Sprint 2 (decision journal + reflection), Sprint 3 (qlib quant signals), Sprint 4 (infrastructure polish).

## 1 Goal & Non-Goals

### Goal
Ship a **Web-opt-in "Convene Investment Committee"** flow that, when enabled, runs a LangGraph multi-agent pipeline producing an additional "Investment Committee Minutes" section appended to the existing report. **Default analysis path is untouched.**

### Non-goals (Sprint 1)
- Decision journal / reflection (Sprint 2)
- Quant signal injection (Sprint 3)
- LangGraph checkpoint resume (Sprint 4)
- Real-time / streaming committee deliberation (Web UI shows the result after async completion)
- Multi-stock joint committee (Sprint 1 is single-stock only; `PortfolioAgent` already handles cross-stock)
- Adding new master personas beyond the four chosen (extensibility is a structural property, not a deliverable)

## 2 Boundary decisions (frozen with user 2026-05-18)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | LLM budget **scales with debate rounds**: `cap = 6 + 2N + 2` → 10 / 12 / 14 for 1 / 2 / 3 rounds. Env `INVESTMENT_COMMITTEE_BUDGET_BASE=12` controls baseline | Cost predictable for each round count; Web UI shows live estimate |
| 2 | Bull ↔ Bear debate rounds: **user-selectable in Web UI** (1 / 2 / 3, default 2) | Lets cost-conscious users dial down; default mirrors TradingAgents paper |
| 3 | Strategy-tool exposure (Sprint 1): **curated 5** — `ma` / `macd` / `boll` / `sentiment_aggregator` / `fundamentals_snapshot` | Caps tool-list token cost; covers 80% of use cases. Persona-specific tool sets deferred |
| 4 | Agent timeout / garbage output: **skip + PM annotates absence** | Resilience > completeness; one bad agent must not break the report |
| 5 | Web opt-in: **task-creation form AND single-stock page** (Sprint 1B) | Covers batch nightly and ad-hoc workflows |
| 6 | Inter-agent schema strictness: **tiered** (critical-strict + non-critical-optional + 1-retry + fallback object) | Prevents the "everything Optional = schema is decoration" trap |
| 7 | Language: **English prompts**, output follows existing `report_language` | Western lenses reproduce best in English prompts; existing translation pipeline handles output language |
| 8 | Display layer uses **"inspired lens" framing** — `Buffett-inspired value lens (巴菲特式价值视角)`, not "Warren Buffett says…" | Avoids implying real-person endorsement; internal `persona` ids stay snake_case English |
| 9 | LangGraph dependency: **Sprint 1 only `langgraph==0.4.8`**; `langgraph-checkpoint-sqlite>=3.0.1` deferred to Sprint 4 | Minimise dependency surface; checkpoint resume not used until Sprint 4 |
| 10 | Committee minutes persist to history DB via `history_service` | Sprint 2 reflection can pull past committee verdicts |

## 3 Existing assets we reuse (no rewrites)

Confirmed via recon at `src/agent/agents/` (2026-05-18):

| Asset | Path | Sprint 1 usage |
|-------|------|----------------|
| `BaseAgent` | `src/agent/agents/base_agent.py` | All new agents subclass this |
| `AgentContext`, `AgentOpinion` | `src/agent/protocols.py` | Reuse for cross-agent message passing; extend if needed |
| `RiskAgent` | `src/agent/agents/risk_agent.py` | Becomes the committee's Risk Manager node (no rewrite — graph just calls it) |
| `PortfolioAgent` | `src/agent/agents/portfolio_agent.py` | Stays at portfolio level; committee PM is a *new* per-stock decision aggregator |
| `DecisionAgent` / `TechnicalAgent` / `IntelAgent` | `src/agent/agents/*` | Available as tool sources for Bull/Bear/masters |
| Tool registry | `src/agent/tools/registry.py` + `src/agent/tools/{analysis,search,backtest,data,market}_tools.py` | Masters and researchers expose these as their `tool_names` |
| Strategy aggregator / router | `src/agent/strategies/{aggregator,router}.py` (SkillAggregator under the hood) | Strategies are wrapped as LangGraph tools |
| LLM adapter | `src/agent/llm_adapter.py` | LangGraph nodes call this — we do NOT add `langchain-openai`/`langchain-anthropic` |
| Report schema | `src/schemas/report_schema.py:AnalysisReportSchema` | Committee field is added as an **additive sibling schema**, not by mutating this |
| Report language | `src/report_language.py` | Output translation reuses this |
| Markdown renderers | `src/notification.py` + `src/services/history_service.py` | Both grow a `_render_committee_minutes` function |
| Async chain | `api/v1/endpoints/analysis.py:349 → src/services/task_queue.py:345,576 → src/services/analysis_service.py:42` | Two new opt-in params thread through |

## 4 New components — file inventory

| New file | Purpose |
|----------|---------|
| `src/schemas/committee_schema.py` | Pydantic v2 schemas — see §6 |
| `src/agent/budget.py` | `LLMCallBudget` class enforcing per-committee hard cap |
| `src/agent/agents/master_personas/__init__.py` | Registry of the 4 personas |
| `src/agent/agents/master_personas/warren_buffett.py` | Buffett persona (subclass of `BaseAgent`) |
| `src/agent/agents/master_personas/michael_burry.py` | Burry persona |
| `src/agent/agents/master_personas/cathie_wood.py` | Cathie Wood persona |
| `src/agent/agents/master_personas/nassim_taleb.py` | Taleb persona |
| `src/agent/agents/bull_researcher.py` | Bull-side researcher |
| `src/agent/agents/bear_researcher.py` | Bear-side researcher |
| `src/agent/agents/committee_pm.py` | Committee Portfolio Manager (per-stock aggregator) |
| `src/agent/orchestrator_committee.py` | LangGraph state machine wiring (the only new orchestrator) |
| `apps/dsa-web/src/components/committee/CommitteeOptIn.tsx` | Toggle + rounds selector |
| `apps/dsa-web/src/components/committee/CommitteeMinutesPanel.tsx` | Rendered minutes panel |
| `tests/test_committee_schema.py` | Schema round-trip + retry |
| `tests/test_master_personas.py` | Snapshot tests for the 4 personas |
| `tests/test_committee_graph.py` | LangGraph execution: happy path, timeout degradation, JSON drift retry |
| `tests/test_analysis_service_committee.py` | End-to-end through async chain |
| `tests/test_notification_committee.py` | Markdown render contract |
| `tests/test_history_markdown_committee.py` | History renderer contract |

## 5 Architecture

```
                    AnalyzeRequest (Web)
                         │ enable_investment_committee=true
                         │ committee_debate_rounds=2
                         ▼
        _handle_async_analysis_batch (api/v1/endpoints/analysis.py)
                         │
                         ▼
            TaskQueue.submit_tasks_batch → _execute_task
                         │
                         ▼
        AnalysisService.analyze_stock                    ◄─── existing LLM flow runs first
                         │ produces AnalysisReportSchema      (unchanged)
                         │
                         ▼
        ┌────────────────────────────────────────────────┐
        │ if enable_investment_committee:                │
        │   InvestmentCommitteeOrchestrator(             │
        │     report, ctx,                                │
        │     budget=LLMCallBudget(cap=12),               │
        │     debate_rounds=N                             │
        │   ).run() → CommitteeMinutes                   │
        └────────────────────────────────────────────────┘
                         │
                         ▼
        report["committee"] = minutes.model_dump()
                         │
                         ▼
        Notification + History renderers
        (both call _render_committee_minutes if "committee" present)
```

### LangGraph state machine

```
                          ┌─────────────────┐
                          │   START / ctx   │
                          └────────┬────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │  bull_researcher│
                          └────────┬────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │  bear_researcher│
                          └────────┬────────┘
                                   │
                  loop ◄───┐       │  (debate_rounds × bull↔bear)
                           │       ▼
                           └─── decide_continue
                                   │ debate_rounds exhausted OR budget low
                                   ▼
        ┌───────────────────┬──────┴──────┬───────────────────┐
        ▼                   ▼             ▼                   ▼
  master_buffett     master_burry   master_wood        master_taleb
        │                   │             │                   │
        └─────┬─────────────┴─────┬───────┴───────────┬───────┘
              │       (parallel — sub-graph fan-out)  │
              └──────────────────┬────────────────────┘
                                 ▼
                          ┌─────────────────┐
                          │    risk_node    │  (wraps existing RiskAgent)
                          └────────┬────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │ committee_pm    │
                          └────────┬────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │  END / minutes  │
                          └─────────────────┘
```

**Node-level rules:**
- Every node acquires `budget.acquire(node_name)` before its LLM call. If `remaining() == 0`, node short-circuits with `status="budget_exhausted"`.
- Every node has try/except → on exception, populate `state.errors[node_name]` and emit a `MasterOpinion`/`DebateExchange`/etc. with `status="failed"` + `error_summary`.
- Master fan-out uses LangGraph's parallel-branch primitive (modern API; refer to `~/reference_repos/TradingAgents/tradingagents/graph/setup.py`).

## 6 Schemas (Pydantic v2, lenient — mirrors existing `AnalysisReportSchema` style)

```python
# src/schemas/committee_schema.py
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class DebateExchange(BaseModel):
    """One Bull/Bear utterance."""
    model_config = ConfigDict(extra="ignore")
    side: Literal["bull", "bear"]
    round_index: int
    claim: Optional[str] = None           # ≤ 200 chars
    evidence: list[str] = Field(default_factory=list)  # ≥ 1 item enforced via post-validator
    rebuttal_to: Optional[str] = None     # short reference to prior claim
    confidence: Optional[float] = None    # 0..1


class MasterOpinion(BaseModel):
    """A single master persona's verdict."""
    model_config = ConfigDict(extra="ignore")
    persona: Literal["warren_buffett", "michael_burry", "cathie_wood", "nassim_taleb"]
    verdict: Optional[Literal["strong_buy", "buy", "hold", "avoid", "short"]] = None
    score: Optional[float] = None          # 0..10
    headline: Optional[str] = None          # one-liner explaining verdict
    rationale: Optional[str] = None         # 2-4 sentences
    key_evidence: list[str] = Field(default_factory=list)
    counter_view: Optional[str] = None      # what would change their mind
    tools_used: list[str] = Field(default_factory=list)
    status: Literal["ok", "failed", "budget_exhausted"] = "ok"
    error_summary: Optional[str] = None


class RiskAssessment(BaseModel):
    """Risk Manager output (wraps existing RiskAgent result)."""
    model_config = ConfigDict(extra="ignore")
    severity: Optional[Literal["none", "soft", "hard"]] = None
    red_flags: list[str] = Field(default_factory=list)
    suggested_position_pct: Optional[float] = None  # 0..1, % of equity
    veto: bool = False                              # if true, PM verdict capped at "hold"
    status: Literal["ok", "failed"] = "ok"
    error_summary: Optional[str] = None


class CommitteeMinutes(BaseModel):
    """Top-level committee output, attached to report['committee']."""
    model_config = ConfigDict(extra="ignore")
    version: Literal["1"] = "1"
    status: Literal["ok", "partial", "failed"] = "ok"   # top-level health signal
    debate_rounds: int
    debate: list[DebateExchange] = Field(default_factory=list)
    masters: list[MasterOpinion] = Field(default_factory=list)
    risk: Optional[RiskAssessment] = None
    pm_verdict: Optional[Literal["strong_buy", "buy", "hold", "avoid", "short"]] = None
    pm_score: Optional[float] = None
    pm_rationale: Optional[str] = None
    pm_dissents: list[str] = Field(default_factory=list)   # names of personas the PM overruled
    budget_used: int = 0
    budget_cap: int = 12
    missing_agents: list[str] = Field(default_factory=list)
    latency_ms: int = 0
```

**`status` semantics:**
- `ok` — all 4 master lenses + risk + PM completed successfully; no `missing_agents`
- `partial` — ≥ 1 missing_agents OR ≥ 1 master returned `status="failed"`, BUT PM still produced a verdict
- `failed` — PM itself could not produce a verdict (rare); treat the whole minutes as "advisory only"; the renderer downgrades the verdict card to a "committee inconclusive" notice

### Schema strictness tiers (frozen rule, applies to all four schemas above)

To prevent the "everything `Optional` = schema is decoration" anti-pattern:

| Tier | Fields | Validation |
|------|--------|-----------|
| **Critical** | `MasterOpinion.persona / .verdict / .score / .headline / .rationale / .key_evidence` (len ≥ 1); `DebateExchange.side / .round_index / .claim / .evidence` (len ≥ 1); `RiskAssessment.severity / .suggested_position_pct / .veto`; `CommitteeMinutes.status / .pm_verdict / .pm_score / .pm_rationale / .budget_used / .budget_cap` | Pydantic **strict** — missing critical field on first response triggers 1 retry with the failing schema embedded as a JSON example in the user message |
| **Non-critical** | `MasterOpinion.counter_view / .tools_used`; `DebateExchange.rebuttal_to / .confidence`; `RiskAssessment.red_flags`; `CommitteeMinutes.pm_dissents / .missing_agents / .latency_ms` | `Optional[…]` or `default_factory=list`; missing → leave empty, do not retry |

### Retry contract
1. Strict parse → if fails on a critical field, log the malformed JSON (truncated to 500 chars)
2. Retry **once** with the failing schema embedded as a JSON example at the top of the user message
3. If second attempt also fails → emit a fallback object with `status="failed"` + `error_summary`, do NOT raise
4. PM prompt receives `missing_agents` + a per-master `status` map so it can explicitly acknowledge gaps in its verdict

## 7 Prompt template skeleton (English-only, "inspired lens" framing)

**Critical product safety rule:** prompts must use the **inspired lens** framing, NOT first-person impersonation. The LLM is an analyst applying a methodology, not the real person. This rule applies to system prompt, output voice, and display strings.

Common structure (each persona swaps the bold blocks):

```
SYSTEM:
You are a senior equity analyst applying the **<Lens Name>** — the decision
framework canonically associated with **<Full Name>**. You speak as an
analyst, not as <Full Name> personally; never use first-person voice
impersonating the real person. Output is in third-person analyst voice
(e.g. "The position appears…", NOT "I, Buffett, see…").

The lens you apply:
1. <Tenet 1, e.g., "Prioritise economic moat and circle of competence">
2. <Tenet 2>
3. <Tenet 3>

You will receive: (a) a structured pre-analysis report on the stock,
(b) optionally one or more strategy-tool outputs from this curated toolbox:
`ma`, `macd`, `boll`, `sentiment_aggregator`, `fundamentals_snapshot`.

You MUST:
- Cite at least three concrete pieces of evidence from the materials provided
- Refuse to invent fundamentals you cannot verify in the supplied context
- If the case is outside this lens's analytical scope, return verdict="hold"
  and explicitly say so in `rationale`
- Output third-person analyst voice; do not impersonate <Full Name>

Output a single JSON object matching this schema (no markdown, no commentary outside JSON):
{
  "persona": "<persona id, e.g. warren_buffett>",
  "verdict": "strong_buy" | "buy" | "hold" | "avoid" | "short",
  "score": <0..10>,
  "headline": "<one sentence, analyst voice>",
  "rationale": "<2-4 sentences, analyst voice>",
  "key_evidence": ["<bullet>", "<bullet>", "<bullet>"],
  "counter_view": "<what would change the verdict>",
  "tools_used": []
}

USER:
Stock: {stock_code} ({stock_name})
Market: {market}
Pre-analysis report (JSON):
{report_json}
Available tools: {tool_summary}
```

### Lens name mapping

| `persona` id | English lens name | Chinese display |
|--------------|-------------------|-----------------|
| `warren_buffett` | Buffett-inspired value lens | 巴菲特式价值视角 |
| `michael_burry` | Burry-inspired contrarian lens | Burry 式逆向视角 |
| `cathie_wood` | Cathie Wood-inspired innovation lens | Cathie Wood 式创新成长视角 |
| `nassim_taleb` | Taleb-inspired tail-risk lens | Taleb 式尾部风险视角 |

The mapping table lives in `src/agent/agents/master_personas/__init__.py` as `PERSONA_DISPLAY` so both the renderer and the Web component import it from one source of truth.

Adapt each lens's tenets using the reference file at `~/reference_repos/ai-hedge-fund/src/agents/<persona>.py` — but rewrite the system-prompt voice to "analyst applying X-inspired lens" rather than "you are X".

## 8 API & param threading contract

### AnalyzeRequest additions (`api/v1/endpoints/analysis.py`)
```python
class AnalyzeRequest(BaseModel):
    # ... existing fields ...
    enable_investment_committee: bool = False
    committee_debate_rounds: int = Field(default=2, ge=1, le=3)
```

### Threading checklist (every hop adds the kwargs)
1. `_handle_async_analysis_batch` (`api/v1/endpoints/analysis.py:349`) — add to `submit_kwargs` dict
2. `TaskQueue.submit_tasks_batch` (`src/services/task_queue.py:345`) — add params + persist on `TaskInfo`
3. `TaskQueue._execute_task` (`src/services/task_queue.py:576`) — add params, pass to `AnalysisService`
4. `AnalysisService.analyze_stock` (`src/services/analysis_service.py:42`) — add params, invoke committee
5. **Bypass path**: search for `_analyze_with_agent` (or any early-return agent path); both branches must invoke the committee hook (user memory note: this trap exists)

### Test (Task 1-4)
Smoke test that with `enable_investment_committee=True` an end-to-end submission produces `result["committee"]["pm_verdict"]` set.

## 9 Web UI

### CommitteeOptIn.tsx
- Disclosure (collapsed by default) labelled "Advanced — Investment Committee (preview)"
- Inside: switch toggle + a radio group (`1 / 2 / 3 rounds`)
- Inline hint: "Adds ~12 LLM calls per stock; the report will include a committee minutes section"
- Wired into:
  - Single-stock analyze form
  - Batch task-creation form

### CommitteeMinutesPanel.tsx
- Renders the `committee` field from the report response
- **First-line health banner** based on `committee.status`:
  - `ok` → no banner (or subtle green tick)
  - `partial` → amber strip: "Committee delivered a verdict with N agent(s) absent"
  - `failed` → red strip: "Committee inconclusive — treat as advisory only" (verdict card hidden)
- Sections: PM verdict card → debate timeline → lenses grid (one card per persona) → risk strip
- Each lens card uses **"inspired lens" display strings** from the `PERSONA_DISPLAY` mapping (imported from `src/agent/agents/master_personas/__init__.py` mirror in `apps/dsa-web/src/utils/personaDisplay.ts`):
  - Card title: lens name (e.g. `Buffett-inspired value lens`)
  - Subtitle in Chinese mode (first card only): `巴菲特式价值视角`
  - Avatar: initials in coloured circle (WB amber / MB red / CW indigo / NT slate)
- Card body: verdict chip + headline + score + collapsible rationale + counter-view
- Missing lenses render as a greyed-out card with "absent" badge — never imply the real person "refused to comment"

### Defaults — two places to update (memory note)
- `apps/dsa-web/src/types/analysis.ts` — type defaults + API typings
- `apps/dsa-web/src/stores/stockPoolStore.ts` — default form values

## 10 Renderers — bilingual contract

Both `src/notification.py` and `src/services/history_service.py` grow:

```python
def _render_committee_minutes(committee: dict, labels: dict) -> list[str]:
    """
    Returns markdown lines for the committee section. Returns [] if committee is empty.
    """
```

Section heading respects `report_language`:
- `zh`: `## 📋 投委会会议纪要`
- `en`: `## 📋 Investment Committee Minutes`
- bilingual modes: section appears once with bilingual subtitles, matching action-plan-items style (memory: `: ` prefix removed in 2026-05 cleanup — follow the same pattern)

Inside the section, the order is:
1. **Status line** (only if `status != "ok"`): e.g. `> Status: partial — N lens(es) absent (committee verdict still issued)`
2. PM verdict + score + rationale + dissents (suppressed when `status == "failed"`)
3. Risk strip (severity + red flags + suggested position %)
4. Debate timeline (compact: `Round 1 — Bull: <claim>; Bear: <claim>`)
5. Lens grid: lens display name (per §7 mapping) + verdict + score + 1-line headline + absent badge if `status="failed"`

The renderer **must use the same `PERSONA_DISPLAY` mapping** as the prompt builder — single source of truth, no string duplication.

Each renderer's tests pin contract via fixtures.

### Discord chunker guard
The committee section can be long. The existing empty-trailing-chunk guard in `src/notification_sender/discord_sender.py` (added in user memory) must remain effective; the test must include a fixture that produces exactly N×limit characters in the committee section.

## 11 Failure modes + mitigations

| Failure | Trigger | Mitigation |
|---------|---------|-----------|
| Master returns malformed JSON | Weak model (`gpt-5.4-mini`) ignores instructions | Strict parse + 1 retry with embedded schema example; if still fails → `status="failed"` |
| Persona refuses to answer (circle-of-competence) | Buffett asked about pre-revenue biotech | Verdict captured as `hold` + rationale documented; NOT treated as failure |
| Bear keeps repeating same claim | Pathological LLM loop | Debate state hashes each utterance; identical utterance twice → force exit current debate round |
| Risk node times out | Slow tool call cascade | Skip + PM annotates "Risk Manager absent — verdict treated as advisory only"; verdict cap at `buy` (not `strong_buy`) when risk absent |
| Whole graph exceeds wall-clock (e.g. 90 s) | Multiple slow LLMs | Top-level orchestrator has `timeout=90s` env-configurable; on timeout → `committee` field gets `status="partial"` + whatever did complete |
| Budget exhausted mid-debate | Initial estimate too low | PM still runs with whatever state exists; `budget_used` reported |
| Bypass path skips committee | `_analyze_with_agent` early return | Test in `test_analysis_service_committee.py` parametrised over both paths |
| Discord 400 on empty chunk | Long committee section ends on whitespace | Empty-chunk guard test fixture |
| Frontend renders before backend has `committee` | Eager rendering of partial response | Component renders `null` when `committee` is undefined; no spinner inside the panel |

## 12 Testing matrix (Sprint 1 gate)

| Layer | File | What it asserts |
|-------|------|----------------|
| Schema | `tests/test_committee_schema.py` | 3 fixture JSONs (perfect / missing / garbage) → strict / retry / fallback |
| Persona | `tests/test_master_personas.py` | Each persona's `system_prompt()` ≤ 2000 tokens; deterministic with fixed seed |
| Graph happy | `tests/test_committee_graph.py::test_happy_path` | 12-call budget covers full run; final `CommitteeMinutes` has all four masters + risk + pm verdict |
| Graph degradation | `tests/test_committee_graph.py::test_master_timeout` | One master forced to timeout → graph completes, PM annotates absence |
| Graph drift | `tests/test_committee_graph.py::test_json_drift_retry` | LLM stub returns garbage once then valid → second attempt succeeds, `budget_used` increments by 2 |
| Service | `tests/test_analysis_service_committee.py` | Both default and bypass paths produce `committee` when opt-in |
| Renderer (push) | `tests/test_notification_committee.py` | Markdown matches fixture for `zh` / `en` / `bilingual` |
| Renderer (history) | `tests/test_history_markdown_committee.py` | Same contract as push |
| Web | `apps/dsa-web/src/components/committee/__tests__/*.test.tsx` | Toggle wiring + minutes panel render |
| Lint/build | `npm run lint && npm run build` | Green |
| Async chain smoke | `tests/test_async_chain_committee.py` | Param round-trip through 4 hops |

**Network-tagged tests:** none in Sprint 1 — the LangGraph runs use a stubbed LLM adapter; real LLM exercise is manual.

## 13 Locked decisions (added 2026-05-18 after user Q&A)

1. **LangGraph version pin** — `langgraph==0.4.8` + `langgraph-checkpoint-sqlite==2.0.0`. Matches TradingAgents minimum so Sprint 4 can directly adopt their `checkpointer.py` pattern.
2. **Persona avatars (Web)** — MVP uses **initials in coloured circles** (WB amber / MB red / CW indigo / NT slate). Design pass to upgrade to custom SVGs deferred to a polish ticket; not a Sprint 1 blocker.
3. **Strategy-tool exposure** — Sprint 1 exposes a **curated 5** to all four personas: `ma` (均线), `macd`, `boll`, `sentiment_aggregator`, `fundamentals_snapshot`. Persona-specific tool sets deferred (Sprint 1.5+).
4. **Committee minutes persistence** — **Write to history DB alongside the full report** via `history_service`. The Web "history" page surfaces the minutes; Sprint 2 reflection can pull committee verdicts back out.
5. **Persona names in Chinese reports** — Keep English name as canonical; **first mention adds Chinese in parentheses**, e.g., `Warren Buffett（巴菲特）`; subsequent mentions in the same report use English only. Mapping table lives in `src/agent/agents/master_personas/__init__.py`.
