from src.analysis.facts import FactBundle, FactRecord, CandidateLevel
from src.analysis.sanitizer_v2 import sanitize_with_candidates


def _candidate(id_, direction, price, strategies, tier="primary", distance=1.0,
               basis_fact_id="technical.resistance", basis_rule="resistance_touch"):
    return CandidateLevel(
        id=id_, type="candidate", label=basis_rule, value=price,
        display_value=f"${price:.2f}", direction=direction, price=price,
        basis_fact_id=basis_fact_id, basis_rule=basis_rule,
        applicable_strategies=strategies, tier=tier,
        distance_pct_from_current=distance,
    )


def _bundle(candidates, current_price=223.47):
    facts = [FactRecord(
        id="technical.current_price", type="technical", label="现价",
        value=current_price, display_value=f"${current_price:.2f}",
    )]
    return FactBundle(as_of="x", market="us", stock_code="NVDA",
                     facts=facts, candidates=candidates)


def test_check1_drop_item_with_unknown_candidate_id():
    bundle = _bundle([_candidate("candidate.exit.1", "take_profit", 226.13,
                                  ["swing_trade"])])
    items = [
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 1, "evidence_refs":
         ["technical.resistance", "committee.pm_verdict"], "tier": "primary"},
        {"candidate_id": "candidate.exit.FAKE", "trigger_price": 999.99,
         "direction": "take_profit", "priority": 2, "evidence_refs":
         ["technical.resistance", "committee.pm_verdict"], "tier": "primary"},
    ]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    ids = [it["candidate_id"] for it in out]
    assert "candidate.exit.1" in ids
    assert "candidate.exit.FAKE" not in ids


def test_check2_override_trigger_price_to_match_candidate():
    """LLM might emit trigger_price 226.50 but candidate is 226.13. Sanitizer
    overrides to 226.13 (and logs the discrepancy)."""
    bundle = _bundle([_candidate("candidate.exit.1", "take_profit", 226.13,
                                  ["swing_trade"])])
    items = [{
        "candidate_id": "candidate.exit.1", "trigger_price": 226.50,  # ← wrong
        "direction": "take_profit", "priority": 1,
        "evidence_refs": ["technical.resistance", "committee.pm_verdict"],
        "tier": "primary",
    }]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert len(out) == 1
    assert out[0]["trigger_price"] == 226.13


def test_check1_drop_when_candidate_id_missing_entirely():
    bundle = _bundle([_candidate("candidate.exit.1", "take_profit", 226.13,
                                  ["swing_trade"])])
    items = [{"trigger_price": 226.13, "direction": "take_profit", "priority": 1}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert out == []


def test_check3_drop_item_when_strategy_not_in_applicable_strategies():
    bundle = _bundle([
        _candidate("candidate.exit.1", "take_profit", 226.13,
                   ["swing_trade", "stepped_profit_taking"]),
        _candidate("candidate.exit.lth", "take_profit", 280.0,
                   ["long_term_hold"]),  # wrong strategy
    ])
    items = [
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 1,
         "evidence_refs": ["technical.resistance", "committee.pm_verdict"],
         "tier": "primary"},
        {"candidate_id": "candidate.exit.lth", "trigger_price": 280.0,
         "direction": "take_profit", "priority": 2,
         "evidence_refs": ["technical.resistance", "committee.pm_verdict"],
         "tier": "primary"},
    ]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    ids = [it["candidate_id"] for it in out]
    assert "candidate.exit.1" in ids
    assert "candidate.exit.lth" not in ids


def test_check4_drop_filtered_tier_candidate():
    bundle = _bundle([
        _candidate("candidate.exit.stale", "take_profit", 100.0,
                   ["swing_trade"], tier="filtered"),
    ])
    items = [{"candidate_id": "candidate.exit.stale", "trigger_price": 100.0,
              "direction": "take_profit", "priority": 1,
              "evidence_refs": ["a", "b"], "tier": "filtered"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert out == []


def test_check5_drop_take_profit_below_current_price():
    bundle = _bundle(
        [_candidate("candidate.exit.bad", "take_profit", 220.0,
                    ["swing_trade"])],
        current_price=223.47,
    )
    items = [{"candidate_id": "candidate.exit.bad", "trigger_price": 220.0,
              "direction": "take_profit", "priority": 1,
              "evidence_refs": ["a", "b"], "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert out == []


def test_check5_drop_stop_loss_above_current_price():
    bundle = _bundle(
        [_candidate("candidate.stop.bad", "stop_loss", 230.0,
                    ["swing_trade"])],
        current_price=223.47,
    )
    items = [{"candidate_id": "candidate.stop.bad", "trigger_price": 230.0,
              "direction": "stop_loss", "priority": 1,
              "evidence_refs": ["a", "b"], "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert out == []


def test_check5_keep_take_profit_above_current():
    bundle = _bundle(
        [_candidate("candidate.exit.ok", "take_profit", 226.0,
                    ["swing_trade"])],
        current_price=223.47,
    )
    items = [{"candidate_id": "candidate.exit.ok", "trigger_price": 226.0,
              "direction": "take_profit", "priority": 1,
              "evidence_refs": ["a", "b"], "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert len(out) == 1


def test_check5_no_current_price_skips_direction_check():
    """When current_price unknown, can't validate direction logic — pass-through."""
    bundle = _bundle(
        [_candidate("candidate.exit.x", "take_profit", 100.0, ["swing_trade"])],
        current_price=223.47,
    )
    items = [{"candidate_id": "candidate.exit.x", "trigger_price": 100.0,
              "direction": "take_profit", "priority": 1,
              "evidence_refs": ["a", "b"], "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=None)
    # No current_price -> direction check skipped, item survives
    assert len(out) == 1
