# -*- coding: utf-8 -*-
"""Regression tests pinning the ``StockAnalysisPipeline.__init__`` contract.

Background
----------
Sprint 2-2 (commit ``fbb3d1b``) removed the ``portfolio_match`` parameter
from :class:`StockAnalysisPipeline` (along with the ``_apply_portfolio_match``
helper that propagated the value onto :class:`AnalysisResult` for renderer
filters). The author noticed the call site in
:func:`src.services.analysis_service.AnalysisService.analyze_stock` still
passed ``portfolio_match=...`` and patched the resulting ``TypeError`` with
a ``**_extra: Any`` shim, explicitly noting it as "separate bug, out of
Sprint 2 scope".

This module pins the real fix: ``portfolio_match`` is a declared keyword
parameter again, and ``AnalysisService`` can hand it across without falling
back to the catch-all shim. The catch-all itself is asserted absent so a
future refactor that adds ``**kwargs`` again is caught by CI rather than
silently swallowing typos.

These tests deliberately avoid spinning up the full pipeline. They patch
out the heavy collaborators (DB, fetchers, analyzer, notifier, search,
sentiment) so only the constructor contract is exercised.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.core.pipeline import StockAnalysisPipeline


def _make_minimal_config() -> SimpleNamespace:
    """Return a stub config exposing only the attributes the constructor reads."""
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


# ---------------------------------------------------------------------------
# Contract: portfolio_match is a declared keyword parameter
# ---------------------------------------------------------------------------


def test_init_signature_declares_portfolio_match():
    """``portfolio_match`` must be a real declared parameter, not absorbed
    by a catch-all ``**kwargs``.
    """
    sig = inspect.signature(StockAnalysisPipeline.__init__)
    assert "portfolio_match" in sig.parameters, (
        "portfolio_match must be a declared __init__ parameter; "
        "AnalysisService.analyze_stock relies on it being a real kwarg."
    )
    param = sig.parameters["portfolio_match"]
    assert param.kind in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ), f"portfolio_match should be a normal keyword param, got kind={param.kind}"
    assert param.default is None, (
        "portfolio_match default must be None so non-portfolio callers "
        "(market review, scheduled jobs) keep working unchanged."
    )


def test_init_does_not_use_var_keyword_shim():
    """No ``**kwargs`` / ``**_extra`` catch-all on the constructor.

    The Sprint 2 ``**_extra`` shim was a workaround. With ``portfolio_match``
    properly declared we want a future typo (``protfolio_match=...``) to
    raise ``TypeError`` instead of being silently swallowed.
    """
    sig = inspect.signature(StockAnalysisPipeline.__init__)
    var_keyword_params = [
        name for name, p in sig.parameters.items()
        if p.kind is inspect.Parameter.VAR_KEYWORD
    ]
    assert not var_keyword_params, (
        "StockAnalysisPipeline.__init__ must not declare a **kwargs / **_extra "
        f"catch-all. Found: {var_keyword_params}. See fbb3d1b commit history."
    )


# ---------------------------------------------------------------------------
# Behaviour: portfolio_match is stored on self and round-trips its value
# ---------------------------------------------------------------------------


def test_portfolio_match_defaults_to_none_on_self():
    pipeline = _build_pipeline()
    assert getattr(pipeline, "portfolio_match", "MISSING") is None


@pytest.mark.parametrize("value", ["held", "not_held", None])
def test_portfolio_match_is_stored_on_self(value):
    pipeline = _build_pipeline(portfolio_match=value)
    assert pipeline.portfolio_match == value


def test_unknown_kwargs_raise_typeerror_after_shim_removal():
    """With ``**_extra`` removed, an unknown kwarg must surface immediately
    instead of being silently absorbed."""
    with pytest.raises(TypeError):
        _build_pipeline(definitely_not_a_real_param=True)


# ---------------------------------------------------------------------------
# Call-site contract: AnalysisService passes portfolio_match without TypeError
# ---------------------------------------------------------------------------


def test_analysis_service_call_signature_matches_pipeline_init():
    """The kwargs ``AnalysisService.analyze_stock`` forwards to the pipeline
    constructor must all be declared on ``StockAnalysisPipeline.__init__``.

    This is the contract that originally broke when Sprint 2-2 deleted
    ``portfolio_match`` from the constructor without touching the caller.
    """
    pipeline_params = set(
        inspect.signature(StockAnalysisPipeline.__init__).parameters.keys()
    )
    # The kwargs analysis_service.analyze_stock forwards to the pipeline
    # constructor (see ``StockAnalysisPipeline(...)`` in that file).
    forwarded_kwargs = {
        "config",
        "query_id",
        "query_source",
        "progress_callback",
        "portfolio_context_block",
        "portfolio_match",
        "reflection_context_block",
        "quant_context_block",
    }
    missing = forwarded_kwargs - pipeline_params
    assert not missing, (
        "AnalysisService forwards kwargs the pipeline constructor does not "
        f"accept: {sorted(missing)}. This is the exact contract that "
        "Sprint 2-2 broke (fbb3d1b) and a defensive **_extra shim hid."
    )
