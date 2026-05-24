from src.analysis.extractors.committee import extract_committee_facts


def test_extract_committee_facts_full_bundle():
    committee = {
        "pm_verdict": "hold", "pm_score": 5.8,
        "pm_rationale": "尽管技术面...", "pm_dissents": ["cathie_wood"],
        "risk": {"severity": "soft", "suggested_position_pct": 0.3,
                 "red_flags": ["RSI 71.1 超买", "PE/PB 缺失"], "veto": False},
        "masters": [
            {"persona": "warren_buffett", "verdict": "hold", "score": 4.0,
             "headline": "技术指标超买...", "key_evidence": ["RSI 71.1"]},
            {"persona": "cathie_wood", "verdict": "strong_buy", "score": 9.2,
             "headline": "AI 革命核心", "key_evidence": []},
        ],
    }
    facts = extract_committee_facts(committee, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "committee.pm_verdict" in ids
    assert "committee.pm_score" in ids
    assert "committee.risk.suggested_position_pct" in ids
    assert "committee.risk.severity" in ids
    assert "committee.master.warren_buffett" in ids
    assert "committee.master.cathie_wood" in ids

    cathie = next(f for f in facts if f.id == "committee.master.cathie_wood")
    assert cathie.extra["is_dissent"] is True
    assert "异议" in cathie.display_value

    risk_pct = next(f for f in facts if f.id == "committee.risk.suggested_position_pct")
    assert risk_pct.display_value == "≤ 30%"
    assert risk_pct.extra["severity"] == "soft"


def test_extract_committee_facts_empty_committee():
    assert extract_committee_facts(None, as_of="2026-05-21T00:43:00Z") == []
    assert extract_committee_facts({}, as_of="2026-05-21T00:43:00Z") == []


def test_extract_committee_facts_missing_risk():
    committee = {"pm_verdict": "hold", "pm_score": 5.0, "masters": []}
    facts = extract_committee_facts(committee, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "committee.pm_verdict" in ids
    assert "committee.risk.suggested_position_pct" not in ids
