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
    for required in [
        "technical.current_price", "technical.ma10", "technical.rsi_12",
        "quant.qlib_score", "quant.qlib_rank",
        "committee.pm_verdict", "committee.master.warren_buffett",
        "intel.risk_alert.0",
        "portfolio.holding_shares", "portfolio.avg_cost",
    ]:
        assert required in fact_ids, f"missing {required}"
    assert not any(f.type in ("flow", "chip") for f in bundle.facts)
    assert len(bundle.candidates) > 0
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
    assert bundle.facts
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
