"""Tests for the max-steps salvage path in `run_agent_loop`.

Background: when an agent's tool-loop hits max_steps without ever producing
a tool-free assistant message, the old code returned success=False, leaving
the orchestrator to bail with "Agent loop did not produce a final answer."
That broke the user-facing analysis pipeline as soon as Gemini fell over to
a non-Gemini provider (Cerebras / OpenRouter), because those providers
emit text *alongside* tool_calls instead of in a separate tool-free turn.

The salvage path walks the message history backwards for the most recent
assistant message that carries non-empty content and treats THAT as the
final answer. These tests pin the salvage behavior so a future refactor
can't silently regress it.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_llm_response(*, content: str = "", tool_calls=None, provider: str = "openai"):
    """Build a stub LLMResponse that the runner can iterate over."""
    from src.agent.llm_adapter import LLMResponse
    resp = LLMResponse.__new__(LLMResponse)
    resp.content = content
    resp.tool_calls = tool_calls or []
    resp.provider = provider
    resp.model = "stub-model"
    resp.usage = {"total_tokens": 100}
    resp.reasoning_content = None
    return resp


def _make_tool_call(name: str, args: dict, call_id: str = "tc_1"):
    from src.agent.llm_adapter import ToolCall
    tc = ToolCall.__new__(ToolCall)
    tc.id = call_id
    tc.name = name
    tc.arguments = args
    tc.thought_signature = None
    return tc


class AgentMaxStepsSalvageTestCase(unittest.TestCase):

    def setUp(self) -> None:
        # Build a tool registry with one harmless tool the stub LLM can keep
        # calling forever without doing anything destructive.
        from src.agent.tools.registry import ToolRegistry, ToolDefinition
        self.registry = ToolRegistry()
        self.registry.register(ToolDefinition(
            name="calculate_ma",
            description="dummy",
            parameters=[],
            handler=lambda **_: {"ok": True},
        ))

    def _run_with_responses(self, llm_responses, *, max_steps=3):
        from src.agent import runner as _runner
        mock_adapter = MagicMock()
        mock_adapter.call_with_tools.side_effect = llm_responses
        messages: list = []
        return _runner.run_agent_loop(
            messages=messages,
            tool_registry=self.registry,
            llm_adapter=mock_adapter,
            max_steps=max_steps,
        )

    def test_salvages_last_assistant_content_when_model_only_calls_tools(self):
        """Model writes prose alongside tool calls but never stops calling
        tools — salvage path should still extract the prose."""
        tc = _make_tool_call("calculate_ma", {"period": 5})
        responses = [
            _make_llm_response(content="先看一下 MA5。", tool_calls=[tc]),
            _make_llm_response(content="再确认 MA10。", tool_calls=[_make_tool_call("calculate_ma", {"period": 10}, "tc_2")]),
            _make_llm_response(content="结论：MA5/MA10 多头排列，技术面强。", tool_calls=[_make_tool_call("calculate_ma", {"period": 20}, "tc_3")]),
        ]
        result = self._run_with_responses(responses, max_steps=3)

        self.assertTrue(result.success, msg=f"expected salvage success, got error={result.error!r}")
        self.assertIn("MA5/MA10 多头排列", result.content)
        self.assertEqual(result.total_steps, 3)

    def test_fails_when_no_assistant_message_has_content(self):
        """If every assistant turn was pure tool_calls with empty content,
        nothing to salvage — should still fail cleanly."""
        responses = [
            _make_llm_response(content="", tool_calls=[_make_tool_call("calculate_ma", {"period": 5}, f"tc_{i}")])
            for i in range(3)
        ]
        result = self._run_with_responses(responses, max_steps=3)

        self.assertFalse(result.success)
        self.assertIn("max steps", (result.error or "").lower())
        self.assertEqual(result.content, "")

    def test_natural_tool_free_response_still_succeeds_without_salvage(self):
        """Regression guard: the original happy-path (model emits a tool-free
        final response) must still succeed via the `else` branch, not via
        salvage."""
        tc = _make_tool_call("calculate_ma", {"period": 5})
        responses = [
            _make_llm_response(content="先算 MA5。", tool_calls=[tc]),
            _make_llm_response(content="MA5 数据已拿到，分析完成。", tool_calls=[]),
        ]
        result = self._run_with_responses(responses, max_steps=5)

        self.assertTrue(result.success)
        self.assertEqual(result.content, "MA5 数据已拿到，分析完成。")
        # Loop exited at step 2, NOT max_steps (5) — proves it wasn't salvage.
        self.assertEqual(result.total_steps, 2)


if __name__ == "__main__":
    unittest.main()
