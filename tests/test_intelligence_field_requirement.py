"""Test that analyzer system prompt strongly requires all 5 intelligence
sub-fields (latest_news / risk_alerts / positive_catalysts /
earnings_outlook / sentiment_summary) — they must always appear in
the output even when there is no data (empty string / empty list).

Why: 2026-05-20 INTC test had report_language=zh and the LLM emitted
only 2 of the 5 intelligence sub-fields, leaving the rest absent from
the dashboard. Schema validators don't catch missing optional fields,
so the report shipped incomplete.
"""
import pytest

from src.analyzer import GeminiAnalyzer


@pytest.fixture
def analyzer():
    # Bypass __init__ to avoid touching LLM SDK / config.
    return GeminiAnalyzer.__new__(GeminiAnalyzer)


def test_zh_system_prompt_lists_all_5_intelligence_fields_as_required(analyzer):
    prompt = analyzer._get_analysis_system_prompt(
        report_language="zh",
        stock_code="AAPL",
    )
    # The prompt must contain an explicit "必填" / "MUST" / "required" directive
    # mentioning all 5 fields together.
    assert "intelligence 区块必填" in prompt or "intelligence MUST emit" in prompt
    for field in ("latest_news", "risk_alerts", "positive_catalysts",
                  "earnings_outlook", "sentiment_summary"):
        assert field in prompt, f"intelligence sub-field {field} missing"


def test_en_system_prompt_lists_all_5_intelligence_fields_as_required(analyzer):
    prompt = analyzer._get_analysis_system_prompt(
        report_language="en",
        stock_code="AAPL",
    )
    assert "intelligence 区块必填" in prompt or "intelligence MUST emit" in prompt
    for field in ("latest_news", "risk_alerts", "positive_catalysts",
                  "earnings_outlook", "sentiment_summary"):
        assert field in prompt, f"intelligence sub-field {field} missing"


def test_zh_system_prompt_instructs_empty_value_when_no_data(analyzer):
    prompt = analyzer._get_analysis_system_prompt(
        report_language="zh",
        stock_code="AAPL",
    )
    assert "无数据" in prompt or "empty" in prompt.lower(), (
        "prompt must instruct LLM to emit empty string / empty list when no "
        "data is available, instead of omitting the field"
    )
