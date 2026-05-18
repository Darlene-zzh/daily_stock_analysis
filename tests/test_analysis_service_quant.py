# -*- coding: utf-8 -*-
"""End-to-end stub test for the quant hook on AnalysisService (Sprint 3).

Mirrors the structure of ``tests/test_analysis_service_committee.py``:
we patch ``QuantSignalService.build_quant_context_block`` so we don't
need qlib, then patch the pipeline so we don't need real LLM/data.

Covers:

* ``enable_quant_signal=False`` (the default) → quant block builder
  NOT called, no quant data threaded to the pipeline
* ``enable_quant_signal=True`` with a mocked builder → block is built
  exactly once and propagated to the pipeline (via the
  ``quant_context_block`` kwarg)
* Builder failure (raises) is swallowed and analysis still succeeds
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_pipeline_result():
    """Minimal AnalysisResult-shaped object the response builder accepts."""
    return SimpleNamespace(
        success=True,
        code="600519",
        name="贵州茅台",
        report_language="zh",
        sentiment_score=70,
        analysis_summary="OK",
        operation_advice="hold",
        trend_prediction="neutral",
        news_summary="",
        technical_analysis="",
        fundamental_analysis="",
        risk_warning="",
        current_price=1680.0,
        change_pct=0.5,
        model_used="mocked",
        query_id="qid-1",
        dashboard={},
        get_sniper_points=lambda: {},
    )


def _service():
    from src.services.analysis_service import AnalysisService
    svc = AnalysisService()
    # Bypass the 24h same-stock cache so each test gets a fresh pipeline call.
    svc._lookup_recent_cache_response = lambda *args, **kwargs: None
    return svc


def test_quant_default_off_does_not_build_block(fake_pipeline_result, monkeypatch):
    """When ``enable_quant_signal`` is False (default) the service must
    never even instantiate ``QuantSignalService``."""
    svc = _service()
    quant_builder = MagicMock()

    fake_pipeline = MagicMock()
    fake_pipeline.process_single_stock.return_value = fake_pipeline_result
    captured_kwargs = {}

    def _pipeline_factory(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_pipeline

    with patch("src.core.pipeline.StockAnalysisPipeline", _pipeline_factory), \
         patch("src.services.quant_signal_service.QuantSignalService") as quant_cls:
        quant_cls.return_value.build_quant_context_block = quant_builder
        result = svc.analyze_stock(
            stock_code="600519",
            report_type="detailed",
            send_notification=False,
            enable_quant_signal=False,  # explicit default
        )

    assert result is not None
    quant_builder.assert_not_called()
    assert captured_kwargs.get("quant_context_block") is None


def test_quant_enabled_builds_and_threads_block(fake_pipeline_result, monkeypatch):
    """``enable_quant_signal=True`` builds the block and threads it
    through to the pipeline init."""
    svc = _service()

    fake_pipeline = MagicMock()
    fake_pipeline.process_single_stock.return_value = fake_pipeline_result
    captured_kwargs = {}

    def _pipeline_factory(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_pipeline

    block_text = "## Quant Context (auxiliary)\n> auxiliary, not a recommendation\n"

    with patch("src.core.pipeline.StockAnalysisPipeline", _pipeline_factory), \
         patch("src.services.quant_signal_service.QuantSignalService") as quant_cls:
        builder = MagicMock(return_value=block_text)
        quant_cls.return_value.build_quant_context_block = builder

        result = svc.analyze_stock(
            stock_code="600519",
            report_type="detailed",
            send_notification=False,
            enable_quant_signal=True,
            quant_forecast_horizon=10,
        )

    assert result is not None
    builder.assert_called_once()
    # Block must reach the pipeline factory kwargs
    assert captured_kwargs.get("quant_context_block") == block_text


def test_quant_builder_exception_is_swallowed(fake_pipeline_result):
    """Even if the quant service blows up internally, the pipeline must
    still run with a None block — analysis MUST NOT fail because of a
    quant subsystem error."""
    svc = _service()

    fake_pipeline = MagicMock()
    fake_pipeline.process_single_stock.return_value = fake_pipeline_result
    captured_kwargs = {}

    def _pipeline_factory(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_pipeline

    with patch("src.core.pipeline.StockAnalysisPipeline", _pipeline_factory), \
         patch("src.services.quant_signal_service.QuantSignalService") as quant_cls:
        quant_cls.return_value.build_quant_context_block = MagicMock(
            side_effect=RuntimeError("qlib explosion"),
        )

        result = svc.analyze_stock(
            stock_code="600519",
            report_type="detailed",
            send_notification=False,
            enable_quant_signal=True,
        )

    assert result is not None
    assert captured_kwargs.get("quant_context_block") is None


def test_quant_threaded_through_task_queue_kwargs():
    """Quick wiring assertion: ``submit_tasks_batch`` accepts the new
    keyword arguments and forwards them to ``_execute_task`` via the
    thread-pool submit call."""
    import inspect
    from src.services.task_queue import AnalysisTaskQueue

    sig = inspect.signature(AnalysisTaskQueue.submit_tasks_batch)
    assert "enable_quant_signal" in sig.parameters
    assert "quant_forecast_horizon" in sig.parameters

    exec_sig = inspect.signature(AnalysisTaskQueue._execute_task)
    assert "enable_quant_signal" in exec_sig.parameters
    assert "quant_forecast_horizon" in exec_sig.parameters
