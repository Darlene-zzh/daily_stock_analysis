from src.analysis.facts import FactBundle, FactRecord, CandidateLevel
from src.analysis.synthesizer import synthesize_from_candidates


def _candidate(id_, direction, price, strategies, tier="primary", distance=1.0,
               basis_fact_id="technical.resistance", basis_rule="resistance_touch"):
    return CandidateLevel(
        id=id_, type="candidate", label=basis_rule, value=price,
        display_value=f"${price:.2f}", direction=direction, price=price,
        basis_fact_id=basis_fact_id, basis_rule=basis_rule,
        applicable_strategies=strategies, tier=tier,
        distance_pct_from_current=distance,
    )


def _bundle(candidates):
    facts = [
        FactRecord(id="committee.pm_verdict", type="committee", label="PM",
                   value="hold", display_value="Hold"),
        FactRecord(id="technical.current_price", type="technical", label="现价",
                   value=223.47, display_value="$223.47"),
    ]
    return FactBundle(as_of="x", market="us", stock_code="NVDA",
                     facts=facts, candidates=candidates)


def test_synthesize_swing_trade_picks_primary_exits_and_one_stop():
    bundle = _bundle([
        _candidate("candidate.exit.1", "take_profit", 226.13, ["swing_trade"],
                   distance=1.2),
        _candidate("candidate.exit.2", "take_profit", 230.0, ["swing_trade"],
                   distance=2.9),
        _candidate("candidate.stop.1", "stop_loss", 213.39, ["swing_trade"],
                   distance=-4.5),
    ])
    out = synthesize_from_candidates(
        bundle.candidates, strategy="swing_trade", facts=bundle.facts,
    )
    assert len(out) >= 2
    assert all(it["provenance"] == "synthesized" for it in out)
    candidate_ids = [it["candidate_id"] for it in out]
    assert "candidate.exit.1" in candidate_ids
    assert "candidate.stop.1" in candidate_ids
    # Each item has the 5 new fields
    for it in out:
        assert "evidence_refs" in it and len(it["evidence_refs"]) >= 2
        assert "narrative" in it
        assert it["tier"] in ("primary", "discipline_anchor")
        assert "trigger_price" in it


def test_synthesize_skips_filtered_candidates():
    bundle = _bundle([
        _candidate("candidate.exit.ok", "take_profit", 226.13, ["swing_trade"]),
        _candidate("candidate.exit.bad", "take_profit", 100.0, ["swing_trade"],
                   tier="filtered"),
    ])
    out = synthesize_from_candidates(
        bundle.candidates, strategy="swing_trade", facts=bundle.facts,
    )
    cids = [it["candidate_id"] for it in out]
    assert "candidate.exit.ok" in cids
    assert "candidate.exit.bad" not in cids


def test_synthesize_only_applicable_strategy():
    bundle = _bundle([
        _candidate("candidate.exit.swing", "take_profit", 226.13, ["swing_trade"]),
        _candidate("candidate.exit.lth", "take_profit", 280.0, ["long_term_hold"]),
    ])
    out = synthesize_from_candidates(
        bundle.candidates, strategy="swing_trade", facts=bundle.facts,
    )
    cids = [it["candidate_id"] for it in out]
    assert "candidate.exit.swing" in cids
    assert "candidate.exit.lth" not in cids


def test_synthesize_fallback_to_discipline_anchor_when_no_primary():
    bundle = _bundle([
        _candidate("candidate.disc.1", "take_profit", 230.0, ["stepped_profit_taking"],
                   tier="discipline_anchor"),
    ])
    out = synthesize_from_candidates(
        bundle.candidates, strategy="stepped_profit_taking", facts=bundle.facts,
    )
    assert len(out) == 1
    assert out[0]["tier"] == "discipline_anchor"


def test_synthesize_empty_pool_returns_empty():
    out = synthesize_from_candidates([], strategy="swing_trade", facts=[])
    assert out == []
