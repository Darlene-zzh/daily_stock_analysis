# -*- coding: utf-8 -*-
"""Prompt-injection tests for Sprint 3 quant context.

These tests assert the contract between the QuantSignalService block
output and the analyzer's prompt:

* When ``quant_context_block`` is None the prompt MUST NOT contain a
  ``Quant Context`` heading.
* When it is a non-empty string the prompt MUST contain the heading and
  the caveat line, spliced between portfolio/reflection context and
  the technical data.
* The dual-language caveat survives the splice (no escaping issues).

We exercise ``GeminiAnalyzer._format_prompt`` directly with a minimal
context dict so we don't need a real LLM.
"""

from __future__ import annotations

import pytest

from src.analyzer import GeminiAnalyzer


def _minimal_context():
    return {
        "code": "600519",
        "stock_name": "贵州茅台",
        "date": "2026-05-18",
        "today": {},
        "realtime": {"price": 1680.0, "change_pct": 0.5},
    }


def _build_analyzer():
    """Construct an analyzer without invoking real config plumbing.

    The methods we exercise (``_format_prompt`` and ``_get_skill_prompt_sections``)
    only need ``self`` to read instance state — no LLM connection.
    """
    # Use __new__ to skip __init__; analyzer.__init__ pulls in heavy config.
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    return analyzer


def test_prompt_omits_quant_section_when_block_none():
    analyzer = _build_analyzer()
    prompt = analyzer._format_prompt(
        _minimal_context(),
        name="贵州茅台",
        news_context=None,
        report_language="zh",
        portfolio_context_block=None,
        reflection_context_block=None,
        quant_context_block=None,
    )
    # No header, no caveat, nothing.
    assert "Quant Context" not in prompt
    assert "量化辅助" not in prompt
    assert "auxiliary" not in prompt.lower()


def test_prompt_includes_quant_section_when_block_present_zh():
    block = (
        "## 量化辅助信号 (Quant Context — auxiliary)\n\n"
        "> 以下为统计模型输出的**辅助观察**，**不是买卖建议**。\n\n"
        "### 因子快照 / Factor snapshot\n"
        "- `ret_5d`: +0.0120\n"
    )
    analyzer = _build_analyzer()
    prompt = analyzer._format_prompt(
        _minimal_context(),
        name="贵州茅台",
        news_context=None,
        report_language="zh",
        portfolio_context_block=None,
        reflection_context_block=None,
        quant_context_block=block,
    )
    assert "Quant Context" in prompt
    assert "辅助观察" in prompt
    assert "不是买卖建议" in prompt
    assert "ret_5d" in prompt


def test_prompt_includes_quant_section_when_block_present_en():
    block = (
        "## Quant Context (auxiliary)\n\n"
        "> The following is an **auxiliary statistical signal**, "
        "**not a buy/sell recommendation**.\n\n"
        "### Forecast\n- Horizon: 10 trading days (~2 weeks)\n"
    )
    analyzer = _build_analyzer()
    prompt = analyzer._format_prompt(
        _minimal_context(),
        name="Kweichow Moutai",
        news_context=None,
        report_language="en",
        portfolio_context_block=None,
        reflection_context_block=None,
        quant_context_block=block,
    )
    assert "Quant Context (auxiliary)" in prompt
    assert "not a buy/sell recommendation" in prompt
    assert "Horizon: 10 trading days" in prompt


def test_prompt_quant_block_coexists_with_reflection_and_portfolio():
    """The three opt-in blocks must all splice correctly without
    clobbering each other."""
    portfolio = "## 持仓上下文\n持仓占比：5%\n"
    reflection = "## 历史决策反思\n上次买入后 +12.3%\n"
    quant = "## Quant Context (auxiliary)\n> auxiliary, not a recommendation\n"
    analyzer = _build_analyzer()
    prompt = analyzer._format_prompt(
        _minimal_context(),
        name="Kweichow Moutai",
        news_context=None,
        report_language="zh",
        portfolio_context_block=portfolio,
        reflection_context_block=reflection,
        quant_context_block=quant,
    )
    # All three headers must be there in document order
    p_idx = prompt.find("持仓上下文")
    r_idx = prompt.find("历史决策反思")
    q_idx = prompt.find("Quant Context")
    assert p_idx != -1 and r_idx != -1 and q_idx != -1
    assert p_idx < r_idx < q_idx
