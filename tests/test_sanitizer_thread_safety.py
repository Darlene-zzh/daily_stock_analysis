"""Regression guard for [[repo-phase-2-sanitizer-race]]:

The Phase 2 wiring stashed `_fact_bundle_for_sanitize` and
`_current_price_for_sanitize` on the shared GeminiAnalyzer instance. Under the
pipeline's ThreadPoolExecutor, one stock's _try_inject_action_plan_items LLM
call could be interrupted by another stock's stash write, causing the first
stock's sanitizer to read the wrong bundle.

Discovery: smoke 2026-05-23 showed NVDA sanitizer overriding candidate price
to $414.95 (MSFT's value, MSFT was attached 1s before). DB inspection proved
NVDA's actual bundle had $214.75 (correct). Damage masked in NVDA's case by
wait_and_see strategy dropping the item — but swing_trade / long_term_hold
stocks would have shown user-visible cross-stock corrupted trigger_prices.

Fix: thread fact_bundle and current_price through _sanitize_action_plan_items
as explicit kwargs; remove instance-attribute stash entirely.
"""
import json
from unittest.mock import MagicMock

from src.analyzer import GeminiAnalyzer, AnalysisResult


def _bundle_with_entry(stock_code: str, entry_price: float):
    """Build a fact_bundle dict with one candidate.entry.1 at entry_price."""
    return {
        "as_of": "x", "market": "us", "stock_code": stock_code,
        "facts": [
            {"id": "technical.current_price", "type": "technical", "label": "现价",
             "value": entry_price, "display_value": f"${entry_price:.2f}", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {}},
            {"id": "technical.ma10", "type": "technical", "label": "MA10",
             "value": entry_price, "display_value": f"${entry_price:.2f}", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {}},
            {"id": "committee.pm_verdict", "type": "committee", "label": "PM",
             "value": "buy", "display_value": "Buy", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {}},
        ],
        "candidates": [
            {"id": "candidate.entry.1", "type": "candidate", "label": "MA10 pullback",
             "value": entry_price, "display_value": f"${entry_price:.2f}",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {},
             "direction": "entry", "price": entry_price,
             "basis_fact_id": "technical.ma10",
             "basis_rule": "ma10_pullback",
             "applicable_strategies": ["swing_trade", "stepped_profit_taking"],
             "tier": "primary", "distance_pct_from_current": 0.0},
        ],
    }


def _result_for(code: str, entry_price: float):
    r = AnalysisResult(
        code=code, name=code, sentiment_score=70,
        trend_prediction="up", operation_advice="buy",
        confidence_level="medium", analysis_summary="ok",
        risk_warning="ok", success=True, model_used="test",
    )
    r.dashboard = {
        "core_conclusion": {},
        "data_perspective": {"price_position": {"current_price": entry_price}},
        "intelligence": {},
        "fact_bundle": _bundle_with_entry(code, entry_price),
    }
    r.portfolio_match = None
    return r


def test_sanitize_accepts_fact_bundle_and_current_price_kwargs():
    """The fixed signature must accept these explicit kwargs."""
    import inspect
    sig = inspect.signature(GeminiAnalyzer._sanitize_action_plan_items)
    assert "fact_bundle" in sig.parameters, (
        "_sanitize_action_plan_items must accept fact_bundle kwarg explicitly "
        "(do NOT use instance-attribute stash — [[repo-phase-2-sanitizer-race]])"
    )
    assert "current_price" in sig.parameters, (
        "_sanitize_action_plan_items must accept current_price kwarg explicitly"
    )


def test_no_instance_attribute_stash_after_inject():
    """After _try_inject_action_plan_items returns, the analyzer instance must
    NOT carry per-call stash attributes — those are racy across threads."""
    nvda_bundle = _bundle_with_entry("NVDA", 214.75)
    msft_bundle = _bundle_with_entry("MSFT", 414.95)
    agent = GeminiAnalyzer.__new__(GeminiAnalyzer)
    # Mock the LLM to return a single item that uses candidate.entry.1
    agent.generate_text = MagicMock(return_value=json.dumps({
        "recommended_strategy": "swing_trade",
        "strategy_thesis": "thesis",
        "strategy_choices": [],
        "action_plan_items": [{
            "candidate_id": "candidate.entry.1",
            "trigger_price": 214.75,
            "direction": "entry",
            "priority": 1,
            "evidence_refs": ["technical.ma10", "committee.pm_verdict"],
            "tier": "primary",
        }],
    }))
    agent._sanitize_strategy_choices = lambda x, **k: x
    agent._recompute_position_outcome_summary = lambda *a, **k: None

    GeminiAnalyzer._try_inject_action_plan_items(
        agent, _result_for("NVDA", 214.75), "NVDA", portfolio_context_block=None,
    )
    # After the call, no per-call stash should remain on the instance
    assert getattr(agent, "_fact_bundle_for_sanitize", None) is None, (
        "_fact_bundle_for_sanitize must not persist on the analyzer instance — "
        "it would leak across threads and corrupt the next stock's sanitizer."
    )
    assert getattr(agent, "_current_price_for_sanitize", None) is None


def test_explicit_fact_bundle_kwarg_wins_over_any_instance_stash():
    """Deterministic race-resistance: simulate the worst case where a stale
    bundle from another thread is sitting on `self._fact_bundle_for_sanitize`
    while we sanitize. The explicit `fact_bundle` kwarg MUST be what's used.

    Pre-fix: signature does not accept fact_bundle kwarg → TypeError.
    Post-fix: explicit kwarg overrides instance state → correct result.
    """
    agent = GeminiAnalyzer.__new__(GeminiAnalyzer)
    # Simulate a stale stash left by another thread mid-race
    agent._fact_bundle_for_sanitize = _bundle_with_entry("MSFT", 414.95)
    agent._current_price_for_sanitize = 414.95

    nvda_bundle = _bundle_with_entry("NVDA", 214.75)
    nvda_items = [{
        "candidate_id": "candidate.entry.1",
        "trigger_price": 214.75,
        "direction": "entry",
        "priority": 1,
        "evidence_refs": ["technical.ma10", "committee.pm_verdict"],
        "tier": "primary",
    }]
    result = GeminiAnalyzer._sanitize_action_plan_items(
        agent, nvda_items, portfolio_context_block=None, code="NVDA",
        strategy="swing_trade",
        fact_bundle=nvda_bundle,
        current_price=214.75,
    )
    assert len(result) == 1, "NVDA's item should survive against NVDA's bundle"
    assert result[0]["trigger_price"] == 214.75, (
        f"NVDA's trigger_price was corrupted to {result[0]['trigger_price']} — "
        "explicit fact_bundle kwarg did not override stale instance stash. "
        "See [[repo-phase-2-sanitizer-race]]."
    )
