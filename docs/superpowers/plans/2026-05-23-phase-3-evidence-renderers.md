# Phase 3 — Evidence-Grounded Renderers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Inline execution (no SDD dispatch) per [[feedback-subagent-prompt-size-limit]]. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface Phase 2's `candidate_id` / `evidence_refs` / `narrative` / `tier` / `provenance` fields in the two backend Markdown renderers (`src/notification.py` for Lark/Feishu/Bark and `src/services/history_service.py::_generate_single_stock_markdown` for the Web/desktop history view) as Wikipedia-style footnotes, with a strict parity test that catches drift between the two.

**Architecture:** Both renderers already keep parallel copies of `_render_action_plan_items` and `_render_strategy_section` (per [[repo-dual-renderers]]). Phase 3 adds a per-renderer `_render_evidence_footnotes(evidence_refs, fact_bundle)` helper to each file, extends both `_render_action_plan_items` to attach footnote superscripts `¹²³` to citation-bearing lines + emit a `🤖 代码兜底` badge when `provenance == "synthesized"`, then emits a unified footnote block at the end of the action plan section. The fact_bundle is sourced from `dashboard.fact_bundle` (already attached by `StockAnalysisPipeline._attach_fact_bundle`). All new behavior is gated on the presence of `fact_bundle` + `evidence_refs` — when absent (old reports), output is byte-identical to today.

**Tech Stack:** Python 3.11, pytest. No new dependencies.

**Reference spec:** `docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md` Section C lines 446–484 + Section D lines 599–608.

**Pre-conditions:** Phase 2 merged at HEAD `fbe7ad6` on `feat/committee-timeout-and-bilingual`. `dashboard.fact_bundle` is attached pre-action-plan-injection. `action_plan_items` may carry the new fields (all optional).

---

## File Structure

**Modify:**
- `src/notification.py:72-145` — extend `_render_action_plan_items` to accept `fact_bundle` and emit footnote superscripts + provenance badge + narrative; add `_render_evidence_footnotes(refs, fact_bundle)` helper above it
- `src/notification.py:1522-1530` (main report loop) — fetch `result.dashboard.fact_bundle`, collect evidence_refs across items, append footnote block after action plan section
- `src/services/history_service.py:39-112` — mirror Task 2 changes (same helper, same signature, same output)
- `src/services/history_service.py:1140-1147` (markdown builder) — mirror main-loop changes

**Create:**
- `tests/test_evidence_footnotes.py` — pure helper tests (`_render_evidence_footnotes` numbering, ordering, dedup, type grouping, missing-fact fallback)
- `tests/test_action_plan_renderer_phase3.py` — superscript attach + provenance badge + narrative inline rendering, both renderers
- `tests/test_renderer_parity_phase3.py` — drive both renderers with the same dashboard fixture, assert action plan + footnote blocks are byte-equal
- `tests/fixtures/nvda_dashboard_phase3.json` — extended NVDA fixture: fact_bundle + 2-3 action_plan_items with evidence_refs + 1 synthesized item

**Not touched in this phase:**
- `apps/dsa-web/` (Phase 4-5 — frontend components)
- `api/v1/endpoints/quote.py` (Phase 4 — refresh endpoint)
- `synthesize_action_plan_items` (Phase 2 — already done)
- `_format_prompt` / sanitizer (Phase 2 — already done)
- Existing legacy action_plan tests — pass through unchanged because fact_bundle/evidence_refs are optional

---

## Naming Conventions

Phase 3 output shape (new lines marked with ⬇):

```markdown
### 📋 持仓操作计划

**① ⬇️ 减仓**（优先级 1）— 触发价：$226.13
- **触发**：阻力位触及¹                       ⬇ superscript appended
- **操作**：卖出 0.2279 股（持仓 30%）
- **技术面**：RSI 71.1 超买²                   ⬇ superscript appended
- **基本面**：PM hold (5.8/10)³                ⬇ superscript appended
- **量化**：风控建议仓位 ≤30%⁴                 ⬇ superscript appended
- **失效**：放量站稳 $230 上方
- 🤖 *代码兜底*                                ⬇ NEW: provenance==synthesized

---
**证据脚注**                                    ⬇ NEW: emitted after all items
¹ `[technical.resistance]` 阻力位 $226.13
² `[technical.rsi_12]` RSI(12) = 71.1 (超买)
³ `[committee.pm_verdict]` PM 裁决 Hold
⁴ `[committee.risk.suggested_position_pct]` 风控建议仓位上限 30%
```

Superscript mapping: `1→¹ 2→² 3→³ ... 10→¹⁰` (the function uses Unicode superscript digits; numbers above 9 use multi-character combinations).

Field-to-superscript attachment rules (deterministic, per renderer):
- Line `- **触发**：` ← attach 1st evidence_ref of the item if present
- Line `- **技术面**：` ← attach next ref whose `fact_id` starts with `technical.`
- Line `- **基本面**：` ← attach next ref whose `fact_id` starts with `intel.` (`risk_alert.*`, `positive_catalyst.*`, `earnings_outlook`)
- Line `- **量化**：` ← attach next ref whose `fact_id` starts with `quant.` or `committee.risk.*`
- Remaining refs are still numbered and emitted in the footnote block — they just don't get an inline superscript

If `fact_bundle` is missing OR `evidence_refs` is empty/missing on every item → emit zero superscripts, no footnote block (byte-identical to current behavior).

---

### Task 1: `_render_evidence_footnotes` helper in notification.py

**Files:**
- Modify: `src/notification.py` — insert helper before `_render_action_plan_items` (around line 71)
- Test: `tests/test_evidence_footnotes.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/test_evidence_footnotes.py
import pytest

from src.notification import _render_evidence_footnotes


def _bundle():
    return {
        "facts": [
            {"id": "technical.resistance", "type": "technical",
             "label": "阻力位", "value": 226.13, "display_value": "$226.13",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {"role": "阻力"}},
            {"id": "technical.rsi_12", "type": "technical",
             "label": "RSI(12)", "value": 71.1, "display_value": "71.1",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {"zone": "超买"}},
            {"id": "committee.pm_verdict", "type": "committee",
             "label": "PM 裁决", "value": "hold", "display_value": "Hold",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {}},
        ],
        "candidates": [],
    }


def test_renders_numbered_footnotes_in_input_order():
    refs = ["technical.resistance", "technical.rsi_12", "committee.pm_verdict"]
    lines = _render_evidence_footnotes(refs, _bundle())
    assert lines[0] == "**证据脚注**"
    assert lines[1] == "¹ `[technical.resistance]` 阻力位 = $226.13"
    assert lines[2] == "² `[technical.rsi_12]` RSI(12) = 71.1 (超买)"
    assert lines[3] == "³ `[committee.pm_verdict]` PM 裁决 = Hold"


def test_dedup_preserves_first_occurrence():
    refs = ["technical.rsi_12", "technical.resistance", "technical.rsi_12"]
    lines = _render_evidence_footnotes(refs, _bundle())
    # Only 2 facts in footnotes (rsi_12 numbered ¹, resistance ²)
    assert lines[0] == "**证据脚注**"
    assert lines[1] == "¹ `[technical.rsi_12]` RSI(12) = 71.1 (超买)"
    assert lines[2] == "² `[technical.resistance]` 阻力位 = $226.13"
    assert len(lines) == 3


def test_missing_fact_id_falls_back_to_raw_id():
    refs = ["technical.resistance", "missing.fact.xyz"]
    lines = _render_evidence_footnotes(refs, _bundle())
    assert "² `[missing.fact.xyz]` (引用未在 FactBundle 中找到)" in lines


def test_empty_refs_returns_empty_list():
    assert _render_evidence_footnotes([], _bundle()) == []


def test_no_bundle_returns_empty_list():
    assert _render_evidence_footnotes(["technical.resistance"], None) == []
```

- [ ] **Step 2: Run failing test**

Run: `python3.11 -m pytest tests/test_evidence_footnotes.py -v`
Expected: ImportError on `_render_evidence_footnotes`.

- [ ] **Step 3: Add helper to notification.py**

Insert just above `_render_action_plan_items` in `src/notification.py` (around line 71):

```python
_SUPERSCRIPT_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _to_superscript(n: int) -> str:
    """Render an integer as Unicode superscript digits."""
    return str(n).translate(_SUPERSCRIPT_DIGITS)


def _resolve_fact(fact_id: str, fact_bundle: dict | None) -> dict | None:
    """Find a fact or candidate record by id in the bundle dict shape."""
    if not isinstance(fact_bundle, dict):
        return None
    for f in fact_bundle.get("facts") or []:
        if isinstance(f, dict) and f.get("id") == fact_id:
            return f
    for c in fact_bundle.get("candidates") or []:
        if isinstance(c, dict) and c.get("id") == fact_id:
            return c
    return None


def _format_fact_footnote(fact: dict) -> str:
    """One-line summary for the footnote block."""
    label = fact.get("label", "")
    display = fact.get("display_value", "")
    extra = fact.get("extra") or {}
    suffix = ""
    if isinstance(extra, dict):
        for key in ("zone", "role", "severity"):
            v = extra.get(key)
            if v not in (None, "", False):
                suffix = f" ({v})"
                break
    return f"`[{fact.get('id', '')}]` {label} = {display}{suffix}"


def _render_evidence_footnotes(
    evidence_refs: list,
    fact_bundle: dict | None,
) -> list:
    """Render the 证据脚注 block. Dedups refs preserving first-occurrence order.

    Returns an empty list when no refs OR no bundle — caller emits nothing.
    """
    if not evidence_refs or not fact_bundle:
        return []
    seen: set = set()
    deduped: list = []
    for r in evidence_refs:
        if isinstance(r, str) and r and r not in seen:
            seen.add(r)
            deduped.append(r)
    if not deduped:
        return []
    lines: list = ["**证据脚注**"]
    for i, fid in enumerate(deduped, start=1):
        sup = _to_superscript(i)
        fact = _resolve_fact(fid, fact_bundle)
        if fact is None:
            lines.append(f"{sup} `[{fid}]` (引用未在 FactBundle 中找到)")
        else:
            lines.append(f"{sup} {_format_fact_footnote(fact)}")
    return lines
```

- [ ] **Step 4: Run tests**

Run: `python3.11 -m pytest tests/test_evidence_footnotes.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/notification.py tests/test_evidence_footnotes.py
git commit -m "feat(notification): add _render_evidence_footnotes helper"
```

---

### Task 2: Mirror `_render_evidence_footnotes` to history_service.py

**Files:**
- Modify: `src/services/history_service.py` — insert helper before `_render_action_plan_items` (around line 38)
- Test: extend `tests/test_evidence_footnotes.py`

- [ ] **Step 1: Write failing test (parity assertion)**

Append to `tests/test_evidence_footnotes.py`:

```python
def test_history_service_helper_byte_equal_with_notification():
    """[[repo-dual-renderers]] gotcha guard: both renderers MUST emit the same
    footnote block for the same input."""
    from src.notification import _render_evidence_footnotes as notif_render
    from src.services.history_service import _render_evidence_footnotes as hist_render

    refs = ["technical.resistance", "technical.rsi_12", "committee.pm_verdict"]
    bundle = _bundle()
    assert notif_render(refs, bundle) == hist_render(refs, bundle)


def test_history_service_helper_handles_empty_inputs():
    from src.services.history_service import _render_evidence_footnotes as hist_render
    assert hist_render([], _bundle()) == []
    assert hist_render(["technical.rsi_12"], None) == []
```

- [ ] **Step 2: Run failing test**

Run: `python3.11 -m pytest tests/test_evidence_footnotes.py -v`
Expected: ImportError on history_service version.

- [ ] **Step 3: Add the identical helper block to history_service.py**

In `src/services/history_service.py`, insert above `_render_action_plan_items` (around line 38) the SAME block of code from Task 1 Step 3 (verbatim — `_SUPERSCRIPT_DIGITS`, `_to_superscript`, `_resolve_fact`, `_format_fact_footnote`, `_render_evidence_footnotes`).

This duplication is intentional per [[repo-dual-renderers]]. The parity test in Task 7 guards against drift.

- [ ] **Step 4: Run tests**

Run: `python3.11 -m pytest tests/test_evidence_footnotes.py -v`
Expected: 7 PASSED (5 from Task 1 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/services/history_service.py tests/test_evidence_footnotes.py
git commit -m "feat(history): mirror _render_evidence_footnotes helper"
```

---

### Task 3: Extend `_render_action_plan_items` (notification.py) — superscripts + badge + narrative

**Files:**
- Modify: `src/notification.py:72-145`
- Test: `tests/test_action_plan_renderer_phase3.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/test_action_plan_renderer_phase3.py
import pytest

from src.notification import _render_action_plan_items as notif_render
from src.services.history_service import _render_action_plan_items as hist_render


def _fact_bundle():
    return {
        "facts": [
            {"id": "technical.resistance", "type": "technical",
             "label": "阻力位", "value": 226.13, "display_value": "$226.13",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {"role": "阻力"}},
            {"id": "technical.rsi_12", "type": "technical",
             "label": "RSI(12)", "value": 71.1, "display_value": "71.1",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {"zone": "超买"}},
            {"id": "committee.pm_verdict", "type": "committee",
             "label": "PM 裁决", "value": "hold", "display_value": "Hold",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {}},
            {"id": "intel.risk_alert.0", "type": "intel",
             "label": "风险警示", "value": "RSI 71.1 超买",
             "display_value": "RSI 71.1 超买", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {}},
        ],
        "candidates": [],
    }


def _llm_item():
    return {
        "candidate_id": "candidate.exit.1",
        "trigger_price": 226.13,
        "trigger_condition": "阻力位触及",
        "direction": "take_profit",
        "shares": 0.2279,
        "pct_of_position": 30.0,
        "pct_of_equity": 3.5,
        "technical_basis": "RSI 71.1 超买",
        "fundamental_basis": "PM hold (5.8/10)",
        "quant_signal": "风控建议仓位 ≤30%",
        "invalidation_rule": "放量站稳 $230 上方",
        "priority": 1,
        "evidence_refs": ["technical.resistance", "technical.rsi_12",
                          "committee.pm_verdict"],
        "narrative": "RSI 超买 + 阻力位触及 → 减仓",
        "tier": "primary",
        "provenance": "llm",
    }


def _synth_item():
    return {
        "candidate_id": "candidate.stop.1",
        "trigger_price": 213.39,
        "trigger_condition": "MA20 跌破",
        "direction": "stop_loss",
        "shares": 0,
        "pct_of_position": 100.0,
        "technical_basis": "ma20_breakdown（来自代码合成）",
        "evidence_refs": ["technical.ma20", "committee.pm_verdict"],
        "narrative": "MA20 跌破（代码兜底）",
        "tier": "primary",
        "provenance": "synthesized",
        "priority": 2,
    }


def test_notification_render_attaches_superscripts_to_basis_lines():
    lines = notif_render([_llm_item()], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    # First ref (technical.resistance) goes to **触发**
    assert "**触发**：阻力位触及¹" in joined
    # Next technical ref → **技术面**
    assert "**技术面**：RSI 71.1 超买²" in joined
    # Committee ref → **量化** (committee.risk.* or committee.* maps to quant slot)
    assert "**量化**：风控建议仓位 ≤30%³" in joined


def test_notification_render_emits_synthesized_badge():
    lines = notif_render([_synth_item()], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "🤖" in joined
    assert "代码兜底" in joined


def test_notification_render_no_badge_for_llm_provenance():
    lines = notif_render([_llm_item()], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "代码兜底" not in joined


def test_notification_render_without_bundle_unchanged():
    """When fact_bundle is None, output must NOT include superscripts or badges
    even if items carry evidence_refs / provenance."""
    lines = notif_render([_llm_item()], fact_bundle=None)
    joined = "\n".join(lines)
    assert "¹" not in joined
    assert "²" not in joined
    assert "代码兜底" not in joined


def test_notification_render_without_evidence_refs_no_superscripts():
    item = _llm_item()
    item.pop("evidence_refs", None)
    lines = notif_render([item], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "¹" not in joined


def test_notification_render_legacy_signature_still_works():
    """Old call sites that pass no fact_bundle keyword must keep working."""
    item = {
        "trigger_price": 100.0, "trigger_condition": "test",
        "direction": "buy", "shares": 1, "priority": 1,
    }
    lines = notif_render([item])  # no fact_bundle
    assert any("100.00" in line for line in lines)
```

- [ ] **Step 2: Run failing tests**

Run: `python3.11 -m pytest tests/test_action_plan_renderer_phase3.py -v`
Expected: FAILs on superscript expectations / badge expectations.

- [ ] **Step 3: Extend the function in notification.py**

Replace `_render_action_plan_items` in `src/notification.py` (lines 72-145) with:

```python
def _render_action_plan_items(items: list, fact_bundle: dict | None = None) -> list:
    """Render action_plan_items as markdown lines replacing the position-advice table.

    Returns a list of markdown strings ending with a trailing empty string.
    Direction emojis: buy=⬆️ sell=⬇️ stop_loss=🛑 take_profit=🎯

    Phase 3: when `fact_bundle` is supplied, attaches Wikipedia-style footnote
    superscripts (¹²³) to lines whose evidence_refs match by type, and emits a
    🤖 代码兜底 badge for items with `provenance == "synthesized"`.
    """
    _DIRECTION_EMOJI = {
        "buy": "⬆️",
        "sell": "⬇️",
        "stop_loss": "🛑",
        "take_profit": "🎯",
    }
    _DIRECTION_ZH = {
        "buy": "买入/加仓",
        "sell": "减仓",
        "stop_loss": "止损清仓",
        "take_profit": "止盈",
    }
    _ORDINALS = ["①", "②", "③", "④", "⑤"]

    # Phase 3: number each evidence_ref globally across items so the footnote
    # block at the end has a stable 1..N numbering.
    ref_to_num: dict = {}
    next_num = [1]

    def _num_for(ref_id: str) -> str:
        if ref_id not in ref_to_num:
            ref_to_num[ref_id] = next_num[0]
            next_num[0] += 1
        return _to_superscript(ref_to_num[ref_id])

    def _pick_ref(refs: list, prefix: str, used: set) -> str | None:
        for r in refs:
            if isinstance(r, str) and r.startswith(prefix) and r not in used:
                used.add(r)
                return r
        return None

    lines = ["### 📋 持仓操作计划", ""]
    for idx, item in enumerate(items[:4]):
        direction = item.get("direction", "buy")
        emoji = _DIRECTION_EMOJI.get(direction, "📌")
        direction_zh = _DIRECTION_ZH.get(direction, direction)
        ordinal = _ORDINALS[idx] if idx < len(_ORDINALS) else f"({idx+1})"
        priority = item.get("priority", idx + 1)
        trigger_price = item.get("trigger_price")
        trigger_cond = item.get("trigger_condition", "")
        shares = item.get("shares", 0)
        pct_pos = item.get("pct_of_position")
        pct_eq = item.get("pct_of_equity")
        tech = item.get("technical_basis", "")
        fund = item.get("fundamental_basis", "")
        quant = item.get("quant_signal", "")
        inv_rule = item.get("invalidation_rule", "")

        if not trigger_price:
            continue

        # Phase 3: assign refs to lines (only when fact_bundle present)
        refs = item.get("evidence_refs") or [] if fact_bundle else []
        if not isinstance(refs, list):
            refs = []
        used: set = set()
        trigger_ref = refs[0] if refs else None
        if trigger_ref:
            used.add(trigger_ref)
        tech_ref = _pick_ref(refs, "technical.", used)
        fund_ref = _pick_ref(refs, "intel.", used)
        # quant slot accepts both quant.* and committee.* (committee anchors are
        # what synthesizer + sanitizer autofill emit when basis is technical)
        quant_ref = _pick_ref(refs, "quant.", used) or _pick_ref(refs, "committee.", used)

        # Pre-register remaining refs so they're numbered in the footnote block
        # even though they don't get an inline superscript
        for r in refs:
            if r not in used and isinstance(r, str):
                used.add(r)
                _num_for(r)

        # position sizing string
        pos_str = ""
        if pct_pos is not None:
            pos_str = f"持仓 {pct_pos:.1f}%"
        if pct_eq:
            pos_str = f"{pos_str} / 权益 {pct_eq:.1f}%" if pos_str else f"权益 {pct_eq:.1f}%"
        if shares:
            ops_str = f"{direction_zh} {shares} 股"
            if pos_str:
                ops_str += f"（{pos_str}）"
        elif pos_str:
            ops_str = f"{direction_zh}（{pos_str}）"
        else:
            ops_str = direction_zh

        lines.append(f"**{ordinal} {emoji} {direction_zh}**（优先级 {priority}）— 触发价：${trigger_price:.2f}")
        sup_trig = _num_for(trigger_ref) if trigger_ref else ""
        lines.append(f"- **触发**：{trigger_cond}{sup_trig}")
        lines.append(f"- **操作**：{ops_str}")
        if tech:
            sup = _num_for(tech_ref) if tech_ref else ""
            lines.append(f"- **技术面**：{tech}{sup}")
        if fund:
            sup = _num_for(fund_ref) if fund_ref else ""
            lines.append(f"- **基本面**：{fund}{sup}")
        if quant:
            sup = _num_for(quant_ref) if quant_ref else ""
            lines.append(f"- **量化**：{quant}{sup}")
        if inv_rule:
            lines.append(f"- **失效**：{inv_rule}")
        if fact_bundle and item.get("provenance") == "synthesized":
            lines.append("- 🤖 *代码兜底*")
        lines.append("")
    return lines
```

- [ ] **Step 4: Run tests**

Run: `python3.11 -m pytest tests/test_action_plan_renderer_phase3.py -v -k notif`
Expected: 4 notification-side tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/notification.py tests/test_action_plan_renderer_phase3.py
git commit -m "feat(notification): attach footnote superscripts + synthesized badge"
```

---

### Task 4: Mirror `_render_action_plan_items` extension in history_service.py

**Files:**
- Modify: `src/services/history_service.py:39-112`
- Test: extend `tests/test_action_plan_renderer_phase3.py`

- [ ] **Step 1: Write failing tests for history_service side**

Append to `tests/test_action_plan_renderer_phase3.py`:

```python
def test_history_render_attaches_superscripts_to_basis_lines():
    lines = hist_render([_llm_item()], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "**触发**：阻力位触及¹" in joined
    assert "**技术面**：RSI 71.1 超买²" in joined
    assert "**量化**：风控建议仓位 ≤30%³" in joined


def test_history_render_emits_synthesized_badge():
    lines = hist_render([_synth_item()], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "🤖" in joined
    assert "代码兜底" in joined


def test_history_render_without_bundle_unchanged():
    lines = hist_render([_llm_item()], fact_bundle=None)
    joined = "\n".join(lines)
    assert "¹" not in joined
    assert "代码兜底" not in joined


def test_history_render_legacy_signature_still_works():
    item = {
        "trigger_price": 100.0, "trigger_condition": "test",
        "direction": "buy", "shares": 1, "priority": 1,
    }
    lines = hist_render([item])
    assert any("100.00" in line for line in lines)
```

- [ ] **Step 2: Run failing tests**

Run: `python3.11 -m pytest tests/test_action_plan_renderer_phase3.py -v -k hist`
Expected: FAILs on hist-side expectations.

- [ ] **Step 3: Mirror the function**

In `src/services/history_service.py`, replace `_render_action_plan_items` (lines 39-112) with the SAME function body from Task 3 Step 3 (verbatim — same signature `def _render_action_plan_items(items: list, fact_bundle: dict | None = None) -> list`, same internal helpers `_num_for` / `_pick_ref`, same line emissions).

This duplication is intentional per [[repo-dual-renderers]]. Task 7's parity test guards against drift.

- [ ] **Step 4: Run tests**

Run: `python3.11 -m pytest tests/test_action_plan_renderer_phase3.py -v`
Expected: 10 PASSED (6 notification + 4 history).

- [ ] **Step 5: Commit**

```bash
git add src/services/history_service.py tests/test_action_plan_renderer_phase3.py
git commit -m "feat(history): mirror action_plan superscripts + synthesized badge"
```

---

### Task 5: Wire fact_bundle + footnote emission into notification.py main report assembly

**Files:**
- Modify: `src/notification.py:1522-1530` (the section that calls `_render_action_plan_items`)
- Test: `tests/test_notification_footnote_emission.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/test_notification_footnote_emission.py
"""End-to-end: feed a result dict with dashboard.fact_bundle + action_plan_items
through notification's main report assembly and assert the footnote block
appears at the end of the action plan section.
"""
import pytest

from src.notification import format_single_stock_report


def _result_with_evidence():
    return {
        "code": "NVDA",
        "name": "NVIDIA",
        "sentiment_score": 65,
        "trend_prediction": "up",
        "operation_advice": "hold",
        "confidence_level": "medium",
        "analysis_summary": "ok",
        "risk_warning": "ok",
        "model_used": "test",
        "report_language": "zh",
        "dashboard": {
            "core_conclusion": {
                "recommended_strategy": "swing_trade",
                "strategy_thesis": "thesis",
                "strategy_choices": [],
                "action_plan_items": [
                    {
                        "candidate_id": "candidate.exit.1",
                        "trigger_price": 226.13,
                        "trigger_condition": "阻力位触及",
                        "direction": "take_profit",
                        "shares": 0,
                        "pct_of_position": 30.0,
                        "technical_basis": "RSI 71.1 超买",
                        "fundamental_basis": "PM hold (5.8/10)",
                        "evidence_refs": ["technical.resistance", "technical.rsi_12",
                                           "committee.pm_verdict"],
                        "tier": "primary",
                        "provenance": "llm",
                        "priority": 1,
                    },
                ],
            },
            "fact_bundle": {
                "as_of": "x", "market": "us", "stock_code": "NVDA",
                "facts": [
                    {"id": "technical.resistance", "type": "technical",
                     "label": "阻力位", "value": 226.13, "display_value": "$226.13",
                     "unit": None, "source": "", "confidence": None,
                     "as_of": None, "extra": {"role": "阻力"}},
                    {"id": "technical.rsi_12", "type": "technical",
                     "label": "RSI(12)", "value": 71.1, "display_value": "71.1",
                     "unit": None, "source": "", "confidence": None,
                     "as_of": None, "extra": {"zone": "超买"}},
                    {"id": "committee.pm_verdict", "type": "committee",
                     "label": "PM 裁决", "value": "hold", "display_value": "Hold",
                     "unit": None, "source": "", "confidence": None,
                     "as_of": None, "extra": {}},
                ],
                "candidates": [],
            },
        },
    }


def test_notification_emits_footnote_section_after_action_plan():
    md = format_single_stock_report(_result_with_evidence())
    # Action plan section appears, then footnote section
    assert "📋 持仓操作计划" in md
    assert "**证据脚注**" in md
    plan_idx = md.index("📋 持仓操作计划")
    footnote_idx = md.index("**证据脚注**")
    assert plan_idx < footnote_idx


def test_notification_no_footnote_section_when_bundle_missing():
    result = _result_with_evidence()
    result["dashboard"].pop("fact_bundle", None)
    md = format_single_stock_report(result)
    assert "📋 持仓操作计划" in md
    assert "**证据脚注**" not in md
```

- [ ] **Step 2: Run failing test**

Run: `python3.11 -m pytest tests/test_notification_footnote_emission.py -v`
Expected: 2 FAILs (footnotes block absent).

- [ ] **Step 3: Wire bundle through the main report loop**

Find the section in `src/notification.py` around line 1520-1535 (the action_plan_items rendering branch). Replace:

```python
                # 持仓操作计划（action_plan_items 优先；fallback 到 position_advice 表格）
                action_plan_items = (
                    core.get("action_plan_items") if isinstance(core.get("action_plan_items"), list)
                    else None
                )
                if action_plan_items:
                    report_lines.extend(_render_action_plan_items(action_plan_items))
```

with:

```python
                # 持仓操作计划（action_plan_items 优先；fallback 到 position_advice 表格）
                action_plan_items = (
                    core.get("action_plan_items") if isinstance(core.get("action_plan_items"), list)
                    else None
                )
                fact_bundle = (
                    dashboard.get("fact_bundle") if isinstance(dashboard, dict) else None
                )
                if action_plan_items:
                    report_lines.extend(
                        _render_action_plan_items(action_plan_items, fact_bundle=fact_bundle)
                    )
                    # Phase 3: emit Wikipedia-style footnote block under the
                    # action plan when any item supplied evidence_refs.
                    if fact_bundle:
                        collected_refs: list = []
                        for it in action_plan_items[:4]:
                            for r in (it.get("evidence_refs") or []):
                                if isinstance(r, str) and r and r not in collected_refs:
                                    collected_refs.append(r)
                        footnote_lines = _render_evidence_footnotes(
                            collected_refs, fact_bundle,
                        )
                        if footnote_lines:
                            report_lines.append("---")
                            report_lines.extend(footnote_lines)
                            report_lines.append("")
```

Verify the surrounding context defines `dashboard` (it does — `dashboard = result.get("dashboard")` is a few lines above; if not, fetch it from `result["dashboard"]`).

- [ ] **Step 4: Run tests**

Run: `python3.11 -m pytest tests/test_notification_footnote_emission.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Confirm no legacy notification tests broke**

Run: `python3.11 -m pytest tests/ -k notification -v --tb=short 2>&1 | tail -20`
Expected: all passing (legacy single-stock tests don't supply fact_bundle so they hit the no-footnote branch).

- [ ] **Step 6: Commit**

```bash
git add src/notification.py tests/test_notification_footnote_emission.py
git commit -m "feat(notification): emit footnote block under action plan when bundle present"
```

---

### Task 6: Wire fact_bundle + footnote emission into history_service.py

**Files:**
- Modify: `src/services/history_service.py:1140-1147`
- Test: `tests/test_history_footnote_emission.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/test_history_footnote_emission.py
"""End-to-end: drive _generate_single_stock_markdown with dashboard.fact_bundle
+ action_plan_items + evidence_refs and assert footnote block emission."""
import pytest

from src.services.history_service import _generate_single_stock_markdown


def _stock_record():
    """Construct a minimal stock record matching the history_service input shape."""
    return {
        "code": "NVDA",
        "name": "NVIDIA",
        "sentiment_score": 65,
        "trend_prediction": "up",
        "operation_advice": "hold",
        "analysis_summary": "ok",
        "model_used": "test",
        "report_language": "zh",
        "dashboard": {
            "core_conclusion": {
                "recommended_strategy": "swing_trade",
                "strategy_thesis": "thesis",
                "strategy_choices": [],
                "action_plan_items": [
                    {
                        "candidate_id": "candidate.exit.1",
                        "trigger_price": 226.13,
                        "trigger_condition": "阻力位触及",
                        "direction": "take_profit",
                        "shares": 0,
                        "pct_of_position": 30.0,
                        "technical_basis": "RSI 71.1 超买",
                        "evidence_refs": ["technical.resistance",
                                           "technical.rsi_12",
                                           "committee.pm_verdict"],
                        "tier": "primary",
                        "provenance": "llm",
                        "priority": 1,
                    },
                ],
            },
            "fact_bundle": {
                "as_of": "x", "market": "us", "stock_code": "NVDA",
                "facts": [
                    {"id": "technical.resistance", "type": "technical",
                     "label": "阻力位", "value": 226.13, "display_value": "$226.13",
                     "unit": None, "source": "", "confidence": None,
                     "as_of": None, "extra": {"role": "阻力"}},
                    {"id": "technical.rsi_12", "type": "technical",
                     "label": "RSI(12)", "value": 71.1, "display_value": "71.1",
                     "unit": None, "source": "", "confidence": None,
                     "as_of": None, "extra": {"zone": "超买"}},
                    {"id": "committee.pm_verdict", "type": "committee",
                     "label": "PM 裁决", "value": "hold", "display_value": "Hold",
                     "unit": None, "source": "", "confidence": None,
                     "as_of": None, "extra": {}},
                ],
                "candidates": [],
            },
        },
    }


def test_history_emits_footnote_section_after_action_plan():
    md = _generate_single_stock_markdown(_stock_record())
    assert "📋 持仓操作计划" in md
    assert "**证据脚注**" in md
    assert md.index("📋 持仓操作计划") < md.index("**证据脚注**")


def test_history_no_footnote_section_when_bundle_missing():
    record = _stock_record()
    record["dashboard"].pop("fact_bundle", None)
    md = _generate_single_stock_markdown(record)
    assert "📋 持仓操作计划" in md
    assert "**证据脚注**" not in md
```

- [ ] **Step 2: Run failing test**

Run: `python3.11 -m pytest tests/test_history_footnote_emission.py -v`
Expected: 2 FAILs.

- [ ] **Step 3: Wire bundle through history_service main loop**

Find the section in `src/services/history_service.py` around line 1140-1147 (the action_plan_items rendering branch). Replace:

```python
        # 持仓操作计划（action_plan_items 优先；fallback 到 position_advice 表格）
        action_plan_items = (
            core.get("action_plan_items") if isinstance(core.get("action_plan_items"), list)
            else None
        )
        if action_plan_items:
            report_lines.extend(_render_action_plan_items(action_plan_items))
```

with:

```python
        # 持仓操作计划（action_plan_items 优先；fallback 到 position_advice 表格）
        action_plan_items = (
            core.get("action_plan_items") if isinstance(core.get("action_plan_items"), list)
            else None
        )
        fact_bundle = (
            dashboard.get("fact_bundle") if isinstance(dashboard, dict) else None
        )
        if action_plan_items:
            report_lines.extend(
                _render_action_plan_items(action_plan_items, fact_bundle=fact_bundle)
            )
            # Phase 3: emit Wikipedia-style footnote block under the action plan
            if fact_bundle:
                collected_refs: list = []
                for it in action_plan_items[:4]:
                    for r in (it.get("evidence_refs") or []):
                        if isinstance(r, str) and r and r not in collected_refs:
                            collected_refs.append(r)
                footnote_lines = _render_evidence_footnotes(
                    collected_refs, fact_bundle,
                )
                if footnote_lines:
                    report_lines.append("---")
                    report_lines.extend(footnote_lines)
                    report_lines.append("")
```

- [ ] **Step 4: Run tests**

Run: `python3.11 -m pytest tests/test_history_footnote_emission.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Confirm no legacy history_service tests broke**

Run: `python3.11 -m pytest tests/ -k history -v --tb=short 2>&1 | tail -20`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/services/history_service.py tests/test_history_footnote_emission.py
git commit -m "feat(history): emit footnote block under action plan when bundle present"
```

---

### Task 7: Renderer parity test (THE critical guard)

**Files:**
- Create: `tests/fixtures/nvda_dashboard_phase3.json`
- Create: `tests/test_renderer_parity_phase3.py`

- [ ] **Step 1: Build the shared fixture**

Create `tests/fixtures/nvda_dashboard_phase3.json` with a dashboard containing:
- `core_conclusion.recommended_strategy = "swing_trade"`
- `core_conclusion.action_plan_items` = 3 items: one LLM provenance with full refs, one synthesized provenance with 2 refs, one item with NO evidence_refs (legacy-shape passthrough)
- `fact_bundle.facts` = 5 facts spanning technical + committee + intel + quant types
- `fact_bundle.candidates` = 3 candidates so candidate_id resolution works

Use this exact content (compact JSON):

```json
{
  "core_conclusion": {
    "recommended_strategy": "swing_trade",
    "strategy_thesis": "RSI 71.1 进入超买区，阻力位 $226.13 触及概率高；PM hold (5.8/10) 建议减仓兑现。",
    "strategy_choices": [],
    "action_plan_items": [
      {
        "candidate_id": "candidate.exit.1",
        "trigger_price": 226.13,
        "trigger_condition": "阻力位触及",
        "direction": "take_profit",
        "shares": 0.2279,
        "pct_of_position": 30.0,
        "pct_of_equity": 3.5,
        "technical_basis": "RSI 71.1 超买",
        "fundamental_basis": "PM hold (5.8/10)",
        "quant_signal": "Qlib rank 前 15%",
        "invalidation_rule": "放量站稳 $230 上方",
        "priority": 1,
        "evidence_refs": ["technical.resistance", "technical.rsi_12", "committee.pm_verdict", "quant.qlib_rank"],
        "narrative": "RSI 超买 + 阻力位触及",
        "tier": "primary",
        "provenance": "llm"
      },
      {
        "candidate_id": "candidate.stop.1",
        "trigger_price": 213.39,
        "trigger_condition": "MA20 跌破",
        "direction": "stop_loss",
        "shares": 0,
        "pct_of_position": 100.0,
        "technical_basis": "ma20_breakdown",
        "evidence_refs": ["technical.ma20", "committee.pm_verdict"],
        "narrative": "MA20 跌破（代码兜底）",
        "tier": "primary",
        "provenance": "synthesized",
        "priority": 2
      },
      {
        "trigger_price": 230.0,
        "trigger_condition": "Legacy item without evidence_refs",
        "direction": "take_profit",
        "shares": 0,
        "pct_of_position": 30.0,
        "technical_basis": "Legacy template",
        "priority": 3
      }
    ]
  },
  "fact_bundle": {
    "as_of": "2026-05-23T08:30:00Z",
    "market": "us",
    "stock_code": "NVDA",
    "facts": [
      {"id": "technical.resistance", "type": "technical", "label": "阻力位", "value": 226.13, "display_value": "$226.13", "unit": null, "source": "", "confidence": null, "as_of": null, "extra": {"role": "阻力"}},
      {"id": "technical.rsi_12", "type": "technical", "label": "RSI(12)", "value": 71.1, "display_value": "71.1", "unit": null, "source": "", "confidence": null, "as_of": null, "extra": {"zone": "超买"}},
      {"id": "technical.ma20", "type": "technical", "label": "MA20", "value": 213.39, "display_value": "$213.39", "unit": null, "source": "", "confidence": null, "as_of": null, "extra": {}},
      {"id": "committee.pm_verdict", "type": "committee", "label": "PM 裁决", "value": "hold", "display_value": "Hold", "unit": null, "source": "", "confidence": null, "as_of": null, "extra": {}},
      {"id": "quant.qlib_rank", "type": "quant", "label": "Qlib 截面分位", "value": 0.847, "display_value": "前 15%", "unit": null, "source": "", "confidence": null, "as_of": null, "extra": {}}
    ],
    "candidates": [
      {"id": "candidate.exit.1", "type": "candidate", "label": "阻力", "value": 226.13, "display_value": "$226.13", "unit": null, "source": "", "confidence": null, "as_of": null, "extra": {}, "direction": "take_profit", "price": 226.13, "basis_fact_id": "technical.resistance", "basis_rule": "resistance_touch", "applicable_strategies": ["swing_trade"], "tier": "primary", "distance_pct_from_current": 1.2},
      {"id": "candidate.stop.1", "type": "candidate", "label": "MA20", "value": 213.39, "display_value": "$213.39", "unit": null, "source": "", "confidence": null, "as_of": null, "extra": {}, "direction": "stop_loss", "price": 213.39, "basis_fact_id": "technical.ma20", "basis_rule": "ma20_breakdown", "applicable_strategies": ["swing_trade"], "tier": "primary", "distance_pct_from_current": -4.5}
    ]
  }
}
```

- [ ] **Step 2: Write the parity test**

```python
# tests/test_renderer_parity_phase3.py
"""[[repo-dual-renderers]] guard: notification.py and history_service.py both
render the same action_plan + footnote block from the same dashboard input.
The two renderers MUST produce byte-equal action_plan + footnote sections.
"""
import json
from pathlib import Path

from src.notification import _render_action_plan_items as notif_render
from src.notification import _render_evidence_footnotes as notif_footnotes
from src.services.history_service import _render_action_plan_items as hist_render
from src.services.history_service import _render_evidence_footnotes as hist_footnotes


FIXTURE = Path(__file__).parent / "fixtures" / "nvda_dashboard_phase3.json"


def test_action_plan_section_byte_equal():
    dashboard = json.loads(FIXTURE.read_text())
    items = dashboard["core_conclusion"]["action_plan_items"]
    bundle = dashboard["fact_bundle"]

    notif_lines = notif_render(items, fact_bundle=bundle)
    hist_lines = hist_render(items, fact_bundle=bundle)
    assert notif_lines == hist_lines, (
        "notification.py vs history_service.py action_plan output diverged"
    )


def test_footnote_section_byte_equal():
    dashboard = json.loads(FIXTURE.read_text())
    items = dashboard["core_conclusion"]["action_plan_items"]
    bundle = dashboard["fact_bundle"]

    # Collect refs identically to how the main report loop does it
    refs: list = []
    for it in items[:4]:
        for r in (it.get("evidence_refs") or []):
            if isinstance(r, str) and r and r not in refs:
                refs.append(r)

    notif_fn = notif_footnotes(refs, bundle)
    hist_fn = hist_footnotes(refs, bundle)
    assert notif_fn == hist_fn, (
        "notification.py vs history_service.py footnote output diverged"
    )


def test_synthesized_badge_appears_in_both():
    dashboard = json.loads(FIXTURE.read_text())
    items = dashboard["core_conclusion"]["action_plan_items"]
    bundle = dashboard["fact_bundle"]
    notif_out = "\n".join(notif_render(items, fact_bundle=bundle))
    hist_out = "\n".join(hist_render(items, fact_bundle=bundle))
    assert "🤖" in notif_out
    assert "🤖" in hist_out


def test_legacy_item_without_evidence_refs_still_renders():
    """The 3rd fixture item has no evidence_refs — must still render its
    trigger price line in both renderers (no superscripts attached)."""
    dashboard = json.loads(FIXTURE.read_text())
    items = dashboard["core_conclusion"]["action_plan_items"]
    bundle = dashboard["fact_bundle"]
    notif_out = "\n".join(notif_render(items, fact_bundle=bundle))
    hist_out = "\n".join(hist_render(items, fact_bundle=bundle))
    assert "230.00" in notif_out
    assert "230.00" in hist_out
```

- [ ] **Step 3: Run the parity test**

Run: `python3.11 -m pytest tests/test_renderer_parity_phase3.py -v`
Expected: 4 PASSED.

If any of `test_action_plan_section_byte_equal` / `test_footnote_section_byte_equal` fail, the two renderers have drifted — go diff the two files and reconcile before continuing.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/nvda_dashboard_phase3.json tests/test_renderer_parity_phase3.py
git commit -m "test(renderer): parity guard for notification vs history footnote output"
```

---

### Task 8: Full-suite regression + CHANGELOG + Phase 3 commit anchor

**Files:** (no new files)

- [ ] **Step 1: Run full offline pytest**

Run: `python3.11 -m pytest -m "not network" --tb=short 2>&1 | tail -30`
Expected: 2500+ passed; the only known failure is the pre-existing `test_agent_executor::test_max_steps_exceeded` per [[repo-agent-salvage-v2]]. If any NEW failure appears (especially in `test_notification_*` / `test_history_*` / `test_action_plan_*`), investigate before continuing.

- [ ] **Step 2: Lint critical errors**

Run: `python3.11 -m flake8 src/notification.py src/services/history_service.py --select=E9,F63,F7,F82 --show-source --statistics`
Expected: 0 errors.

- [ ] **Step 3: Py-compile the touched files**

Run: `python3.11 -m py_compile src/notification.py src/services/history_service.py`
Expected: no output.

- [ ] **Step 4: Update CHANGELOG**

Append to `docs/CHANGELOG.md` under `## [Unreleased]` (flat format per CLAUDE.md), at the top of the existing list:

```
- [新功能] FactBundle Phase 3 渲染层落地：`src/notification.py` 与 `src/services/history_service.py` 双 renderer 的 `_render_action_plan_items` 在收到 `fact_bundle` 时为各依据行附加 Wikipedia 风格脚注上标 (¹²³)，并对 `provenance == "synthesized"` 的条目展示 🤖 *代码兜底* 徽章；新增 `_render_evidence_footnotes(refs, fact_bundle)` 辅助函数，每只股票通知/历史 Markdown 报告在持仓操作计划之后追加完整脚注块（按出现顺序去重、未在 bundle 命中的 fact_id 显示为"引用未找到"）。新增 `tests/test_renderer_parity_phase3.py` 强制两份 renderer 字节相等输出，防止 [[repo-dual-renderers]] 漂移。`fact_bundle` 缺失或 `evidence_refs` 为空时输出与改造前字节相同，保持老报告兼容。
```

- [ ] **Step 5: Anchor commit**

```bash
git add docs/CHANGELOG.md
git commit -m "docs(changelog): Phase 3 evidence renderers entry"
```

---

## Self-Review

**Spec coverage (Section C lines 446-484):**
- Wikipedia-style footnotes on Lark/Feishu/Bark notification — Tasks 1, 3, 5 ✅
- Mirror format in history_service.py — Tasks 2, 4, 6 ✅
- `_render_evidence_footnotes` helper — Tasks 1, 2 ✅
- Provenance badge `🤖 代码兜底` — Tasks 3, 4 ✅
- Parity test (`test_renderer_parity`) — Task 7 ✅
- Section C "strategy_thesis / strategy_choices 同 pattern" — **DEFERRED**: spec mentions applying the pattern to strategy_thesis + strategy_choices too, but those fields don't currently carry `evidence_refs` in our Phase 2 output (the LLM emits `strategy_thesis` as plain string, see analyzer.py:2540-2541). When/if Phase 2 LLMs start emitting structured `strategy_thesis: {text, evidence_refs, provenance}`, we'll add another Phase 3.5 task. Documented as scope deferral, not skipped silently.

**Placeholder scan:** None — every step has exact test code, exact replacement code, exact commands.

**Type consistency:**
- `_render_action_plan_items(items: list, fact_bundle: dict | None = None) -> list` — consistent in Tasks 3, 4, 5, 6, 7
- `_render_evidence_footnotes(evidence_refs: list, fact_bundle: dict | None) -> list` — consistent in Tasks 1, 2, 5, 6, 7
- `_to_superscript(n: int) -> str` — Task 1, reused in Task 2 verbatim
- `_resolve_fact(fact_id, fact_bundle) -> dict | None` — Task 1, reused in Task 2 verbatim

**Notes for the executor:**
- The `dashboard` variable referenced in Tasks 5/6 — verify the variable name in each renderer's main loop; if it's named differently in `history_service.py::_generate_single_stock_markdown`, use that local name.
- Old call sites that pass `_render_action_plan_items(items)` positionally MUST keep working — the new `fact_bundle` keyword has a `None` default to preserve compat. The Task 3/4 "legacy signature" tests guard this explicitly.
- The footnote block formatting (`---` separator + blank line at end) matches the spec example exactly. If Lark/Feishu Markdown rendering has a known issue with `---`, we'll discover it during live smoke and adjust in a follow-up.
- Phase 3 is **renderer-only**. It does NOT change `action_plan_items` content, sanitizer behavior, or LLM prompt. If the live smoke (post-Phase-2-pending in [[project-phase-2-smoke-pending]]) shows action_plan_items missing `evidence_refs`, Phase 3 simply emits no superscripts — degrades gracefully.
- Tests use `python3.11` per [[repo-py-toolchain]]; `python` is system 3.9.6 and will not work.
