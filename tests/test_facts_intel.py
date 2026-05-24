from src.analysis.extractors.intel import extract_intel_facts


def test_extract_intel_facts():
    intelligence = {
        "risk_alerts": ["PE/PB 缺失", "RSI 71.1 超买"],
        "risk_alerts_zh": ["估值数据缺失", "RSI 71.1 超买"],
        "positive_catalysts": ["AI 算力增长"],
        "positive_catalysts_zh": ["AI 算力增长"],
        "latest_news": "NVIDIA announces...",
        "latest_news_zh": "英伟达宣布...",
        "sentiment_summary": "Mixed positive",
        "sentiment_summary_zh": "整体偏正向",
        "earnings_outlook": "FY26 EPS revised up",
        "sentiment_dimensions": {
            "reddit": {"score": 0.6, "summary": "热度高"},
            "x_twitter": {"score": 0.5, "summary": "话题度持续"},
            "stocktwits": {"score": 0.7, "summary": "情绪偏多"},
        },
    }
    facts = extract_intel_facts(intelligence, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "intel.risk_alert.0" in ids
    assert "intel.risk_alert.1" in ids
    assert "intel.positive_catalyst.0" in ids
    assert "intel.latest_news" in ids
    assert "intel.sentiment_summary" in ids
    assert "intel.earnings_outlook" in ids
    assert "intel.sentiment.reddit" in ids
    assert "intel.sentiment.x_twitter" in ids

    risk0 = next(f for f in facts if f.id == "intel.risk_alert.0")
    assert "PE/PB" in risk0.value
    assert risk0.extra.get("zh") == "估值数据缺失"


def test_extract_intel_empty():
    assert extract_intel_facts(None, as_of="2026-05-21T00:43:00Z") == []
    assert extract_intel_facts({}, as_of="2026-05-21T00:43:00Z") == []


def test_extract_intel_partial_dims_only_real_sources():
    intelligence = {
        "sentiment_dimensions": {
            "reddit": {"score": 0.5},
            "polymarket": None,
        },
    }
    facts = extract_intel_facts(intelligence, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "intel.sentiment.reddit" in ids
    assert "intel.sentiment.polymarket" not in ids
