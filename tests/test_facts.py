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
