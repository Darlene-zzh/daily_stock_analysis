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


# ---- Spec Section A rules 21-23 (previously deferred) ----

def test_support_breakdown_stop_when_support_below_current():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.support", 210.0),
    ]
    cands = compute_candidates(facts)
    stops = [c for c in cands if c.basis_rule == "support_breakdown"]
    assert len(stops) == 1
    s = stops[0]
    assert s.price == 210.0
    assert s.direction == "stop_loss"
    assert s.tier == "primary"
    assert s.applicable_strategies == ["swing_trade"]


def test_support_breakdown_skipped_when_support_at_or_above_current():
    facts = [
        _fact("technical.current_price", 200.0),
        _fact("technical.support", 222.0),
    ]
    cands = compute_candidates(facts)
    assert not any(c.basis_rule == "support_breakdown" for c in cands)


def test_ma20_pullback_entry_when_at_or_below_current():
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.ma20", 213.4),
    ]
    cands = compute_candidates(facts)
    entries = [c for c in cands if c.basis_rule == "ma20_pullback"]
    assert len(entries) == 1
    e = entries[0]
    assert e.price == 213.4
    assert e.direction == "entry"
    assert e.tier == "primary"
    assert "swing_trade" in e.applicable_strategies
    assert "stepped_profit_taking" in e.applicable_strategies
    assert "long_term_hold" in e.applicable_strategies


def test_ma20_pullback_skipped_when_above_current():
    facts = [
        _fact("technical.current_price", 200.0),
        _fact("technical.ma20", 222.0),
    ]
    cands = compute_candidates(facts)
    assert not any(c.basis_rule == "ma20_pullback" for c in cands)


def test_breakout_retest_entry_when_swing_high_below_current():
    # Price has broken above the prior 20d swing high; that level now acts as
    # support on a retest -> entry candidate.
    facts = [
        _fact("technical.current_price", 223.47),
        _fact("technical.swing_high_20d", 215.0),
    ]
    cands = compute_candidates(facts)
    entries = [c for c in cands if c.basis_rule == "breakout_retest"]
    assert len(entries) == 1
    e = entries[0]
    assert e.price == 215.0
    assert e.direction == "entry"
    assert e.tier == "primary"
    assert "swing_trade" in e.applicable_strategies
    assert "stepped_profit_taking" in e.applicable_strategies


def test_breakout_retest_skipped_when_swing_high_above_current():
    # swing_high above current is a take_profit target (prev_swing_high), not a
    # breakout retest entry.
    facts = [
        _fact("technical.current_price", 200.0),
        _fact("technical.swing_high_20d", 215.0),
    ]
    cands = compute_candidates(facts)
    assert not any(c.basis_rule == "breakout_retest" for c in cands)
