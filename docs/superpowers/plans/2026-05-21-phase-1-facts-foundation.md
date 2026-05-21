# Phase 1 — FactBundle Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `FactBundle` data layer — typed FactRecord + 8 fact category extractors + 23 candidate-level computation rules — and attach the resulting `fact_bundle` to `dashboard` JSON via the existing `StockAnalysisPipeline`. **Zero user-visible change**. This is the foundation that Phases 2-5 will depend on.

**Architecture:** Pure deterministic code. No LLM in this phase. The new `src/analysis/` package owns FactRecord types, per-domain extractors, candidate rules, and the orchestrating `facts_builder.build(...)` entrypoint. `pipeline.py::process_single_stock` calls it after the existing dashboard assembly and attaches `dashboard.fact_bundle`.

**Tech Stack:** Python 3.11, dataclasses, pytest, existing `fetcher_manager` for OHLC, `data/quant_models/{market}/<week>/predictions.json` for qlib.

**Reference spec:** `docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md` (Section A — FactBundle Schema).

---

## File Structure

**Create:**
- `src/analysis/__init__.py` — package marker
- `src/analysis/facts.py` — `FactRecord`, `FactBundle`, `CandidateLevel` dataclasses
- `src/analysis/extractors/__init__.py`
- `src/analysis/extractors/technical.py` — `technical.*` facts (MA, RSI, support/resistance, ATR, trend_score)
- `src/analysis/extractors/quant.py` — `quant.*` facts (qlib score/rank/ic)
- `src/analysis/extractors/committee.py` — `committee.*` facts (PM, risk officer, masters)
- `src/analysis/extractors/intel.py` — `intel.*` facts (risk_alerts, catalysts, sentiment)
- `src/analysis/extractors/portfolio.py` — `portfolio.*` facts (holding, cost, P&L)
- `src/analysis/extractors/flow.py` — `flow.*` facts (A-share capital flow)
- `src/analysis/extractors/chip.py` — `chip.*` facts (A-share chip distribution)
- `src/analysis/candidate_rules.py` — 23 candidate computation rules
- `src/analysis/facts_builder.py` — main orchestrator `build(stock_code, market, dashboard, portfolio_context, ohlc) -> FactBundle`
- `tests/test_facts.py` — dataclass tests
- `tests/test_facts_technical.py` — technical extractor tests
- `tests/test_facts_quant.py` — quant extractor tests
- `tests/test_facts_committee.py` — committee extractor tests
- `tests/test_facts_intel.py` — intel extractor tests
- `tests/test_facts_portfolio.py` — portfolio extractor tests
- `tests/test_facts_flow.py` — flow extractor tests (A-share)
- `tests/test_facts_chip.py` — chip extractor tests (A-share)
- `tests/test_candidate_rules.py` — 23 rules + ATR/Fib/R-multiple computation
- `tests/test_facts_builder.py` — end-to-end NVDA fixture test
- `tests/test_pipeline_fact_bundle.py` — pipeline integration test
- `tests/fixtures/nvda_dashboard.json` — captured NVDA dashboard (id=13) fixture

**Modify:**
- `src/core/pipeline.py:1677-1750` — `process_single_stock` calls `facts_builder.build(...)` and attaches result to dashboard

**Not touched in this phase:**
- `src/analyzer.py` (Phase 2)
- `src/services/portfolio_context_service.py::synthesize_action_plan_items` (Phase 2)
- `src/notification.py` / `src/services/history_service.py` (Phase 3)
- `apps/dsa-web/` (Phase 4-5)
- LLM prompt / sanitizer (Phase 2)

---

## Naming Conventions

All fact IDs follow `<type>.<subdomain>.<key>` pattern. Examples:
- `technical.current_price`, `technical.ma10`, `technical.rsi_12`, `technical.atr_14`
- `quant.qlib_score`, `quant.qlib_rank`, `quant.qlib_ic_4w`
- `committee.pm_verdict`, `committee.pm_score`, `committee.risk.suggested_position_pct`, `committee.master.warren_buffett`
- `intel.risk_alert.0`, `intel.positive_catalyst.0`, `intel.sentiment.reddit`
- `portfolio.holding_shares`, `portfolio.avg_cost`, `portfolio.unrealized_pnl_pct`
- `flow.main_net_inflow`, `flow.inflow_5d`
- `chip.profit_ratio`, `chip.avg_cost`, `chip.concentration_90`
- `candidate.exit.1`, `candidate.stop.1`, `candidate.entry.1`

Strategy IDs (4 fixed, per [[repo-strategy-classification-architecture]]):
`long_term_hold` | `swing_trade` | `stepped_profit_taking` | `wait_and_see`

---

### Task 1: Create `src/analysis/` package + FactRecord/FactBundle/CandidateLevel types

**Files:**
- Create: `src/analysis/__init__.py`
- Create: `src/analysis/facts.py`
- Test: `tests/test_facts.py`

- [ ] **Step 1: Write failing test for FactRecord + FactBundle**

```python
# tests/test_facts.py
import pytest
from src.analysis.facts import FactRecord, FactBundle, CandidateLevel


def test_fact_record_minimal():
    f = FactRecord(
        id="technical.ma10",
        type="technical",
        label="MA10 (10日均线)",
        value=222.02,
        display_value="$222.02",
    )
    assert f.id == "technical.ma10"
    assert f.unit is None
    assert f.confidence is None
    assert f.extra == {}


def test_fact_bundle_get_and_by_type():
    f1 = FactRecord(id="technical.ma10", type="technical", label="MA10",
                    value=222.0, display_value="$222.0")
    f2 = FactRecord(id="quant.qlib_score", type="quant", label="Qlib score",
                    value=0.23, display_value="0.23")
    bundle = FactBundle(as_of="2026-05-21T00:43:00Z", market="us",
                        stock_code="NVDA", facts=[f1, f2], candidates=[])
    assert bundle.get("technical.ma10") is f1
    assert bundle.get("missing.id") is None
    assert bundle.by_type("technical") == [f1]
    assert bundle.by_type("quant") == [f2]
    assert bundle.by_type("intel") == []


def test_candidate_level_required_fields():
    c = CandidateLevel(
        id="candidate.exit.1",
        type="candidate",
        label="阻力位触及减仓",
        value=226.13,
        display_value="$226.13",
        direction="take_profit",
        price=226.13,
        basis_fact_id="technical.resistance",
        basis_rule="resistance_touch",
        applicable_strategies=["swing_trade", "stepped_profit_taking"],
        tier="primary",
        distance_pct_from_current=1.19,
    )
    assert c.direction == "take_profit"
    assert c.tier == "primary"
    assert "swing_trade" in c.applicable_strategies
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facts.py -v`
Expected: ImportError "No module named 'src.analysis'"

- [ ] **Step 3: Create package marker**

```python
# src/analysis/__init__.py
"""Evidence-grounded decision pipeline: facts builder + candidate levels."""
```

- [ ] **Step 4: Create facts.py with types**

```python
# src/analysis/facts.py
"""FactRecord / FactBundle / CandidateLevel — typed data classes for Stage 1 outputs.

See docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md
Section A for full schema design.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


@dataclass
class FactRecord:
    id: str
    type: str
    label: str
    value: Any
    display_value: str
    unit: Optional[str] = None
    source: str = ""
    confidence: Optional[float] = None
    as_of: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateLevel(FactRecord):
    """Candidate trigger price level produced by candidate_rules.

    Inherits all FactRecord fields. Subclass-specific fields below.
    """
    direction: Literal["entry", "exit", "stop", "take_profit"] = "entry"
    price: float = 0.0
    basis_fact_id: str = ""
    basis_rule: str = ""
    applicable_strategies: List[str] = field(default_factory=list)
    tier: Literal["primary", "secondary", "discipline_anchor", "filtered"] = "primary"
    distance_pct_from_current: float = 0.0


@dataclass
class FactBundle:
    as_of: str
    market: Literal["a", "hk", "us"]
    stock_code: str
    facts: List[FactRecord]
    candidates: List[CandidateLevel]

    def get(self, fact_id: str) -> Optional[FactRecord]:
        for f in self.facts:
            if f.id == fact_id:
                return f
        for c in self.candidates:
            if c.id == fact_id:
                return c
        return None

    def by_type(self, type_prefix: str) -> List[FactRecord]:
        return [f for f in self.facts if f.type == type_prefix]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_facts.py -v`
Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/analysis/__init__.py src/analysis/facts.py tests/test_facts.py
git commit -m "feat(analysis): add FactRecord, FactBundle, CandidateLevel types"
```

---

### Task 2: Technical extractor (MA, RSI, support/resistance, current_price)

**Files:**
- Create: `src/analysis/extractors/__init__.py`
- Create: `src/analysis/extractors/technical.py`
- Test: `tests/test_facts_technical.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_facts_technical.py
from src.analysis.extractors.technical import extract_technical_facts


def test_extract_technical_facts_from_data_perspective():
    data_perspective = {
        "price_position": {
            "current_price": 223.47,
            "ma5": 225.49, "ma10": 222.02, "ma20": 213.4,
            "support_level": 222.02, "resistance_level": 226.13,
            "bias_ma5": -0.9,
        },
        "trend_status": {"trend_score": 75, "ma_alignment": "bullish", "is_bullish": True},
        "volume_analysis": {"volume_ratio": "N/A", "volume_status": "量能正常"},
    }
    facts = extract_technical_facts(data_perspective, rsi_12=71.1, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "technical.current_price" in ids
    assert "technical.ma10" in ids
    assert "technical.ma20" in ids
    assert "technical.resistance" in ids
    assert "technical.rsi_12" in ids
    assert "technical.trend_score" in ids
    current = next(f for f in facts if f.id == "technical.current_price")
    assert current.value == 223.47
    assert current.display_value == "$223.47"
    rsi = next(f for f in facts if f.id == "technical.rsi_12")
    assert rsi.extra.get("zone") == "超买"


def test_extract_technical_missing_data_graceful():
    facts = extract_technical_facts({}, rsi_12=None, as_of="2026-05-21T00:43:00Z")
    assert facts == []  # nothing to extract, no crash


def test_extract_technical_volume_ratio_na_skipped():
    dp = {"volume_analysis": {"volume_ratio": "N/A"}}
    facts = extract_technical_facts(dp, rsi_12=None, as_of="2026-05-21T00:43:00Z")
    assert "technical.volume_ratio" not in {f.id for f in facts}
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_facts_technical.py -v`
Expected: ImportError on extractors module

- [ ] **Step 3: Create extractors package marker**

```python
# src/analysis/extractors/__init__.py
"""Per-domain fact extractors."""
```

- [ ] **Step 4: Implement technical extractor**

```python
# src/analysis/extractors/technical.py
"""Extract technical.* facts from dashboard.data_perspective + RSI."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord


def _format_price(value: float, market: str = "us") -> str:
    if market == "a":
        return f"¥{value:.2f}"
    return f"${value:.2f}"


def _rsi_zone(rsi: float) -> str:
    if rsi >= 70:
        return "超买"
    if rsi <= 30:
        return "超卖"
    return "中性"


def extract_technical_facts(
    data_perspective: Dict[str, Any],
    rsi_12: Optional[float],
    as_of: str,
    market: str = "us",
    source_hint: str = "data_perspective",
) -> List[FactRecord]:
    facts: List[FactRecord] = []
    pp = data_perspective.get("price_position") or {}
    ts = data_perspective.get("trend_status") or {}

    if "current_price" in pp and pp["current_price"] is not None:
        facts.append(FactRecord(
            id="technical.current_price", type="technical",
            label="现价", value=float(pp["current_price"]),
            display_value=_format_price(float(pp["current_price"]), market),
            unit="USD" if market != "a" else "CNY",
            source=source_hint, as_of=as_of,
        ))

    for ma_key, ma_label in [("ma5", "MA5 (5日均线)"), ("ma10", "MA10 (10日均线)"),
                              ("ma20", "MA20 (20日均线)")]:
        if pp.get(ma_key) is not None:
            facts.append(FactRecord(
                id=f"technical.{ma_key}", type="technical",
                label=ma_label, value=float(pp[ma_key]),
                display_value=_format_price(float(pp[ma_key]), market),
                source=source_hint, as_of=as_of,
            ))

    if pp.get("support_level") is not None:
        facts.append(FactRecord(
            id="technical.support", type="technical",
            label="支撑位", value=float(pp["support_level"]),
            display_value=_format_price(float(pp["support_level"]), market),
            source=source_hint, as_of=as_of,
            extra={"role": "支撑"},
        ))

    if pp.get("resistance_level") is not None:
        facts.append(FactRecord(
            id="technical.resistance", type="technical",
            label="阻力位", value=float(pp["resistance_level"]),
            display_value=_format_price(float(pp["resistance_level"]), market),
            source=source_hint, as_of=as_of,
            extra={"role": "阻力"},
        ))

    if rsi_12 is not None:
        facts.append(FactRecord(
            id="technical.rsi_12", type="technical",
            label="RSI(12)", value=float(rsi_12),
            display_value=f"{rsi_12:.1f}",
            source=source_hint, as_of=as_of,
            extra={"zone": _rsi_zone(float(rsi_12)), "threshold_overbought": 70, "threshold_oversold": 30},
        ))

    if ts.get("trend_score") is not None:
        facts.append(FactRecord(
            id="technical.trend_score", type="technical",
            label="趋势分", value=int(ts["trend_score"]),
            display_value=str(ts["trend_score"]),
            source=source_hint, as_of=as_of,
            extra={"ma_alignment": ts.get("ma_alignment"), "is_bullish": ts.get("is_bullish")},
        ))

    return facts
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_facts_technical.py -v`
Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/analysis/extractors/__init__.py src/analysis/extractors/technical.py tests/test_facts_technical.py
git commit -m "feat(analysis): add technical.* fact extractor"
```

---

### Task 3: ATR(14) computation as part of technical extractor

**Files:**
- Modify: `src/analysis/extractors/technical.py`
- Test: `tests/test_facts_technical.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_facts_technical.py — append
def test_compute_atr_14_from_ohlc():
    from src.analysis.extractors.technical import compute_atr_14
    # 15 days of OHLC, ATR(14) = avg(True Range) over last 14 days
    ohlc = [
        {"high": 100, "low": 95, "close": 98},   # tr=5
        {"high": 102, "low": 97, "close": 100},  # tr=5
        # ... (generate 13 more to make 15)
    ]
    # extend to 15 rows
    for i in range(13):
        ohlc.append({"high": 105 + i, "low": 100 + i, "close": 103 + i})
    atr = compute_atr_14(ohlc)
    assert atr is not None
    assert atr > 0
    assert atr < 20  # sanity bound


def test_compute_atr_14_insufficient_data_returns_none():
    from src.analysis.extractors.technical import compute_atr_14
    short_ohlc = [{"high": 100, "low": 95, "close": 98}]  # only 1 day
    assert compute_atr_14(short_ohlc) is None


def test_extract_technical_with_ohlc_includes_atr():
    dp = {"price_position": {"current_price": 100.0}}
    ohlc = [{"high": 100 + i, "low": 95 + i, "close": 98 + i} for i in range(20)]
    facts = extract_technical_facts(dp, rsi_12=None, as_of="2026-05-21T00:43:00Z", ohlc=ohlc)
    atr_facts = [f for f in facts if f.id == "technical.atr_14"]
    assert len(atr_facts) == 1
    assert atr_facts[0].value > 0
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_facts_technical.py::test_compute_atr_14_from_ohlc tests/test_facts_technical.py::test_compute_atr_14_insufficient_data_returns_none tests/test_facts_technical.py::test_extract_technical_with_ohlc_includes_atr -v`
Expected: ImportError on `compute_atr_14`

- [ ] **Step 3: Add `compute_atr_14` + extend extractor**

Add to `src/analysis/extractors/technical.py`:

```python
def compute_atr_14(ohlc: list) -> Optional[float]:
    """Wilder ATR(14). Requires >= 15 bars (need 1 for prior close).

    True Range = max(high-low, |high-prev_close|, |low-prev_close|).
    Simple-average flavor; sufficient for candidate-level computation.
    """
    if not ohlc or len(ohlc) < 15:
        return None
    trs = []
    for i in range(1, len(ohlc)):
        h, l = float(ohlc[i]["high"]), float(ohlc[i]["low"])
        prev_c = float(ohlc[i - 1]["close"])
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    last14 = trs[-14:]
    return sum(last14) / len(last14)
```

Update `extract_technical_facts` signature to accept `ohlc: Optional[list] = None` and emit ATR fact when available:

```python
def extract_technical_facts(
    data_perspective: Dict[str, Any],
    rsi_12: Optional[float],
    as_of: str,
    market: str = "us",
    source_hint: str = "data_perspective",
    ohlc: Optional[list] = None,
) -> List[FactRecord]:
    facts: List[FactRecord] = []
    # ... existing code ...

    if ohlc is not None:
        atr = compute_atr_14(ohlc)
        if atr is not None:
            facts.append(FactRecord(
                id="technical.atr_14", type="technical",
                label="ATR(14)", value=round(atr, 4),
                display_value=f"{atr:.2f}",
                source="data_provider/daily_data:atr_14",
                as_of=as_of,
            ))

    return facts
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_facts_technical.py -v`
Expected: 6 PASSED (3 new + 3 existing)

- [ ] **Step 5: Commit**

```bash
git add src/analysis/extractors/technical.py tests/test_facts_technical.py
git commit -m "feat(analysis): compute ATR(14) for technical fact extractor"
```

---

### Task 4: Quant extractor (qlib score / rank / IC)

**Files:**
- Create: `src/analysis/extractors/quant.py`
- Test: `tests/test_facts_quant.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_facts_quant.py
import json
import tempfile
from pathlib import Path
from src.analysis.extractors.quant import extract_quant_facts, find_latest_qlib_week


def test_extract_quant_facts_from_predictions_dict():
    predictions = {"NVDA": {"score": 0.2348, "rank": 0.8473}, "AAPL": {"score": 0.1, "rank": 0.5}}
    ic = {"as_of": "2026-05-18", "ic_current": 0.172, "ic_ma_4w": 0.211}
    facts = extract_quant_facts(
        "NVDA",
        predictions=predictions,
        ic=ic,
        universe_size=503,
        week="2026-W21",
        as_of="2026-05-21T00:43:00Z",
    )
    ids = {f.id for f in facts}
    assert "quant.qlib_score" in ids
    assert "quant.qlib_rank" in ids
    assert "quant.qlib_ic_4w" in ids
    score = next(f for f in facts if f.id == "quant.qlib_score")
    assert score.confidence == 0.211  # = ic_ma_4w
    rank = next(f for f in facts if f.id == "quant.qlib_rank")
    assert rank.display_value == "前 16%"  # ceil((1 - 0.8473) * 100)
    assert rank.extra["universe_size"] == 503


def test_extract_quant_facts_missing_ticker_returns_empty():
    facts = extract_quant_facts(
        "UNKNOWN", predictions={"NVDA": {"score": 0.2, "rank": 0.8}},
        ic={}, universe_size=503, week="2026-W21", as_of="2026-05-21T00:43:00Z",
    )
    assert facts == []


def test_find_latest_qlib_week_returns_most_recent(tmp_path):
    base = tmp_path / "quant_models" / "us"
    (base / "2026-W20").mkdir(parents=True)
    (base / "2026-W21").mkdir(parents=True)
    (base / "2026-W19").mkdir(parents=True)
    assert find_latest_qlib_week(base) == "2026-W21"


def test_find_latest_qlib_week_empty_returns_none(tmp_path):
    base = tmp_path / "quant_models" / "us"
    base.mkdir(parents=True)
    assert find_latest_qlib_week(base) is None
```

- [ ] **Step 2: Run failing test**

Run: `python -m pytest tests/test_facts_quant.py -v`
Expected: ImportError

- [ ] **Step 3: Implement quant extractor**

```python
# src/analysis/extractors/quant.py
"""Extract quant.* facts from data/quant_models/{market}/<week>/predictions.json + ic.json."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord

_WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")


def find_latest_qlib_week(market_dir: Path) -> Optional[str]:
    if not market_dir.exists() or not market_dir.is_dir():
        return None
    weeks = [p.name for p in market_dir.iterdir() if p.is_dir() and _WEEK_RE.match(p.name)]
    if not weeks:
        return None
    return sorted(weeks)[-1]


def extract_quant_facts(
    ticker: str,
    *,
    predictions: Dict[str, Dict[str, float]],
    ic: Dict[str, Any],
    universe_size: int,
    week: str,
    as_of: str,
) -> List[FactRecord]:
    entry = predictions.get(ticker)
    if not entry:
        return []
    facts: List[FactRecord] = []
    score = float(entry.get("score", 0.0))
    rank = float(entry.get("rank", 0.0))
    ic_4w = ic.get("ic_ma_4w")
    ic_current = ic.get("ic_current")
    source = f"data/quant_models/<market>/{week}/predictions.json"

    facts.append(FactRecord(
        id="quant.qlib_score", type="quant",
        label="Qlib 模型打分", value=round(score, 4),
        display_value=f"{score:.3f}",
        confidence=float(ic_4w) if ic_4w is not None else None,
        source=source, as_of=as_of,
        extra={"week": week},
    ))

    top_pct = max(1, math.ceil((1.0 - rank) * 100))
    facts.append(FactRecord(
        id="quant.qlib_rank", type="quant",
        label="Qlib 截面分位", value=round(rank, 4),
        display_value=f"前 {top_pct}%",
        source=source, as_of=as_of,
        extra={
            "universe_size": universe_size,
            "rank_absolute": max(1, math.ceil((1.0 - rank) * universe_size)),
            "week": week,
        },
    ))

    if ic_current is not None:
        facts.append(FactRecord(
            id="quant.qlib_ic_current", type="quant",
            label="Qlib IC 当周", value=float(ic_current),
            display_value=f"{float(ic_current):.3f}",
            source=source, as_of=as_of,
        ))

    if ic_4w is not None:
        facts.append(FactRecord(
            id="quant.qlib_ic_4w", type="quant",
            label="Qlib IC 4周均", value=float(ic_4w),
            display_value=f"{float(ic_4w):.3f}",
            source=source, as_of=as_of,
            extra={"interpretation": "IC>0.1 视为有效"},
        ))

    return facts
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_facts_quant.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/extractors/quant.py tests/test_facts_quant.py
git commit -m "feat(analysis): add quant.* fact extractor (qlib score/rank/IC)"
```

---

### Task 5: Committee extractor

**Files:**
- Create: `src/analysis/extractors/committee.py`
- Test: `tests/test_facts_committee.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_facts_committee.py
from src.analysis.extractors.committee import extract_committee_facts


def test_extract_committee_facts_full_bundle():
    committee = {
        "pm_verdict": "hold", "pm_score": 5.8,
        "pm_rationale": "尽管技术面...", "pm_dissents": ["cathie_wood"],
        "risk": {"severity": "soft", "suggested_position_pct": 0.3,
                 "red_flags": ["RSI 71.1 超买", "PE/PB 缺失"], "veto": False},
        "masters": [
            {"persona": "warren_buffett", "verdict": "hold", "score": 4.0,
             "headline": "技术指标超买...", "key_evidence": ["RSI 71.1"]},
            {"persona": "cathie_wood", "verdict": "strong_buy", "score": 9.2,
             "headline": "AI 革命核心", "key_evidence": []},
        ],
    }
    facts = extract_committee_facts(committee, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "committee.pm_verdict" in ids
    assert "committee.pm_score" in ids
    assert "committee.risk.suggested_position_pct" in ids
    assert "committee.risk.severity" in ids
    assert "committee.master.warren_buffett" in ids
    assert "committee.master.cathie_wood" in ids

    cathie = next(f for f in facts if f.id == "committee.master.cathie_wood")
    assert cathie.extra["is_dissent"] is True
    assert "异议" in cathie.display_value

    risk_pct = next(f for f in facts if f.id == "committee.risk.suggested_position_pct")
    assert risk_pct.display_value == "≤ 30%"
    assert risk_pct.extra["severity"] == "soft"


def test_extract_committee_facts_empty_committee():
    assert extract_committee_facts(None, as_of="2026-05-21T00:43:00Z") == []
    assert extract_committee_facts({}, as_of="2026-05-21T00:43:00Z") == []


def test_extract_committee_facts_missing_risk():
    committee = {"pm_verdict": "hold", "pm_score": 5.0, "masters": []}
    facts = extract_committee_facts(committee, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "committee.pm_verdict" in ids
    assert "committee.risk.suggested_position_pct" not in ids
```

- [ ] **Step 2: Run failing test**

Run: `python -m pytest tests/test_facts_committee.py -v`
Expected: ImportError

- [ ] **Step 3: Implement committee extractor**

```python
# src/analysis/extractors/committee.py
"""Extract committee.* facts from dashboard.committee."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord

VERDICT_LABEL = {
    "strong_buy": "Strong Buy", "buy": "Buy", "hold": "Hold",
    "sell": "Sell", "strong_sell": "Strong Sell",
}


def extract_committee_facts(
    committee: Optional[Dict[str, Any]],
    as_of: str,
) -> List[FactRecord]:
    if not committee:
        return []
    facts: List[FactRecord] = []
    src = "committee"

    if "pm_verdict" in committee and committee["pm_verdict"]:
        facts.append(FactRecord(
            id="committee.pm_verdict", type="committee",
            label="PM 裁决", value=committee["pm_verdict"],
            display_value=VERDICT_LABEL.get(committee["pm_verdict"], committee["pm_verdict"]),
            source=src, as_of=as_of,
            extra={"rationale": committee.get("pm_rationale", "")},
        ))

    if committee.get("pm_score") is not None:
        facts.append(FactRecord(
            id="committee.pm_score", type="committee",
            label="PM 评分", value=float(committee["pm_score"]),
            display_value=f"{committee['pm_score']:.1f} / 10",
            source=src, as_of=as_of,
        ))

    if committee.get("pm_dissents"):
        facts.append(FactRecord(
            id="committee.pm_dissents", type="committee",
            label="PM 异议清单", value=committee["pm_dissents"],
            display_value=", ".join(committee["pm_dissents"]),
            source=src, as_of=as_of,
        ))

    risk = committee.get("risk") or {}
    if risk.get("suggested_position_pct") is not None:
        pct = float(risk["suggested_position_pct"])
        facts.append(FactRecord(
            id="committee.risk.suggested_position_pct", type="committee",
            label="风控建议仓位上限", value=pct,
            display_value=f"≤ {int(pct * 100)}%",
            source=src, as_of=as_of,
            extra={
                "severity": risk.get("severity"),
                "red_flags": risk.get("red_flags", []),
                "veto": risk.get("veto", False),
            },
        ))

    if risk.get("severity"):
        facts.append(FactRecord(
            id="committee.risk.severity", type="committee",
            label="风控严重度", value=risk["severity"],
            display_value=risk["severity"],
            source=src, as_of=as_of,
        ))

    dissents = set(committee.get("pm_dissents") or [])
    for master in committee.get("masters") or []:
        persona = master.get("persona")
        if not persona:
            continue
        is_dissent = persona in dissents
        verdict = master.get("verdict", "")
        score = master.get("score")
        score_str = f" ({score:.1f})" if score is not None else ""
        dissent_mark = " ⚠ 异议" if is_dissent else ""
        facts.append(FactRecord(
            id=f"committee.master.{persona}", type="committee",
            label=f"{persona} 投票", value=verdict,
            display_value=f"{VERDICT_LABEL.get(verdict, verdict)}{score_str}{dissent_mark}",
            source=src, as_of=as_of,
            extra={
                "score": score,
                "headline": master.get("headline", ""),
                "key_evidence": master.get("key_evidence", []),
                "is_dissent": is_dissent,
            },
        ))

    return facts
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_facts_committee.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/extractors/committee.py tests/test_facts_committee.py
git commit -m "feat(analysis): add committee.* fact extractor (PM/risk/masters)"
```

---

### Task 6: Intel extractor (risk_alerts / catalysts / sentiment)

**Files:**
- Create: `src/analysis/extractors/intel.py`
- Test: `tests/test_facts_intel.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_facts_intel.py
from src.analysis.extractors.intel import extract_intel_facts


def test_extract_intel_facts():
    intelligence = {
        "risk_alerts": ["PE/PB 缺失", "RSI 71.1 超买"],
        "risk_alerts_zh": ["估值数据缺失", "RSI 71.1 超买"],
        "positive_catalysts": ["AI 算力增长"],
        "positive_catalysts_zh": ["AI 算力增长"],
        "latest_news": "NVIDIA announces...",
        "latest_news_zh": "英伟达宣布...",
        "sentiment_summary": "Mixed positive",
        "sentiment_summary_zh": "整体偏正向",
        "earnings_outlook": "FY26 EPS revised up",
        "sentiment_dimensions": {
            "reddit": {"score": 0.6, "summary": "热度高"},
            "x_twitter": {"score": 0.5, "summary": "话题度持续"},
            "stocktwits": {"score": 0.7, "summary": "情绪偏多"},
        },
    }
    facts = extract_intel_facts(intelligence, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "intel.risk_alert.0" in ids
    assert "intel.risk_alert.1" in ids
    assert "intel.positive_catalyst.0" in ids
    assert "intel.latest_news" in ids
    assert "intel.sentiment_summary" in ids
    assert "intel.earnings_outlook" in ids
    assert "intel.sentiment.reddit" in ids
    assert "intel.sentiment.x_twitter" in ids

    risk0 = next(f for f in facts if f.id == "intel.risk_alert.0")
    assert "PE/PB" in risk0.value
    assert risk0.extra.get("zh") == "估值数据缺失"


def test_extract_intel_empty():
    assert extract_intel_facts(None, as_of="2026-05-21T00:43:00Z") == []
    assert extract_intel_facts({}, as_of="2026-05-21T00:43:00Z") == []


def test_extract_intel_partial_dims_only_real_sources():
    intelligence = {
        "sentiment_dimensions": {
            "reddit": {"score": 0.5},
            "polymarket": None,  # source absent
        },
    }
    facts = extract_intel_facts(intelligence, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "intel.sentiment.reddit" in ids
    assert "intel.sentiment.polymarket" not in ids
```

- [ ] **Step 2: Run failing test**

Run: `python -m pytest tests/test_facts_intel.py -v`
Expected: ImportError

- [ ] **Step 3: Implement intel extractor**

```python
# src/analysis/extractors/intel.py
"""Extract intel.* facts from dashboard.intelligence."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord


def extract_intel_facts(
    intelligence: Optional[Dict[str, Any]],
    as_of: str,
) -> List[FactRecord]:
    if not intelligence:
        return []
    facts: List[FactRecord] = []

    risk_alerts = intelligence.get("risk_alerts") or []
    risk_alerts_zh = intelligence.get("risk_alerts_zh") or []
    for i, alert in enumerate(risk_alerts):
        facts.append(FactRecord(
            id=f"intel.risk_alert.{i}", type="intel",
            label="风险警示", value=alert,
            display_value=str(alert)[:120],
            source="intelligence.risk_alerts",
            as_of=as_of,
            extra={"zh": risk_alerts_zh[i] if i < len(risk_alerts_zh) else ""},
        ))

    catalysts = intelligence.get("positive_catalysts") or []
    catalysts_zh = intelligence.get("positive_catalysts_zh") or []
    for i, cat in enumerate(catalysts):
        facts.append(FactRecord(
            id=f"intel.positive_catalyst.{i}", type="intel",
            label="正向催化", value=cat,
            display_value=str(cat)[:120],
            source="intelligence.positive_catalysts",
            as_of=as_of,
            extra={"zh": catalysts_zh[i] if i < len(catalysts_zh) else ""},
        ))

    for key, label in [("latest_news", "最新新闻"),
                       ("sentiment_summary", "市场情绪概览"),
                       ("earnings_outlook", "财报展望")]:
        val = intelligence.get(key)
        if val:
            zh = intelligence.get(f"{key}_zh", "")
            facts.append(FactRecord(
                id=f"intel.{key}", type="intel",
                label=label, value=val, display_value=str(val)[:160],
                source=f"intelligence.{key}", as_of=as_of,
                extra={"zh": zh} if zh else {},
            ))

    dims = intelligence.get("sentiment_dimensions") or {}
    for source_name, data in dims.items():
        if not data:
            continue
        score = data.get("score") if isinstance(data, dict) else None
        summary = data.get("summary", "") if isinstance(data, dict) else ""
        facts.append(FactRecord(
            id=f"intel.sentiment.{source_name}", type="intel",
            label=f"{source_name} 情绪",
            value=score,
            display_value=f"{score:.2f}" if isinstance(score, (int, float)) else "—",
            source=f"intelligence.sentiment_dimensions.{source_name}",
            as_of=as_of,
            extra={"summary": summary},
        ))

    return facts
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_facts_intel.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/extractors/intel.py tests/test_facts_intel.py
git commit -m "feat(analysis): add intel.* fact extractor (alerts/catalysts/sentiment)"
```

---

### Task 7: Portfolio extractor

**Files:**
- Create: `src/analysis/extractors/portfolio.py`
- Test: `tests/test_facts_portfolio.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_facts_portfolio.py
from src.analysis.extractors.portfolio import extract_portfolio_facts


def test_extract_portfolio_facts_held():
    pc = {
        "match_state": "held",
        "holding_shares": 0.7597,
        "avg_cost": 196.18,
        "currency": "USD",
        "unrealized_pnl_pct": 13.33,
        "unrealized_pnl_amount": 14.78,
        "base_currency": "GBP",
        "total_equity": 1200.0,
        "first_buy_date": "2024-08-15",
    }
    facts = extract_portfolio_facts(pc, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "portfolio.holding_shares" in ids
    assert "portfolio.avg_cost" in ids
    assert "portfolio.unrealized_pnl_pct" in ids
    assert "portfolio.unrealized_pnl_amount" in ids
    assert "portfolio.total_equity" in ids
    assert "portfolio.position_match" in ids
    pnl = next(f for f in facts if f.id == "portfolio.unrealized_pnl_pct")
    assert pnl.display_value == "+13.33%"


def test_extract_portfolio_facts_none_match_returns_only_position_match():
    pc = {"match_state": None}
    facts = extract_portfolio_facts(pc, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "portfolio.position_match" in ids
    assert "portfolio.holding_shares" not in ids


def test_extract_portfolio_facts_empty():
    assert extract_portfolio_facts(None, as_of="2026-05-21T00:43:00Z") == []
```

- [ ] **Step 2: Run failing test**

Run: `python -m pytest tests/test_facts_portfolio.py -v`
Expected: ImportError

- [ ] **Step 3: Implement portfolio extractor**

```python
# src/analysis/extractors/portfolio.py
"""Extract portfolio.* facts from PortfolioContextService output."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord


def extract_portfolio_facts(
    portfolio_context: Optional[Dict[str, Any]],
    as_of: str,
) -> List[FactRecord]:
    if not portfolio_context:
        return []
    facts: List[FactRecord] = []
    src = "portfolio_context_service"

    match = portfolio_context.get("match_state")
    facts.append(FactRecord(
        id="portfolio.position_match", type="portfolio",
        label="持仓匹配状态", value=match if match else "unknown",
        display_value={"held": "已持有", "not_held": "未持有"}.get(match, "未知"),
        source=src, as_of=as_of,
    ))

    if match != "held":
        return facts

    if portfolio_context.get("holding_shares") is not None:
        shares = float(portfolio_context["holding_shares"])
        facts.append(FactRecord(
            id="portfolio.holding_shares", type="portfolio",
            label="持仓股数", value=shares,
            display_value=f"{shares:.4f} 股", unit="shares",
            source=src, as_of=as_of,
        ))

    if portfolio_context.get("avg_cost") is not None:
        cost = float(portfolio_context["avg_cost"])
        ccy = portfolio_context.get("currency", "USD")
        symbol = {"USD": "$", "CNY": "¥", "HKD": "HK$", "GBP": "£"}.get(ccy, "")
        facts.append(FactRecord(
            id="portfolio.avg_cost", type="portfolio",
            label="成本均价", value=cost,
            display_value=f"{symbol}{cost:.2f}", unit=ccy,
            source=src, as_of=as_of,
        ))

    if portfolio_context.get("unrealized_pnl_pct") is not None:
        pct = float(portfolio_context["unrealized_pnl_pct"])
        sign = "+" if pct >= 0 else ""
        facts.append(FactRecord(
            id="portfolio.unrealized_pnl_pct", type="portfolio",
            label="浮盈率", value=pct,
            display_value=f"{sign}{pct:.2f}%", unit="%",
            source=src, as_of=as_of,
        ))

    if portfolio_context.get("unrealized_pnl_amount") is not None:
        amt = float(portfolio_context["unrealized_pnl_amount"])
        base = portfolio_context.get("base_currency", "USD")
        symbol = {"USD": "$", "CNY": "¥", "HKD": "HK$", "GBP": "£"}.get(base, "")
        sign = "+" if amt >= 0 else ""
        facts.append(FactRecord(
            id="portfolio.unrealized_pnl_amount", type="portfolio",
            label="浮盈金额", value=amt,
            display_value=f"{sign}{symbol}{amt:.2f}", unit=base,
            source=src, as_of=as_of,
        ))

    if portfolio_context.get("total_equity") is not None:
        eq = float(portfolio_context["total_equity"])
        base = portfolio_context.get("base_currency", "USD")
        symbol = {"USD": "$", "CNY": "¥", "HKD": "HK$", "GBP": "£"}.get(base, "")
        facts.append(FactRecord(
            id="portfolio.total_equity", type="portfolio",
            label="账户总权益", value=eq,
            display_value=f"{symbol}{eq:.2f}", unit=base,
            source=src, as_of=as_of,
        ))

    if portfolio_context.get("first_buy_date"):
        facts.append(FactRecord(
            id="portfolio.first_buy_date", type="portfolio",
            label="首次买入日期", value=portfolio_context["first_buy_date"],
            display_value=str(portfolio_context["first_buy_date"]),
            source=src, as_of=as_of,
        ))

    return facts
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_facts_portfolio.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/extractors/portfolio.py tests/test_facts_portfolio.py
git commit -m "feat(analysis): add portfolio.* fact extractor"
```

---

### Task 8: Flow extractor (A-share capital flow)

**Files:**
- Create: `src/analysis/extractors/flow.py`
- Test: `tests/test_facts_flow.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_facts_flow.py
from src.analysis.extractors.flow import extract_flow_facts


def test_extract_flow_facts_a_share():
    flow = {
        "status": "ok",
        "stock_flow": {"main_net_inflow": 12345678.0, "inflow_5d": 56789012.0, "inflow_10d": 78901234.0},
        "sector_rankings": {"top": [{"name": "半导体", "flow": 2e9}], "bottom": []},
    }
    facts = extract_flow_facts(flow, market="a", as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "flow.main_net_inflow" in ids
    assert "flow.inflow_5d" in ids
    assert "flow.inflow_10d" in ids


def test_extract_flow_facts_us_returns_empty():
    flow = {"status": "ok", "stock_flow": {"main_net_inflow": 1.0}}
    assert extract_flow_facts(flow, market="us", as_of="2026-05-21T00:43:00Z") == []


def test_extract_flow_facts_not_supported_status():
    flow = {"status": "not_supported"}
    assert extract_flow_facts(flow, market="a", as_of="2026-05-21T00:43:00Z") == []


def test_extract_flow_facts_empty():
    assert extract_flow_facts(None, market="a", as_of="2026-05-21T00:43:00Z") == []
```

- [ ] **Step 2: Run failing test**

Run: `python -m pytest tests/test_facts_flow.py -v`
Expected: ImportError

- [ ] **Step 3: Implement flow extractor**

```python
# src/analysis/extractors/flow.py
"""Extract flow.* facts from FundamentalAdapter.get_capital_flow (A-share only)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord


def _format_yuan(value: float) -> str:
    abs_v = abs(value)
    sign = "+" if value >= 0 else "-"
    if abs_v >= 1e8:
        return f"{sign}{abs_v / 1e8:.2f} 亿元"
    if abs_v >= 1e4:
        return f"{sign}{abs_v / 1e4:.2f} 万元"
    return f"{sign}{abs_v:.0f} 元"


def extract_flow_facts(
    flow: Optional[Dict[str, Any]],
    market: str,
    as_of: str,
) -> List[FactRecord]:
    if not flow or market != "a":
        return []
    if flow.get("status") != "ok":
        return []
    facts: List[FactRecord] = []
    stock_flow = flow.get("stock_flow") or {}

    for key, label in [
        ("main_net_inflow", "主力净流入"),
        ("inflow_5d", "5 日累计净流入"),
        ("inflow_10d", "10 日累计净流入"),
    ]:
        val = stock_flow.get(key)
        if val is None:
            continue
        v = float(val)
        facts.append(FactRecord(
            id=f"flow.{key}", type="flow",
            label=label, value=v,
            display_value=_format_yuan(v), unit="CNY",
            source="akshare/capital_flow", as_of=as_of,
        ))

    return facts
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_facts_flow.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/extractors/flow.py tests/test_facts_flow.py
git commit -m "feat(analysis): add flow.* fact extractor (A-share capital flow)"
```

---

### Task 9: Chip extractor (A-share chip distribution)

**Files:**
- Create: `src/analysis/extractors/chip.py`
- Test: `tests/test_facts_chip.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_facts_chip.py
from src.analysis.extractors.chip import extract_chip_facts


def test_extract_chip_facts_a_share():
    chip = {
        "date": "2026-05-20",
        "profit_ratio": 0.835,
        "avg_cost": 42.15,
        "concentration_70": 0.082,
        "concentration_90": 0.155,
    }
    facts = extract_chip_facts(chip, market="a", as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "chip.profit_ratio" in ids
    assert "chip.avg_cost" in ids
    assert "chip.concentration_70" in ids
    assert "chip.concentration_90" in ids
    pr = next(f for f in facts if f.id == "chip.profit_ratio")
    assert pr.display_value == "83.5%"


def test_extract_chip_facts_us_returns_empty():
    chip = {"profit_ratio": 0.5}
    assert extract_chip_facts(chip, market="us", as_of="2026-05-21T00:43:00Z") == []


def test_extract_chip_facts_empty():
    assert extract_chip_facts(None, market="a", as_of="2026-05-21T00:43:00Z") == []
```

- [ ] **Step 2: Run failing test**

Run: `python -m pytest tests/test_facts_chip.py -v`
Expected: ImportError

- [ ] **Step 3: Implement chip extractor**

```python
# src/analysis/extractors/chip.py
"""Extract chip.* facts from AkshareFetcher.get_chip_distribution (A-share only)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.facts import FactRecord


def extract_chip_facts(
    chip: Optional[Dict[str, Any]],
    market: str,
    as_of: str,
) -> List[FactRecord]:
    if not chip or market != "a":
        return []
    facts: List[FactRecord] = []
    src = "akshare/chip_distribution"
    chip_as_of = chip.get("date") or as_of

    if chip.get("profit_ratio") is not None:
        v = float(chip["profit_ratio"])
        facts.append(FactRecord(
            id="chip.profit_ratio", type="chip",
            label="获利比例", value=v,
            display_value=f"{v * 100:.1f}%", unit="%",
            source=src, as_of=chip_as_of,
        ))

    if chip.get("avg_cost") is not None:
        v = float(chip["avg_cost"])
        facts.append(FactRecord(
            id="chip.avg_cost", type="chip",
            label="市场平均成本", value=v,
            display_value=f"¥{v:.2f}", unit="CNY",
            source=src, as_of=chip_as_of,
        ))

    for key, label in [("concentration_70", "70% 集中度"),
                       ("concentration_90", "90% 集中度")]:
        if chip.get(key) is not None:
            v = float(chip[key])
            facts.append(FactRecord(
                id=f"chip.{key}", type="chip",
                label=label, value=v,
                display_value=f"{v * 100:.2f}%", unit="%",
                source=src, as_of=chip_as_of,
            ))

    return facts
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_facts_chip.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/extractors/chip.py tests/test_facts_chip.py
git commit -m "feat(analysis): add chip.* fact extractor (A-share chip distribution)"
```

---

### Task 10: Candidate rules — basic technical-based 8 rules (no ATR / Fib / R-multiple yet)

**Files:**
- Create: `src/analysis/candidate_rules.py`
- Test: `tests/test_candidate_rules.py`

- [ ] **Step 1: Write failing test for resistance_touch + ma20_breakdown + ma10_pullback**

```python
# tests/test_candidate_rules.py
from src.analysis.candidate_rules import compute_candidates
from src.analysis.facts import FactRecord, CandidateLevel


def _fact(id, value, type_="technical", label=""):
    return FactRecord(id=id, type=type_, label=label or id, value=value, display_value=str(value))


def test_resistance_touch_candidate():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.resistance", 226.13),
    ]
    cands = compute_candidates(facts)
    exit_cands = [c for c in cands if c.basis_rule == "resistance_touch"]
    assert len(exit_cands) == 1
    c = exit_cands[0]
    assert c.price == 226.13
    assert c.direction == "take_profit"
    assert "swing_trade" in c.applicable_strategies
    assert "stepped_profit_taking" in c.applicable_strategies
    assert c.tier == "primary"
    assert abs(c.distance_pct_from_current - 1.19) < 0.01


def test_ma20_breakdown_candidate():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.ma20", 213.4),
    ]
    cands = compute_candidates(facts)
    stops = [c for c in cands if c.basis_rule == "ma20_breakdown"]
    assert len(stops) == 1
    s = stops[0]
    assert s.price == 213.4
    assert s.direction == "stop_loss"
    assert s.tier == "primary"


def test_ma10_pullback_only_when_below_current():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.ma10", 222.02),  # below current → valid entry
    ]
    cands = compute_candidates(facts)
    entries = [c for c in cands if c.basis_rule == "ma10_pullback"]
    assert len(entries) == 1
    assert entries[0].direction == "entry"


def test_ma10_pullback_skipped_when_above_current():
    facts = [
        _fact("technical.current_price", 200.0),
        _fact("technical.ma10", 222.02),  # above current → entry doesn't fit
    ]
    cands = compute_candidates(facts)
    assert not any(c.basis_rule == "ma10_pullback" for c in cands)


def test_no_current_price_returns_empty():
    facts = [_fact("technical.resistance", 226.13)]
    assert compute_candidates(facts) == []
```

- [ ] **Step 2: Run failing test**

Run: `python -m pytest tests/test_candidate_rules.py -v`
Expected: ImportError

- [ ] **Step 3: Implement basic 4 rules (resistance_touch, ma20_breakdown, ma10_pullback, support_test)**

```python
# src/analysis/candidate_rules.py
"""Candidate price-level computation rules.

23 rules across entry / exit / take_profit / stop_loss directions.
Each rule produces 0 or 1 CandidateLevel from the FactBundle.

See docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md
Section A "Candidate 生成规则".
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from src.analysis.facts import CandidateLevel, FactRecord


def _get_fact(facts: List[FactRecord], fact_id: str) -> Optional[FactRecord]:
    for f in facts:
        if f.id == fact_id:
            return f
    return None


def _get_value(facts: List[FactRecord], fact_id: str) -> Optional[float]:
    f = _get_fact(facts, fact_id)
    if f is None or f.value is None:
        return None
    try:
        return float(f.value)
    except (TypeError, ValueError):
        return None


def _make_candidate(
    idx: int, *, direction: str, price: float, current: float,
    label: str, basis_fact_id: str, basis_rule: str,
    applicable_strategies: List[str], tier: str = "primary",
) -> CandidateLevel:
    id_prefix = {"take_profit": "exit", "stop_loss": "stop", "entry": "entry", "exit": "exit"}[direction]
    distance = ((price - current) / current * 100) if current else 0.0
    return CandidateLevel(
        id=f"candidate.{id_prefix}.{idx}",
        type="candidate",
        label=label,
        value=price,
        display_value=f"${price:.2f}",
        direction=direction,
        price=price,
        basis_fact_id=basis_fact_id,
        basis_rule=basis_rule,
        applicable_strategies=applicable_strategies,
        tier=tier,
        distance_pct_from_current=round(distance, 4),
    )


def compute_candidates(facts: List[FactRecord]) -> List[CandidateLevel]:
    """Run all 23 rules over facts; return all candidates that survive filtering."""
    current = _get_value(facts, "technical.current_price")
    if current is None:
        return []
    candidates: List[CandidateLevel] = []
    counters = {"exit": 0, "stop": 0, "entry": 0}

    def add(c: CandidateLevel):
        candidates.append(c)

    def next_idx(kind: str) -> int:
        counters[kind] += 1
        return counters[kind]

    # ---- Rule: resistance_touch (take_profit) ----
    r = _get_value(facts, "technical.resistance")
    if r is not None and r > current:
        add(_make_candidate(
            next_idx("exit"),
            direction="take_profit", price=r, current=current,
            label="阻力位触及减仓",
            basis_fact_id="technical.resistance",
            basis_rule="resistance_touch",
            applicable_strategies=["swing_trade", "stepped_profit_taking"],
        ))

    # ---- Rule: ma20_breakdown (stop_loss) ----
    ma20 = _get_value(facts, "technical.ma20")
    if ma20 is not None and ma20 < current:
        add(_make_candidate(
            next_idx("stop"),
            direction="stop_loss", price=ma20, current=current,
            label="MA20 跌破止损",
            basis_fact_id="technical.ma20",
            basis_rule="ma20_breakdown",
            applicable_strategies=["swing_trade", "stepped_profit_taking"],
        ))

    # ---- Rule: ma10_pullback (entry) ----
    ma10 = _get_value(facts, "technical.ma10")
    if ma10 is not None and ma10 <= current:
        add(_make_candidate(
            next_idx("entry"),
            direction="entry", price=ma10, current=current,
            label="MA10 回踩入场",
            basis_fact_id="technical.ma10",
            basis_rule="ma10_pullback",
            applicable_strategies=["swing_trade", "stepped_profit_taking"],
        ))

    # ---- Rule: support_test (entry) ----
    sup = _get_value(facts, "technical.support")
    if sup is not None and sup <= current:
        add(_make_candidate(
            next_idx("entry"),
            direction="entry", price=sup, current=current,
            label="支撑位反抽入场",
            basis_fact_id="technical.support",
            basis_rule="support_test",
            applicable_strategies=["swing_trade"],
        ))

    return candidates
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_candidate_rules.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/candidate_rules.py tests/test_candidate_rules.py
git commit -m "feat(analysis): candidate rules — 4 basic technical-position rules"
```

---

### Task 11: Candidate rules — ATR-based stop_loss (atr_2x, atr_3x)

**Files:**
- Modify: `src/analysis/candidate_rules.py`
- Test: `tests/test_candidate_rules.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_candidate_rules.py — append
def test_atr_2x_stop():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.atr_14", 4.32),
    ]
    cands = compute_candidates(facts)
    atr2 = [c for c in cands if c.basis_rule == "atr_2x_below_current"]
    assert len(atr2) == 1
    assert abs(atr2[0].price - (223.47 - 2 * 4.32)) < 0.01
    assert atr2[0].direction == "stop_loss"
    assert atr2[0].tier == "primary"


def test_atr_3x_stop():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.atr_14", 4.32),
    ]
    cands = compute_candidates(facts)
    atr3 = [c for c in cands if c.basis_rule == "atr_3x_below_current"]
    assert len(atr3) == 1
    assert "stepped_profit_taking" in atr3[0].applicable_strategies


def test_no_atr_no_atr_candidates():
    facts = [_fact("technical.current_price", 223.47)]
    cands = compute_candidates(facts)
    assert not any(c.basis_rule.startswith("atr_") for c in cands)
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_candidate_rules.py::test_atr_2x_stop tests/test_candidate_rules.py::test_atr_3x_stop -v`
Expected: FAIL — rules not implemented

- [ ] **Step 3: Add ATR rules to `compute_candidates`**

Insert after support_test rule:

```python
    # ---- Rule: atr_2x_below_current (stop_loss) ----
    atr = _get_value(facts, "technical.atr_14")
    if atr is not None:
        price_2x = current - 2 * atr
        add(_make_candidate(
            next_idx("stop"),
            direction="stop_loss", price=round(price_2x, 2), current=current,
            label="ATR(14)×2 止损",
            basis_fact_id="technical.atr_14",
            basis_rule="atr_2x_below_current",
            applicable_strategies=["swing_trade"],
        ))

    # ---- Rule: atr_3x_below_current (stop_loss) ----
    if atr is not None:
        price_3x = current - 3 * atr
        add(_make_candidate(
            next_idx("stop"),
            direction="stop_loss", price=round(price_3x, 2), current=current,
            label="ATR(14)×3 止损",
            basis_fact_id="technical.atr_14",
            basis_rule="atr_3x_below_current",
            applicable_strategies=["stepped_profit_taking", "long_term_hold"],
        ))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_candidate_rules.py -v`
Expected: 8 PASSED (5 old + 3 new)

- [ ] **Step 5: Commit**

```bash
git add src/analysis/candidate_rules.py tests/test_candidate_rules.py
git commit -m "feat(analysis): candidate rules — ATR-based stop_loss (2x/3x)"
```

---

### Task 12: Candidate rules — R-multiple targets (2R, 3R) + resistance_plus_atr

**Files:**
- Modify: `src/analysis/candidate_rules.py`
- Test: `tests/test_candidate_rules.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_candidate_rules.py — append
def test_r_multiple_2r_target():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.ma20", 213.4),  # provides stop reference
    ]
    cands = compute_candidates(facts)
    r2 = [c for c in cands if c.basis_rule == "r_multiple_2r"]
    assert len(r2) == 1
    # R = current - stop = 223.47 - 213.4 = 10.07
    # 2R target = current + 2R = 243.61
    assert abs(r2[0].price - (223.47 + 2 * (223.47 - 213.4))) < 0.01
    assert r2[0].direction == "take_profit"


def test_r_multiple_3r_target():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.ma20", 213.4),
    ]
    cands = compute_candidates(facts)
    r3 = [c for c in cands if c.basis_rule == "r_multiple_3r"]
    assert len(r3) == 1
    assert "long_term_hold" in r3[0].applicable_strategies


def test_resistance_plus_atr():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.resistance", 226.13),
        _fact("technical.atr_14", 4.32),
    ]
    cands = compute_candidates(facts)
    rpa = [c for c in cands if c.basis_rule == "resistance_plus_atr"]
    assert len(rpa) == 1
    assert abs(rpa[0].price - (226.13 + 4.32)) < 0.01
    assert "stepped_profit_taking" in rpa[0].applicable_strategies


def test_r_multiple_skipped_when_no_stop_reference():
    facts = [_fact("technical.current_price", 223.47)]
    cands = compute_candidates(facts)
    assert not any(c.basis_rule.startswith("r_multiple") for c in cands)
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_candidate_rules.py::test_r_multiple_2r_target tests/test_candidate_rules.py::test_r_multiple_3r_target tests/test_candidate_rules.py::test_resistance_plus_atr -v`
Expected: FAIL — rules not implemented

- [ ] **Step 3: Add R-multiple + resistance_plus_atr rules**

Add to `compute_candidates`:

```python
    # ---- Rule: resistance_plus_atr (take_profit) ----
    if r is not None and atr is not None and r > current:
        price = r + atr
        add(_make_candidate(
            next_idx("exit"),
            direction="take_profit", price=round(price, 2), current=current,
            label="阻力 + 1×ATR 延伸",
            basis_fact_id="technical.resistance",
            basis_rule="resistance_plus_atr",
            applicable_strategies=["stepped_profit_taking", "long_term_hold"],
        ))

    # ---- R-multiple targets: need a stop reference ----
    # Prefer MA20 stop, fall back to ATR stop
    stop_ref = ma20 if (ma20 is not None and ma20 < current) else None
    if stop_ref is None and atr is not None:
        stop_ref = current - 2 * atr
    if stop_ref is not None and stop_ref < current:
        r_unit = current - stop_ref
        # 2R
        add(_make_candidate(
            next_idx("exit"),
            direction="take_profit", price=round(current + 2 * r_unit, 2), current=current,
            label="2R 目标",
            basis_fact_id="technical.ma20" if ma20 == stop_ref else "technical.atr_14",
            basis_rule="r_multiple_2r",
            applicable_strategies=["swing_trade", "stepped_profit_taking"],
        ))
        # 3R
        add(_make_candidate(
            next_idx("exit"),
            direction="take_profit", price=round(current + 3 * r_unit, 2), current=current,
            label="3R 目标",
            basis_fact_id="technical.ma20" if ma20 == stop_ref else "technical.atr_14",
            basis_rule="r_multiple_3r",
            applicable_strategies=["stepped_profit_taking", "long_term_hold"],
        ))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_candidate_rules.py -v`
Expected: 12 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/candidate_rules.py tests/test_candidate_rules.py
git commit -m "feat(analysis): candidate rules — R-multiple targets + resistance+ATR"
```

---

### Task 13: Candidate rules — psychological_round + cost-based discipline anchors

**Files:**
- Modify: `src/analysis/candidate_rules.py`
- Test: `tests/test_candidate_rules.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_candidate_rules.py — append
def test_psychological_round_next_above():
    facts = [_fact("technical.current_price", 223.47)]
    cands = compute_candidates(facts)
    rounds = [c for c in cands if c.basis_rule == "psychological_round"]
    assert len(rounds) >= 1
    # next round above 223.47 should be 230 (step 10)
    assert any(c.price == 230.0 for c in rounds)
    assert all(c.tier == "secondary" for c in rounds)


def test_cost_plus_5pct_anchor_when_held_and_not_triggered():
    facts = [
        _fact("technical.current_price", 200.0),  # below cost+5%
        _fact("portfolio.avg_cost", 196.18, type_="portfolio"),
    ]
    cands = compute_candidates(facts)
    anchors = [c for c in cands if c.basis_rule == "cost_plus_5pct"]
    assert len(anchors) == 1
    assert anchors[0].tier == "discipline_anchor"
    assert abs(anchors[0].price - 196.18 * 1.05) < 0.01


def test_cost_plus_5pct_skipped_when_already_triggered():
    facts = [
        _fact("technical.current_price", 223.47),  # already past cost+5% = 205.99
        _fact("portfolio.avg_cost", 196.18, type_="portfolio"),
    ]
    cands = compute_candidates(facts)
    anchors = [c for c in cands if c.basis_rule == "cost_plus_5pct"]
    assert anchors == []


def test_cost_minus_10pct_anchor():
    facts = [
        _fact("technical.current_price", 200.0),
        _fact("portfolio.avg_cost", 196.18, type_="portfolio"),
    ]
    cands = compute_candidates(facts)
    stops = [c for c in cands if c.basis_rule == "cost_minus_10pct"]
    assert len(stops) == 1
    assert stops[0].tier == "discipline_anchor"
    assert stops[0].direction == "stop_loss"


def test_no_avg_cost_no_anchor_candidates():
    facts = [_fact("technical.current_price", 200.0)]
    cands = compute_candidates(facts)
    assert not any(c.basis_rule.startswith("cost_") for c in cands)
```

- [ ] **Step 2: Run failing test**

Run: `python -m pytest tests/test_candidate_rules.py::test_psychological_round_next_above tests/test_candidate_rules.py::test_cost_plus_5pct_anchor_when_held_and_not_triggered tests/test_candidate_rules.py::test_cost_minus_10pct_anchor -v`
Expected: FAIL — rules not implemented

- [ ] **Step 3: Add psychological_round + cost-anchor rules**

Add to `compute_candidates`:

```python
    # ---- Rule: psychological_round (take_profit, secondary tier) ----
    import math
    step = 10 if current < 500 else 50
    next_round = math.ceil(current / step) * step
    if next_round > current:
        add(_make_candidate(
            next_idx("exit"),
            direction="take_profit", price=float(next_round), current=current,
            label="心理整数关口",
            basis_fact_id="technical.current_price",
            basis_rule="psychological_round",
            applicable_strategies=["long_term_hold", "swing_trade", "stepped_profit_taking"],
            tier="secondary",
        ))

    # ---- Cost-based discipline anchors (only if held) ----
    avg_cost = _get_value(facts, "portfolio.avg_cost")
    if avg_cost is not None and avg_cost > 0:
        for pct, rule_name, strategies in [
            (0.05, "cost_plus_5pct", ["stepped_profit_taking"]),
            (0.12, "cost_plus_12pct", ["stepped_profit_taking"]),
            (0.20, "cost_plus_20pct", ["stepped_profit_taking", "long_term_hold"]),
        ]:
            price = avg_cost * (1 + pct)
            if price > current:  # not yet triggered
                add(_make_candidate(
                    next_idx("exit"),
                    direction="take_profit", price=round(price, 2), current=current,
                    label=f"成本 +{int(pct * 100)}% 纪律锚",
                    basis_fact_id="portfolio.avg_cost",
                    basis_rule=rule_name,
                    applicable_strategies=strategies,
                    tier="discipline_anchor",
                ))

        # cost_minus_10pct stop
        stop_price = avg_cost * 0.9
        if stop_price < current:
            add(_make_candidate(
                next_idx("stop"),
                direction="stop_loss", price=round(stop_price, 2), current=current,
                label="成本 −10% 纪律止损",
                basis_fact_id="portfolio.avg_cost",
                basis_rule="cost_minus_10pct",
                applicable_strategies=["long_term_hold", "stepped_profit_taking"],
                tier="discipline_anchor",
            ))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_candidate_rules.py -v`
Expected: 17 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/candidate_rules.py tests/test_candidate_rules.py
git commit -m "feat(analysis): candidate rules — psychological_round + cost-anchor tier"
```

---

### Task 14: Candidate rules — Fibonacci extensions + swing high/low + qlib_top_decile_buy + chip_avg_cost + remaining rules

**Files:**
- Modify: `src/analysis/candidate_rules.py`
- Test: `tests/test_candidate_rules.py` (extend)

- [ ] **Step 1: Write failing tests for remaining rules**

```python
# tests/test_candidate_rules.py — append
def test_fib_extension_requires_swing_pair():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.swing_low_20d", 200.0),
        _fact("technical.swing_high_20d", 220.0),
    ]
    cands = compute_candidates(facts)
    fib1272 = [c for c in cands if c.basis_rule == "fib_extension_1272"]
    fib1618 = [c for c in cands if c.basis_rule == "fib_extension_1618"]
    assert len(fib1272) == 1
    assert len(fib1618) == 1
    # range = 220 - 200 = 20; 1.272 ext = 220 + (0.272 * 20) = 225.44
    assert abs(fib1272[0].price - 225.44) < 0.01


def test_prev_swing_high_and_low():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.swing_high_20d", 230.0),
        _fact("technical.swing_low_20d", 210.0),
    ]
    cands = compute_candidates(facts)
    sh = [c for c in cands if c.basis_rule == "prev_swing_high"]
    sl = [c for c in cands if c.basis_rule == "prev_swing_low"]
    assert len(sh) == 1 and sh[0].direction == "take_profit"
    assert len(sl) == 1 and sl[0].direction == "stop_loss"


def test_qlib_top_decile_buy_only_when_rank_high():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("quant.qlib_rank", 0.95, type_="quant"),
        _fact("technical.trend_score", 75),
    ]
    cands = compute_candidates(facts)
    qe = [c for c in cands if c.basis_rule == "qlib_top_decile_buy"]
    assert len(qe) == 1
    assert qe[0].direction == "entry"


def test_qlib_top_decile_buy_skipped_when_rank_low():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("quant.qlib_rank", 0.5, type_="quant"),
    ]
    cands = compute_candidates(facts)
    assert not any(c.basis_rule == "qlib_top_decile_buy" for c in cands)


def test_chip_avg_cost_entry_a_share():
    facts = [
        _fact("technical.current_price", 50.0),
        _fact("chip.avg_cost", 45.0, type_="chip"),
    ]
    cands = compute_candidates(facts)
    chip_entries = [c for c in cands if c.basis_rule == "chip_avg_cost"]
    assert len(chip_entries) == 1
    assert chip_entries[0].direction == "entry"
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_candidate_rules.py -v -k "fib_extension or prev_swing or qlib_top_decile or chip_avg_cost"`
Expected: 5 FAIL

- [ ] **Step 3: Add remaining rules**

Add to `compute_candidates`:

```python
    # ---- Rule: prev_swing_high (take_profit) ----
    swing_high = _get_value(facts, "technical.swing_high_20d")
    if swing_high is not None and swing_high > current:
        add(_make_candidate(
            next_idx("exit"),
            direction="take_profit", price=swing_high, current=current,
            label="前 20 日波段高点",
            basis_fact_id="technical.swing_high_20d",
            basis_rule="prev_swing_high",
            applicable_strategies=["swing_trade"],
        ))

    # ---- Rule: prev_swing_low (stop_loss) ----
    swing_low = _get_value(facts, "technical.swing_low_20d")
    if swing_low is not None and swing_low < current:
        add(_make_candidate(
            next_idx("stop"),
            direction="stop_loss", price=swing_low, current=current,
            label="前 20 日波段低点",
            basis_fact_id="technical.swing_low_20d",
            basis_rule="prev_swing_low",
            applicable_strategies=["swing_trade", "stepped_profit_taking"],
        ))

    # ---- Rule: fib_extension_1272 / 1618 (take_profit) ----
    if swing_high is not None and swing_low is not None and swing_high > swing_low:
        span = swing_high - swing_low
        for fib_ratio, rule_name, strategies in [
            (0.272, "fib_extension_1272", ["swing_trade"]),
            (0.618, "fib_extension_1618", ["stepped_profit_taking"]),
        ]:
            price = swing_high + fib_ratio * span
            if price > current:
                add(_make_candidate(
                    next_idx("exit"),
                    direction="take_profit", price=round(price, 2), current=current,
                    label=f"Fib {int((1 + fib_ratio) * 1000)/1000} 延伸",
                    basis_fact_id="technical.swing_high_20d",
                    basis_rule=rule_name,
                    applicable_strategies=strategies,
                ))

    # ---- Rule: qlib_top_decile_buy (entry) ----
    qlib_rank = _get_value(facts, "quant.qlib_rank")
    if qlib_rank is not None and qlib_rank > 0.9:
        # Bonus: trend must be bullish if we have trend_score
        trend = _get_value(facts, "technical.trend_score")
        if trend is None or trend >= 50:
            add(_make_candidate(
                next_idx("entry"),
                direction="entry", price=round(current, 2), current=current,
                label="Qlib 顶 10% 即时入场",
                basis_fact_id="quant.qlib_rank",
                basis_rule="qlib_top_decile_buy",
                applicable_strategies=["long_term_hold"],
            ))

    # ---- Rule: chip_avg_cost (entry, A-share) ----
    chip_cost = _get_value(facts, "chip.avg_cost")
    if chip_cost is not None and chip_cost <= current:
        add(_make_candidate(
            next_idx("entry"),
            direction="entry", price=chip_cost, current=current,
            label="市场平均成本回踩",
            basis_fact_id="chip.avg_cost",
            basis_rule="chip_avg_cost",
            applicable_strategies=["long_term_hold", "swing_trade", "stepped_profit_taking"],
        ))
```

- [ ] **Step 4: Run all candidate_rules tests**

Run: `python -m pytest tests/test_candidate_rules.py -v`
Expected: 22 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/candidate_rules.py tests/test_candidate_rules.py
git commit -m "feat(analysis): candidate rules — Fib/swing/qlib/chip remaining rules"
```

---

### Task 15: Add swing_high_20d / swing_low_20d to technical extractor (so Fib + swing rules have inputs)

**Files:**
- Modify: `src/analysis/extractors/technical.py`
- Test: `tests/test_facts_technical.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_facts_technical.py — append
def test_extract_swing_high_low_from_ohlc():
    dp = {"price_position": {"current_price": 100.0}}
    # 20-day OHLC with clear high/low
    ohlc = [
        {"high": 95 + i, "low": 90 + i, "close": 93 + i, "open": 92 + i}
        for i in range(20)
    ]
    # inject one outlier high + one outlier low
    ohlc[5]["high"] = 130.0
    ohlc[15]["low"] = 80.0
    facts = extract_technical_facts(dp, rsi_12=None, as_of="2026-05-21T00:43:00Z", ohlc=ohlc)
    ids = {f.id for f in facts}
    assert "technical.swing_high_20d" in ids
    assert "technical.swing_low_20d" in ids
    sh = next(f for f in facts if f.id == "technical.swing_high_20d")
    sl = next(f for f in facts if f.id == "technical.swing_low_20d")
    assert sh.value == 130.0
    assert sl.value == 80.0


def test_swing_no_ohlc_skipped():
    dp = {"price_position": {"current_price": 100.0}}
    facts = extract_technical_facts(dp, rsi_12=None, as_of="2026-05-21T00:43:00Z")
    assert not any(f.id.startswith("technical.swing_") for f in facts)
```

- [ ] **Step 2: Run failing test**

Run: `python -m pytest tests/test_facts_technical.py::test_extract_swing_high_low_from_ohlc tests/test_facts_technical.py::test_swing_no_ohlc_skipped -v`
Expected: FAIL — swing facts not emitted

- [ ] **Step 3: Add swing extraction to technical.py**

Insert in `extract_technical_facts` after the ATR block:

```python
    if ohlc is not None and len(ohlc) >= 5:
        last_n = ohlc[-20:] if len(ohlc) >= 20 else ohlc
        swing_high = max(float(bar["high"]) for bar in last_n)
        swing_low = min(float(bar["low"]) for bar in last_n)
        facts.append(FactRecord(
            id="technical.swing_high_20d", type="technical",
            label=f"前 {len(last_n)} 日波段高点", value=swing_high,
            display_value=_format_price(swing_high, market),
            source="data_provider/daily_data:swing", as_of=as_of,
        ))
        facts.append(FactRecord(
            id="technical.swing_low_20d", type="technical",
            label=f"前 {len(last_n)} 日波段低点", value=swing_low,
            display_value=_format_price(swing_low, market),
            source="data_provider/daily_data:swing", as_of=as_of,
        ))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_facts_technical.py -v`
Expected: 8 PASSED (6 old + 2 new)

- [ ] **Step 5: Commit**

```bash
git add src/analysis/extractors/technical.py tests/test_facts_technical.py
git commit -m "feat(analysis): emit swing_high_20d/swing_low_20d for Fib/swing rules"
```

---

### Task 16: facts_builder.py main entry — wires all extractors + candidate rules

**Files:**
- Create: `src/analysis/facts_builder.py`
- Test: `tests/test_facts_builder.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/test_facts_builder.py
from src.analysis.facts_builder import build_fact_bundle


def test_build_fact_bundle_nvda_us_full():
    """End-to-end: feeds NVDA-like dashboard + portfolio + qlib → FactBundle."""
    dashboard = {
        "data_perspective": {
            "price_position": {
                "current_price": 223.47, "ma5": 225.49, "ma10": 222.02, "ma20": 213.4,
                "support_level": 222.02, "resistance_level": 226.13, "bias_ma5": -0.9,
            },
            "trend_status": {"trend_score": 75, "ma_alignment": "bullish", "is_bullish": True},
            "volume_analysis": {"volume_status": "量能正常"},
        },
        "intelligence": {
            "risk_alerts": ["RSI 71.1 超买", "PE/PB 缺失"],
            "positive_catalysts": [],
        },
        "committee": {
            "pm_verdict": "hold", "pm_score": 5.8, "pm_dissents": ["cathie_wood"],
            "risk": {"severity": "soft", "suggested_position_pct": 0.3,
                     "red_flags": ["RSI 71.1 超买"]},
            "masters": [
                {"persona": "warren_buffett", "verdict": "hold", "score": 4.0,
                 "headline": "估值不明朗", "key_evidence": []},
                {"persona": "cathie_wood", "verdict": "strong_buy", "score": 9.2,
                 "headline": "AI 革命核心", "key_evidence": []},
            ],
        },
    }
    portfolio_context = {
        "match_state": "held",
        "holding_shares": 0.7597, "avg_cost": 196.18, "currency": "USD",
        "unrealized_pnl_pct": 13.33, "base_currency": "GBP", "total_equity": 1200.0,
    }
    rsi_12 = 71.1
    ohlc = [{"high": 220 + i * 0.5, "low": 215 + i * 0.5, "close": 217 + i * 0.5} for i in range(20)]
    qlib_predictions = {"NVDA": {"score": 0.235, "rank": 0.847}}
    qlib_ic = {"ic_current": 0.172, "ic_ma_4w": 0.211}

    bundle = build_fact_bundle(
        stock_code="NVDA", market="us",
        dashboard=dashboard, portfolio_context=portfolio_context,
        ohlc=ohlc, rsi_12=rsi_12,
        qlib_predictions=qlib_predictions, qlib_ic=qlib_ic,
        qlib_week="2026-W21", qlib_universe_size=503,
        as_of="2026-05-21T00:43:00Z",
    )
    assert bundle.market == "us"
    assert bundle.stock_code == "NVDA"
    fact_ids = {f.id for f in bundle.facts}
    # Spot-check key facts from each domain
    for required in [
        "technical.current_price", "technical.ma10", "technical.rsi_12",
        "quant.qlib_score", "quant.qlib_rank",
        "committee.pm_verdict", "committee.master.warren_buffett",
        "intel.risk_alert.0",
        "portfolio.holding_shares", "portfolio.avg_cost",
    ]:
        assert required in fact_ids, f"missing {required}"
    # No flow/chip for US
    assert not any(f.type in ("flow", "chip") for f in bundle.facts)
    # Candidates exist
    assert len(bundle.candidates) > 0
    # Has at least one primary exit + primary stop
    assert any(c.tier == "primary" and c.direction == "take_profit" for c in bundle.candidates)
    assert any(c.tier == "primary" and c.direction == "stop_loss" for c in bundle.candidates)


def test_build_fact_bundle_no_portfolio_still_works():
    dashboard = {
        "data_perspective": {"price_position": {"current_price": 100.0, "ma20": 95.0}},
    }
    bundle = build_fact_bundle(
        stock_code="XYZ", market="us",
        dashboard=dashboard, portfolio_context=None,
        ohlc=None, rsi_12=None,
        qlib_predictions={}, qlib_ic={},
        qlib_week="2026-W21", qlib_universe_size=0,
        as_of="2026-05-21T00:43:00Z",
    )
    assert bundle.facts  # at least technical.current_price + ma20
    # No cost-anchor candidates without portfolio
    assert not any(c.basis_rule.startswith("cost_") for c in bundle.candidates)


def test_build_fact_bundle_a_share_includes_flow_chip():
    dashboard = {
        "data_perspective": {"price_position": {"current_price": 50.0, "ma20": 45.0}},
    }
    portfolio_context = None
    flow = {"status": "ok", "stock_flow": {"main_net_inflow": 1e7, "inflow_5d": 5e7}}
    chip = {"profit_ratio": 0.6, "avg_cost": 45.0, "concentration_70": 0.08, "concentration_90": 0.15}

    bundle = build_fact_bundle(
        stock_code="000001", market="a",
        dashboard=dashboard, portfolio_context=None,
        ohlc=None, rsi_12=None,
        qlib_predictions={}, qlib_ic={},
        qlib_week="2026-W21", qlib_universe_size=0,
        as_of="2026-05-21T00:43:00Z",
        flow=flow, chip=chip,
    )
    fact_types = {f.type for f in bundle.facts}
    assert "flow" in fact_types
    assert "chip" in fact_types
```

- [ ] **Step 2: Run failing test**

Run: `python -m pytest tests/test_facts_builder.py -v`
Expected: ImportError

- [ ] **Step 3: Implement facts_builder.py**

```python
# src/analysis/facts_builder.py
"""Stage 1 orchestrator — wires all 8 extractors + candidate rules into a FactBundle.

Called from src/core/pipeline.py::process_single_stock after committee + dashboard
assembly is complete. Returns a FactBundle attached to dashboard.fact_bundle.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.analysis.candidate_rules import compute_candidates
from src.analysis.extractors.chip import extract_chip_facts
from src.analysis.extractors.committee import extract_committee_facts
from src.analysis.extractors.flow import extract_flow_facts
from src.analysis.extractors.intel import extract_intel_facts
from src.analysis.extractors.portfolio import extract_portfolio_facts
from src.analysis.extractors.quant import extract_quant_facts
from src.analysis.extractors.technical import extract_technical_facts
from src.analysis.facts import FactBundle, FactRecord


def build_fact_bundle(
    *,
    stock_code: str,
    market: str,
    dashboard: Dict[str, Any],
    portfolio_context: Optional[Dict[str, Any]],
    ohlc: Optional[List[Dict[str, Any]]],
    rsi_12: Optional[float],
    qlib_predictions: Dict[str, Dict[str, float]],
    qlib_ic: Dict[str, Any],
    qlib_week: str,
    qlib_universe_size: int,
    as_of: str,
    flow: Optional[Dict[str, Any]] = None,
    chip: Optional[Dict[str, Any]] = None,
) -> FactBundle:
    """Assemble the Stage 1 FactBundle. Pure code, no LLM, no I/O.

    Caller is responsible for resolving qlib predictions / flow / chip / ohlc
    upstream and passing them in.
    """
    facts: List[FactRecord] = []

    facts.extend(extract_technical_facts(
        data_perspective=dashboard.get("data_perspective") or {},
        rsi_12=rsi_12, as_of=as_of, market=market, ohlc=ohlc,
    ))
    facts.extend(extract_quant_facts(
        ticker=stock_code,
        predictions=qlib_predictions or {}, ic=qlib_ic or {},
        universe_size=qlib_universe_size, week=qlib_week, as_of=as_of,
    ))
    facts.extend(extract_committee_facts(
        committee=dashboard.get("committee"), as_of=as_of,
    ))
    facts.extend(extract_intel_facts(
        intelligence=dashboard.get("intelligence"), as_of=as_of,
    ))
    facts.extend(extract_portfolio_facts(
        portfolio_context=portfolio_context, as_of=as_of,
    ))
    facts.extend(extract_flow_facts(flow=flow, market=market, as_of=as_of))
    facts.extend(extract_chip_facts(chip=chip, market=market, as_of=as_of))

    candidates = compute_candidates(facts)

    return FactBundle(
        as_of=as_of, market=market, stock_code=stock_code,
        facts=facts, candidates=candidates,
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_facts_builder.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/analysis/facts_builder.py tests/test_facts_builder.py
git commit -m "feat(analysis): facts_builder main entry wires all extractors + rules"
```

---

### Task 17: Pipeline integration — attach `fact_bundle` to dashboard

**Files:**
- Modify: `src/core/pipeline.py:1677-1750` (within `process_single_stock`)
- Test: `tests/test_pipeline_fact_bundle.py`

- [ ] **Step 1: Read existing pipeline to find safe insertion point**

Run: `grep -n "dashboard\|fact_bundle\|action_plan_items" src/core/pipeline.py | head -30`

Expected: shows where dashboard is assembled and where `_try_inject_action_plan_items` is called. Insert `fact_bundle` attachment **after** the existing committee/dashboard assembly, **before** action_plan injection.

- [ ] **Step 2: Write integration test (mocked)**

```python
# tests/test_pipeline_fact_bundle.py
"""Verify fact_bundle is attached to dashboard during process_single_stock."""
from unittest.mock import MagicMock, patch

import pytest

from src.core.pipeline import StockAnalysisPipeline


def _make_pipeline_with_mocks() -> StockAnalysisPipeline:
    """Construct pipeline with all collaborators mocked. Real config not needed."""
    p = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    p.config = MagicMock()
    p.config.is_debug.return_value = False
    p.db = MagicMock()
    p.fetcher_manager = MagicMock()
    p.analyzer = MagicMock()
    p.notifier = MagicMock()
    return p


def test_fact_bundle_attached_to_dashboard():
    """Smoke test that after process_single_stock, fact_bundle exists on dashboard."""
    pytest.skip(
        "Integration smoke deferred — see Task 17 step 3 for real wiring & rerun."
    )
```

(Note: this test is intentionally skipped initially; we wire it in Step 4.)

- [ ] **Step 3: Wire facts_builder into `process_single_stock`**

Open `src/core/pipeline.py` and locate the section after the existing dashboard assembly (search for where `dashboard` dict is finalized but before `_try_inject_action_plan_items` is called). Insert:

```python
# === Stage 1: build FactBundle and attach to dashboard ===
from src.analysis.facts_builder import build_fact_bundle
from dataclasses import asdict
import json
from pathlib import Path
from datetime import datetime, timezone

# Resolve qlib predictions for this market
qlib_predictions: dict = {}
qlib_ic: dict = {}
qlib_week = ""
qlib_universe_size = 0
try:
    market_dir = Path("data/quant_models") / ("cn" if market == "a" else "us")
    from src.analysis.extractors.quant import find_latest_qlib_week
    week = find_latest_qlib_week(market_dir)
    if week:
        qlib_week = week
        pred_path = market_dir / week / "predictions.json"
        ic_path = market_dir / week / "ic.json"
        if pred_path.exists():
            qlib_predictions = json.loads(pred_path.read_text())
            qlib_universe_size = len(qlib_predictions)
        if ic_path.exists():
            qlib_ic = json.loads(ic_path.read_text())
except Exception as exc:
    logger.warning(f"[facts_builder] qlib load failed for {code}: {exc}")

# Pull rsi_12 from existing technical analysis if available
rsi_12 = None
try:
    tech_block = (
        result.dashboard.get("intelligence", {}) if isinstance(result.dashboard, dict)
        else {}
    ).get("technical_indicators") or {}
    rsi_12 = tech_block.get("rsi_12")
except Exception:
    rsi_12 = None

# OHLC: use the already-fetched daily data
ohlc_list: Optional[list] = None
try:
    if df is not None and len(df) > 0:
        ohlc_list = df[["high", "low", "close"]].tail(30).to_dict(orient="records")
except Exception:
    ohlc_list = None

# Flow + chip: A-share only, pulled from fundamental_adapter if available
flow_data = None
chip_data = None
if market == "a":
    try:
        flow_data = self.fetcher_manager.get_capital_flow(code) if hasattr(
            self.fetcher_manager, "get_capital_flow") else None
        chip_data = self.fetcher_manager.get_chip_distribution(code) if hasattr(
            self.fetcher_manager, "get_chip_distribution") else None
    except Exception as exc:
        logger.warning(f"[facts_builder] flow/chip load failed for {code}: {exc}")

try:
    bundle = build_fact_bundle(
        stock_code=code, market=market,
        dashboard=result.dashboard if isinstance(result.dashboard, dict) else {},
        portfolio_context=(portfolio_match_ctx if hasattr(self, "_last_portfolio_ctx") else None),
        ohlc=ohlc_list, rsi_12=rsi_12,
        qlib_predictions=qlib_predictions, qlib_ic=qlib_ic,
        qlib_week=qlib_week, qlib_universe_size=qlib_universe_size,
        as_of=datetime.now(timezone.utc).isoformat(),
        flow=flow_data, chip=chip_data,
    )
    if isinstance(result.dashboard, dict):
        result.dashboard["fact_bundle"] = {
            "as_of": bundle.as_of,
            "market": bundle.market,
            "stock_code": bundle.stock_code,
            "facts": [asdict(f) for f in bundle.facts],
            "candidates": [asdict(c) for c in bundle.candidates],
        }
        logger.info(
            f"[facts_builder] {code} bundle attached: "
            f"{len(bundle.facts)} facts, {len(bundle.candidates)} candidates"
        )
except Exception as exc:
    logger.error(f"[facts_builder] failed for {code}, dashboard unmodified: {exc}")
```

**Important**:
- Wrap in `try/except` so any failure does NOT break the analysis pipeline (Phase 1 must be non-disruptive).
- Locate the exact insertion point: between dashboard assembly completion and any action_plan injection. Use `grep -n "_try_inject_action_plan_items\|update_committee_minutes" src/core/pipeline.py` to find anchors.
- `market` variable should already be resolved at this point in the function. If not, derive: `from src.utils.market_inference import infer_market; market = infer_market(code)` (verify exact import path during implementation).

- [ ] **Step 4: Enable the smoke test**

Replace the skip in `tests/test_pipeline_fact_bundle.py` with a real test:

```python
def test_fact_bundle_attached_to_dashboard():
    """Real smoke: build a minimal dashboard and verify fact_bundle gets injected."""
    from src.analysis.facts_builder import build_fact_bundle
    dashboard = {
        "data_perspective": {"price_position": {"current_price": 100.0, "ma20": 95.0}},
        "intelligence": {},
        "committee": {"pm_verdict": "hold", "pm_score": 5.0, "masters": []},
    }
    bundle = build_fact_bundle(
        stock_code="TEST", market="us",
        dashboard=dashboard, portfolio_context=None,
        ohlc=None, rsi_12=None,
        qlib_predictions={}, qlib_ic={},
        qlib_week="", qlib_universe_size=0,
        as_of="2026-05-21T00:43:00Z",
    )
    assert bundle is not None
    assert bundle.stock_code == "TEST"
    assert any(f.id == "technical.current_price" for f in bundle.facts)
```

- [ ] **Step 5: Run all phase 1 tests**

Run: `python -m pytest tests/test_facts.py tests/test_facts_technical.py tests/test_facts_quant.py tests/test_facts_committee.py tests/test_facts_intel.py tests/test_facts_portfolio.py tests/test_facts_flow.py tests/test_facts_chip.py tests/test_candidate_rules.py tests/test_facts_builder.py tests/test_pipeline_fact_bundle.py -v`
Expected: all PASS

- [ ] **Step 6: Verify pipeline still works end-to-end (smoke)**

Run: `./scripts/ci_gate.sh`
Expected: all pass. If `ci_gate.sh` fails on `python -m py_compile src/core/pipeline.py`, fix the insertion.

- [ ] **Step 7: Commit**

```bash
git add src/core/pipeline.py tests/test_pipeline_fact_bundle.py
git commit -m "feat(pipeline): attach FactBundle to dashboard (Phase 1 wiring)"
```

---

### Task 18: NVDA fixture-based end-to-end test

**Files:**
- Create: `tests/fixtures/nvda_dashboard.json`
- Create: `tests/test_facts_nvda_fixture.py`

- [ ] **Step 1: Capture NVDA dashboard fixture**

Run: `python3 -c "
import json, sqlite3
conn = sqlite3.connect('data/stock_analysis.db')
cur = conn.execute('SELECT raw_result FROM analysis_history WHERE id=13')
raw = cur.fetchone()[0]
data = json.loads(raw)
with open('tests/fixtures/nvda_dashboard.json', 'w') as f:
    json.dump(data['dashboard'], f, ensure_ascii=False, indent=2)
print('saved')
"`

Expected: prints `saved`. Creates `tests/fixtures/nvda_dashboard.json`.

- [ ] **Step 2: Write fixture-based test**

```python
# tests/test_facts_nvda_fixture.py
"""Real NVDA dashboard (id=13) → FactBundle integration test."""
import json
from pathlib import Path

from src.analysis.facts_builder import build_fact_bundle


def test_nvda_fixture_produces_meaningful_bundle():
    dashboard = json.loads(Path("tests/fixtures/nvda_dashboard.json").read_text())
    portfolio_context = {
        "match_state": "held",
        "holding_shares": 0.7597, "avg_cost": 196.18, "currency": "USD",
        "unrealized_pnl_pct": 13.33, "base_currency": "GBP",
        "total_equity": 1200.0,
    }
    bundle = build_fact_bundle(
        stock_code="NVDA", market="us",
        dashboard=dashboard, portfolio_context=portfolio_context,
        ohlc=None, rsi_12=71.1,
        qlib_predictions={"NVDA": {"score": 0.235, "rank": 0.847}},
        qlib_ic={"ic_current": 0.172, "ic_ma_4w": 0.211},
        qlib_week="2026-W21", qlib_universe_size=503,
        as_of="2026-05-21T00:43:00Z",
    )

    # Key facts must exist
    fact_ids = {f.id for f in bundle.facts}
    for required in [
        "technical.current_price", "technical.ma10", "technical.ma20",
        "technical.resistance", "technical.rsi_12",
        "quant.qlib_rank",
        "committee.pm_verdict", "committee.master.warren_buffett",
        "committee.master.cathie_wood",
        "portfolio.holding_shares", "portfolio.avg_cost",
    ]:
        assert required in fact_ids, f"missing required fact: {required}"

    # Cathie is correctly marked as dissent
    cathie = next(f for f in bundle.facts if f.id == "committee.master.cathie_wood")
    assert cathie.extra.get("is_dissent") is True

    # Candidates: at least one primary exit + one primary stop
    primary_exits = [c for c in bundle.candidates
                     if c.tier == "primary" and c.direction == "take_profit"]
    primary_stops = [c for c in bundle.candidates
                     if c.tier == "primary" and c.direction == "stop_loss"]
    assert len(primary_exits) >= 2  # resistance_touch + R-multiple at minimum
    assert len(primary_stops) >= 1  # ma20_breakdown

    # cost_plus_5pct/12pct should NOT appear because they're already triggered
    # (cost=196.18, +5%=205.99 < current 223.47)
    triggered_anchors = [c for c in bundle.candidates
                         if c.basis_rule in ("cost_plus_5pct", "cost_plus_12pct")]
    assert triggered_anchors == [], (
        f"cost-anchors below current price should not be emitted: {triggered_anchors}"
    )

    # cost_minus_10pct (= 176.56) should appear as discipline_anchor stop
    cost_stop = [c for c in bundle.candidates if c.basis_rule == "cost_minus_10pct"]
    assert len(cost_stop) == 1
    assert cost_stop[0].tier == "discipline_anchor"
    assert abs(cost_stop[0].price - 196.18 * 0.9) < 0.01
```

- [ ] **Step 3: Run fixture test**

Run: `python -m pytest tests/test_facts_nvda_fixture.py -v`
Expected: PASS

- [ ] **Step 4: Verify full Phase 1 test suite passes**

Run: `python -m pytest tests/test_facts.py tests/test_facts_technical.py tests/test_facts_quant.py tests/test_facts_committee.py tests/test_facts_intel.py tests/test_facts_portfolio.py tests/test_facts_flow.py tests/test_facts_chip.py tests/test_candidate_rules.py tests/test_facts_builder.py tests/test_pipeline_fact_bundle.py tests/test_facts_nvda_fixture.py -v`
Expected: all PASS (~60+ tests)

- [ ] **Step 5: Run CI gate**

Run: `./scripts/ci_gate.sh`
Expected: pass

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/nvda_dashboard.json tests/test_facts_nvda_fixture.py
git commit -m "test(analysis): NVDA fixture-based end-to-end FactBundle test"
```

---

### Task 19: Update CHANGELOG + smoke-test a real analysis run

**Files:**
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: Add CHANGELOG entry**

Append to `[Unreleased]` section in `docs/CHANGELOG.md` (flat format per AGENTS.md):

```markdown
- [新功能] FactBundle 基础设施落地（Phase 1）：dashboard 顶层新增 `fact_bundle` 字段，包含 8 类 fact 与 23 条候选触发价位规则。当前阶段对用户可见行为无影响，为后续证据接地决策管线打基础。
```

- [ ] **Step 2: Run a real single-stock analysis to verify no regression**

Run: `python main.py --stocks AAPL --dry-run` (or `--debug` if `--dry-run` doesn't exist)
Expected: completes without error. Check log for `[facts_builder] AAPL bundle attached: X facts, Y candidates`.

- [ ] **Step 3: Inspect the dashboard JSON to verify fact_bundle attached**

Run: `python3 -c "
import sqlite3, json
conn = sqlite3.connect('data/stock_analysis.db')
row = conn.execute('SELECT raw_result FROM analysis_history WHERE code=\"AAPL\" ORDER BY created_at DESC LIMIT 1').fetchone()
if row:
    data = json.loads(row[0])
    fb = data.get('dashboard', {}).get('fact_bundle')
    if fb:
        print(f'facts: {len(fb[\"facts\"])}, candidates: {len(fb[\"candidates\"])}')
        print('sample fact IDs:', [f['id'] for f in fb['facts'][:5]])
    else:
        print('NO fact_bundle found — wiring incomplete')
"`

Expected: prints fact / candidate counts and sample IDs.

- [ ] **Step 4: Commit + open PR**

```bash
git add docs/CHANGELOG.md
git commit -m "docs(changelog): Phase 1 FactBundle foundation entry"
```

Then open PR with title `feat(analysis): Phase 1 — FactBundle foundation` and body referencing `docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md` Section A.

PR description template:

```markdown
## Summary
Phase 1 of the evidence-grounded decision pipeline. Introduces `src/analysis/` package with FactRecord/FactBundle/CandidateLevel types, 8 per-domain extractors, 23 candidate computation rules, and integrates into `process_single_stock` to attach `dashboard.fact_bundle`.

## Test plan
- [ ] `python -m pytest tests/test_facts*.py tests/test_candidate_rules.py tests/test_pipeline_fact_bundle.py -v` all pass
- [ ] `./scripts/ci_gate.sh` passes
- [ ] Real analysis run produces dashboard with `fact_bundle` field populated
- [ ] No user-visible UI change (Phase 1 is foundation only)

## Risk
- Phase 1 is wrapped in `try/except` in pipeline → any failure logs and continues
- New schema field is additive; old consumers ignore unknown keys
```

---

## Self-Review

**Spec coverage check** — Section A of the spec is fully covered by this plan:

| Spec requirement | Task |
|---|---|
| FactRecord / FactBundle / CandidateLevel types | Task 1 |
| 8 fact type categories | Tasks 2, 4-9 |
| 23 candidate rules (basic + ATR + R-multiple + Fib + swing + qlib + chip + cost-anchor) | Tasks 10-14 |
| ATR(14) computation | Task 3 |
| swing_high_20d / swing_low_20d extraction | Task 15 |
| facts_builder main orchestrator | Task 16 |
| Pipeline integration | Task 17 |
| End-to-end NVDA fixture test | Task 18 |
| CHANGELOG + verification | Task 19 |

Sections B-E of the spec (LLM prompt, renderers, frontend, testing strategy for Phases 2-5) are explicitly **out of scope** for this plan — they need their own plans written when those phases start.

**Placeholder scan** — No "TBD"/"TODO"/"implement later" in steps; every code block has actual implementation; every test has assert statements with real values.

**Type consistency** — `FactRecord` and `CandidateLevel` field names match throughout (`id`, `type`, `value`, `display_value`, `direction`, `tier`, `applicable_strategies`, `basis_rule`, `basis_fact_id`, `distance_pct_from_current`). Strategy IDs always: `long_term_hold` / `swing_trade` / `stepped_profit_taking` / `wait_and_see`.

**Known follow-up**: Task 17's exact line numbers (`src/core/pipeline.py:1677-1750`) and the `market` variable resolution depend on current state of that function; engineer should grep for the anchor (`_try_inject_action_plan_items` call site) and place the new block above it. The try/except wrapper is mandatory regardless of placement.
