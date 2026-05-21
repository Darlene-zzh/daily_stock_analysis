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
        _fact("technical.ma10", 222.02),
    ]
    cands = compute_candidates(facts)
    entries = [c for c in cands if c.basis_rule == "ma10_pullback"]
    assert len(entries) == 1
    assert entries[0].direction == "entry"


def test_ma10_pullback_skipped_when_above_current():
    facts = [
        _fact("technical.current_price", 200.0),
        _fact("technical.ma10", 222.02),
    ]
    cands = compute_candidates(facts)
    assert not any(c.basis_rule == "ma10_pullback" for c in cands)


def test_no_current_price_returns_empty():
    facts = [_fact("technical.resistance", 226.13)]
    assert compute_candidates(facts) == []
