"""Tests that the committee orchestrator appends a Chinese-output suffix
to all 5 prompt sites (bull / bear / master / risk / pm) when
``ctx.report_language == 'zh'``, and stays English-only otherwise.

Why: the 2026-05-15 bilingual feature added a zh suffix to the main
analyzer prompt but the committee orchestrator was never wired up. The
INTC test on 2026-05-20 (report_language=zh) shipped with all
committee minutes (debate claims, master headlines, PM rationale) in
English while the rest of the report was Chinese.
"""
from unittest.mock import MagicMock

from src.agent.budget import LLMCallBudget
from src.agent.orchestrator_committee import (
    COMMITTEE_LANGUAGE_SUFFIX_ZH,
    InvestmentCommitteeOrchestrator,
)
from src.agent.protocols import AgentContext


def _make_orch(report_language: str) -> InvestmentCommitteeOrchestrator:
    ctx = AgentContext(
        stock_code="AAPL",
        stock_name="Apple",
        report_language=report_language,
        meta={"market": "US"},
    )
    return InvestmentCommitteeOrchestrator(
        ctx,
        report_json={"summary": "x"},
        budget=LLMCallBudget(cap=14),
        llm_callable=MagicMock(return_value="{}"),
        debate_rounds=2,
        timeout_s=999,
    )


def test_language_suffix_emits_zh_block_when_report_language_zh():
    orch = _make_orch("zh")
    suffix = orch._language_suffix()
    assert "输出语言" in suffix
    assert "JSON" in suffix or "键名" in suffix
    assert "headline" in suffix or "rationale" in suffix or "claim" in suffix


def test_language_suffix_empty_when_report_language_en():
    orch = _make_orch("en")
    suffix = orch._language_suffix()
    assert suffix == ""


def test_language_suffix_constant_module_export():
    """The suffix constant must be importable for testing & reuse."""
    assert "输出语言" in COMMITTEE_LANGUAGE_SUFFIX_ZH
    assert "verdict" in COMMITTEE_LANGUAGE_SUFFIX_ZH
    assert "rationale" in COMMITTEE_LANGUAGE_SUFFIX_ZH


def test_bull_prompt_includes_zh_suffix_under_zh_context():
    from src.agent.agents.bull_researcher import BullResearcher
    orch = _make_orch("zh")
    composed = BullResearcher.system_prompt() + orch._language_suffix()
    assert "输出语言" in composed
    assert "Bull Researcher" in composed


def test_bull_prompt_unchanged_under_en_context():
    from src.agent.agents.bull_researcher import BullResearcher
    orch = _make_orch("en")
    composed = BullResearcher.system_prompt() + orch._language_suffix()
    assert "输出语言" not in composed
    assert "Bull Researcher" in composed
