from src.analysis.extractors.chip import extract_chip_facts


def test_extract_chip_facts_a_share():
    chip = {
        "date": "2026-05-20",
        "profit_ratio": 0.835,
        "avg_cost": 42.15,
        "concentration_70": 0.082,
        "concentration_90": 0.155,
    }
    facts = extract_chip_facts(chip, market="a", as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "chip.profit_ratio" in ids
    assert "chip.avg_cost" in ids
    assert "chip.concentration_70" in ids
    assert "chip.concentration_90" in ids
    pr = next(f for f in facts if f.id == "chip.profit_ratio")
    assert pr.display_value == "83.5%"


def test_extract_chip_facts_us_returns_empty():
    chip = {"profit_ratio": 0.5}
    assert extract_chip_facts(chip, market="us", as_of="2026-05-21T00:43:00Z") == []


def test_extract_chip_facts_empty():
    assert extract_chip_facts(None, market="a", as_of="2026-05-21T00:43:00Z") == []
