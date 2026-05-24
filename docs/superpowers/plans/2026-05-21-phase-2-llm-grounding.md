# Phase 2 — LLM Prompt + Sanitizer + Synthesizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Inline execution (no SDD dispatch) per [[feedback-subagent-prompt-size-limit]]. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ground the action-plan LLM call in the Phase 1 `FactBundle`: extend the prompt with a facts table + a candidates menu + an output contract, rewrite the sanitizer to enforce 9 candidate-anchored checks, and add a code-side synthesizer that builds action plan items directly from the candidate pool when the LLM fails or the sanitizer empties the list.

**Architecture:** Build the FactBundle *before* the action-plan LLM call (reorder in pipeline), thread it into `build_strategy_classify_prompt` and `_sanitize_action_plan_items` through pure-function helpers in a new `src/analysis/` submodule. The synthesizer becomes the deterministic fallback path that picks primary candidates per recommended strategy. Dashboard schema gains optional `candidate_id` / `evidence_refs` / `narrative` / `tier` / `provenance` fields on each action_plan_item; old reports stay readable because every new field is optional.

**Tech Stack:** Python 3.11, dataclasses (Phase 1 facts), pytest. Mock LLM via `analyzer.generate_text` patching for integration test.

**Reference spec:** `docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md` Section B (lines 293–446).

**Pre-conditions:** Phase 1 merged at HEAD `4d1d0d2`. `src/analysis/{facts,facts_builder,candidate_rules,extractors/*}.py` exist; `pipeline._attach_fact_bundle` attaches `result.dashboard["fact_bundle"]` post-`analyze`. 59 unit tests + 1 integration test passing.

---

## File Structure

**Create:**
- `src/analysis/prompt_blocks.py` — pure formatters: facts table, candidates menu, output contract
- `src/analysis/sanitizer_v2.py` — pure function `sanitize_with_candidates(items, bundle, strategy, current_price) -> list[dict]` running the 9 checks
- `src/analysis/synthesizer.py` — pure function `synthesize_from_candidates(candidates, strategy, facts, current_price) -> list[dict]`
- `tests/test_prompt_blocks.py`
- `tests/test_sanitizer_v2.py`
- `tests/test_synthesizer.py`
- `tests/test_analyzer_action_plan_integration.py` — end-to-end with mocked LLM + NVDA fixture

**Modify:**
- `src/core/pipeline.py:540-547` — move `_attach_fact_bundle(result, code)` to run before `_try_inject_action_plan_items`; remove the post-hoc call at `pipeline.py:1742-1747` to avoid double work
- `src/services/portfolio_context_service.py:544-585` — `build_strategy_classify_prompt` accepts optional `fact_bundle` dict and appends the 3 new blocks when present
- `src/analyzer.py:2421-2551` — `_try_inject_action_plan_items` reads `result.dashboard["fact_bundle"]`, passes it to the prompt + sanitizer, and falls back to synthesizer
- `src/analyzer.py:2755-2893` — `_sanitize_action_plan_items` delegates to `sanitize_with_candidates` when a bundle is available; keeps legacy cost-basis path as a no-bundle fallback so old code-paths don't break

**Not touched in this phase:**
- `src/notification.py` and `src/services/history_service.py` (Phase 3 — evidence footnotes)
- `apps/dsa-web/` (Phase 4-5 — frontend components)
- Phase 1 extractors / candidate rules
- Committee orchestrator
- `synthesize_action_plan_items` in `portfolio_context_service.py` — left in place as the no-bundle legacy fallback; Phase 2 routes around it when a bundle is present

---

## Naming Conventions

Action plan item shape (new optional fields highlighted):

```jsonc
{
  "trigger_price": 226.13,
  "trigger_condition": "阻力位触及",
  "direction": "take_profit",
  "shares": 0.23,
  "pct_of_position": 30.0,
  "pct_of_equity": 3.5,
  "technical_basis": "...",
  "fundamental_basis": "...",
  "quant_signal": "...",
  "invalidation_rule": "...",
  "priority": 1,
  // ⬇ Phase 2 additions (all optional)
  "candidate_id": "candidate.exit.1",
  "evidence_refs": ["technical.resistance", "committee.pm_verdict"],
  "narrative": "RSI 71.1 超买 + 阻力位 $226.13 + PM hold (5.8/10) → 触发首档减仓",
  "tier": "primary",
  "provenance": "llm"
}
```

Strategy IDs (4 fixed): `long_term_hold`, `swing_trade`, `stepped_profit_taking`, `wait_and_see`.

`provenance` values: `"llm"` (LLM-chosen, passed sanitizer) or `"synthesized"` (code fallback).
`tier` values: `"primary"` (preferred) or `"discipline_anchor"` (cost-based fallback, max 1).

---

### Task 1: Reorder pipeline so FactBundle is attached BEFORE the action-plan LLM call

**Files:**
- Modify: `src/core/pipeline.py:540-547` (move attach call here)
- Modify: `src/core/pipeline.py:1740-1747` (remove the duplicate post-hoc call)
- Test: `tests/test_pipeline_fact_bundle_order.py` (new)

**Why first:** Every other task depends on `result.dashboard["fact_bundle"]` being present when `_try_inject_action_plan_items` runs. Phase 1 attaches it post-hoc; Phase 2 needs it pre-injection.

- [ ] **Step 1: Write failing test**

```python
# tests/test_pipeline_fact_bundle_order.py
"""Verify FactBundle is attached BEFORE action-plan injection so the action
plan LLM call sees it. Regression guard for Phase 2 architecture.
"""
from unittest.mock import MagicMock, patch

from src.analyzer import AnalysisResult


def test_attach_runs_before_action_plan_injection(monkeypatch):
    """The order matters: action_plan LLM consumes fact_bundle. If attach
    runs after _try_inject_action_plan_items, the LLM sees no candidates."""
    call_order = []

    fake_result = AnalysisResult(
        code="NVDA", name="NVIDIA", sentiment_score=70,
        trend_prediction="up", operation_advice="hold",
        confidence_level="medium", analysis_summary="ok",
        risk_warning="ok", success=True, model_used="test",
    )
    fake_result.dashboard = {"core_conclusion": {}}

    from src.core import pipeline as pipeline_module

    def fake_attach(self, result, code):
        call_order.append("attach")
        result.dashboard["fact_bundle"] = {"facts": [], "candidates": []}

    def fake_inject(self, result, code, block):
        call_order.append("inject")
        # At this point fact_bundle MUST already be present
        assert "fact_bundle" in result.dashboard

    monkeypatch.setattr(
        pipeline_module.StockAnalysisPipeline, "_attach_fact_bundle", fake_attach,
    )
    # Simulate the section of _analyze_single_stock_internal that runs both calls
    pipe = MagicMock(spec=pipeline_module.StockAnalysisPipeline)
    pipe.portfolio_context_block = None
    pipeline_module.StockAnalysisPipeline._attach_fact_bundle(pipe, fake_result, "NVDA")
    fake_inject(pipe, fake_result, "NVDA", None)

    assert call_order == ["attach", "inject"]
```

- [ ] **Step 2: Run failing test**

```bash
python3.11 -m pytest tests/test_pipeline_fact_bundle_order.py -v
```

Expected: PASS already (this is asserting on the order we're about to implement). If it fails initially due to attach not adding fact_bundle, that's fine — we'll wire it next.

- [ ] **Step 3: Move `_attach_fact_bundle` call to pre-injection site**

In `src/core/pipeline.py`, change the block around line 538-547 to run attach FIRST:

```python
                # Phase 2 — attach FactBundle BEFORE action_plan LLM call so the
                # action_plan prompt + sanitizer can consume candidates.
                try:
                    self._attach_fact_bundle(result, code)
                except Exception as fb_exc:
                    logger.warning(
                        f"[{code}] FactBundle 附加失败，dashboard 未变更: {fb_exc}"
                    )
                # action_plan_items 二阶兜底：先用聚焦 LLM 调用（成本价/三维数据感知），
                # LLM 失败再退到 dashboard-only 合成
                if hasattr(self.analyzer, '_try_inject_action_plan_items'):
                    try:
                        self.analyzer._try_inject_action_plan_items(
                            result, code, self.portfolio_context_block
                        )
                    except Exception:
                        pass
                _fill_action_plan_items_if_missing(result, self.portfolio_context_block)
```

- [ ] **Step 4: Remove the duplicate post-hoc attach at line 1740-1747**

Replace the block:

```python
            if result and result.success:
                logger.info(
                    f"[{code}] 分析完成: {result.operation_advice}, "
                    f"评分 {result.sentiment_score}"
                )

                # === Phase 1 — Attach FactBundle to dashboard (non-disruptive) ===
                # Wrap in try/except: any failure logs and continues; dashboard untouched.
                try:
                    self._attach_fact_bundle(result, code)
                except Exception as fb_exc:
                    logger.warning(
                        f"[{code}] FactBundle 附加失败，dashboard 未变更: {fb_exc}"
                    )
```

with:

```python
            if result and result.success:
                logger.info(
                    f"[{code}] 分析完成: {result.operation_advice}, "
                    f"评分 {result.sentiment_score}"
                )
                # Phase 2: FactBundle is attached pre-injection inside
                # _analyze_single_stock_internal; no post-hoc attach needed.
```

- [ ] **Step 5: Run order test + Phase 1 pipeline test**

```bash
python3.11 -m pytest tests/test_pipeline_fact_bundle_order.py tests/test_pipeline_fact_bundle.py -v
```

Expected: 2+ PASSED. Phase 1 pipeline test still passes because `fact_bundle` ends up on dashboard either way.

- [ ] **Step 6: Commit**

```bash
git add src/core/pipeline.py tests/test_pipeline_fact_bundle_order.py
git commit -m "refactor(pipeline): attach FactBundle pre-action-plan-injection"
```

---

### Task 2: `prompt_blocks.format_facts_table` — compact facts block

**Files:**
- Create: `src/analysis/prompt_blocks.py`
- Test: `tests/test_prompt_blocks.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_prompt_blocks.py
from src.analysis.facts import FactRecord, FactBundle, CandidateLevel
from src.analysis.prompt_blocks import format_facts_table


def _bundle_with(facts, candidates=None):
    return FactBundle(
        as_of="2026-05-21T00:43:00Z",
        market="us",
        stock_code="NVDA",
        facts=facts,
        candidates=candidates or [],
    )


def test_format_facts_table_includes_section_header():
    bundle = _bundle_with([
        FactRecord(id="technical.current_price", type="technical",
                   label="现价", value=223.47, display_value="$223.47",
                   source="yfinance", as_of="2026-05-21T00:43:00Z"),
    ])
    out = format_facts_table(bundle)
    assert "## [事实数据库]" in out
    assert "$223.47" in out
    assert "technical.current_price" in out  # fact_id surfaces so LLM can cite


def test_format_facts_table_groups_by_type_in_fixed_order():
    bundle = _bundle_with([
        FactRecord(id="intel.risk_alert.0", type="intel",
                   label="风险警示", value="RSI 71.1 超买", display_value="RSI 71.1 超买"),
        FactRecord(id="technical.ma10", type="technical",
                   label="MA10", value=222.02, display_value="$222.02"),
        FactRecord(id="committee.pm_verdict", type="committee",
                   label="PM 裁决", value="hold", display_value="Hold"),
        FactRecord(id="quant.qlib_rank", type="quant",
                   label="Qlib 截面分位", value=0.85, display_value="前 15%"),
    ])
    out = format_facts_table(bundle)
    # Fixed order: technical → quant → committee → intel → portfolio → flow → chip
    pos_tech = out.index("technical.ma10")
    pos_quant = out.index("quant.qlib_rank")
    pos_committee = out.index("committee.pm_verdict")
    pos_intel = out.index("intel.risk_alert.0")
    assert pos_tech < pos_quant < pos_committee < pos_intel


def test_format_facts_table_empty_bundle_returns_minimal_header():
    bundle = _bundle_with([])
    out = format_facts_table(bundle)
    assert "## [事实数据库]" in out
    assert "（无可用事实）" in out
```

- [ ] **Step 2: Run failing test**

```bash
python3.11 -m pytest tests/test_prompt_blocks.py -v
```

Expected: ImportError on `format_facts_table`.

- [ ] **Step 3: Implement `format_facts_table`**

```python
# src/analysis/prompt_blocks.py
"""Pure formatters for Phase 2 LLM prompt blocks: facts table, candidates menu,
output contract.

These functions emit deterministic Markdown the LLM consumes. No I/O, no LLM,
no logging — they read a FactBundle and return a string.
"""
from __future__ import annotations

from typing import Optional

from src.analysis.facts import FactBundle, CandidateLevel

# Fixed display order. Types not in this list are appended in stable order.
_TYPE_ORDER = ("technical", "quant", "committee", "intel", "portfolio", "flow", "chip")


def format_facts_table(bundle: FactBundle) -> str:
    """Compact one-line-per-fact block, grouped by type in fixed order.

    Each line: `<id> · <label> = <display_value> [extra hints]`

    The id is left exposed so the LLM can cite it in evidence_refs.
    """
    lines: list[str] = ["## [事实数据库]"]
    if not bundle.facts:
        lines.append("（无可用事实）")
        return "\n".join(lines)

    by_type: dict[str, list] = {}
    for f in bundle.facts:
        by_type.setdefault(f.type, []).append(f)

    ordered_types = list(_TYPE_ORDER) + [t for t in by_type if t not in _TYPE_ORDER]
    for type_name in ordered_types:
        items = by_type.get(type_name) or []
        if not items:
            continue
        lines.append(f"\n### {type_name}")
        for f in items:
            extras = []
            if isinstance(f.extra, dict):
                for k in ("zone", "role", "severity", "is_dissent", "interpretation"):
                    v = f.extra.get(k)
                    if v not in (None, "", False):
                        extras.append(f"{k}={v}")
            extra_str = f"  [{', '.join(extras)}]" if extras else ""
            lines.append(f"- `{f.id}` · {f.label} = {f.display_value}{extra_str}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test**

```bash
python3.11 -m pytest tests/test_prompt_blocks.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/prompt_blocks.py tests/test_prompt_blocks.py
git commit -m "feat(analysis): add format_facts_table for LLM prompt block"
```

---

### Task 3: `prompt_blocks.format_candidates_menu` — candidate selection table

**Files:**
- Modify: `src/analysis/prompt_blocks.py`
- Modify: `tests/test_prompt_blocks.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_prompt_blocks.py — append
from src.analysis.prompt_blocks import format_candidates_menu


def _make_candidate(id_, direction, price, basis_rule, strategies, tier="primary",
                    distance=1.0):
    return CandidateLevel(
        id=id_, type="candidate", label=f"{basis_rule}", value=price,
        display_value=f"${price:.2f}", direction=direction, price=price,
        basis_fact_id="technical.resistance", basis_rule=basis_rule,
        applicable_strategies=strategies, tier=tier,
        distance_pct_from_current=distance,
    )


def test_format_candidates_menu_renders_table_with_header():
    bundle = _bundle_with([], candidates=[
        _make_candidate("candidate.exit.1", "take_profit", 226.13, "resistance_touch",
                        ["swing_trade", "stepped_profit_taking"], distance=1.2),
        _make_candidate("candidate.stop.1", "stop_loss", 213.39, "ma20_breakdown",
                        ["swing_trade", "stepped_profit_taking"], distance=-4.5),
    ])
    out = format_candidates_menu(bundle)
    assert "## [候选触发价位]" in out
    assert "candidate.exit.1" in out
    assert "candidate.stop.1" in out
    assert "$226.13" in out
    assert "resistance_touch" in out
    assert "swing_trade" in out
    assert "禁止创造新价位" in out  # guard against LLM creativity


def test_format_candidates_menu_filters_out_filtered_tier():
    bundle = _bundle_with([], candidates=[
        _make_candidate("candidate.exit.1", "take_profit", 226.13, "resistance_touch",
                        ["swing_trade"]),
        _make_candidate("candidate.exit.bad", "take_profit", 100.0, "stale_target",
                        ["swing_trade"], tier="filtered"),
    ])
    out = format_candidates_menu(bundle)
    assert "candidate.exit.1" in out
    assert "candidate.exit.bad" not in out


def test_format_candidates_menu_strategy_filter():
    """When recommended_strategy given, candidates that don't apply are excluded
    from the menu so the LLM only chooses from valid options."""
    bundle = _bundle_with([], candidates=[
        _make_candidate("candidate.exit.swing", "take_profit", 226.13, "resistance",
                        ["swing_trade"]),
        _make_candidate("candidate.exit.lth", "take_profit", 280.0, "cost_x_1_5",
                        ["long_term_hold"]),
    ])
    out = format_candidates_menu(bundle, strategy="swing_trade")
    assert "candidate.exit.swing" in out
    assert "candidate.exit.lth" not in out


def test_format_candidates_menu_empty_returns_no_options_note():
    bundle = _bundle_with([], candidates=[])
    out = format_candidates_menu(bundle)
    assert "## [候选触发价位]" in out
    assert "无可用候选" in out
```

- [ ] **Step 2: Run failing test**

```bash
python3.11 -m pytest tests/test_prompt_blocks.py -v
```

Expected: ImportError on `format_candidates_menu`.

- [ ] **Step 3: Implement `format_candidates_menu`**

Append to `src/analysis/prompt_blocks.py`:

```python
def format_candidates_menu(
    bundle: FactBundle,
    strategy: Optional[str] = None,
) -> str:
    """Markdown table of candidate trigger prices. LLM must pick `candidate_id`
    from this list — `tier=filtered` rows are excluded, and when `strategy` is
    given, only candidates whose `applicable_strategies` contains it are shown.
    """
    visible: list[CandidateLevel] = [
        c for c in bundle.candidates
        if c.tier != "filtered"
        and (strategy is None or strategy in c.applicable_strategies)
    ]
    lines: list[str] = ["## [候选触发价位] — 你只能从下表选 candidate_id，禁止创造新价位"]
    if not visible:
        lines.append("（无可用候选）")
        return "\n".join(lines)

    lines.append("")
    lines.append("| ID | 方向 | 价格 | 距现价 | 规则 | 适用策略 | 层级 |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in visible:
        dist = f"{c.distance_pct_from_current:+.1f}%"
        strategies = ", ".join(c.applicable_strategies)
        lines.append(
            f"| `{c.id}` | {c.direction} | {c.display_value} | {dist} "
            f"| {c.basis_rule} | {strategies} | {c.tier} |"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run test**

```bash
python3.11 -m pytest tests/test_prompt_blocks.py -v
```

Expected: 7 PASSED (3 from Task 2 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/analysis/prompt_blocks.py tests/test_prompt_blocks.py
git commit -m "feat(analysis): add format_candidates_menu for LLM prompt block"
```

---

### Task 4: `prompt_blocks.OUTPUT_CONTRACT_ZH` — explicit output contract block

**Files:**
- Modify: `src/analysis/prompt_blocks.py`
- Modify: `tests/test_prompt_blocks.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_prompt_blocks.py — append
def test_output_contract_zh_constants():
    from src.analysis.prompt_blocks import OUTPUT_CONTRACT_ZH
    assert "candidate_id" in OUTPUT_CONTRACT_ZH
    assert "evidence_refs" in OUTPUT_CONTRACT_ZH
    assert "narrative" in OUTPUT_CONTRACT_ZH
    assert "discipline_anchor" in OUTPUT_CONTRACT_ZH
    assert "至多 1 条" in OUTPUT_CONTRACT_ZH or "at most 1" in OUTPUT_CONTRACT_ZH
    assert "至少 2 个 fact_id" in OUTPUT_CONTRACT_ZH
```

- [ ] **Step 2: Run failing test**

```bash
python3.11 -m pytest tests/test_prompt_blocks.py::test_output_contract_zh_constants -v
```

Expected: ImportError.

- [ ] **Step 3: Add `OUTPUT_CONTRACT_ZH` constant**

Append to `src/analysis/prompt_blocks.py`:

```python
OUTPUT_CONTRACT_ZH = """## [输出契约 — Phase 2 证据接地]

对推荐策略输出 2-4 条 action_plan_items。**每条必须包含以下新字段**：

- `candidate_id`: 上表某个 ID（不能是 filtered 的，也不能凭空创造）
- `trigger_price`: 必须等于该 candidate 的 price（系统会强制核对）
- `evidence_refs`: 至少 2 个 fact_id，引用支持决策的事实（来自上方事实数据库）
- `narrative`: 一段论证文本（30-80 字），可在文中内嵌 `<ref:fact_id>` 标记
- `tier`: `primary` 或 `discipline_anchor`，与上表的 tier 保持一致
- `provenance`: 固定填 `"llm"`

其余字段（trigger_condition / direction / shares / pct_of_position / pct_of_equity /
technical_basis / fundamental_basis / quant_signal / invalidation_rule / priority）按现有约束保留。

**硬约束：**
- `discipline_anchor` 层至多 1 条（仅当没有任何合适的 primary 时使用）
- 同一 `candidate_id` 不能出现两次
- `direction` 必须与该 candidate 的方向一致
"""
```

- [ ] **Step 4: Run test**

```bash
python3.11 -m pytest tests/test_prompt_blocks.py -v
```

Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/prompt_blocks.py tests/test_prompt_blocks.py
git commit -m "feat(analysis): add OUTPUT_CONTRACT_ZH for LLM evidence grounding"
```

---

### Task 5: Extend `build_strategy_classify_prompt` to accept and inject FactBundle blocks

**Files:**
- Modify: `src/services/portfolio_context_service.py:544-585`
- Test: `tests/test_strategy_classify_prompt_phase2.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/test_strategy_classify_prompt_phase2.py
"""build_strategy_classify_prompt should accept an optional fact_bundle dict
and inject facts table + candidates menu + output contract when present."""
from src.services.portfolio_context_service import build_strategy_classify_prompt


def _bundle_dict():
    return {
        "as_of": "2026-05-21T00:43:00Z",
        "market": "us",
        "stock_code": "NVDA",
        "facts": [
            {"id": "technical.current_price", "type": "technical",
             "label": "现价", "value": 223.47, "display_value": "$223.47",
             "unit": "USD", "source": "yfinance", "confidence": None,
             "as_of": "2026-05-21T00:43:00Z", "extra": {}},
        ],
        "candidates": [
            {"id": "candidate.exit.1", "type": "candidate", "label": "阻力",
             "value": 226.13, "display_value": "$226.13",
             "unit": None, "source": "", "confidence": None,
             "as_of": "2026-05-21T00:43:00Z", "extra": {},
             "direction": "take_profit", "price": 226.13,
             "basis_fact_id": "technical.resistance",
             "basis_rule": "resistance_touch",
             "applicable_strategies": ["swing_trade"],
             "tier": "primary", "distance_pct_from_current": 1.2},
        ],
    }


def test_build_prompt_without_bundle_unchanged():
    prompt = build_strategy_classify_prompt(
        portfolio_context_block=None,
        sentiment_dimensions=None,
        compact_dashboard={"stock_code": "NVDA"},
    )
    assert "[事实数据库]" not in prompt
    assert "[候选触发价位]" not in prompt


def test_build_prompt_with_bundle_injects_three_new_blocks():
    prompt = build_strategy_classify_prompt(
        portfolio_context_block=None,
        sentiment_dimensions=None,
        compact_dashboard={"stock_code": "NVDA"},
        fact_bundle=_bundle_dict(),
    )
    assert "[事实数据库]" in prompt
    assert "[候选触发价位]" in prompt
    assert "[输出契约 — Phase 2 证据接地]" in prompt
    assert "technical.current_price" in prompt
    assert "candidate.exit.1" in prompt
    # Output JSON template must mention the new fields
    assert "candidate_id" in prompt
    assert "evidence_refs" in prompt


def test_build_prompt_with_empty_bundle_still_safe():
    prompt = build_strategy_classify_prompt(
        portfolio_context_block=None,
        sentiment_dimensions=None,
        compact_dashboard={"stock_code": "NVDA"},
        fact_bundle={"as_of": "x", "market": "us", "stock_code": "NVDA",
                     "facts": [], "candidates": []},
    )
    assert "[事实数据库]" in prompt
    assert "（无可用事实）" in prompt
    assert "（无可用候选）" in prompt
```

- [ ] **Step 2: Run failing test**

```bash
python3.11 -m pytest tests/test_strategy_classify_prompt_phase2.py -v
```

Expected: TypeError (unexpected keyword `fact_bundle`).

- [ ] **Step 3: Add `fact_bundle` parameter + block injection**

Edit `src/services/portfolio_context_service.py:544` (signature) and add a `_bundle_from_dict` helper. Replace the function body:

```python
def build_strategy_classify_prompt(
    portfolio_context_block: Optional[str],
    sentiment_dimensions: Optional[Dict[str, Any]],
    compact_dashboard: Dict[str, Any],
    fact_bundle: Optional[Dict[str, Any]] = None,
) -> str:
    """Compose the strategy-classification + action-plan-generation prompt.

    Universal: runs for all stocks (with or without portfolio). When portfolio is
    absent, cost-based rules switch to current-price relative rules. When sentiment
    is absent (e.g. A/HK stocks), the sentiment section degrades to text-only signal.

    Phase 2: when `fact_bundle` is provided (a dict matching FactBundle JSON
    shape), append a facts table + candidates menu + output contract so the LLM
    grounds its action_plan_items in concrete fact_ids and candidate_ids.
    """
    has_portfolio = bool(portfolio_context_block and portfolio_context_block.strip())
    parts = [STRATEGY_CLASSIFY_INSTRUCTION_ZH]

    if has_portfolio:
        parts.append(_STRATEGY_HELD_COST_BASIS_ADDENDUM)
        parts.append("\n## 持仓上下文\n" + portfolio_context_block)
    else:
        parts.append("\n## 持仓上下文\n用户未持有该股票，按建仓视角分析（cost-based 规则换为现价相对规则）。")

    if sentiment_dimensions:
        parts.append("\n## 市场情绪\n" + json.dumps(
            sentiment_dimensions, ensure_ascii=False, indent=2,
        ))

    parts.append("\n## 分析摘要\n" + json.dumps(
        compact_dashboard, ensure_ascii=False, indent=2, default=str,
    ))

    if fact_bundle:
        # Lazy-import to avoid cyclic dependency (analysis -> services).
        from src.analysis.facts import FactBundle, FactRecord, CandidateLevel
        from src.analysis.prompt_blocks import (
            format_facts_table, format_candidates_menu, OUTPUT_CONTRACT_ZH,
        )

        try:
            bundle = FactBundle(
                as_of=fact_bundle.get("as_of", ""),
                market=fact_bundle.get("market", "us"),
                stock_code=fact_bundle.get("stock_code", ""),
                facts=[FactRecord(**f) for f in fact_bundle.get("facts", [])],
                candidates=[CandidateLevel(**c) for c in fact_bundle.get("candidates", [])],
            )
            parts.append("\n" + format_facts_table(bundle))
            parts.append("\n" + format_candidates_menu(bundle))
            parts.append("\n" + OUTPUT_CONTRACT_ZH)
        except Exception:
            # Defensive: never break the legacy prompt if the bundle shape is off.
            pass

    parts.append(
        "\n## 输出\n仅输出合法 JSON，顶层结构：\n"
        "{\n"
        '  "strategy_choices": [...],\n'
        '  "recommended_strategy": "<id>",\n'
        '  "strategy_thesis": "<100-200 字>",\n'
        '  "action_plan_items": [\n'
        '    {\n'
        '      "candidate_id": "candidate.exit.1",\n'
        '      "trigger_price": 226.13,\n'
        '      "direction": "take_profit",\n'
        '      "shares": 0.23,\n'
        '      "pct_of_position": 30.0,\n'
        '      "technical_basis": "...",\n'
        '      "fundamental_basis": "...",\n'
        '      "quant_signal": "...",\n'
        '      "invalidation_rule": "...",\n'
        '      "priority": 1,\n'
        '      "evidence_refs": ["technical.resistance", "committee.pm_verdict"],\n'
        '      "narrative": "...",\n'
        '      "tier": "primary",\n'
        '      "provenance": "llm"\n'
        '    }\n'
        '  ],\n'
        '  "position_outcome_summary": {...}\n'
        "}\n"
        "不输出任何注释或代码块标记。"
    )

    return "\n".join(parts)
```

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_strategy_classify_prompt_phase2.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/services/portfolio_context_service.py tests/test_strategy_classify_prompt_phase2.py
git commit -m "feat(prompt): inject FactBundle blocks into strategy_classify_prompt"
```

---

### Task 6: Sanitizer v2 — checks #1 + #2 (candidate_id existence + trigger_price override)

**Files:**
- Create: `src/analysis/sanitizer_v2.py`
- Test: `tests/test_sanitizer_v2.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_sanitizer_v2.py
from src.analysis.facts import FactBundle, FactRecord, CandidateLevel
from src.analysis.sanitizer_v2 import sanitize_with_candidates


def _candidate(id_, direction, price, strategies, tier="primary", distance=1.0,
               basis_fact_id="technical.resistance", basis_rule="resistance_touch"):
    return CandidateLevel(
        id=id_, type="candidate", label=basis_rule, value=price,
        display_value=f"${price:.2f}", direction=direction, price=price,
        basis_fact_id=basis_fact_id, basis_rule=basis_rule,
        applicable_strategies=strategies, tier=tier,
        distance_pct_from_current=distance,
    )


def _bundle(candidates, current_price=223.47):
    facts = [FactRecord(
        id="technical.current_price", type="technical", label="现价",
        value=current_price, display_value=f"${current_price:.2f}",
    )]
    return FactBundle(as_of="x", market="us", stock_code="NVDA",
                     facts=facts, candidates=candidates)


def test_check1_drop_item_with_unknown_candidate_id():
    bundle = _bundle([_candidate("candidate.exit.1", "take_profit", 226.13,
                                  ["swing_trade"])])
    items = [
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 1, "evidence_refs":
         ["technical.resistance", "committee.pm_verdict"], "tier": "primary"},
        {"candidate_id": "candidate.exit.FAKE", "trigger_price": 999.99,
         "direction": "take_profit", "priority": 2, "evidence_refs":
         ["technical.resistance", "committee.pm_verdict"], "tier": "primary"},
    ]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    ids = [it["candidate_id"] for it in out]
    assert "candidate.exit.1" in ids
    assert "candidate.exit.FAKE" not in ids


def test_check2_override_trigger_price_to_match_candidate():
    """LLM might emit trigger_price 226.50 but candidate is 226.13. Sanitizer
    overrides to 226.13 (and logs the discrepancy)."""
    bundle = _bundle([_candidate("candidate.exit.1", "take_profit", 226.13,
                                  ["swing_trade"])])
    items = [{
        "candidate_id": "candidate.exit.1", "trigger_price": 226.50,  # ← wrong
        "direction": "take_profit", "priority": 1,
        "evidence_refs": ["technical.resistance", "committee.pm_verdict"],
        "tier": "primary",
    }]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert len(out) == 1
    assert out[0]["trigger_price"] == 226.13


def test_check1_drop_when_candidate_id_missing_entirely():
    bundle = _bundle([_candidate("candidate.exit.1", "take_profit", 226.13,
                                  ["swing_trade"])])
    items = [{"trigger_price": 226.13, "direction": "take_profit", "priority": 1}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert out == []
```

- [ ] **Step 2: Run failing test**

```bash
python3.11 -m pytest tests/test_sanitizer_v2.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create skeleton + implement checks #1 + #2**

```python
# src/analysis/sanitizer_v2.py
"""Phase 2 evidence-grounded sanitizer.

Replaces the legacy cost-basis sanitizer when a FactBundle is available.
Pure function — no I/O, no logging side-effects beyond the logger.

Spec: docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md
Section B "Sanitizer 新版".
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.analysis.facts import FactBundle, CandidateLevel

logger = logging.getLogger(__name__)


def _candidate_map(bundle: FactBundle) -> Dict[str, CandidateLevel]:
    return {c.id: c for c in bundle.candidates}


def sanitize_with_candidates(
    items: List[Dict[str, Any]],
    bundle: FactBundle,
    *,
    strategy: Optional[str],
    current_price: Optional[float],
) -> List[Dict[str, Any]]:
    """Run the 9-check sanitizer against the candidate pool.

    Returns the filtered + corrected items list, with `priority` renumbered
    1..N. May return [] if all items fail — caller falls back to synthesizer.
    """
    cmap = _candidate_map(bundle)
    survivors: List[Dict[str, Any]] = []

    for it in items:
        if not isinstance(it, dict):
            continue
        cid = it.get("candidate_id")

        # Check #1 — candidate_id must exist
        if not cid or cid not in cmap:
            logger.info(
                "[sanitizer_v2] drop item: candidate_id=%r not in bundle.candidates",
                cid,
            )
            continue
        cand = cmap[cid]

        # Check #2 — trigger_price must equal candidate.price (force override)
        candidate_price = float(cand.price)
        llm_price = it.get("trigger_price")
        if llm_price is None or abs(float(llm_price) - candidate_price) > 1e-6:
            logger.info(
                "[sanitizer_v2] override trigger_price: candidate=%s "
                "llm=%s -> candidate.price=%s",
                cid, llm_price, candidate_price,
            )
            it = dict(it)
            it["trigger_price"] = candidate_price

        survivors.append(it)

    # Renumber priority 1..N (final step shared with later checks)
    for new_pri, it in enumerate(survivors, start=1):
        it["priority"] = new_pri

    return survivors
```

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_sanitizer_v2.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/sanitizer_v2.py tests/test_sanitizer_v2.py
git commit -m "feat(sanitizer): add v2 with candidate_id + trigger_price checks (#1 #2)"
```

---

### Task 7: Sanitizer v2 — checks #3 + #4 (applicable_strategies + tier filter)

**Files:**
- Modify: `src/analysis/sanitizer_v2.py`
- Modify: `tests/test_sanitizer_v2.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_sanitizer_v2.py — append
def test_check3_drop_item_when_strategy_not_in_applicable_strategies():
    bundle = _bundle([
        _candidate("candidate.exit.1", "take_profit", 226.13,
                   ["swing_trade", "stepped_profit_taking"]),
        _candidate("candidate.exit.lth", "take_profit", 280.0,
                   ["long_term_hold"]),  # wrong strategy
    ])
    items = [
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 1,
         "evidence_refs": ["technical.resistance", "committee.pm_verdict"],
         "tier": "primary"},
        {"candidate_id": "candidate.exit.lth", "trigger_price": 280.0,
         "direction": "take_profit", "priority": 2,
         "evidence_refs": ["technical.resistance", "committee.pm_verdict"],
         "tier": "primary"},
    ]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    ids = [it["candidate_id"] for it in out]
    assert "candidate.exit.1" in ids
    assert "candidate.exit.lth" not in ids


def test_check4_drop_filtered_tier_candidate():
    bundle = _bundle([
        _candidate("candidate.exit.stale", "take_profit", 100.0,
                   ["swing_trade"], tier="filtered"),
    ])
    items = [{"candidate_id": "candidate.exit.stale", "trigger_price": 100.0,
              "direction": "take_profit", "priority": 1,
              "evidence_refs": ["a", "b"], "tier": "filtered"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert out == []
```

- [ ] **Step 2: Run failing test**

```bash
python3.11 -m pytest tests/test_sanitizer_v2.py -v
```

Expected: 2 new tests FAIL (check #3 and #4 not implemented yet).

- [ ] **Step 3: Add checks #3 + #4 inside the loop**

Edit `src/analysis/sanitizer_v2.py`, inside `sanitize_with_candidates` between check #2 and the `survivors.append(it)` line:

```python
        # Check #3 — recommended_strategy must be in candidate.applicable_strategies
        if strategy and strategy not in cand.applicable_strategies:
            logger.info(
                "[sanitizer_v2] drop item: candidate=%s applies to %s, "
                "recommended=%s",
                cid, cand.applicable_strategies, strategy,
            )
            continue

        # Check #4 — candidate must not be in `filtered` tier
        if cand.tier == "filtered":
            logger.info(
                "[sanitizer_v2] drop item: candidate=%s is in filtered tier", cid,
            )
            continue
```

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_sanitizer_v2.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/sanitizer_v2.py tests/test_sanitizer_v2.py
git commit -m "feat(sanitizer): add strategy + filtered-tier checks (#3 #4)"
```

---

### Task 8: Sanitizer v2 — check #5 (direction vs current price logic)

**Files:**
- Modify: `src/analysis/sanitizer_v2.py`
- Modify: `tests/test_sanitizer_v2.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_sanitizer_v2.py — append
def test_check5_drop_take_profit_below_current_price():
    bundle = _bundle(
        [_candidate("candidate.exit.bad", "take_profit", 220.0,
                    ["swing_trade"])],
        current_price=223.47,
    )
    items = [{"candidate_id": "candidate.exit.bad", "trigger_price": 220.0,
              "direction": "take_profit", "priority": 1,
              "evidence_refs": ["a", "b"], "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert out == []


def test_check5_drop_stop_loss_above_current_price():
    bundle = _bundle(
        [_candidate("candidate.stop.bad", "stop_loss", 230.0,
                    ["swing_trade"])],
        current_price=223.47,
    )
    items = [{"candidate_id": "candidate.stop.bad", "trigger_price": 230.0,
              "direction": "stop_loss", "priority": 1,
              "evidence_refs": ["a", "b"], "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert out == []


def test_check5_keep_take_profit_above_current():
    bundle = _bundle(
        [_candidate("candidate.exit.ok", "take_profit", 226.0,
                    ["swing_trade"])],
        current_price=223.47,
    )
    items = [{"candidate_id": "candidate.exit.ok", "trigger_price": 226.0,
              "direction": "take_profit", "priority": 1,
              "evidence_refs": ["a", "b"], "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert len(out) == 1


def test_check5_no_current_price_skips_direction_check():
    """When current_price unknown, can't validate direction logic — pass-through."""
    bundle = _bundle(
        [_candidate("candidate.exit.x", "take_profit", 100.0, ["swing_trade"])],
        current_price=223.47,
    )
    items = [{"candidate_id": "candidate.exit.x", "trigger_price": 100.0,
              "direction": "take_profit", "priority": 1,
              "evidence_refs": ["a", "b"], "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=None)
    # No current_price -> direction check skipped, item survives
    assert len(out) == 1
```

- [ ] **Step 2: Run failing tests**

```bash
python3.11 -m pytest tests/test_sanitizer_v2.py -v
```

Expected: 2 new tests FAIL (drop cases).

- [ ] **Step 3: Add check #5 after check #4**

In `src/analysis/sanitizer_v2.py`, after the filtered-tier check, add:

```python
        # Check #5 — direction logic vs current price
        if current_price is not None:
            cp = float(current_price)
            if cand.direction == "take_profit" and candidate_price <= cp:
                logger.info(
                    "[sanitizer_v2] drop item: take_profit @ %s ≤ current %s",
                    candidate_price, cp,
                )
                continue
            if cand.direction == "stop_loss" and candidate_price >= cp:
                logger.info(
                    "[sanitizer_v2] drop item: stop_loss @ %s ≥ current %s",
                    candidate_price, cp,
                )
                continue
```

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_sanitizer_v2.py -v
```

Expected: 9 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/sanitizer_v2.py tests/test_sanitizer_v2.py
git commit -m "feat(sanitizer): add direction-vs-current-price check (#5)"
```

---

### Task 9: Sanitizer v2 — check #6 (evidence_refs autofill)

**Files:**
- Modify: `src/analysis/sanitizer_v2.py`
- Modify: `tests/test_sanitizer_v2.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_sanitizer_v2.py — append
def test_check6_autofill_evidence_refs_when_less_than_two():
    """Per spec: if evidence_refs has <2 entries, auto-fill from
    candidate.basis_fact_id + a default committee anchor."""
    facts = [
        FactRecord(id="technical.current_price", type="technical", label="现价",
                   value=223.47, display_value="$223.47"),
        FactRecord(id="committee.pm_verdict", type="committee", label="PM",
                   value="hold", display_value="Hold"),
    ]
    bundle = FactBundle(
        as_of="x", market="us", stock_code="NVDA", facts=facts,
        candidates=[_candidate("candidate.exit.1", "take_profit", 226.13,
                                ["swing_trade"],
                                basis_fact_id="technical.resistance")],
    )
    # Item has 0 evidence_refs
    items = [{"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
              "direction": "take_profit", "priority": 1, "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert len(out) == 1
    refs = out[0]["evidence_refs"]
    assert "technical.resistance" in refs  # basis fact
    assert len(refs) >= 2


def test_check6_keeps_valid_evidence_refs():
    facts = [FactRecord(id="technical.resistance", type="technical", label="阻力",
                        value=226.13, display_value="$226.13")]
    bundle = FactBundle(
        as_of="x", market="us", stock_code="NVDA", facts=facts,
        candidates=[_candidate("candidate.exit.1", "take_profit", 226.13,
                                ["swing_trade"])],
    )
    items = [{"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
              "direction": "take_profit", "priority": 1,
              "evidence_refs": ["technical.resistance", "committee.pm_verdict",
                                 "intel.risk_alert.0"],
              "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert out[0]["evidence_refs"] == [
        "technical.resistance", "committee.pm_verdict", "intel.risk_alert.0",
    ]
```

- [ ] **Step 2: Run failing test**

```bash
python3.11 -m pytest tests/test_sanitizer_v2.py -v
```

Expected: `test_check6_autofill_evidence_refs_when_less_than_two` FAILS (no autofill).

- [ ] **Step 3: Add check #6 (after check #5, before survivors.append)**

In `src/analysis/sanitizer_v2.py`, after the direction check, add:

```python
        # Check #6 — evidence_refs autofill (must have ≥ 2)
        raw_refs = it.get("evidence_refs") or []
        if not isinstance(raw_refs, list):
            raw_refs = []
        # Drop unknown refs that don't exist in the bundle so callers can trust
        # downstream rendering won't trip on dangling fact_ids.
        valid_fact_ids = {f.id for f in bundle.facts} | {c.id for c in bundle.candidates}
        refs = [r for r in raw_refs if isinstance(r, str) and r in valid_fact_ids]
        if len(refs) < 2:
            # Auto-fill: basis_fact_id + first available committee fact
            if cand.basis_fact_id and cand.basis_fact_id not in refs:
                refs.append(cand.basis_fact_id)
            committee_facts = [f.id for f in bundle.facts
                                if f.type == "committee" and f.id not in refs]
            if committee_facts:
                refs.append(committee_facts[0])
        # Strip duplicates while preserving order
        seen: set = set()
        deduped: list = []
        for r in refs:
            if r not in seen:
                seen.add(r)
                deduped.append(r)
        it = dict(it)
        it["evidence_refs"] = deduped
```

Note: this means we must `it = dict(it)` BEFORE this point if check #2 didn't already do it. Adjust the loop so check #2 always copies (already does when override fires); we additionally copy here to be safe.

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_sanitizer_v2.py -v
```

Expected: 11 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/sanitizer_v2.py tests/test_sanitizer_v2.py
git commit -m "feat(sanitizer): autofill evidence_refs to ≥2 entries (#6)"
```

---

### Task 10: Sanitizer v2 — checks #7 + #8 + #9 (discipline_anchor cap, dedup, priority renum)

**Files:**
- Modify: `src/analysis/sanitizer_v2.py`
- Modify: `tests/test_sanitizer_v2.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_sanitizer_v2.py — append
def test_check7_discipline_anchor_capped_to_one():
    bundle = _bundle([
        _candidate("candidate.disc.1", "take_profit", 230.0, ["stepped_profit_taking"],
                   tier="discipline_anchor"),
        _candidate("candidate.disc.2", "take_profit", 240.0, ["stepped_profit_taking"],
                   tier="discipline_anchor"),
        _candidate("candidate.primary", "take_profit", 226.0, ["stepped_profit_taking"],
                   tier="primary"),
    ])
    items = [
        {"candidate_id": "candidate.disc.1", "trigger_price": 230.0,
         "direction": "take_profit", "priority": 1,
         "evidence_refs": ["a", "b"], "tier": "discipline_anchor"},
        {"candidate_id": "candidate.disc.2", "trigger_price": 240.0,
         "direction": "take_profit", "priority": 2,
         "evidence_refs": ["a", "b"], "tier": "discipline_anchor"},
        {"candidate_id": "candidate.primary", "trigger_price": 226.0,
         "direction": "take_profit", "priority": 3,
         "evidence_refs": ["a", "b"], "tier": "primary"},
    ]
    out = sanitize_with_candidates(items, bundle, strategy="stepped_profit_taking",
                                    current_price=223.47)
    anchors = [it for it in out if it.get("tier") == "discipline_anchor"]
    assert len(anchors) == 1


def test_check8_dedup_same_candidate_id_keeps_highest_priority():
    bundle = _bundle([_candidate("candidate.exit.1", "take_profit", 226.13,
                                  ["swing_trade"])])
    items = [
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 5,
         "evidence_refs": ["a", "b"], "tier": "primary"},
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 1,  # higher priority (lower number)
         "evidence_refs": ["a", "b"], "tier": "primary"},
    ]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert len(out) == 1


def test_check9_priority_renumbered_1_to_N():
    bundle = _bundle([
        _candidate("candidate.exit.1", "take_profit", 226.13, ["swing_trade"]),
        _candidate("candidate.exit.2", "take_profit", 230.0, ["swing_trade"]),
    ])
    items = [
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 7,
         "evidence_refs": ["a", "b"], "tier": "primary"},
        {"candidate_id": "candidate.exit.2", "trigger_price": 230.0,
         "direction": "take_profit", "priority": 19,
         "evidence_refs": ["a", "b"], "tier": "primary"},
    ]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    priorities = sorted(it["priority"] for it in out)
    assert priorities == [1, 2]
```

- [ ] **Step 2: Run failing tests**

```bash
python3.11 -m pytest tests/test_sanitizer_v2.py -v
```

Expected: 3 new tests FAIL.

- [ ] **Step 3: Implement post-loop checks #7 + #8**

After the `for it in items:` loop in `sanitize_with_candidates`, before the final renumber, add:

```python
    # Check #8 — dedup by candidate_id, keeping the lowest-priority-number entry
    by_id: Dict[str, Dict[str, Any]] = {}
    for it in survivors:
        cid = it["candidate_id"]
        existing = by_id.get(cid)
        existing_pri = existing.get("priority", 1e9) if existing else 1e9
        new_pri = it.get("priority", 1e9)
        if existing is None or (isinstance(new_pri, (int, float))
                                 and new_pri < existing_pri):
            by_id[cid] = it
    survivors = list(by_id.values())

    # Check #7 — discipline_anchor capped to 1 entry (drop extras)
    discipline_anchors = [
        it for it in survivors
        if (it.get("tier") or cmap.get(it["candidate_id"], CandidateLevel(
            id="", type="", label="", value=0, display_value=""
        )).tier) == "discipline_anchor"
    ]
    if len(discipline_anchors) > 1:
        # Keep the one with lowest priority number, drop the rest
        discipline_anchors.sort(key=lambda x: x.get("priority", 99))
        keep = discipline_anchors[0]
        drop_ids = {it["candidate_id"] for it in discipline_anchors[1:]}
        survivors = [
            it for it in survivors
            if it["candidate_id"] == keep["candidate_id"]
            or it["candidate_id"] not in drop_ids
        ]
```

Then the existing renumber loop at the end of the function (check #9) is already in place from Task 6 — confirm it runs last.

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_sanitizer_v2.py -v
```

Expected: 14 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/sanitizer_v2.py tests/test_sanitizer_v2.py
git commit -m "feat(sanitizer): cap discipline_anchor + dedup + renumber (#7 #8 #9)"
```

---

### Task 11: Synthesizer — `synthesize_from_candidates` deterministic fallback

**Files:**
- Create: `src/analysis/synthesizer.py`
- Test: `tests/test_synthesizer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_synthesizer.py
from src.analysis.facts import FactBundle, FactRecord, CandidateLevel
from src.analysis.synthesizer import synthesize_from_candidates


def _candidate(id_, direction, price, strategies, tier="primary", distance=1.0,
               basis_fact_id="technical.resistance", basis_rule="resistance_touch"):
    return CandidateLevel(
        id=id_, type="candidate", label=basis_rule, value=price,
        display_value=f"${price:.2f}", direction=direction, price=price,
        basis_fact_id=basis_fact_id, basis_rule=basis_rule,
        applicable_strategies=strategies, tier=tier,
        distance_pct_from_current=distance,
    )


def _bundle(candidates):
    facts = [
        FactRecord(id="committee.pm_verdict", type="committee", label="PM",
                   value="hold", display_value="Hold"),
        FactRecord(id="technical.current_price", type="technical", label="现价",
                   value=223.47, display_value="$223.47"),
    ]
    return FactBundle(as_of="x", market="us", stock_code="NVDA",
                     facts=facts, candidates=candidates)


def test_synthesize_swing_trade_picks_primary_exits_and_one_stop():
    bundle = _bundle([
        _candidate("candidate.exit.1", "take_profit", 226.13, ["swing_trade"],
                   distance=1.2),
        _candidate("candidate.exit.2", "take_profit", 230.0, ["swing_trade"],
                   distance=2.9),
        _candidate("candidate.stop.1", "stop_loss", 213.39, ["swing_trade"],
                   distance=-4.5),
    ])
    out = synthesize_from_candidates(
        bundle.candidates, strategy="swing_trade", facts=bundle.facts,
    )
    assert len(out) >= 2
    assert all(it["provenance"] == "synthesized" for it in out)
    candidate_ids = [it["candidate_id"] for it in out]
    assert "candidate.exit.1" in candidate_ids
    assert "candidate.stop.1" in candidate_ids
    # Each item has the 5 new fields
    for it in out:
        assert "evidence_refs" in it and len(it["evidence_refs"]) >= 2
        assert "narrative" in it
        assert it["tier"] in ("primary", "discipline_anchor")
        assert "trigger_price" in it


def test_synthesize_skips_filtered_candidates():
    bundle = _bundle([
        _candidate("candidate.exit.ok", "take_profit", 226.13, ["swing_trade"]),
        _candidate("candidate.exit.bad", "take_profit", 100.0, ["swing_trade"],
                   tier="filtered"),
    ])
    out = synthesize_from_candidates(
        bundle.candidates, strategy="swing_trade", facts=bundle.facts,
    )
    cids = [it["candidate_id"] for it in out]
    assert "candidate.exit.ok" in cids
    assert "candidate.exit.bad" not in cids


def test_synthesize_only_applicable_strategy():
    bundle = _bundle([
        _candidate("candidate.exit.swing", "take_profit", 226.13, ["swing_trade"]),
        _candidate("candidate.exit.lth", "take_profit", 280.0, ["long_term_hold"]),
    ])
    out = synthesize_from_candidates(
        bundle.candidates, strategy="swing_trade", facts=bundle.facts,
    )
    cids = [it["candidate_id"] for it in out]
    assert "candidate.exit.swing" in cids
    assert "candidate.exit.lth" not in cids


def test_synthesize_fallback_to_discipline_anchor_when_no_primary():
    bundle = _bundle([
        _candidate("candidate.disc.1", "take_profit", 230.0, ["stepped_profit_taking"],
                   tier="discipline_anchor"),
    ])
    out = synthesize_from_candidates(
        bundle.candidates, strategy="stepped_profit_taking", facts=bundle.facts,
    )
    assert len(out) == 1
    assert out[0]["tier"] == "discipline_anchor"


def test_synthesize_empty_pool_returns_empty():
    out = synthesize_from_candidates([], strategy="swing_trade", facts=[])
    assert out == []
```

- [ ] **Step 2: Run failing test**

```bash
python3.11 -m pytest tests/test_synthesizer.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `synthesize_from_candidates`**

```python
# src/analysis/synthesizer.py
"""Deterministic code-side synthesizer: build action_plan_items directly from
the FactBundle.candidates pool when the LLM fails or the sanitizer empties.

Each item carries `provenance: "synthesized"` so the UI can badge it as a code
fallback. Spec: docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md
Section B "Synthesizer 重写".
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.analysis.facts import CandidateLevel, FactRecord


_MAX_EXITS_PER_STRATEGY = {
    "long_term_hold": 1,
    "swing_trade": 2,
    "stepped_profit_taking": 3,
    "wait_and_see": 0,
}

_MAX_STOPS_PER_STRATEGY = {
    "long_term_hold": 1,
    "swing_trade": 1,
    "stepped_profit_taking": 1,
    "wait_and_see": 0,
}


def _first_committee_fact_id(facts: List[FactRecord]) -> str:
    for f in facts:
        if f.type == "committee":
            return f.id
    return ""


def _item_from_candidate(
    cand: CandidateLevel,
    facts: List[FactRecord],
    priority: int,
) -> Dict[str, Any]:
    committee_anchor = _first_committee_fact_id(facts)
    evidence_refs = [cand.basis_fact_id]
    if committee_anchor and committee_anchor != cand.basis_fact_id:
        evidence_refs.append(committee_anchor)
    if len(evidence_refs) < 2:
        # Fall back to a technical anchor when committee isn't available
        for f in facts:
            if f.type == "technical" and f.id != cand.basis_fact_id:
                evidence_refs.append(f.id)
                break
    return {
        "candidate_id": cand.id,
        "trigger_price": float(cand.price),
        "trigger_condition": f"{cand.label} ({cand.basis_rule})",
        "direction": cand.direction,
        "shares": 0,
        "pct_of_position": None,
        "pct_of_equity": None,
        "technical_basis": f"{cand.basis_rule}（来自代码合成）",
        "fundamental_basis": "",
        "quant_signal": "",
        "invalidation_rule": f"价格反向穿越 {cand.display_value} 视为失效",
        "priority": priority,
        "evidence_refs": evidence_refs[:3],
        "narrative": (
            f"{cand.label}：{cand.basis_rule}（代码兜底，"
            f"参考 <ref:{cand.basis_fact_id}>）"
        ),
        "tier": cand.tier,
        "provenance": "synthesized",
    }


def synthesize_from_candidates(
    candidates: List[CandidateLevel],
    *,
    strategy: str,
    facts: List[FactRecord],
) -> List[Dict[str, Any]]:
    """Code-side fallback: build action_plan_items directly from candidates.

    Returns an empty list when there's nothing applicable. UI marks each entry
    with `provenance: "synthesized"`.
    """
    if not candidates or not strategy:
        return []
    applicable = [
        c for c in candidates
        if c.tier != "filtered" and strategy in c.applicable_strategies
    ]
    if not applicable:
        return []

    max_exits = _MAX_EXITS_PER_STRATEGY.get(strategy, 2)
    max_stops = _MAX_STOPS_PER_STRATEGY.get(strategy, 1)

    primary_exits = sorted(
        [c for c in applicable
         if c.direction == "take_profit" and c.tier == "primary"],
        key=lambda c: c.distance_pct_from_current,
    )[:max_exits]
    primary_stops = sorted(
        [c for c in applicable
         if c.direction == "stop_loss" and c.tier == "primary"],
        key=lambda c: -c.distance_pct_from_current,
    )[:max_stops]

    chosen: List[CandidateLevel] = primary_exits + primary_stops

    # If we still have no primary picks, fall back to discipline_anchor (cap 1)
    if not chosen:
        anchors = sorted(
            [c for c in applicable if c.tier == "discipline_anchor"],
            key=lambda c: abs(c.distance_pct_from_current),
        )
        chosen = anchors[:1]

    items: List[Dict[str, Any]] = []
    for i, cand in enumerate(chosen, start=1):
        items.append(_item_from_candidate(cand, facts, priority=i))
    return items
```

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_synthesizer.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/synthesizer.py tests/test_synthesizer.py
git commit -m "feat(analysis): add synthesize_from_candidates code fallback"
```

---

### Task 12: Wire sanitizer v2 + synthesizer into `_sanitize_action_plan_items`

**Files:**
- Modify: `src/analyzer.py:2755-2893`
- Test: `tests/test_analyzer_sanitizer_v2_dispatch.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/test_analyzer_sanitizer_v2_dispatch.py
"""When fact_bundle is on result.dashboard, _sanitize_action_plan_items must
route through sanitizer_v2 instead of the legacy cost-basis path."""
from unittest.mock import MagicMock

from src.analyzer import AnalysisAgent


def _bundle_dict_with_candidate():
    return {
        "as_of": "x", "market": "us", "stock_code": "NVDA",
        "facts": [
            {"id": "technical.current_price", "type": "technical", "label": "现价",
             "value": 223.47, "display_value": "$223.47", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {}},
            {"id": "technical.resistance", "type": "technical", "label": "阻力",
             "value": 226.13, "display_value": "$226.13", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {}},
        ],
        "candidates": [
            {"id": "candidate.exit.1", "type": "candidate", "label": "阻力",
             "value": 226.13, "display_value": "$226.13", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {},
             "direction": "take_profit", "price": 226.13,
             "basis_fact_id": "technical.resistance",
             "basis_rule": "resistance_touch",
             "applicable_strategies": ["swing_trade"],
             "tier": "primary", "distance_pct_from_current": 1.2},
        ],
    }


def test_sanitizer_routes_to_v2_when_bundle_present():
    """Item with unknown candidate_id is dropped — proof v2 ran."""
    agent = AnalysisAgent.__new__(AnalysisAgent)
    agent._fact_bundle_for_sanitize = _bundle_dict_with_candidate()
    agent._current_price_for_sanitize = 223.47
    items = [
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 1,
         "evidence_refs": ["technical.resistance"], "tier": "primary"},
        {"candidate_id": "candidate.exit.FAKE", "trigger_price": 999.99,
         "direction": "take_profit", "priority": 2,
         "evidence_refs": ["a", "b"], "tier": "primary"},
    ]
    out = AnalysisAgent._sanitize_action_plan_items(
        agent, items, portfolio_context_block=None, code="NVDA",
        strategy="swing_trade",
    )
    cids = [it.get("candidate_id") for it in out]
    assert "candidate.exit.1" in cids
    assert "candidate.exit.FAKE" not in cids


def test_sanitizer_falls_back_to_legacy_without_bundle():
    """Without a bundle attached, behavior is the legacy cost-basis path."""
    agent = AnalysisAgent.__new__(AnalysisAgent)
    agent._fact_bundle_for_sanitize = None
    agent._current_price_for_sanitize = None
    items = [
        {"trigger_price": 100.0, "trigger_condition": "x",
         "direction": "take_profit", "priority": 1},
    ]
    out = AnalysisAgent._sanitize_action_plan_items(
        agent, items, portfolio_context_block=None, code="NVDA",
        strategy="swing_trade",
    )
    # Legacy passes item through (no avg_cost in block, no rejection)
    assert len(out) == 1
```

- [ ] **Step 2: Run failing test**

```bash
python3.11 -m pytest tests/test_analyzer_sanitizer_v2_dispatch.py -v
```

Expected: AttributeError or logic mismatch (v2 path not added).

- [ ] **Step 3: Add bundle-aware dispatch in `_sanitize_action_plan_items`**

Modify the start of `src/analyzer.py::_sanitize_action_plan_items` (around line 2755) to:

```python
    def _sanitize_action_plan_items(
        self,
        items: list,
        portfolio_context_block: Optional[str],
        code: str,
        strategy: Optional[str] = None,
    ) -> list:
        """Apply post-LLM sanitization.

        Phase 2: when a FactBundle is stashed on the agent (set by
        `_try_inject_action_plan_items` before calling sanitize), route through
        the v2 candidate-anchored 9-check pipeline. Otherwise fall back to the
        legacy cost-basis path so old callers / test fixtures keep working.
        """
        bundle_dict = getattr(self, "_fact_bundle_for_sanitize", None)
        current_price = getattr(self, "_current_price_for_sanitize", None)
        if bundle_dict and isinstance(bundle_dict, dict):
            try:
                from src.analysis.facts import FactBundle, FactRecord, CandidateLevel
                from src.analysis.sanitizer_v2 import sanitize_with_candidates
                bundle = FactBundle(
                    as_of=bundle_dict.get("as_of", ""),
                    market=bundle_dict.get("market", "us"),
                    stock_code=bundle_dict.get("stock_code", ""),
                    facts=[FactRecord(**f) for f in bundle_dict.get("facts", [])],
                    candidates=[CandidateLevel(**c)
                                for c in bundle_dict.get("candidates", [])],
                )
                return sanitize_with_candidates(
                    items, bundle, strategy=strategy, current_price=current_price,
                )
            except Exception as exc:
                logger.warning(
                    "[sanitizer_v2] fallback to legacy due to error: %s", exc,
                )
                # fall through to legacy

        # Legacy cost-basis path (unchanged from Phase 1)
        from src.services.portfolio_context_service import _parse_portfolio_facts
        avg_cost = _parse_portfolio_facts(portfolio_context_block or "").get("avg_cost")
        # ... (rest of the existing legacy implementation stays as-is)
```

Keep the existing legacy body (lines 2769-2893) verbatim after the new dispatch block. Do not delete the legacy code.

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_analyzer_sanitizer_v2_dispatch.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Verify legacy sanitizer tests still pass**

```bash
python3.11 -m pytest tests/ -k "sanitize" -v
```

Expected: all `sanitize`-themed tests pass (legacy + v2).

- [ ] **Step 6: Commit**

```bash
git add src/analyzer.py tests/test_analyzer_sanitizer_v2_dispatch.py
git commit -m "feat(analyzer): dispatch sanitizer to v2 when FactBundle present"
```

---

### Task 13: Wire FactBundle + synthesizer fallback into `_try_inject_action_plan_items`

**Files:**
- Modify: `src/analyzer.py:2421-2551`
- Test: `tests/test_try_inject_action_plan_phase2.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/test_try_inject_action_plan_phase2.py
"""When fact_bundle is on dashboard, _try_inject_action_plan_items must:
  1. Pass the bundle into the prompt builder
  2. Stash bundle + current_price on self for the sanitizer
  3. Fall back to synthesize_from_candidates when sanitizer empties
"""
import json
from unittest.mock import MagicMock, patch

from src.analyzer import AnalysisAgent, AnalysisResult


def _result_with_bundle():
    r = AnalysisResult(
        code="NVDA", name="NVIDIA", sentiment_score=70,
        trend_prediction="up", operation_advice="hold",
        confidence_level="medium", analysis_summary="ok",
        risk_warning="ok", success=True, model_used="test",
    )
    r.dashboard = {
        "core_conclusion": {},
        "data_perspective": {"price_position": {"current_price": 223.47}},
        "intelligence": {},
        "fact_bundle": {
            "as_of": "x", "market": "us", "stock_code": "NVDA",
            "facts": [
                {"id": "technical.current_price", "type": "technical", "label": "现价",
                 "value": 223.47, "display_value": "$223.47", "unit": None,
                 "source": "", "confidence": None, "as_of": None, "extra": {}},
                {"id": "technical.resistance", "type": "technical", "label": "阻力",
                 "value": 226.13, "display_value": "$226.13", "unit": None,
                 "source": "", "confidence": None, "as_of": None, "extra": {}},
                {"id": "committee.pm_verdict", "type": "committee", "label": "PM",
                 "value": "hold", "display_value": "Hold", "unit": None,
                 "source": "", "confidence": None, "as_of": None, "extra": {}},
            ],
            "candidates": [
                {"id": "candidate.exit.1", "type": "candidate", "label": "阻力",
                 "value": 226.13, "display_value": "$226.13", "unit": None,
                 "source": "", "confidence": None, "as_of": None, "extra": {},
                 "direction": "take_profit", "price": 226.13,
                 "basis_fact_id": "technical.resistance",
                 "basis_rule": "resistance_touch",
                 "applicable_strategies": ["swing_trade"],
                 "tier": "primary", "distance_pct_from_current": 1.2},
                {"id": "candidate.stop.1", "type": "candidate", "label": "MA20",
                 "value": 213.39, "display_value": "$213.39", "unit": None,
                 "source": "", "confidence": None, "as_of": None, "extra": {},
                 "direction": "stop_loss", "price": 213.39,
                 "basis_fact_id": "technical.ma20",
                 "basis_rule": "ma20_breakdown",
                 "applicable_strategies": ["swing_trade"],
                 "tier": "primary", "distance_pct_from_current": -4.5},
            ],
        },
    }
    r.portfolio_match = None
    return r


def test_inject_passes_bundle_to_prompt_builder():
    """The prompt sent to the LLM must include the [事实数据库] block."""
    agent = AnalysisAgent.__new__(AnalysisAgent)
    agent.generate_text = MagicMock(return_value=json.dumps({
        "recommended_strategy": "swing_trade",
        "strategy_thesis": "thesis",
        "strategy_choices": [],
        "action_plan_items": [{
            "candidate_id": "candidate.exit.1", "trigger_price": 226.13,
            "direction": "take_profit", "priority": 1,
            "evidence_refs": ["technical.resistance", "committee.pm_verdict"],
            "tier": "primary",
        }],
    }))
    agent._sanitize_strategy_choices = lambda x, **k: x
    agent._recompute_position_outcome_summary = lambda *a, **k: None

    result = _result_with_bundle()
    AnalysisAgent._try_inject_action_plan_items(
        agent, result, "NVDA", portfolio_context_block=None,
    )
    sent_prompt = agent.generate_text.call_args[0][0]
    assert "[事实数据库]" in sent_prompt
    assert "[候选触发价位]" in sent_prompt
    assert "candidate.exit.1" in sent_prompt


def test_inject_falls_back_to_synthesizer_when_sanitizer_empties():
    """LLM emits all-invalid candidate_ids → sanitizer drops everything →
    synthesizer fills the gap with candidate-based items."""
    agent = AnalysisAgent.__new__(AnalysisAgent)
    agent.generate_text = MagicMock(return_value=json.dumps({
        "recommended_strategy": "swing_trade",
        "strategy_thesis": "thesis",
        "strategy_choices": [],
        "action_plan_items": [
            # All candidate_ids are bogus → sanitizer drops them
            {"candidate_id": "candidate.fake.1", "trigger_price": 999,
             "direction": "take_profit", "priority": 1,
             "evidence_refs": ["a", "b"], "tier": "primary"},
        ],
    }))
    agent._sanitize_strategy_choices = lambda x, **k: x
    agent._recompute_position_outcome_summary = lambda *a, **k: None

    result = _result_with_bundle()
    AnalysisAgent._try_inject_action_plan_items(
        agent, result, "NVDA", portfolio_context_block=None,
    )
    items = result.dashboard["core_conclusion"]["action_plan_items"]
    assert len(items) >= 1
    assert all(it.get("provenance") == "synthesized" for it in items)
    # Real candidate.exit.1 / candidate.stop.1 should now be the synthesized basis
    cids = [it["candidate_id"] for it in items]
    assert any(cid in ("candidate.exit.1", "candidate.stop.1") for cid in cids)
```

- [ ] **Step 2: Run failing tests**

```bash
python3.11 -m pytest tests/test_try_inject_action_plan_phase2.py -v
```

Expected: 2 tests FAIL (prompt does not include facts, synthesizer not wired).

- [ ] **Step 3: Wire bundle into prompt + synthesizer fallback**

The agent-mode bypass at `src/analyzer.py:2445-2461` ALSO calls `_sanitize_action_plan_items`, so the bundle stash must be done at the very top of `_try_inject_action_plan_items` (before the upstream-strategy branch), not after the compact_input block.

Add this block at the start of `_try_inject_action_plan_items` (right after `core = result.dashboard.get("core_conclusion") or {}` near line 2435):

```python
        # Phase 2: stash FactBundle + current price so `_sanitize_action_plan_items`
        # (called by both the upstream-strategy branch AND the LLM branch below) can
        # route to the v2 candidate-anchored sanitizer.
        fact_bundle = result.dashboard.get("fact_bundle") if isinstance(
            result.dashboard, dict
        ) else None
        self._fact_bundle_for_sanitize = fact_bundle
        current_price = None
        try:
            persp_local = result.dashboard.get("data_perspective") or {}
            cp = (persp_local.get("price_position") or {}).get("current_price")
            current_price = float(cp) if cp is not None else None
        except (TypeError, ValueError):
            current_price = None
        self._current_price_for_sanitize = current_price
```

The existing `persp = result.dashboard.get("data_perspective") or {}` line further down (around line 2466) stays — don't remove it.

Change the `build_strategy_classify_prompt(...)` call to forward the bundle:

```python
        prompt = build_strategy_classify_prompt(
            portfolio_context_block=portfolio_context_block,
            sentiment_dimensions=sentiment_dims,
            compact_dashboard=compact_input,
            fact_bundle=fact_bundle,
        )
```

After `items = self._sanitize_action_plan_items(items, portfolio_context_block, code, strategy=strategy)` (around line 2526), add the synthesizer fallback:

```python
        if not items and fact_bundle and isinstance(fact_bundle, dict):
            try:
                from src.analysis.facts import FactBundle, FactRecord, CandidateLevel
                from src.analysis.synthesizer import synthesize_from_candidates
                bundle_obj = FactBundle(
                    as_of=fact_bundle.get("as_of", ""),
                    market=fact_bundle.get("market", "us"),
                    stock_code=fact_bundle.get("stock_code", ""),
                    facts=[FactRecord(**f) for f in fact_bundle.get("facts", [])],
                    candidates=[CandidateLevel(**c)
                                for c in fact_bundle.get("candidates", [])],
                )
                fallback_strategy = strategy or "swing_trade"
                items = synthesize_from_candidates(
                    bundle_obj.candidates,
                    strategy=fallback_strategy,
                    facts=bundle_obj.facts,
                )
                logger.info(
                    "[action_plan] sanitizer empty -> synthesized %d items "
                    "from candidates for %s/%s", len(items), code, fallback_strategy,
                )
            except Exception as exc:
                logger.warning(
                    "[action_plan] synthesize_from_candidates failed for %s: %s",
                    code, exc,
                )
```

Also tag any LLM-produced items with `provenance: "llm"` BEFORE the synthesizer fallback runs (so we can distinguish):

After `items = self._sanitize_action_plan_items(...)` but BEFORE the fallback `if not items`, add:

```python
        for it in items:
            if isinstance(it, dict) and "provenance" not in it:
                it["provenance"] = "llm"
```

Finally, after the whole inject method exits, clean up the stashed bundle:

```python
        # Don't leak per-call state to the next stock
        self._fact_bundle_for_sanitize = None
        self._current_price_for_sanitize = None
```

Place that cleanup at the end of `_try_inject_action_plan_items` (just before the final `result.dashboard["core_conclusion"] = core_out` is implicit). Add a `try/finally` around the body if straightforward; if not, put it right after `self._recompute_position_outcome_summary(...)` near line 2549-2551.

- [ ] **Step 4: Run tests**

```bash
python3.11 -m pytest tests/test_try_inject_action_plan_phase2.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/analyzer.py tests/test_try_inject_action_plan_phase2.py
git commit -m "feat(analyzer): wire FactBundle into action_plan prompt + synthesizer"
```

---

### Task 14: End-to-end integration test with NVDA fixture

**Files:**
- Create: `tests/test_phase2_end_to_end.py`
- Reuse: `tests/fixtures/nvda_dashboard.json` (from Phase 1)

- [ ] **Step 1: Write the integration test**

```python
# tests/test_phase2_end_to_end.py
"""End-to-end: feed the NVDA dashboard fixture through facts_builder, then
through _try_inject_action_plan_items with a mocked LLM, and verify the final
action_plan_items pass all evidence-grounding invariants.
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.analyzer import AnalysisAgent, AnalysisResult
from src.analysis.facts_builder import build_fact_bundle
from dataclasses import asdict


FIXTURE = Path(__file__).parent / "fixtures" / "nvda_dashboard.json"


@pytest.mark.skipif(not FIXTURE.exists(), reason="NVDA fixture missing")
def test_phase2_nvda_pipeline_with_mocked_llm():
    dashboard = json.loads(FIXTURE.read_text())
    bundle = build_fact_bundle(
        stock_code="NVDA", market="us", dashboard=dashboard,
        portfolio_context=None, ohlc=None, rsi_12=71.1,
        qlib_predictions={"NVDA": {"score": 0.235, "rank": 0.847}},
        qlib_ic={"ic_ma_4w": 0.21},
        qlib_universe_size=503, qlib_week="2026-W21",
        as_of="2026-05-21T00:43:00Z",
    )

    result = AnalysisResult(
        code="NVDA", name="NVIDIA", sentiment_score=65,
        trend_prediction="up", operation_advice="hold",
        confidence_level="medium", analysis_summary="ok",
        risk_warning="ok", success=True, model_used="test",
    )
    result.dashboard = dict(dashboard)
    result.dashboard["fact_bundle"] = {
        "as_of": bundle.as_of, "market": bundle.market,
        "stock_code": bundle.stock_code,
        "facts": [asdict(f) for f in bundle.facts],
        "candidates": [asdict(c) for c in bundle.candidates],
    }
    result.portfolio_match = None

    # Pick the first 2 real candidate IDs from the bundle for the mocked LLM
    real_ids = [c.id for c in bundle.candidates if c.tier == "primary"][:2]
    assert len(real_ids) >= 2, "Fixture should yield ≥2 primary candidates"

    mock_resp = {
        "recommended_strategy": "swing_trade",
        "strategy_thesis": "..." * 30,
        "strategy_choices": [],
        "action_plan_items": [
            {
                "candidate_id": real_ids[0],
                "trigger_price": next(c.price for c in bundle.candidates
                                       if c.id == real_ids[0]),
                "direction": next(c.direction for c in bundle.candidates
                                   if c.id == real_ids[0]),
                "shares": 0.23, "pct_of_position": 30.0,
                "technical_basis": "x", "fundamental_basis": "y",
                "quant_signal": "z", "invalidation_rule": "w",
                "priority": 1,
                "evidence_refs": ["technical.current_price", "committee.pm_verdict"],
                "tier": "primary", "narrative": "...",
            },
            {
                "candidate_id": real_ids[1],
                "trigger_price": next(c.price for c in bundle.candidates
                                       if c.id == real_ids[1]),
                "direction": next(c.direction for c in bundle.candidates
                                   if c.id == real_ids[1]),
                "shares": 0.23, "pct_of_position": 30.0,
                "technical_basis": "x", "fundamental_basis": "y",
                "quant_signal": "z", "invalidation_rule": "w",
                "priority": 2,
                "evidence_refs": ["technical.current_price"],  # only 1 — autofill
                "tier": "primary", "narrative": "...",
            },
        ],
    }

    agent = AnalysisAgent.__new__(AnalysisAgent)
    agent.generate_text = MagicMock(return_value=json.dumps(mock_resp))
    agent._sanitize_strategy_choices = lambda x, **k: x
    agent._recompute_position_outcome_summary = lambda *a, **k: None

    AnalysisAgent._try_inject_action_plan_items(
        agent, result, "NVDA", portfolio_context_block=None,
    )

    core = result.dashboard["core_conclusion"]
    items = core["action_plan_items"]
    assert len(items) == 2

    # Invariants
    candidate_ids_in_bundle = {c.id for c in bundle.candidates}
    for it in items:
        # All candidate_ids must exist
        assert it["candidate_id"] in candidate_ids_in_bundle
        # All evidence_refs must be valid + ≥ 2
        valid_ids = ({f.id for f in bundle.facts}
                     | {c.id for c in bundle.candidates})
        assert all(r in valid_ids for r in it["evidence_refs"])
        assert len(it["evidence_refs"]) >= 2
        # provenance tagged
        assert it.get("provenance") == "llm"
    # Priorities renumbered 1..N
    assert sorted(it["priority"] for it in items) == [1, 2]
```

- [ ] **Step 2: Run the integration test**

```bash
python3.11 -m pytest tests/test_phase2_end_to_end.py -v
```

Expected: PASS, or SKIP if fixture missing.

- [ ] **Step 3: Verify all Phase 2 tests together**

```bash
python3.11 -m pytest tests/test_prompt_blocks.py tests/test_sanitizer_v2.py tests/test_synthesizer.py tests/test_strategy_classify_prompt_phase2.py tests/test_analyzer_sanitizer_v2_dispatch.py tests/test_try_inject_action_plan_phase2.py tests/test_phase2_end_to_end.py -v
```

Expected: all PASS (no skips except fixture).

- [ ] **Step 4: Commit**

```bash
git add tests/test_phase2_end_to_end.py
git commit -m "test(phase2): end-to-end with NVDA fixture + mocked LLM"
```

---

### Task 15: Full-suite regression + Phase 2 commit anchor

**Files:** (no new files)

- [ ] **Step 1: Run full offline pytest**

```bash
python3.11 -m pytest -m "not network" --tb=short 2>&1 | tail -40
```

Expected: 2400+ passed, ≤1 pre-existing failure (the known `test_agent_executor::test_max_steps_exceeded` from [[repo-agent-salvage-v2]] context). If a NEW failure appears, investigate before continuing.

- [ ] **Step 2: Lint critical errors**

```bash
flake8 src/analysis/ src/analyzer.py src/services/portfolio_context_service.py src/core/pipeline.py --select=E9,F63,F7,F82 --show-source --statistics
```

Expected: 0 errors.

- [ ] **Step 3: Py-compile the touched files**

```bash
python3.11 -m py_compile \
  src/analysis/prompt_blocks.py \
  src/analysis/sanitizer_v2.py \
  src/analysis/synthesizer.py \
  src/analyzer.py \
  src/services/portfolio_context_service.py \
  src/core/pipeline.py
```

Expected: no output (success).

- [ ] **Step 4: Update CHANGELOG**

Append to `docs/CHANGELOG.md` under `## [Unreleased]` (flat format per CLAUDE.md):

```
- [新功能] FactBundle Phase 2 落地：action_plan_items 提示词、sanitizer、synthesizer 全部接入 FactBundle 候选池，所有触发价位必须从代码生成的 candidates 中选择并附带 ≥2 条 evidence_refs。
```

- [ ] **Step 5: Anchor commit**

```bash
git add docs/CHANGELOG.md
git commit -m "docs(changelog): Phase 2 LLM grounding entry"
```

---

## Self-Review

**Spec coverage (Section B):**
- Prompt 改造 (3 blocks) — Tasks 2-5 ✅
- Sanitizer 9 checks — Tasks 6-10 (#1-#9) ✅
- Synthesizer 重写 (synthesize_from_candidates) — Task 11 ✅
- Dashboard schema 扩展 (candidate_id, evidence_refs, narrative, tier, provenance) — passes through via sanitizer + synthesizer (Tasks 6, 9, 11, 13); old reports still readable because every new field is optional and old reports just don't have them
- Token 预算 — informational, not a code requirement

**Placeholder scan:** None — every step has the actual test code, the actual implementation, and the exact command.

**Type consistency:**
- `sanitize_with_candidates(items, bundle, *, strategy, current_price)` — used consistently across Tasks 6, 7, 8, 9, 10, 12
- `synthesize_from_candidates(candidates, *, strategy, facts)` — used consistently across Tasks 11, 13, 14
- `build_strategy_classify_prompt(..., fact_bundle=...)` — added in Task 5, consumed in Task 13
- Stashed agent attributes: `_fact_bundle_for_sanitize` / `_current_price_for_sanitize` — set in Task 13, read in Task 12

**Notes for the executor:**
- Phase 2 does NOT touch notification/history rendering or frontend; those are Phase 3-5.
- The legacy `_sanitize_action_plan_items` code path stays in place as a no-bundle fallback. Don't delete it — agent-mode or upstream paths without a bundle still need it.
- Items the LLM emits without explicit `provenance` get tagged `"llm"` by Task 13. The synthesizer always tags `"synthesized"` (Task 11).
- Tests use `python3.11` per [[repo-py-toolchain.md]]; `python` is system 3.9.6 and will not work.
- Avoid running live LLM smoke until the user explicitly authorizes (per Phase 1 journal — quota concerns).
