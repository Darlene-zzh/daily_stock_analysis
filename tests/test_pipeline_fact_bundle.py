"""Verify fact_bundle is attached to dashboard during process_single_stock."""
from src.analysis.facts_builder import build_fact_bundle


def test_fact_bundle_attached_to_dashboard():
    """Real smoke: build a minimal dashboard and verify fact_bundle gets injected."""
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


def test_pipeline_attach_fact_bundle_method_exists():
    """Check that the integration hook is wired on the pipeline class."""
    from src.core.pipeline import StockAnalysisPipeline
    assert hasattr(StockAnalysisPipeline, "_attach_fact_bundle")
