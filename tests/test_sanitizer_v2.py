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


def test_check6_autofill_evidence_refs_when_less_than_two():
    """Per spec: if evidence_refs has <2 entries, auto-fill from
    candidate.basis_fact_id + a default committee anchor."""
    facts = [
        FactRecord(id="technical.current_price", type="technical", label="现价",
                   value=223.47, display_value="$223.47"),
        FactRecord(id="committee.pm_verdict", type="committee", label="PM",
                   value="hold", display_value="Hold"),
    ]
    bundle = FactBundle(
        as_of="x", market="us", stock_code="NVDA", facts=facts,
        candidates=[_candidate("candidate.exit.1", "take_profit", 226.13,
                                ["swing_trade"],
                                basis_fact_id="technical.resistance")],
    )
    # Item has 0 evidence_refs
    items = [{"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
              "direction": "take_profit", "priority": 1, "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert len(out) == 1
    refs = out[0]["evidence_refs"]
    assert "technical.resistance" in refs  # basis fact
    assert len(refs) >= 2


def test_check6_keeps_valid_evidence_refs():
    facts = [
        FactRecord(id="technical.resistance", type="technical", label="阻力",
                   value=226.13, display_value="$226.13"),
        FactRecord(id="committee.pm_verdict", type="committee", label="PM",
                   value="hold", display_value="Hold"),
        FactRecord(id="intel.risk_alert.0", type="intel", label="风险",
                   value="RSI 71.1", display_value="RSI 71.1"),
    ]
    bundle = FactBundle(
        as_of="x", market="us", stock_code="NVDA", facts=facts,
        candidates=[_candidate("candidate.exit.1", "take_profit", 226.13,
                                ["swing_trade"])],
    )
    items = [{"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
              "direction": "take_profit", "priority": 1,
              "evidence_refs": ["technical.resistance", "committee.pm_verdict",
                                 "intel.risk_alert.0"],
              "tier": "primary"}]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert out[0]["evidence_refs"] == [
        "technical.resistance", "committee.pm_verdict", "intel.risk_alert.0",
    ]


def test_check7_discipline_anchor_capped_to_one():
    bundle = _bundle([
        _candidate("candidate.disc.1", "take_profit", 230.0, ["stepped_profit_taking"],
                   tier="discipline_anchor"),
        _candidate("candidate.disc.2", "take_profit", 240.0, ["stepped_profit_taking"],
                   tier="discipline_anchor"),
        _candidate("candidate.primary", "take_profit", 226.0, ["stepped_profit_taking"],
                   tier="primary"),
    ])
    items = [
        {"candidate_id": "candidate.disc.1", "trigger_price": 230.0,
         "direction": "take_profit", "priority": 1,
         "evidence_refs": ["a", "b"], "tier": "discipline_anchor"},
        {"candidate_id": "candidate.disc.2", "trigger_price": 240.0,
         "direction": "take_profit", "priority": 2,
         "evidence_refs": ["a", "b"], "tier": "discipline_anchor"},
        {"candidate_id": "candidate.primary", "trigger_price": 226.0,
         "direction": "take_profit", "priority": 3,
         "evidence_refs": ["a", "b"], "tier": "primary"},
    ]
    out = sanitize_with_candidates(items, bundle, strategy="stepped_profit_taking",
                                    current_price=223.47)
    anchors = [it for it in out if it.get("tier") == "discipline_anchor"]
    assert len(anchors) == 1


def test_check8_dedup_same_candidate_id_keeps_highest_priority():
    bundle = _bundle([_candidate("candidate.exit.1", "take_profit", 226.13,
                                  ["swing_trade"])])
    items = [
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 5,
         "evidence_refs": ["a", "b"], "tier": "primary"},
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 1,  # higher priority (lower number)
         "evidence_refs": ["a", "b"], "tier": "primary"},
    ]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    assert len(out) == 1


def test_check9_priority_renumbered_1_to_N():
    bundle = _bundle([
        _candidate("candidate.exit.1", "take_profit", 226.13, ["swing_trade"]),
        _candidate("candidate.exit.2", "take_profit", 230.0, ["swing_trade"]),
    ])
    items = [
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 7,
         "evidence_refs": ["a", "b"], "tier": "primary"},
        {"candidate_id": "candidate.exit.2", "trigger_price": 230.0,
         "direction": "take_profit", "priority": 19,
         "evidence_refs": ["a", "b"], "tier": "primary"},
    ]
    out = sanitize_with_candidates(items, bundle, strategy="swing_trade",
                                    current_price=223.47)
    priorities = sorted(it["priority"] for it in out)
    assert priorities == [1, 2]
