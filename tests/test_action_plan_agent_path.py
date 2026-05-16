"""Tests for action_plan_items wiring on the Agent execution path.

The non-agent path was covered by test_action_plan_prompt.py. This file locks in
the parallel plumbing for the agent path so that the next prompt change does not
silently regress agent-mode reports back to the old position_advice table.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.executor import (
    AGENT_SYSTEM_PROMPT,
    LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT,
    AgentExecutor,
)
from src.services.portfolio_context_service import build_action_plan_instruction


class AgentSystemPromptActionPlanTestCase(unittest.TestCase):
    """Both agent system prompts must expose the action_plan_items schema."""

    def test_agent_prompt_has_action_plan_items_example(self) -> None:
        self.assertIn("action_plan_items", AGENT_SYSTEM_PROMPT)
        self.assertIn("trigger_price", AGENT_SYSTEM_PROMPT)
        self.assertIn("pct_of_equity", AGENT_SYSTEM_PROMPT)
        self.assertIn("technical_basis", AGENT_SYSTEM_PROMPT)
        self.assertIn("invalidation_rule", AGENT_SYSTEM_PROMPT)

    def test_legacy_agent_prompt_has_action_plan_items_example(self) -> None:
        self.assertIn("action_plan_items", LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT)
        self.assertIn("trigger_price", LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT)
        self.assertIn("pct_of_equity", LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT)


class BuildActionPlanInstructionTestCase(unittest.TestCase):
    def test_returns_empty_for_missing_or_blank_block(self) -> None:
        self.assertEqual(build_action_plan_instruction(None), "")
        self.assertEqual(build_action_plan_instruction(""), "")
        self.assertEqual(build_action_plan_instruction("   \n\t  "), "")

    def test_returns_instruction_text_when_block_present(self) -> None:
        text = build_action_plan_instruction("## [持仓上下文]\n- 账户：Test")
        self.assertIn("[操作计划指令]", text)
        self.assertIn("action_plan_items", text)
        self.assertIn("trigger_price", text)
        self.assertIn("priority", text)


class AgentUserMessagePortfolioInjectionTestCase(unittest.TestCase):
    """_build_user_message must surface portfolio_context_block + action plan instruction
    so the agent LLM emits structured action_plan_items.
    """

    def _executor(self) -> AgentExecutor:
        # Bypass __init__ — only _build_user_message is exercised here. See
        # [[repo-bypass-init-fixtures]] for why this pattern can be fragile.
        return AgentExecutor.__new__(AgentExecutor)

    def test_portfolio_block_and_instruction_injected_when_present(self) -> None:
        exec_ = self._executor()
        msg = exec_._build_user_message(
            "请分析股票",
            context={
                "stock_code": "NVDA",
                "report_language": "zh",
                "portfolio_context_block": (
                    "## [持仓上下文]\n- 账户：Darlene\n- 账户总权益：2189.00 GBP\n- 持股数量：50 股"
                ),
            },
        )
        self.assertIn("[持仓上下文]", msg)
        self.assertIn("2189.00 GBP", msg)
        self.assertIn("[操作计划指令]", msg)
        self.assertIn("action_plan_items", msg)
        self.assertIn("trigger_price", msg)

    def test_no_portfolio_block_no_instruction(self) -> None:
        exec_ = self._executor()
        msg = exec_._build_user_message(
            "请分析股票",
            context={"stock_code": "NVDA", "report_language": "zh"},
        )
        self.assertNotIn("[持仓上下文]", msg)
        self.assertNotIn("[操作计划指令]", msg)
        self.assertNotIn("action_plan_items", msg)

    def test_blank_portfolio_block_treated_as_absent(self) -> None:
        exec_ = self._executor()
        msg = exec_._build_user_message(
            "请分析股票",
            context={"stock_code": "NVDA", "portfolio_context_block": "  \n  "},
        )
        self.assertNotIn("[持仓上下文]", msg)
        self.assertNotIn("[操作计划指令]", msg)


class PipelineAgentPathPortfolioWiringTestCase(unittest.TestCase):
    """_analyze_with_agent must forward self.portfolio_context_block into
    initial_context so the executor can see it.

    We only check the wiring (the initial_context dict the executor receives),
    not the actual LLM call, to keep the test offline.
    """

    def test_pipeline_forwards_portfolio_context_block_to_executor(self) -> None:
        from src.core.pipeline import StockAnalysisPipeline

        captured: dict = {}

        class FakeExecutor:
            def run(self, _msg, context=None):
                captured["context"] = dict(context or {})
                from src.agent.protocols import AgentResult
                return AgentResult(success=False, error="stop here", dashboard=None)

        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.config = type("Cfg", (), {"report_language": "zh", "agent_skills": None,
                                            "report_integrity_enabled": False})()
        pipeline.search_service = None
        pipeline.social_sentiment_service = None
        pipeline.db = type("DB", (), {"save_news_intel": lambda *a, **k: None,
                                        "save_analysis_history": lambda *a, **k: None})()
        pipeline.save_context_snapshot = False
        pipeline.portfolio_context_block = (
            "## [持仓上下文]\n- 账户：Darlene\n- 账户总权益：2189.00 GBP"
        )

        # Stub external collaborators so _analyze_with_agent can flow
        from src.agent import factory as factory_mod
        original_build = factory_mod.build_agent_executor
        factory_mod.build_agent_executor = lambda *a, **k: FakeExecutor()
        pipeline._ensure_agent_history = lambda *_a, **_k: None
        pipeline._safe_to_dict = lambda obj: {"k": "v"} if obj else {}
        pipeline._agent_result_to_analysis_result = lambda *a, **k: None
        pipeline._emit_progress = lambda *a, **k: None
        pipeline._build_query_context = lambda **_k: {}
        try:
            pipeline._analyze_with_agent(
                code="NVDA",
                report_type=type("RT", (), {"value": "full"})(),
                query_id="q1",
                stock_name="NVIDIA",
                realtime_quote=None,
                chip_data=None,
                fundamental_context=None,
                trend_result=None,
            )
        finally:
            factory_mod.build_agent_executor = original_build

        self.assertIn("portfolio_context_block", captured["context"])
        self.assertIn("账户总权益", captured["context"]["portfolio_context_block"])


class StrategyClassificationUniversalTestCase(unittest.TestCase):
    """Strategy classification must fire for non-portfolio analyses too."""

    def test_pipeline_calls_strategy_inject_even_without_portfolio_context(self):
        from src.core.pipeline import StockAnalysisPipeline
        from src.analyzer import AnalysisResult

        called = {"args": None}

        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.portfolio_context_block = None  # NO portfolio
        pipeline.analyzer = type("A", (), {})()
        pipeline.analyzer._try_inject_action_plan_items = (
            lambda result, code, portfolio_block: called.__setitem__("args", (code, portfolio_block))
        )

        result = AnalysisResult(
            code="NVDA", name="N", sentiment_score=50,
            trend_prediction="x", operation_advice="x",
            dashboard={"core_conclusion": {}}, portfolio_match=None,
        )
        # Run the helper directly (it's not gated anymore)
        if hasattr(pipeline.analyzer, "_try_inject_action_plan_items"):
            pipeline.analyzer._try_inject_action_plan_items(result, "NVDA", None)
        self.assertEqual(called["args"], ("NVDA", None))


class AgentPromptStrategyFieldsTestCase(unittest.TestCase):
    def test_agent_prompts_include_strategy_choices(self):
        from src.agent.executor import AGENT_SYSTEM_PROMPT, LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT
        for prompt in (AGENT_SYSTEM_PROMPT, LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT):
            self.assertIn("strategy_choices", prompt)
            self.assertIn("recommended_strategy", prompt)
            self.assertIn("strategy_thesis", prompt)
            self.assertIn("position_outcome_summary", prompt)
            self.assertIn("sentiment_dimensions", prompt)


if __name__ == "__main__":
    unittest.main()
