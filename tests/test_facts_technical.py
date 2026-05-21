from src.analysis.extractors.technical import extract_technical_facts


def test_extract_technical_facts_from_data_perspective():
    data_perspective = {
        "price_position": {
            "current_price": 223.47,
            "ma5": 225.49, "ma10": 222.02, "ma20": 213.4,
            "support_level": 222.02, "resistance_level": 226.13,
            "bias_ma5": -0.9,
        },
        "trend_status": {"trend_score": 75, "ma_alignment": "bullish", "is_bullish": True},
        "volume_analysis": {"volume_ratio": "N/A", "volume_status": "量能正常"},
    }
    facts = extract_technical_facts(data_perspective, rsi_12=71.1, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "technical.current_price" in ids
    assert "technical.ma10" in ids
    assert "technical.ma20" in ids
    assert "technical.resistance" in ids
    assert "technical.rsi_12" in ids
    assert "technical.trend_score" in ids
    current = next(f for f in facts if f.id == "technical.current_price")
    assert current.value == 223.47
    assert current.display_value == "$223.47"
    rsi = next(f for f in facts if f.id == "technical.rsi_12")
    assert rsi.extra.get("zone") == "超买"


def test_extract_technical_missing_data_graceful():
    facts = extract_technical_facts({}, rsi_12=None, as_of="2026-05-21T00:43:00Z")
    assert facts == []  # nothing to extract, no crash


def test_extract_technical_volume_ratio_na_skipped():
    dp = {"volume_analysis": {"volume_ratio": "N/A"}}
    facts = extract_technical_facts(dp, rsi_12=None, as_of="2026-05-21T00:43:00Z")
    assert "technical.volume_ratio" not in {f.id for f in facts}
