"""Real NVDA dashboard (id=13 captured fixture) → FactBundle integration test."""
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

    cathie = next(f for f in bundle.facts if f.id == "committee.master.cathie_wood")
    assert cathie.extra.get("is_dissent") is True

    primary_exits = [c for c in bundle.candidates
                     if c.tier == "primary" and c.direction == "take_profit"]
    primary_stops = [c for c in bundle.candidates
                     if c.tier == "primary" and c.direction == "stop_loss"]
    assert len(primary_exits) >= 2  # resistance_touch + R-multiple at minimum
    assert len(primary_stops) >= 1  # ma20_breakdown

    # cost_plus_5pct/12pct should NOT appear because already triggered
    # cost=196.18 → +5%=205.99 < current 223.47
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
