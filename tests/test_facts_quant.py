import json
import tempfile
from pathlib import Path
from src.analysis.extractors.quant import extract_quant_facts, find_latest_qlib_week


def test_extract_quant_facts_from_predictions_dict():
    predictions = {"NVDA": {"score": 0.2348, "rank": 0.8473}, "AAPL": {"score": 0.1, "rank": 0.5}}
    ic = {"as_of": "2026-05-18", "ic_current": 0.172, "ic_ma_4w": 0.211}
    facts = extract_quant_facts(
        "NVDA",
        predictions=predictions,
        ic=ic,
        universe_size=503,
        week="2026-W21",
        as_of="2026-05-21T00:43:00Z",
    )
    ids = {f.id for f in facts}
    assert "quant.qlib_score" in ids
    assert "quant.qlib_rank" in ids
    assert "quant.qlib_ic_4w" in ids
    score = next(f for f in facts if f.id == "quant.qlib_score")
    assert score.confidence == 0.211
    rank = next(f for f in facts if f.id == "quant.qlib_rank")
    assert rank.display_value == "前 16%"
    assert rank.extra["universe_size"] == 503


def test_extract_quant_facts_missing_ticker_returns_empty():
    facts = extract_quant_facts(
        "UNKNOWN", predictions={"NVDA": {"score": 0.2, "rank": 0.8}},
        ic={}, universe_size=503, week="2026-W21", as_of="2026-05-21T00:43:00Z",
    )
    assert facts == []


def test_find_latest_qlib_week_returns_most_recent(tmp_path):
    base = tmp_path / "quant_models" / "us"
    (base / "2026-W20").mkdir(parents=True)
    (base / "2026-W21").mkdir(parents=True)
    (base / "2026-W19").mkdir(parents=True)
    assert find_latest_qlib_week(base) == "2026-W21"


def test_find_latest_qlib_week_empty_returns_none(tmp_path):
    base = tmp_path / "quant_models" / "us"
    base.mkdir(parents=True)
    assert find_latest_qlib_week(base) is None
