"""Regression guards for PR #10 self-review finding (Haiku score 92).

Before the fix, `_attach_fact_bundle` in `src/core/pipeline.py` read
`getattr(result, "portfolio_context", None)`, but nothing in the codebase ever
wrote `result.portfolio_context`. The portfolio extractor at
`src/analysis/extractors/portfolio.py` short-circuited on `None` input, so
the FactBundle's portfolio.* facts were permanently dead code — even when
the user wired a `portfolio_account_id` to the analysis API.

The fix wires the structured portfolio context dict from
`src/services/analysis_service.py` → `StockAnalysisPipeline.__init__` →
`self.portfolio_context` → `_attach_fact_bundle`. These tests pin the fix:

1. ``to_fact_bundle_dict()`` produces the dict shape the extractor expects
   (NOT the same as ``to_dict()`` — different field names).
2. ``build_fact_bundle`` with that dict emits portfolio.* facts.
3. ``StockAnalysisPipeline`` accepts ``portfolio_context`` kwarg and stores
   it as ``self.portfolio_context`` for ``_attach_fact_bundle`` to read.
"""
from __future__ import annotations

from src.analysis.facts_builder import build_fact_bundle
from src.services.portfolio_context_service import PortfolioContextResult


# ---------------------------------------------------------------------------
# Translator: PortfolioContextResult → extractor-shape dict
# ---------------------------------------------------------------------------

def test_to_fact_bundle_dict_held_position_has_extractor_field_names():
    """The extractor at src/analysis/extractors/portfolio.py reads
    `match_state` / `holding_shares` / `unrealized_pnl_amount` / `currency`.
    These names differ from PortfolioContextResult's native field names
    (`is_held` / `quantity` / `unrealized_pnl_base` / `position_currency`)
    — the translator must produce the extractor-expected keys.
    """
    ctx = PortfolioContextResult(
        account_id=1,
        account_name="Test Account",
        base_currency="USD",
        symbol="NVDA",
        is_held=True,
        quantity=100.0,
        avg_cost=150.5,
        position_currency="USD",
        unrealized_pnl_base=2450.0,
        unrealized_pnl_pct=16.28,
        first_buy_date="2025-01-15",
        total_equity=50000.0,
    )
    d = ctx.to_fact_bundle_dict()

    assert d["match_state"] == "held"
    assert d["holding_shares"] == 100.0
    assert d["avg_cost"] == 150.5
    assert d["currency"] == "USD"
    assert d["unrealized_pnl_amount"] == 2450.0
    assert d["unrealized_pnl_pct"] == 16.28
    assert d["base_currency"] == "USD"
    assert d["total_equity"] == 50000.0
    assert d["first_buy_date"] == "2025-01-15"


def test_to_fact_bundle_dict_not_held_returns_match_state_only_position_fields_none():
    """When the user has never traded this symbol on the account, the
    extractor only emits a single `portfolio.position_match=not_held` fact.
    The translator must mark the position-specific fields as None so the
    extractor's `if portfolio_context.get("holding_shares") is not None`
    guards correctly skip them."""
    ctx = PortfolioContextResult(
        account_id=1,
        account_name="Test Account",
        base_currency="USD",
        symbol="NVDA",
        is_held=False,
        total_equity=50000.0,
    )
    d = ctx.to_fact_bundle_dict()

    assert d["match_state"] == "not_held"
    assert d["holding_shares"] is None
    assert d["avg_cost"] is None
    assert d["unrealized_pnl_amount"] is None
    assert d["unrealized_pnl_pct"] is None
    # Account-level fields are still populated
    assert d["base_currency"] == "USD"
    assert d["total_equity"] == 50000.0


# ---------------------------------------------------------------------------
# End-to-end: extractor produces portfolio.* facts when wired
# ---------------------------------------------------------------------------

def test_build_fact_bundle_emits_portfolio_facts_when_context_supplied():
    """Smoke: feed `build_fact_bundle` a `to_fact_bundle_dict()` result and
    verify portfolio.* fact ids appear in the bundle. This is the test that
    would have caught the dead-code path before the fix."""
    ctx = PortfolioContextResult(
        account_id=1, account_name="Test", base_currency="USD",
        symbol="NVDA", is_held=True,
        quantity=100.0, avg_cost=150.5, position_currency="USD",
        unrealized_pnl_base=2450.0, unrealized_pnl_pct=16.28,
        first_buy_date="2025-01-15", total_equity=50000.0,
    )
    dashboard = {
        "data_perspective": {"price_position": {"current_price": 175.0, "ma20": 170.0}},
        "intelligence": {},
        "committee": {"pm_verdict": "hold", "pm_score": 5.0, "masters": []},
    }
    bundle = build_fact_bundle(
        stock_code="NVDA", market="us",
        dashboard=dashboard,
        portfolio_context=ctx.to_fact_bundle_dict(),
        ohlc=None, rsi_12=None,
        qlib_predictions={}, qlib_ic={},
        qlib_week="", qlib_universe_size=0,
        as_of="2026-05-24T00:00:00Z",
    )

    fact_ids = {f.id for f in bundle.facts}
    assert "portfolio.position_match" in fact_ids
    assert "portfolio.holding_shares" in fact_ids
    assert "portfolio.avg_cost" in fact_ids
    assert "portfolio.unrealized_pnl_pct" in fact_ids


def test_build_fact_bundle_emits_no_portfolio_facts_when_context_is_none():
    """Backward compat: when no portfolio context is wired (most callers),
    the extractor must short-circuit and the bundle must contain zero
    portfolio.* facts. The fix must not break this default behavior."""
    dashboard = {
        "data_perspective": {"price_position": {"current_price": 175.0, "ma20": 170.0}},
        "intelligence": {},
        "committee": {"pm_verdict": "hold", "pm_score": 5.0, "masters": []},
    }
    bundle = build_fact_bundle(
        stock_code="NVDA", market="us",
        dashboard=dashboard, portfolio_context=None,
        ohlc=None, rsi_12=None,
        qlib_predictions={}, qlib_ic={},
        qlib_week="", qlib_universe_size=0,
        as_of="2026-05-24T00:00:00Z",
    )

    fact_ids = {f.id for f in bundle.facts}
    portfolio_ids = {fid for fid in fact_ids if fid.startswith("portfolio.")}
    assert portfolio_ids == set(), (
        f"Expected zero portfolio.* facts when context is None, got: {portfolio_ids}"
    )


# ---------------------------------------------------------------------------
# Pipeline plumbing: the new init kwarg lands on self.portfolio_context
# ---------------------------------------------------------------------------

def test_pipeline_init_accepts_portfolio_context_and_stashes_on_self():
    """Pipeline must accept the `portfolio_context` kwarg and expose it as
    `self.portfolio_context` so `_attach_fact_bundle` can read it. This
    closes the dead-code path the review identified."""
    from src.core.pipeline import StockAnalysisPipeline

    expected = {
        "match_state": "held",
        "holding_shares": 100.0,
        "avg_cost": 150.5,
        "currency": "USD",
    }
    pipeline = StockAnalysisPipeline(portfolio_context=expected)
    assert pipeline.portfolio_context == expected


def test_pipeline_init_default_portfolio_context_is_none():
    """Default value must be None so existing call sites (task_service,
    analyzer_service) — which don't pass the kwarg — keep working
    backward-compatibly. The extractor then short-circuits as before."""
    from src.core.pipeline import StockAnalysisPipeline

    pipeline = StockAnalysisPipeline()
    assert pipeline.portfolio_context is None
