# Committee Timeout Bump + missing_agents Tagging + Bilingual Committee Prompts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复用户测试 INTC（US 股 + 中文报告）时观察到的两个回归 —— "3 位大师缺席"（committee timeout 90s 不够用，剩余 master 没被标记 missing）以及 "委员会全英文"（orchestrator prompts 不感知 `report_language`）。本计划落地 **A**（默认超时 90→180s）+ **C**（master fan-out break 路径补标 missing_agents）+ **D**（委员会 prompts 跟随 `report_language` 输出中文）三项修复。**B**（master 并行化）留待后续独立计划。

**Architecture:**

- **A. Timeout 默认值**：把 [`src/agent/budget.py:38`](src/agent/budget.py#L38) 的 `DEFAULT_TIMEOUT_S = 90` 提到 `180`。同步更新 `.env.example` 和 `docs/full-guide.md` 注释中的 90 秒提示。
- **C. master 漏标 missing_agents**：[`orchestrator_committee.py:244-249`](src/agent/orchestrator_committee.py#L244-L249) 的 master fan-out 循环在 `_past_deadline` 时 `break`，但**未将未运行的 persona 加入 `state["missing_agents"]`，也未把 failed_master_opinion 占位写入 `state["masters"]`**。修复方法：当 deadline 触发时，遍历剩余 `DEFAULT_PERSONA_ORDER`，为每个未完成 persona 追加 `failed_master_opinion(persona, error_summary="deadline reached before invocation")` 和 `state["missing_agents"].append(f"master_{persona}")`，使前后端数据一致（renderer 已按 `m.status != 'ok'` 标 "缺席"，所以行为不变；变的是 `missing_agents` 列表准确性）。
- **D. 委员会双语 prompt**：在 `AgentContext` 加 `report_language: str = "zh"` 字段，由 [`analysis_service.py:505-509`](src/services/analysis_service.py#L505-L509) 构造 ctx 时填入。在 `InvestmentCommitteeOrchestrator` 加 `_language_suffix()` 辅助方法，并在 5 处 prompt（bull/bear/master/risk/pm）的 `system_prompt` 后拼接该 suffix。当 `report_language == "zh"` 时 suffix 要求 JSON 键名、verdict/side/severity 枚举、persona ID 保持英文，但 `headline`/`rationale`/`claim`/`evidence`/`red_flags`/`pm_rationale` 等自由文本字段用简体中文。保持向后兼容：`report_language == "en"` 或 ctx 未设置时不追加 suffix（current behavior）。

**Tech Stack:** Python 3.11, pytest, dataclasses (`AgentContext`), LangGraph (committee orchestrator), Pydantic v2 (CommitteeMinutes schema).

---

## Pre-flight

- [ ] **Step 0: 创建分支**

Run: `git checkout -b feat/committee-timeout-and-bilingual`
Expected: `Switched to a new branch 'feat/committee-timeout-and-bilingual'`

---

## Phase A: 委员会超时默认值 90 → 180 秒

### Task A1: 写失败测试 — `resolve_timeout_s()` 默认返回 180

**Files:**
- Modify: `tests/test_agent_budget.py`（新建或追加）
- Modify: `src/agent/budget.py:38`

- [ ] **Step 1: 检查测试文件是否存在**

Run: `ls tests/test_agent_budget.py 2>&1 || echo MISSING`

如 MISSING，新建该文件，否则追加测试到现有文件。

- [ ] **Step 2: 写失败测试**

新建/追加 `tests/test_agent_budget.py`：

```python
"""Tests for the committee budget module — timeout resolution + cap."""
import importlib

import pytest

from src.agent.budget import DEFAULT_TIMEOUT_S, resolve_timeout_s


def test_default_timeout_is_180_seconds():
    """Default committee wall-clock timeout must be 180s.

    Why: with 4 debate rounds + 4 master fan-outs + retry budget,
    90s was empirically insufficient (see INTC 2026-05-20 incident
    where 3 masters were silently skipped at the deadline break).
    """
    assert DEFAULT_TIMEOUT_S == 180


def test_resolve_timeout_s_defaults_to_180_when_env_absent(monkeypatch):
    monkeypatch.delenv("INVESTMENT_COMMITTEE_TIMEOUT_S", raising=False)
    assert resolve_timeout_s() == 180


def test_resolve_timeout_s_respects_env_override(monkeypatch):
    monkeypatch.setenv("INVESTMENT_COMMITTEE_TIMEOUT_S", "300")
    assert resolve_timeout_s() == 300


def test_resolve_timeout_s_falls_back_to_default_on_garbage(monkeypatch):
    monkeypatch.setenv("INVESTMENT_COMMITTEE_TIMEOUT_S", "not-a-number")
    assert resolve_timeout_s() == DEFAULT_TIMEOUT_S
```

- [ ] **Step 3: 跑测试验证 FAIL**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_agent_budget.py -q`
Expected: 2 failures — `test_default_timeout_is_180_seconds` 和 `test_resolve_timeout_s_defaults_to_180_when_env_absent` 都失败（实际值是 90）。

- [ ] **Step 4: 改实现 — `src/agent/budget.py:38`**

把：

```python
DEFAULT_TIMEOUT_S = 90
```

改为：

```python
DEFAULT_TIMEOUT_S = 180
```

- [ ] **Step 5: 跑测试验证 PASS**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_agent_budget.py -q`
Expected: 4 passed

- [ ] **Step 6: 回归 — 跑既有 committee 测试套件**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_committee_graph.py tests/test_analysis_service_committee.py tests/test_master_personas.py tests/test_committee_schema.py -q`
Expected: 全 PASS（既有 `test_wall_clock_timeout_short_circuits_remaining_nodes` 用 `timeout_s=0` 显式覆盖，不依赖默认值，因此不受影响）。

- [ ] **Step 7: Stage**

Run: `git add src/agent/budget.py tests/test_agent_budget.py`

---

### Task A2: 更新 `.env.example` 与中文文档

**Files:**
- Modify: `.env.example:787`
- Modify: `docs/full-guide.md:1411`

- [ ] **Step 1: 改 `.env.example`**

读 `.env.example` 第 787 行 — 当前为：

```
# INVESTMENT_COMMITTEE_TIMEOUT_S=90
```

改为：

```
# INVESTMENT_COMMITTEE_TIMEOUT_S=180
```

⚠️ 该文件已被 PUA Integrity Guard 标记为 secrets-adjacent，编辑前**先用 Read 查看上下文确认只动这一行**，避免误改密钥相关注释。

- [ ] **Step 2: 改中文文档**

读 `docs/full-guide.md` 第 1411 行 — 当前为：

```
- 单次运行 wall-clock 超时由 `INVESTMENT_COMMITTEE_TIMEOUT_S`（默认 90 秒）控制；超时会跳过未完成节点并降级为 `status="partial"`。
```

改为：

```
- 单次运行 wall-clock 超时由 `INVESTMENT_COMMITTEE_TIMEOUT_S`（默认 180 秒）控制；超时会跳过未完成节点并降级为 `status="partial"`。
```

- [ ] **Step 3: 查英文文档是否有同源说明**

Run: `grep -rn "INVESTMENT_COMMITTEE_TIMEOUT_S\|默认 90\|default 90" docs/ 2>/dev/null`
Expected: 只命中 `docs/full-guide.md`（已改）。若命中其他文件，同步更新；若无其他命中，跳过。

- [ ] **Step 4: Stage**

Run: `git add .env.example docs/full-guide.md`

---

### Task A3: CHANGELOG entry (Phase A)

**Files:**
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: 在 `[Unreleased]` 段追加扁平条目**

打开 `docs/CHANGELOG.md`，定位 `## [Unreleased]` 段，在末尾追加一行（保持扁平格式，不要加 `### 类目标题`）：

```markdown
- [改进] 投委会 wall-clock 超时默认值由 90s 提升到 180s（`INVESTMENT_COMMITTEE_TIMEOUT_S`），避免 4 大师串行 fan-out + retry 时剩余 master 被静默跳过。
```

- [ ] **Step 2: Stage**

Run: `git add docs/CHANGELOG.md`

---

### Phase A Commit Gate ⏸️

- [ ] **Step 1: `git status` 自检**

Run: `git status --short`
Expected: 5 个 staged 文件：`src/agent/budget.py`、`tests/test_agent_budget.py`、`.env.example`、`docs/full-guide.md`、`docs/CHANGELOG.md`。

- [ ] **Step 2: 暂停等用户确认提交**

⚠️ **STOP**：按用户偏好（phase commit gating），此处暂停。向用户报告：
- 改了什么：默认 timeout 90→180s；测试 4 passed；env + docs + changelog 同步。
- 验证情况：`tests/test_agent_budget.py`（4 passed），committee 回归套件全绿。
- 风险点：原 90s 用户若依赖快速失败，可通过 env 显式回设 90 保留旧行为。
- 等待用户回复 "commit A" 后再执行。

- [ ] **Step 3: 收到批准后提交**

Run:

```bash
git commit -m "chore(committee): bump default wall-clock timeout 90s -> 180s

The committee orchestrator runs 4 debate rounds + 4 master fan-outs + risk
+ PM serially; with 1-2 parse retries the wall-clock easily exceeds 90s.
INTC test on 2026-05-20 hit 128s total and three masters were silently
skipped at the deadline break in _master_node fan-out. Bump default to
180s to give the serial chain enough headroom; users on faster paid LLM
keys can dial back via INVESTMENT_COMMITTEE_TIMEOUT_S env var.

- src/agent/budget.py: DEFAULT_TIMEOUT_S 90 -> 180
- .env.example, docs/full-guide.md: documented new default
- tests/test_agent_budget.py: lock default + env-override behavior"
```

---

## Phase C: master fan-out break 路径补标 missing_agents

### Task C1: 写失败测试 — 超时跳过的 master 必须出现在 missing_agents 且有 failed 占位

**Files:**
- Modify: `tests/test_committee_graph.py`

- [ ] **Step 1: 在 `tests/test_committee_graph.py` 末尾追加测试**

```python
def test_deadline_in_master_fanout_tags_skipped_personas_as_missing(monkeypatch):
    """When deadline trips DURING master fan-out, remaining personas must
    appear in both ``minutes.masters`` (as failed placeholders) AND
    ``minutes.missing_agents``.

    Regression: prior to this fix the deadline-break path in
    ``_master_node`` fan-out (orchestrator_committee.py:244-249) silently
    dropped the remaining personas, leaving missing_agents inconsistent
    with the actual list of LLM calls that were skipped. The UI inferred
    absence by re-iterating DEFAULT_PERSONA_ORDER which masked the bug,
    but ``missing_agents`` data itself was wrong (causing the partial
    banner's count to under-report and the renderer footnote to drift).
    """
    # 4 debate replies + 1 buffett reply, then we monkeypatch time so the
    # deadline trips before the loop reaches Burry.
    responses = [
        _bull_payload(1),
        _bear_payload(1),
        _bull_payload(2),
        _bear_payload(2),
        _master_payload("warren_buffett"),
        # No more responses needed — the next call would be Burry, but
        # the deadline trips before that.
        _pm_payload(status="partial"),
    ]
    llm = StubLLM(responses)
    budget = LLMCallBudget(cap=14)

    orch = InvestmentCommitteeOrchestrator(
        _make_ctx(),
        report_json={"summary": "x"},
        budget=budget,
        llm_callable=llm,
        debate_rounds=2,
        timeout_s=999,  # disable real wall-clock; we'll patch time
    )

    # Trip the deadline immediately after Buffett completes.
    import src.agent.orchestrator_committee as oc_mod
    real_time = oc_mod.time.time
    call_state = {"buffett_done": False}

    def fake_time():
        # First the orchestrator records t0; let real time flow until
        # after Buffett's master_node completes, then return a value past
        # the deadline so subsequent _past_deadline() calls short-circuit.
        if call_state["buffett_done"]:
            return real_time() + 10_000
        return real_time()

    monkeypatch.setattr(oc_mod.time, "time", fake_time)

    # Hook: after Buffett's master_node appends to state["masters"], flip
    # the time fake. We override _master_node to flag the state.
    real_master_node = orch._master_node

    def wrapped_master_node(state, persona_id):
        result = real_master_node(state, persona_id)
        if persona_id == "warren_buffett":
            call_state["buffett_done"] = True
        return result

    monkeypatch.setattr(orch, "_master_node", wrapped_master_node)

    result = orch.run()
    minutes = result.minutes

    # Buffett succeeded
    buff = next(m for m in minutes.masters if m.persona == "warren_buffett")
    assert buff.status == "ok"

    # The other 3 personas must appear as failed placeholders (NOT silently absent)
    for persona in ("michael_burry", "cathie_wood", "nassim_taleb"):
        m = next((x for x in minutes.masters if x.persona == persona), None)
        assert m is not None, f"{persona} must be appended as failed placeholder"
        assert m.status == "failed", f"{persona} should have status=failed"
        assert m.error_summary, f"{persona} should have non-empty error_summary"

    # missing_agents must list all 3 skipped masters (and risk too, since
    # the same deadline trip prevents risk from running)
    assert "master_michael_burry" in minutes.missing_agents
    assert "master_cathie_wood" in minutes.missing_agents
    assert "master_nassim_taleb" in minutes.missing_agents
    assert "risk" in minutes.missing_agents

    # status must be partial (3 masters + risk missing)
    assert minutes.status == "partial"
```

- [ ] **Step 2: 跑测试验证 FAIL**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_committee_graph.py::test_deadline_in_master_fanout_tags_skipped_personas_as_missing -v`
Expected: FAIL — `michael_burry must be appended as failed placeholder` 断言失败（实际 `state["masters"]` 只有 1 个 Buffett，3 个被静默跳过）。

---

### Task C2: 修复 — 在 master fan-out 的 `break` 路径补占位 + 标 missing

**Files:**
- Modify: `src/agent/orchestrator_committee.py:243-249`

- [ ] **Step 1: 读当前代码段确认上下文**

读 [`src/agent/orchestrator_committee.py:240-260`](src/agent/orchestrator_committee.py#L240-L260)。

- [ ] **Step 2: 改实现**

把原：

```python
        # Master fan-out (deterministic order = serial for now;
        # parallelisation hook can plug into LangGraph later)
        for persona_id in DEFAULT_PERSONA_ORDER:
            if self._past_deadline(state):
                break
            if not self._has_completed_master(state, persona_id):
                self._master_node(state, persona_id)
                self._snapshot(state)
```

替换为：

```python
        # Master fan-out (deterministic order = serial for now;
        # parallelisation hook can plug into LangGraph later).
        # When the deadline trips mid-fan-out, append failed placeholders
        # for the remaining personas so minutes.masters keeps a stable
        # 4-element shape AND minutes.missing_agents accurately lists
        # which personas were skipped — symmetric with the risk path
        # below (line 257).
        for persona_id in DEFAULT_PERSONA_ORDER:
            if self._past_deadline(state):
                for remaining in DEFAULT_PERSONA_ORDER:
                    if self._has_completed_master(state, remaining):
                        continue
                    node = f"master_{remaining}"
                    if node in state["missing_agents"]:
                        continue
                    fb = failed_master_opinion(
                        remaining,
                        error_summary="deadline reached before invocation",
                    )
                    state["masters"].append(fb.model_dump())
                    state["missing_agents"].append(node)
                break
            if not self._has_completed_master(state, persona_id):
                self._master_node(state, persona_id)
                self._snapshot(state)
```

- [ ] **Step 3: 跑新测试验证 PASS**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_committee_graph.py::test_deadline_in_master_fanout_tags_skipped_personas_as_missing -v`
Expected: PASS

- [ ] **Step 4: 跑既有 committee 回归套件**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_committee_graph.py tests/test_analysis_service_committee.py tests/test_committee_checkpoint_resume.py tests/test_history_markdown_committee.py tests/test_notification_committee.py -q`
Expected: 全 PASS。`test_master_timeout_triggers_partial_status` 和 `test_wall_clock_timeout_short_circuits_remaining_nodes` 既有行为不变。

- [ ] **Step 5: Stage**

Run: `git add src/agent/orchestrator_committee.py tests/test_committee_graph.py`

---

### Task C3: CHANGELOG entry (Phase C)

**Files:**
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: 追加扁平条目**

在 `## [Unreleased]` 段追加：

```markdown
- [修复] 投委会 master fan-out 在超时触发时，未执行的 persona 现在会以 `status="failed"` 占位写入 `minutes.masters` 并加入 `missing_agents`，前后端 partial 状态计数与渲染一致（之前是渲染层凭 `DEFAULT_PERSONA_ORDER` 兜底，`missing_agents` 数据本身漏标）。
```

- [ ] **Step 2: Stage**

Run: `git add docs/CHANGELOG.md`

---

### Phase C Commit Gate ⏸️

- [ ] **Step 1: `git status` 自检**

Run: `git status --short`
Expected: 3 个 staged 文件：`src/agent/orchestrator_committee.py`、`tests/test_committee_graph.py`、`docs/CHANGELOG.md`。

- [ ] **Step 2: 等用户确认**

向用户报告 Phase C：
- 改了什么：master fan-out break 路径补 `failed_master_opinion` 占位 + `missing_agents` 标记。
- 验证情况：新增 1 个回归测试 + 既有 committee 套件全绿。
- 风险点：`minutes.masters` 长度由 "可能 < 4" 变为 "始终 4"，依赖 `len(masters)` 判断的下游需 audit；渲染层已按 `m.status != 'ok'` 标 absent，不受影响。
- 等用户回复 "commit C" 后再提交。

- [ ] **Step 3: 收到批准后提交**

Run:

```bash
git commit -m "fix(committee): tag deadline-skipped masters as missing + failed placeholder

When the wall-clock deadline tripped mid-fan-out, _master_node loop's
break path silently dropped the remaining personas: they did not get a
failed_master_opinion placeholder in state[\"masters\"] and they were
never appended to state[\"missing_agents\"]. The web UI's LensCard
inferred absence by re-iterating DEFAULT_PERSONA_ORDER which masked
the bug, but minutes.missing_agents data itself under-reported, and
the partial banner count was wrong.

This change makes the master fan-out break path symmetric with the
risk path (line 257): for each remaining persona, append a
failed_master_opinion with error_summary='deadline reached before
invocation' AND add master_<persona> to missing_agents.

- src/agent/orchestrator_committee.py: deadline branch in master loop
- tests/test_committee_graph.py: new regression test"
```

---

## Phase D: 委员会 prompts 双语化（跟随 `report_language`）

### Task D1: 给 `AgentContext` 加 `report_language` 字段

**Files:**
- Modify: `src/agent/protocols.py:62-93`
- Modify: `tests/test_agent_context_language.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_agent_context_language.py`：

```python
"""Tests that AgentContext carries report_language for downstream agents."""
from src.agent.protocols import AgentContext


def test_agent_context_default_report_language_is_zh():
    """Default report_language is 'zh' — matches main analyzer default.

    Why: the committee orchestrator branches on ctx.report_language to
    append a Chinese-output suffix to its prompts. Defaulting to 'zh'
    means callers that omit the field (e.g. older test fixtures) still
    get the Chinese behavior expected by the rest of the pipeline.
    """
    ctx = AgentContext(stock_code="AAPL")
    assert ctx.report_language == "zh"


def test_agent_context_accepts_explicit_report_language():
    ctx = AgentContext(stock_code="AAPL", report_language="en")
    assert ctx.report_language == "en"


def test_agent_context_report_language_independent_of_meta():
    """report_language is a top-level field, not buried in meta."""
    ctx = AgentContext(stock_code="AAPL", report_language="en", meta={"market": "US"})
    assert ctx.report_language == "en"
    assert ctx.meta == {"market": "US"}
```

- [ ] **Step 2: 跑测试验证 FAIL**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_agent_context_language.py -q`
Expected: FAIL — `AttributeError: 'AgentContext' object has no attribute 'report_language'`。

- [ ] **Step 3: 改实现**

读 [`src/agent/protocols.py:60-93`](src/agent/protocols.py#L60-L93)。在 `@dataclass class AgentContext:` 内、`stock_name: str = ""` 之后、`session_id: str = ""` 之前（保持 identity 字段连续），插入：

```python
    report_language: str = "zh"  # "zh" | "en" — propagated to committee prompts for bilingual output
```

最终该段约为：

```python
@dataclass
class AgentContext:
    """Shared context carried across all agents in a single run."""

    # --- identity ---
    query: str = ""
    stock_code: str = ""
    stock_name: str = ""
    report_language: str = "zh"  # "zh" | "en" — propagated to committee prompts for bilingual output
    session_id: str = ""
    ...
```

- [ ] **Step 4: 跑测试验证 PASS**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_agent_context_language.py -q`
Expected: 3 passed

- [ ] **Step 5: 回归 — 确保现有 AgentContext 使用方未破**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_committee_graph.py tests/test_master_personas.py tests/test_analysis_service_committee.py -q`
Expected: 全 PASS（dataclass 加默认字段不会破老的位置参数构造）。

- [ ] **Step 6: Stage**

Run: `git add src/agent/protocols.py tests/test_agent_context_language.py`

---

### Task D2: 在 `analysis_service.py` 构造 ctx 时填入 `report_language`

**Files:**
- Modify: `src/services/analysis_service.py:505-509`
- Modify: `tests/test_analysis_service_committee.py`

- [ ] **Step 1: 检查既有测试是否覆盖 ctx 构造**

Run: `grep -n "AgentContext\|report_language" tests/test_analysis_service_committee.py | head -10`

如已覆盖，追加新测试用例；否则新增。

- [ ] **Step 2: 写失败测试**

在 `tests/test_analysis_service_committee.py` 末尾追加：

```python
def test_invoke_committee_threads_report_language_into_agent_context(monkeypatch):
    """The committee invocation must propagate result.report_language into
    AgentContext.report_language so the orchestrator can branch on it.

    Why: prior to this wiring the committee orchestrator always emitted
    English prompts regardless of the analyzer's report_language setting,
    causing US/zh reports to ship with English committee minutes (debate,
    master lenses, PM rationale) — see 2026-05-20 INTC incident.
    """
    from unittest.mock import MagicMock, patch
    from src.services.analysis_service import AnalysisService

    captured_ctx = {}

    class _SpyOrchestrator:
        def __init__(self, ctx, *args, **kwargs):  # noqa: ARG002
            captured_ctx["ctx"] = ctx

        def run(self):
            # Return a minimal partial minutes so the service flow completes.
            from src.schemas.committee_schema import failed_committee_minutes
            from src.agent.orchestrator_committee import CommitteeRunResult
            return CommitteeRunResult(
                minutes=failed_committee_minutes(
                    debate_rounds=2,
                    budget_used=0,
                    budget_cap=14,
                    error_summary="stub",
                    missing_agents=[],
                    debate=[],
                    masters=[],
                    risk=None,
                    latency_ms=0,
                ),
                raw_state={},
                duration_s=0.01,
            )

    svc = AnalysisService()
    fake_result = MagicMock()
    fake_result.code = "AAPL"
    fake_result.name = "Apple Inc."
    fake_result.report_language = "en"

    with patch(
        "src.services.analysis_service.InvestmentCommitteeOrchestrator",
        _SpyOrchestrator,
    ):
        svc._invoke_committee(
            stock_code="AAPL",
            result=fake_result,
            response={"report": {"summary": "x"}, "stock_name": "Apple Inc."},
            debate_rounds=2,
        )

    ctx = captured_ctx["ctx"]
    assert ctx.report_language == "en"
```

- [ ] **Step 3: 跑测试验证 FAIL**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_analysis_service_committee.py::test_invoke_committee_threads_report_language_into_agent_context -v`
Expected: FAIL — `ctx.report_language == 'zh'`（默认）而非 `'en'`，因为 ctx 构造未填入。

- [ ] **Step 4: 改实现**

读 [`src/services/analysis_service.py:495-525`](src/services/analysis_service.py#L495-L525) 确认上下文。把：

```python
        normalised = normalize_stock_code(stock_code)
        if is_hk_stock_code(normalised):
            market = "HK"
        elif is_us_stock_code(normalised):
            market = "US"
        else:
            market = "A"
        stock_name = response.get("stock_name") or getattr(result, "name", None) or ""
        ctx = AgentContext(
            stock_code=stock_code,
            stock_name=stock_name,
            meta={"market": market},
        )
```

改为：

```python
        normalised = normalize_stock_code(stock_code)
        if is_hk_stock_code(normalised):
            market = "HK"
        elif is_us_stock_code(normalised):
            market = "US"
        else:
            market = "A"
        stock_name = response.get("stock_name") or getattr(result, "name", None) or ""
        report_language = normalize_report_language(
            getattr(result, "report_language", None)
            or getattr(get_config(), "report_language", "zh")
        )
        ctx = AgentContext(
            stock_code=stock_code,
            stock_name=stock_name,
            report_language=report_language,
            meta={"market": market},
        )
```

确认文件顶部已 `from src.report_language import normalize_report_language`（[analysis_service.py:24](src/services/analysis_service.py#L24) 已存在）。`get_config` 也已在文件中使用（[analysis_service.py:128](src/services/analysis_service.py#L128)）。

- [ ] **Step 5: 跑测试验证 PASS**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_analysis_service_committee.py -q`
Expected: 全 PASS（新增测试 + 既有用例）。

- [ ] **Step 6: Stage**

Run: `git add src/services/analysis_service.py tests/test_analysis_service_committee.py`

---

### Task D3: 在 orchestrator 加 `_language_suffix()` + 写失败测试

**Files:**
- Modify: `src/agent/orchestrator_committee.py`
- Modify: `tests/test_committee_bilingual_prompts.py`（新建）

- [ ] **Step 1: 写失败测试 — 5 处 prompt 在 zh 下追加 suffix**

新建 `tests/test_committee_bilingual_prompts.py`：

```python
"""Tests that the committee orchestrator appends a Chinese-output suffix
to all 5 prompt sites (bull / bear / master / risk / pm) when
``ctx.report_language == 'zh'``, and stays English-only otherwise.

Why: the 2026-05-15 bilingual feature added a zh suffix to the main
analyzer prompt but the committee orchestrator was never wired up. The
INTC test on 2026-05-20 (report_language=zh) shipped with all
committee minutes (debate claims, master headlines, PM rationale) in
English while the rest of the report was Chinese.
"""
from unittest.mock import MagicMock

from src.agent.budget import LLMCallBudget
from src.agent.orchestrator_committee import (
    COMMITTEE_LANGUAGE_SUFFIX_ZH,
    InvestmentCommitteeOrchestrator,
)
from src.agent.protocols import AgentContext


def _make_orch(report_language: str) -> InvestmentCommitteeOrchestrator:
    ctx = AgentContext(
        stock_code="AAPL",
        stock_name="Apple",
        report_language=report_language,
        meta={"market": "US"},
    )
    return InvestmentCommitteeOrchestrator(
        ctx,
        report_json={"summary": "x"},
        budget=LLMCallBudget(cap=14),
        llm_callable=MagicMock(return_value="{}"),
        debate_rounds=2,
        timeout_s=999,
    )


def test_language_suffix_emits_zh_block_when_report_language_zh():
    orch = _make_orch("zh")
    suffix = orch._language_suffix()
    # Must mention output language directive in Chinese
    assert "输出语言" in suffix
    # Must instruct enum/key preservation (so we don't break parse)
    assert "JSON" in suffix or "键名" in suffix
    # Must reference the free-text fields that should be translated
    assert "headline" in suffix or "rationale" in suffix or "claim" in suffix


def test_language_suffix_empty_when_report_language_en():
    orch = _make_orch("en")
    suffix = orch._language_suffix()
    assert suffix == ""


def test_language_suffix_constant_module_export():
    """The suffix constant must be importable for testing & reuse."""
    assert "输出语言" in COMMITTEE_LANGUAGE_SUFFIX_ZH
    # Lists explicit fields that must stay English
    assert "verdict" in COMMITTEE_LANGUAGE_SUFFIX_ZH
    # Lists explicit fields that must be translated
    assert "rationale" in COMMITTEE_LANGUAGE_SUFFIX_ZH


def test_bull_prompt_includes_zh_suffix_under_zh_context():
    from src.agent.agents.bull_researcher import BullResearcher
    orch = _make_orch("zh")
    composed = BullResearcher.system_prompt() + orch._language_suffix()
    assert "输出语言" in composed
    # Original English instruction is still present
    assert "Bull Researcher" in composed


def test_bull_prompt_unchanged_under_en_context():
    from src.agent.agents.bull_researcher import BullResearcher
    orch = _make_orch("en")
    composed = BullResearcher.system_prompt() + orch._language_suffix()
    assert "输出语言" not in composed
    assert "Bull Researcher" in composed
```

- [ ] **Step 2: 跑测试验证 FAIL**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_committee_bilingual_prompts.py -q`
Expected: FAIL — `ImportError: cannot import COMMITTEE_LANGUAGE_SUFFIX_ZH`，以及 `_language_suffix` 不存在。

---

### Task D4: 实现 `_language_suffix()` + 在 5 处 prompt 后拼接 suffix

**Files:**
- Modify: `src/agent/orchestrator_committee.py`

- [ ] **Step 1: 在 orchestrator 文件顶部模块级（imports 后）插入常量**

读 [`src/agent/orchestrator_committee.py:1-80`](src/agent/orchestrator_committee.py#L1-L80) 找到 imports 与第一个 class 定义之间的空白处。插入：

```python
# ============================================================
# Bilingual output — committee prompts append this suffix when the
# caller's AgentContext has report_language == "zh". JSON keys and
# enum values stay English (so parsers don't break); only the
# user-facing free-text fields switch to Simplified Chinese.
#
# Symmetric with src/analyzer.py's main-prompt zh_suffix (2026-05-15
# bilingual feature) — but scoped to the committee narrative (debate,
# master lenses, risk red_flags, PM rationale).
# ============================================================
COMMITTEE_LANGUAGE_SUFFIX_ZH = """

## 输出语言（最高优先级）

- 所有 JSON 键名保持英文不变。
- 所有 verdict / side / severity / status 等枚举值保持英文（如 `strong_buy` / `buy` / `hold` / `avoid` / `short` / `bull` / `bear` / `none` / `soft` / `hard` / `ok` / `failed` / `partial`）。
- persona ID 保持英文（如 `warren_buffett` / `michael_burry` / `cathie_wood` / `nassim_taleb`）。
- 数值字段（`score` / `round_index` / `confidence` / `suggested_position_pct` / `budget_used` / `budget_cap`）保持原始类型。
- 所有面向用户的人类可读自由文本字段必须使用简体中文，包括但不限于：
  `headline` / `rationale` / `key_evidence` 各项 / `counter_view` / `thesis` /
  `claim` / `evidence` 各项 / `rebuttal_to` /
  `red_flags` 各项 /
  `pm_rationale` / `pm_dissents` 各项的描述部分 / `error_summary`。
- 翻译时忠实于原英文 prompt 要求的分析角度，不要扩写或二次分析。
"""
```

- [ ] **Step 2: 在 `InvestmentCommitteeOrchestrator` 类内加 `_language_suffix` 方法**

找到 `_past_deadline` 方法（约 line 463），在它**前面**（即 `# Helper — deadline & retry contract` 注释块之前）插入：

```python
    # ----------------------------------------------------------------- #
    # Helper — output language
    # ----------------------------------------------------------------- #

    def _language_suffix(self) -> str:
        """Return the Chinese-output instruction suffix when ctx requests zh.

        Returns empty string for non-zh contexts so existing English
        behavior is byte-identical.
        """
        lang = (getattr(self.ctx, "report_language", "zh") or "zh").lower()
        if lang.startswith("zh"):
            return COMMITTEE_LANGUAGE_SUFFIX_ZH
        return ""
```

- [ ] **Step 3: 在 5 处 prompt 调用拼接 suffix**

读 [`src/agent/orchestrator_committee.py:517-555`](src/agent/orchestrator_committee.py#L517-L555)（`_bull_node`）。把：

```python
                system_prompt=BullResearcher.system_prompt(),
```

改为：

```python
                system_prompt=BullResearcher.system_prompt() + self._language_suffix(),
```

读 `_bear_node`（约 line 557-595）。把：

```python
                system_prompt=BearResearcher.system_prompt(),
```

改为：

```python
                system_prompt=BearResearcher.system_prompt() + self._language_suffix(),
```

读 `_master_node`（约 line 595-631）。把：

```python
                system_prompt=persona_cls.system_prompt(self.ctx),
```

改为：

```python
                system_prompt=persona_cls.system_prompt(self.ctx) + self._language_suffix(),
```

读 `_risk_node`（约 line 633-682）。把：

```python
            parsed: RiskAssessment = self._call_llm_with_retry(
                node_name="risk",
                system_prompt=risk_sys,
```

改为：

```python
            parsed: RiskAssessment = self._call_llm_with_retry(
                node_name="risk",
                system_prompt=risk_sys + self._language_suffix(),
```

读 `_pm_node`（约 line 684-800）。找到 `_call_llm_with_retry(... system_prompt=pm_sys, ...)` 调用，把：

```python
                system_prompt=pm_sys,
```

改为：

```python
                system_prompt=pm_sys + self._language_suffix(),
```

- [ ] **Step 4: 跑 D3 测试验证 PASS**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_committee_bilingual_prompts.py -q`
Expected: 5 passed

- [ ] **Step 5: 回归 — 跑全部 committee 套件**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_committee_graph.py tests/test_master_personas.py tests/test_analysis_service_committee.py tests/test_committee_checkpoint_resume.py tests/test_committee_schema.py tests/test_history_markdown_committee.py tests/test_notification_committee.py tests/test_agent_context_language.py tests/test_committee_bilingual_prompts.py tests/test_agent_budget.py -q`
Expected: 全 PASS。既有 schema/parse 测试不受影响（suffix 不改变 JSON 结构要求）。

- [ ] **Step 6: 后端门禁**

Run: `./scripts/ci_gate.sh`
Expected: 通过（如本地环境差异导致失败，记录差异并在交付说明中标注）。

- [ ] **Step 7: Stage**

Run: `git add src/agent/orchestrator_committee.py tests/test_committee_bilingual_prompts.py`

---

### Task D5: CHANGELOG entry (Phase D)

**Files:**
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: 追加扁平条目**

在 `## [Unreleased]` 段追加：

```markdown
- [新功能] 投委会 prompts（bull / bear / master 4 视角 / risk / PM）现在跟随 `report_language` 输出中文：JSON 键名、verdict/side/severity 枚举、persona ID 保持英文，但 `headline` / `rationale` / `key_evidence` / `claim` / `evidence` / `red_flags` / `pm_rationale` 等自由文本字段在 `report_language=zh` 下用简体中文（与主分析器的「双语速览」对齐）。
- [改进] `AgentContext` 新增 `report_language` 字段（默认 `zh`），由 `AnalysisService._invoke_committee` 从 `result.report_language` / `config.report_language` 解析后填入，供 committee orchestrator 分支使用。
```

- [ ] **Step 2: Stage**

Run: `git add docs/CHANGELOG.md`

---

### Phase D Commit Gate ⏸️

- [ ] **Step 1: `git status` 自检**

Run: `git status --short`
Expected: 5 个 staged 文件：`src/agent/protocols.py`、`tests/test_agent_context_language.py`、`src/services/analysis_service.py`、`tests/test_analysis_service_committee.py`、`src/agent/orchestrator_committee.py`、`tests/test_committee_bilingual_prompts.py`、`docs/CHANGELOG.md`。

- [ ] **Step 2: 等用户确认**

向用户报告 Phase D：
- 改了什么：`AgentContext` + `report_language`；service 透传；orchestrator 加 `_language_suffix()` + 5 处拼接；常量 `COMMITTEE_LANGUAGE_SUFFIX_ZH`。
- 验证情况：3 个新测试文件全绿（8 + 5 + 3 = 16 个新断言），既有 committee 套件 + master_personas + checkpoint + schema 全绿，`ci_gate.sh` 通过。
- 未验证项：实际跑一次 INTC 端到端验证中文输出（建议用户在 commit 后手动跑一次 `python main.py --stocks INTC` 或在 web UI 触发，目测 committee 区块是否中文）。
- 风险点：suffix 拼接是字符串相加，prompt 总长增加 ~600 字符；TPM 紧张的免费层可能更易触发限流（B 计划独立解决）。
- 等用户回复 "commit D" 后再提交。

- [ ] **Step 3: 收到批准后提交**

Run:

```bash
git commit -m "feat(committee): bilingual prompts follow report_language

The 2026-05-15 bilingual feature added a zh suffix only to the main
analyzer prompt. The committee orchestrator's 5 prompt sites (bull,
bear, master fan-out, risk, PM) were hard-coded English, so US/zh
reports shipped with English debate claims, master headlines, and PM
rationale — see 2026-05-20 INTC test where the user observed
all-English committee minutes despite report_language=zh.

This change:
- AgentContext.report_language (new field, default 'zh') carries the
  language signal into the committee.
- AnalysisService._invoke_committee resolves report_language from
  result/config and threads it into the ctx.
- InvestmentCommitteeOrchestrator._language_suffix() returns a Chinese
  output directive (or empty string) based on ctx.report_language.
- Each of the 5 LLM-callable prompts concatenates the suffix; JSON
  keys, verdict/side/severity enums, persona IDs, and numeric fields
  stay English so strict parsing is unaffected.

- src/agent/protocols.py: AgentContext.report_language
- src/services/analysis_service.py: thread language into ctx
- src/agent/orchestrator_committee.py: _language_suffix + 5 call sites
- 3 new test files covering ctx, service wiring, prompt composition"
```

---

## Phase E: 端到端验证（人工 + 可选）

### Task E1: 端到端冒烟

- [ ] **Step 1: 用户重跑 INTC**

向用户建议（不自动执行）：

```bash
python main.py --stocks INTC --debug
```

或在 Web UI 触发 INTC 单股分析，观察：

1. 委员会区域 `bull r1 claim` / `bear r1 claim` / Buffett `headline` / PM `pm_rationale` 是否为简体中文。
2. 4 张大师卡片是否完整出现（不再有 3 张"缺席"）；若仍有 1 张缺席属正常（可能因 retry 偶发，整体大概率改善）。
3. 报告其他区域不应有英文残留（保持原有中文行为）。

- [ ] **Step 2: 用户反馈后判断是否需要后续动作**

如观察到 LLM 不遵从（e.g. 仍输出英文 `claim`），考虑 follow-up：
- 把 suffix 移到 `system_prompt` 开头而非末尾（部分 mini 模型对前置指令更敏感，参考 memory [[repo-llm-mini-models-schema]]）。
- 或在 `_call_llm_with_retry` 解析后做 post-process 翻译兜底（更重，不建议作为首发）。

---

## Self-Review

**1. Spec coverage:**

- A. Timeout 90→180s：Task A1 (实现 + 测试) + A2 (env/docs) + A3 (changelog) ✓
- C. master fan-out 漏标 missing_agents：Task C1 (failing test) + C2 (实现) + C3 (changelog) ✓
- D. 委员会双语：Task D1 (`AgentContext.report_language`) + D2 (service 透传) + D3 (failing test for suffix) + D4 (实现 + 5 处拼接) + D5 (changelog) ✓
- E. 端到端冒烟（人工）✓

**2. Placeholder scan:** 无 TBD / TODO / "add appropriate error handling" / "similar to Task N" 占位；每个 code step 都有完整代码块；每个 Run command 都有 Expected 输出预期。

**3. Type consistency:**

- `AgentContext.report_language: str` 在 D1 定义、D2 填入、D3/D4 读取，签名一致。
- `_language_suffix(self) -> str` 在 D4 定义、D3 测试，签名一致。
- `COMMITTEE_LANGUAGE_SUFFIX_ZH: str` 模块常量在 D4 定义、D3 导入测试，名称一致。
- `failed_master_opinion(persona: str, *, error_summary: str)` 在 C2 使用，签名与 `src/schemas/committee_schema.py:398` 一致。
- 既有：`InvestmentCommitteeOrchestrator(_make_ctx, ...)` 构造在 D3 测试沿用，签名不变。

**4. Risk audit:**

- Phase A 的 timeout 提升不会破任何测试（既有 `timeout_s=0` 测试显式覆盖短超时）。
- Phase C 改变 `minutes.masters` 长度语义（"可能 < 4" → "始终 4"），但渲染层按 `m.status != 'ok'` 标 absent，不受影响。需在 commit 消息明确，便于 audit 下游消费方。
- Phase D 的 prompt suffix 增长 ~600 字符；免费层 TPM 紧张时可能加剧限流（memory [[repo-parallel-masters-rate-limit]]）；B 计划（并行/精简 prompt）独立处理。
- `.env.example` 编辑（A2 Step 1）已被 PUA hook 标 secrets-adjacent —— 计划中已要求 "先用 Read 查看上下文确认只动这一行"。
