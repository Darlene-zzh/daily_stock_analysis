"""Regression guard for [[repo-agent-mode-bypass]]: when agent mode runs the
analysis, _attach_fact_bundle MUST still fire before _try_inject_action_plan_items
so that Phase 2's sanitizer + synthesizer see the candidates pool.

Discovered via Phase 2 smoke 2026-05-23: agent mode is the default, so the original
Phase 2 wiring (placed only in the non-agent branch at pipeline.py:540) never fired
in production. This test pins both branches.
"""
import inspect

from src.core.pipeline import StockAnalysisPipeline


def _get_source(method):
    return inspect.getsource(method)


def test_agent_mode_path_calls_attach_fact_bundle_before_action_plan():
    """The agent-mode analysis function must call _attach_fact_bundle before
    _try_inject_action_plan_items so Phase 2 sees candidates."""
    src = inspect.getsource(StockAnalysisPipeline)
    # Find the agent-mode analyze function block — it's the one that has the
    # comment "持仓感知 + 翻译后处理（与非 agent 路径保持一致" before the
    # _try_inject_zh_translations / _try_inject_action_plan_items chain.
    anchor = "与非 agent 路径保持一致"
    assert anchor in src, "Agent-mode comment anchor moved; update this test"
    # Within ~50 lines after that anchor, both _attach_fact_bundle and
    # _try_inject_action_plan_items must appear, with attach FIRST.
    idx = src.index(anchor)
    window = src[idx : idx + 2000]
    assert "_attach_fact_bundle" in window, (
        "agent-mode path missing _attach_fact_bundle — Phase 2 candidates won't "
        "reach the LLM. See [[repo-agent-mode-bypass]]."
    )
    attach_pos = window.index("_attach_fact_bundle")
    inject_pos = window.index("_try_inject_action_plan_items")
    assert attach_pos < inject_pos, (
        "_attach_fact_bundle must run BEFORE _try_inject_action_plan_items in "
        "the agent-mode path (otherwise sanitizer + synthesizer get no bundle)."
    )


def test_non_agent_path_still_has_attach_first():
    """Sanity: the original non-agent path still has the right ordering."""
    src = inspect.getsource(StockAnalysisPipeline)
    # The non-agent path is identified by the "BEFORE action_plan LLM call" comment
    anchor = "BEFORE action_plan LLM call"
    assert anchor in src
    idx = src.index(anchor)
    window = src[idx : idx + 2000]
    assert "_attach_fact_bundle" in window
    attach_pos = window.index("_attach_fact_bundle")
    inject_pos = window.index("_try_inject_action_plan_items")
    assert attach_pos < inject_pos


def test_both_paths_have_attach():
    """Count attach occurrences in the pipeline class — must be at least 2
    (one per analysis path) plus the method definition itself."""
    src = inspect.getsource(StockAnalysisPipeline)
    # Count callsites only — exclude the `def _attach_fact_bundle` definition
    call_count = src.count("self._attach_fact_bundle(result, code)")
    assert call_count >= 2, (
        f"Expected ≥2 self._attach_fact_bundle callsites (agent + non-agent paths), "
        f"found {call_count}. [[repo-agent-mode-bypass]] applies."
    )
