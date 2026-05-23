import pytest

from src.notification import _render_evidence_footnotes


def _bundle():
    return {
        "facts": [
            {"id": "technical.resistance", "type": "technical",
             "label": "阻力位", "value": 226.13, "display_value": "$226.13",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {"role": "阻力"}},
            {"id": "technical.rsi_12", "type": "technical",
             "label": "RSI(12)", "value": 71.1, "display_value": "71.1",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {"zone": "超买"}},
            {"id": "committee.pm_verdict", "type": "committee",
             "label": "PM 裁决", "value": "hold", "display_value": "Hold",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {}},
        ],
        "candidates": [],
    }


def test_renders_numbered_footnotes_in_input_order():
    refs = ["technical.resistance", "technical.rsi_12", "committee.pm_verdict"]
    lines = _render_evidence_footnotes(refs, _bundle())
    assert lines[0] == "**证据脚注**"
    assert lines[1] == "¹ `[technical.resistance]` 阻力位 = $226.13 (阻力)"
    assert lines[2] == "² `[technical.rsi_12]` RSI(12) = 71.1 (超买)"
    assert lines[3] == "³ `[committee.pm_verdict]` PM 裁决 = Hold"


def test_dedup_preserves_first_occurrence():
    refs = ["technical.rsi_12", "technical.resistance", "technical.rsi_12"]
    lines = _render_evidence_footnotes(refs, _bundle())
    assert lines[0] == "**证据脚注**"
    assert lines[1] == "¹ `[technical.rsi_12]` RSI(12) = 71.1 (超买)"
    assert lines[2] == "² `[technical.resistance]` 阻力位 = $226.13 (阻力)"
    assert len(lines) == 3


def test_missing_fact_id_falls_back_to_raw_id():
    refs = ["technical.resistance", "missing.fact.xyz"]
    lines = _render_evidence_footnotes(refs, _bundle())
    assert "² `[missing.fact.xyz]` (引用未在 FactBundle 中找到)" in lines


def test_empty_refs_returns_empty_list():
    assert _render_evidence_footnotes([], _bundle()) == []


def test_no_bundle_returns_empty_list():
    assert _render_evidence_footnotes(["technical.resistance"], None) == []
