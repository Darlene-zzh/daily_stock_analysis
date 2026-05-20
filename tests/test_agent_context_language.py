"""Tests that AgentContext carries report_language for downstream agents."""
from src.agent.protocols import AgentContext


def test_agent_context_default_report_language_is_zh():
    """Default report_language is 'zh' — matches main analyzer default.

    Why: the committee orchestrator branches on ctx.report_language to
    append a Chinese-output suffix to its prompts. Defaulting to 'zh'
    means callers that omit the field (e.g. older test fixtures) still
    get the Chinese behavior expected by the rest of the pipeline.
    """
    ctx = AgentContext(stock_code="AAPL")
    assert ctx.report_language == "zh"


def test_agent_context_accepts_explicit_report_language():
    ctx = AgentContext(stock_code="AAPL", report_language="en")
    assert ctx.report_language == "en"


def test_agent_context_report_language_independent_of_meta():
    """report_language is a top-level field, not buried in meta."""
    ctx = AgentContext(stock_code="AAPL", report_language="en", meta={"market": "US"})
    assert ctx.report_language == "en"
    assert ctx.meta == {"market": "US"}
