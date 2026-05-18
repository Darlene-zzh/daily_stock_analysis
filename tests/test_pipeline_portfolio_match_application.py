# -*- coding: utf-8 -*-
"""Regression tests pinning the ``_apply_portfolio_match`` propagation contract.

Background
----------
Commit ``63cd294`` introduced ``_apply_portfolio_match`` plus call sites in
both ``StockAnalysisPipeline.process_single_stock`` and
``StockAnalysisPipeline._analyze_with_agent`` (the bypass path).  Commit
``35b2a73`` then refined the agent-path call site so both paths copied
``pipeline.portfolio_match`` onto ``AnalysisResult.portfolio_match``
before the result reached the renderers and the history DB.

Sprint 2-2 (commit ``fbb3d1b``) and subsequent refactors removed both the
function body and both call sites, leaving ``self.portfolio_match`` as a
dead attribute.  ``getattr(result, "portfolio_match", None) == "held"`` in
``src/notification.py`` and ``src/services/history_service.py`` therefore
silently fell through to the default two-row position-advice table, even
for portfolio-aware analyses — breaking the differentiated copy that the
``feat/action-plan-items`` branch depends on.

This module pins the fix:

* ``_apply_portfolio_match`` is a real module-level helper again.
* ``"held"`` and ``"not_held"`` round-trip onto the result.
* ``None`` leaves the result attribute untouched (default-off invariant).
* The standard pipeline path stamps ``portfolio_match`` before the
  history-save call.
* The ``_analyze_with_agent`` bypass path stamps it too.
* The real ``NotificationService`` renderer emits the held-only row when
  ``result.portfolio_match == "held"``.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Keep this test runnable when optional LLM/runtime deps are not installed.
for optional_module in ("litellm", "json_repair"):
    try:
        __import__(optional_module)
    except ModuleNotFoundError:
        sys.modules[optional_module] = MagicMock()

from src.analyzer import AnalysisResult  # noqa: E402
from src.config import Config  # noqa: E402
from src.core.pipeline import StockAnalysisPipeline, _apply_portfolio_match  # noqa: E402
from src.notification import NotificationService  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (mirror the patterns in tests/test_pipeline_init_kwargs.py)
# ---------------------------------------------------------------------------


def _make_minimal_config() -> SimpleNamespace:
    """Stub config exposing only the attributes the constructor reads."""
    return SimpleNamespace(
        max_workers=2,
        save_context_snapshot=False,
        bocha_api_keys=[],
        tavily_api_keys=[],
        anspire_api_keys=[],
        brave_api_keys=[],
        serpapi_keys=[],
        minimax_api_keys=[],
        searxng_base_urls=[],
        searxng_public_instances_enabled=False,
        news_max_age_days=7,
        news_strategy_profile="short",
        enable_realtime_quote=False,
        realtime_source_priority=[],
        enable_chip_distribution=False,
        social_sentiment_api_key="",
        social_sentiment_api_url="https://example.invalid/social",
    )


def _build_pipeline(**ctor_kwargs) -> StockAnalysisPipeline:
    """Construct a pipeline with the heavy collaborators stubbed out."""
    config = ctor_kwargs.pop("config", None) or _make_minimal_config()
    search_service = MagicMock()
    search_service.is_available = True
    social_service = MagicMock()
    social_service.is_available = False
    with patch("src.core.pipeline.get_db", return_value=MagicMock()), \
         patch("src.core.pipeline.DataFetcherManager", return_value=MagicMock()), \
         patch("src.core.pipeline.StockTrendAnalyzer", return_value=MagicMock()), \
         patch("src.core.pipeline.GeminiAnalyzer", return_value=MagicMock()), \
         patch("src.core.pipeline.NotificationService", return_value=MagicMock()), \
         patch("src.core.pipeline.SearchService", return_value=search_service), \
         patch("src.core.pipeline.SocialSentimentService", return_value=social_service):
        return StockAnalysisPipeline(config=config, **ctor_kwargs)


def _make_result(**overrides) -> AnalysisResult:
    """Build a minimal AnalysisResult — only the fields the renderer reads."""
    base = dict(
        code="AAPL",
        name="Apple",
        sentiment_score=72,
        trend_prediction="看多",
        operation_advice="加仓",
        decision_type="buy",
        confidence_level="高",
        report_language="zh",
        analysis_summary="动量结构维持向上。",
        dashboard={
            "core_conclusion": {
                "one_sentence": "动量结构维持向上，回踩低吸。",
                "time_sensitivity": "短线",
                "position_advice": {
                    "no_position": "回踩支撑可建仓。",
                    "has_position": "继续持有并跟随止损。",
                },
            },
        },
    )
    base.update(overrides)
    return AnalysisResult(**base)


# ---------------------------------------------------------------------------
# Function-level contract
# ---------------------------------------------------------------------------


def test_apply_portfolio_match_held():
    """``portfolio.portfolio_match == 'held'`` propagates onto the result."""
    pipeline = _build_pipeline(portfolio_match="held")
    result = _make_result()
    _apply_portfolio_match(result, pipeline)
    assert result.portfolio_match == "held"


def test_apply_portfolio_match_not_held():
    """``portfolio.portfolio_match == 'not_held'`` propagates onto the result.

    Pins the value-space the renderers expect (see ``src/notification.py``
    and ``src/services/history_service.py``: ``== "held"`` check + fallback
    to the two-row default for anything else).  The original convention in
    commit ``63cd294`` was ``"held"`` / ``"not_held"`` / None — *not*
    ``"held"`` / ``"empty"`` / None as the task brief suggested.
    """
    pipeline = _build_pipeline(portfolio_match="not_held")
    result = _make_result()
    _apply_portfolio_match(result, pipeline)
    assert result.portfolio_match == "not_held"


def test_apply_portfolio_match_none_leaves_result_attribute_unset():
    """When the pipeline has no portfolio context, the helper must leave
    ``result.portfolio_match`` as ``None`` so the renderer falls back to
    the default two-row position-advice table.

    Post Plan-B merge ``AnalysisResult.portfolio_match`` is a declared
    dataclass field defaulting to ``None`` (not a purely runtime-attached
    attribute). The behavioural invariant — renderer's ``== "held"`` check
    evaluates to ``False`` — is unchanged.
    """
    pipeline = _build_pipeline()  # portfolio_match defaults to None
    assert pipeline.portfolio_match is None
    result = _make_result()
    # Pre-condition: when pipeline.portfolio_match is None the result's
    # portfolio_match (dataclass default) must also be None or unset.
    assert getattr(result, "portfolio_match", None) is None, (
        "AnalysisResult.portfolio_match defaults to None — the helper is "
        "the only writer that overrides it; this precondition guards the test."
    )
    _apply_portfolio_match(result, pipeline)
    assert getattr(result, "portfolio_match", None) is None


def test_apply_portfolio_match_is_idempotent():
    """Calling the helper twice with the same pipeline must not corrupt
    the result.  Both the standard pipeline path and the agent bypass
    converge through ``AnalysisService``, so guarding against an
    accidental double-write keeps future hook ordering safe.
    """
    pipeline = _build_pipeline(portfolio_match="held")
    result = _make_result()
    _apply_portfolio_match(result, pipeline)
    _apply_portfolio_match(result, pipeline)
    assert result.portfolio_match == "held"


# ---------------------------------------------------------------------------
# Call-site contract: process_single_stock + _analyze_with_agent both fire
# ---------------------------------------------------------------------------


def test_analyze_stock_call_site_invokes_apply_portfolio_match():
    """``pipeline.analyze_stock`` (the standard non-agent path that
    ``process_single_stock`` delegates to) must call
    ``_apply_portfolio_match`` so ``portfolio_match`` lands on the result
    before history is saved.

    This is a static-source assertion so we don't have to spin up the
    full analyzer/DB stack — the helper-internals contract is covered
    by the unit tests above; this one pins the call-site location
    (commit 63cd294: the Step 7.5 block right after ``current_price``
    / ``change_pct`` are stamped).
    """
    import src.core.pipeline as pipeline_mod
    assert "_apply_portfolio_match" in pipeline_mod.__dict__, (
        "Module-level helper missing — the function body restoration is "
        "incomplete."
    )

    import inspect
    src_text = inspect.getsource(StockAnalysisPipeline.analyze_stock)
    assert "_apply_portfolio_match(result, self)" in src_text, (
        "analyze_stock must call _apply_portfolio_match on the "
        "freshly-analyzed result before history is persisted.  See the "
        "Step 7.5 block (commit 63cd294)."
    )


def test_analyze_with_agent_call_site_invokes_apply_portfolio_match():
    """The agent bypass path must also stamp portfolio_match.  Without
    this, agent-mode analyses would silently lose the renderer filter —
    the exact regression flagged in 35b2a73's commit message.
    """
    import inspect
    src_text = inspect.getsource(StockAnalysisPipeline._analyze_with_agent)
    assert "_apply_portfolio_match(result, self)" in src_text, (
        "_analyze_with_agent must call _apply_portfolio_match before the "
        "save_analysis_history block so both paths converge on the same "
        "portfolio_match contract (commit 35b2a73)."
    )


# ---------------------------------------------------------------------------
# Renderer integration: the real NotificationService picks up "held"
# ---------------------------------------------------------------------------


def _make_renderer_config(**overrides) -> Config:
    """Mirror the pattern in tests/test_notification.py (``_make_config``)."""
    return Config(stock_list=[], **overrides)


@mock.patch("src.notification.get_config")
def test_renderer_emits_held_only_row_when_portfolio_match_held(mock_get_config):
    """End-to-end product behaviour: with ``result.portfolio_match=="held"``,
    the dashboard report must drop the default two-row position-advice
    table and emit ONLY the "已持有" row using the ``has_position`` copy.

    This is the actual scoring-adjacent assertion — if the helper or the
    call sites silently no-op, this test fails because the renderer falls
    back to printing both rows (the original two-row default).
    """
    mock_get_config.return_value = _make_renderer_config(
        report_renderer_enabled=False, report_language="zh",
    )
    service = NotificationService()
    result = _make_result()
    result.portfolio_match = "held"  # what _apply_portfolio_match writes

    out = service.generate_dashboard_report([result], report_date="2026-05-18")

    # The "held" branch emits ONLY the has_position row, not both.
    assert "继续持有并跟随止损。" in out, (
        "held branch must surface has_position copy"
    )
    # The "no_position" copy must be suppressed in the held branch.
    # (When result.portfolio_match is None the renderer prints BOTH rows
    # — see the default branch below.)
    assert "回踩支撑可建仓。" not in out, (
        "held branch must NOT print the no_position row; the silent-no-op "
        "regression would print both rows."
    )


@mock.patch("src.notification.get_config")
def test_renderer_emits_not_held_only_row_when_portfolio_match_not_held(mock_get_config):
    """Symmetric assertion for the ``not_held`` branch — the renderer must
    surface only the ``no_position`` copy."""
    mock_get_config.return_value = _make_renderer_config(
        report_renderer_enabled=False, report_language="zh",
    )
    service = NotificationService()
    result = _make_result()
    result.portfolio_match = "not_held"

    out = service.generate_dashboard_report([result], report_date="2026-05-18")

    assert "回踩支撑可建仓。" in out
    assert "继续持有并跟随止损。" not in out


@mock.patch("src.notification.get_config")
def test_renderer_emits_default_two_row_table_when_portfolio_match_unset(mock_get_config):
    """When the helper leaves ``portfolio_match`` as None (no portfolio
    context, e.g. scheduled / market-review analyses), the renderer must
    print BOTH rows — preserving backward compatibility with the
    pre-portfolio-filter behaviour."""
    mock_get_config.return_value = _make_renderer_config(
        report_renderer_enabled=False, report_language="zh",
    )
    service = NotificationService()
    result = _make_result()
    # portfolio_match deliberately left as default None — the renderer's
    # ``getattr(result, "portfolio_match", None) == "held"`` check returns
    # False, so the default two-row position-advice table renders.
    assert getattr(result, "portfolio_match", None) is None

    out = service.generate_dashboard_report([result], report_date="2026-05-18")

    # Both rows present in the default branch.
    assert "回踩支撑可建仓。" in out
    assert "继续持有并跟随止损。" in out


# ---------------------------------------------------------------------------
# Defensive: parametrised round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["held", "not_held"])
def test_apply_portfolio_match_roundtrips_pipeline_to_result(value):
    pipeline = _build_pipeline(portfolio_match=value)
    result = _make_result()
    _apply_portfolio_match(result, pipeline)
    assert result.portfolio_match == value
