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


def test_r_multiple_2r_target():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.ma20", 213.4),
    ]
    cands = compute_candidates(facts)
    r2 = [c for c in cands if c.basis_rule == "r_multiple_2r"]
    assert len(r2) == 1
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


def test_psychological_round_next_above():
    facts = [_fact("technical.current_price", 223.47)]
    cands = compute_candidates(facts)
    rounds = [c for c in cands if c.basis_rule == "psychological_round"]
    assert len(rounds) >= 1
    assert any(c.price == 230.0 for c in rounds)
    assert all(c.tier == "secondary" for c in rounds)


def test_cost_plus_5pct_anchor_when_held_and_not_triggered():
    facts = [
        _fact("technical.current_price", 200.0),
        _fact("portfolio.avg_cost", 196.18, type_="portfolio"),
    ]
    cands = compute_candidates(facts)
    anchors = [c for c in cands if c.basis_rule == "cost_plus_5pct"]
    assert len(anchors) == 1
    assert anchors[0].tier == "discipline_anchor"
    assert abs(anchors[0].price - 196.18 * 1.05) < 0.01


def test_cost_plus_5pct_skipped_when_already_triggered():
    facts = [
        _fact("technical.current_price", 223.47),
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
