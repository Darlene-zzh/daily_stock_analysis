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


def test_compute_atr_14_from_ohlc():
    from src.analysis.extractors.technical import compute_atr_14
    ohlc = [
        {"high": 100, "low": 95, "close": 98},
        {"high": 102, "low": 97, "close": 100},
    ]
    for i in range(13):
        ohlc.append({"high": 105 + i, "low": 100 + i, "close": 103 + i})
    atr = compute_atr_14(ohlc)
    assert atr is not None
    assert atr > 0
    assert atr < 20


def test_compute_atr_14_insufficient_data_returns_none():
    from src.analysis.extractors.technical import compute_atr_14
    short_ohlc = [{"high": 100, "low": 95, "close": 98}]
    assert compute_atr_14(short_ohlc) is None


def test_extract_technical_with_ohlc_includes_atr():
    dp = {"price_position": {"current_price": 100.0}}
    ohlc = [{"high": 100 + i, "low": 95 + i, "close": 98 + i} for i in range(20)]
    facts = extract_technical_facts(dp, rsi_12=None, as_of="2026-05-21T00:43:00Z", ohlc=ohlc)
    atr_facts = [f for f in facts if f.id == "technical.atr_14"]
    assert len(atr_facts) == 1
    assert atr_facts[0].value > 0


def test_extract_swing_high_low_from_ohlc():
    dp = {"price_position": {"current_price": 100.0}}
    ohlc = [
        {"high": 95 + i, "low": 90 + i, "close": 93 + i, "open": 92 + i}
        for i in range(20)
    ]
    ohlc[5]["high"] = 130.0
    ohlc[15]["low"] = 80.0
    facts = extract_technical_facts(dp, rsi_12=None, as_of="2026-05-21T00:43:00Z", ohlc=ohlc)
    ids = {f.id for f in facts}
    assert "technical.swing_high_20d" in ids
    assert "technical.swing_low_20d" in ids
    sh = next(f for f in facts if f.id == "technical.swing_high_20d")
    sl = next(f for f in facts if f.id == "technical.swing_low_20d")
    assert sh.value == 130.0
    assert sl.value == 80.0


def test_swing_no_ohlc_skipped():
    dp = {"price_position": {"current_price": 100.0}}
    facts = extract_technical_facts(dp, rsi_12=None, as_of="2026-05-21T00:43:00Z")
    assert not any(f.id.startswith("technical.swing_") for f in facts)
