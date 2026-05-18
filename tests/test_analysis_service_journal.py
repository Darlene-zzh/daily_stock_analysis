# -*- coding: utf-8 -*-
"""End-to-end integration test for the Sprint 2 decision-journal hook.

Stubs out the heavy ``StockAnalysisPipeline`` so the test stays offline
and deterministic, then asserts:

1. First call with ``enable_decision_journal_reflection=False`` writes an
   entry but emits NO reflection block (the prompt assembler is checked
   via a recorded ``reflection_context_block`` arg).
2. Second call with ``enable_decision_journal_reflection=True`` reads
   the first entry, builds a reflection block, and threads it into the
   pipeline.  After this run the journal holds 2 entries.
3. Inserting a corrupt half-written entry between writes still lets the
   read path build a reflection (degraded — bad section skipped, valid
   ones surfaced).  No exception propagates.

This is the "stub-LLM smoke" required by Sprint 2 DONE step #5.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_pipeline_result() -> SimpleNamespace:
    """Mimic just enough of AnalysisResult for ``_build_analysis_response``
    + ``_write_journal_entry_safe`` to work."""
    return SimpleNamespace(
        code="600519",
        name="贵州茅台",
        success=True,
        sentiment_score=72,
        trend_prediction="震荡向上",
        operation_advice="逢低买入",
        report_language="zh",
        current_price=1700.0,
        change_pct=0.5,
        model_used="gpt-test",
        analysis_summary="护城河稳健，估值合理。",
        news_summary="",
        technical_analysis="",
        fundamental_analysis="",
        risk_warning="监管不确定性; 毛利率收窄",
        key_points="云业务回暖; ROIC 21%",
        buy_reason="",
        dashboard={"core_conclusion": {"one_sentence": "Buy on dips"}},
        portfolio_match=None,
        query_id="qid-stub",
        get_sniper_points=lambda: {},
    )


class _RecorderPipeline:
    """Stub pipeline that records the constructor kwargs (so the test can
    assert which ``reflection_context_block`` got threaded in) and returns
    a fresh AnalysisResult per call."""

    captured: List[Dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Capture every kwarg so the test can verify reflection threading.
        type(self).captured.append(dict(kwargs))

    def process_single_stock(self, code: str, **kwargs: Any) -> SimpleNamespace:
        return _make_pipeline_result()


@pytest.fixture(autouse=True)
def _reset_recorder() -> None:
    _RecorderPipeline.captured = []


@pytest.fixture()
def stub_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.services import analysis_service as _as_mod
    import src.core.pipeline as _pipeline_mod

    monkeypatch.setattr(
        _as_mod.AnalysisService,
        "_lookup_recent_cache_response",
        lambda self, code, rt: None,
    )
    monkeypatch.setattr(_as_mod, "StockAnalysisPipeline", _RecorderPipeline, raising=False)
    monkeypatch.setattr(_pipeline_mod, "StockAnalysisPipeline", _RecorderPipeline, raising=False)
    # Skip notification side-effect — its repo writes touch a real DB.
    monkeypatch.setattr(
        _as_mod.AnalysisService,
        "_build_analysis_response",
        _as_mod.AnalysisService._build_analysis_response,
    )


@pytest.fixture()
def journal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the journal base_dir to the tmp_path so writes don't pollute
    the repo's ``data/decision_journals/`` folder."""
    target = tmp_path / "journals"
    target.mkdir()
    from src.services import decision_journal_service as _dj

    original = _dj.DecisionJournalService.__init__

    def _init(self: Any, base_dir: Optional[Path] = None,
              *, fetcher_manager: Optional[Any] = None) -> None:
        original(self, base_dir=base_dir or target, fetcher_manager=fetcher_manager)

    monkeypatch.setattr(_dj.DecisionJournalService, "__init__", _init)
    return target


# Stub the alpha-fetching side so the reflection block doesn't try to
# contact the real fetcher network when running offline.
@pytest.fixture(autouse=True)
def _stub_alpha(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.services import decision_journal_service as _dj

    def _stub(self: Any, stock_code: str, market: str, lookback_days: int) -> None:
        return None  # forces compute_realised_alpha to return all None

    monkeypatch.setattr(
        _dj.DecisionJournalService,
        "_fetch_adjusted_kline",
        _stub,
    )


# Suppress the per-stock repo write (history persistence) — would
# require a real DB.
@pytest.fixture(autouse=True)
def _stub_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.repositories import analysis_repo as _repo_mod

    def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(_repo_mod.AnalysisRepository, "save", _noop, raising=False)
    monkeypatch.setattr(_repo_mod.AnalysisRepository, "update_committee_minutes", _noop, raising=False)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_first_call_writes_entry_but_emits_no_reflection_block(
    stub_pipeline: None, journal_root: Path
) -> None:
    from src.services.analysis_service import AnalysisService

    svc = AnalysisService()
    response = svc.analyze_stock(
        stock_code="600519",
        enable_decision_journal_reflection=False,
    )
    assert response is not None
    assert _RecorderPipeline.captured, "pipeline should have been constructed once"
    # Default-off: reflection_context_block must be None.
    assert _RecorderPipeline.captured[0].get("reflection_context_block") is None

    # Journal file exists with exactly one entry.
    journal_path = journal_root / "cn" / "600519.md"
    assert journal_path.exists()
    text = journal_path.read_text(encoding="utf-8")
    assert text.count("## 20") == 1
    assert "verdict: 逢低买入" in text
    assert "price_at_decision: 1700" in text


def test_second_call_with_reflection_threads_block_into_pipeline(
    stub_pipeline: None, journal_root: Path
) -> None:
    from src.services.analysis_service import AnalysisService

    svc = AnalysisService()
    # 1st call seeds the journal — keep reflection off.
    svc.analyze_stock(
        stock_code="600519",
        enable_decision_journal_reflection=False,
    )
    # 2nd call opts in to reflection.
    svc.analyze_stock(
        stock_code="600519",
        enable_decision_journal_reflection=True,
    )

    assert len(_RecorderPipeline.captured) == 2
    first_kwargs = _RecorderPipeline.captured[0]
    second_kwargs = _RecorderPipeline.captured[1]
    assert first_kwargs.get("reflection_context_block") is None
    block = second_kwargs.get("reflection_context_block")
    assert block is not None, "Second call must thread the reflection block"
    assert "Reflection" in block
    assert "prior verdict" in block
    assert "calibrate" in block  # closing directive

    # Journal now has 2 entries.
    journal_path = journal_root / "cn" / "600519.md"
    assert journal_path.read_text(encoding="utf-8").count("## 20") == 2


def test_reflection_skips_half_written_entry(
    stub_pipeline: None, journal_root: Path
) -> None:
    from src.services.analysis_service import AnalysisService

    svc = AnalysisService()
    svc.analyze_stock(
        stock_code="600519",
        enable_decision_journal_reflection=False,
    )

    # Forcibly append a corrupt half-written section between writes.  The
    # reflection read must skip it without raising and still surface the
    # valid entry.
    journal_path = journal_root / "cn" / "600519.md"
    with open(journal_path, "ab") as fh:
        fh.write(b"## broken-not-a-date\n- decision_at: bogus\n")

    svc.analyze_stock(
        stock_code="600519",
        enable_decision_journal_reflection=True,
    )
    # Two valid + one corrupt header that doesn't match the date regex
    # (so it is silently skipped on the read path).  No exception must
    # propagate — captured kwargs prove the pipeline was constructed.
    assert len(_RecorderPipeline.captured) == 2
    second_block = _RecorderPipeline.captured[1].get("reflection_context_block")
    assert second_block is not None
    assert "Reflection" in second_block


def test_task_queue_threads_reflection_flag_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sprint 1A parity — confirm the queue's executor passes the new flag
    through to ``AnalysisService.analyze_stock``."""
    from src.services import task_queue as _tq

    captured: Dict[str, Any] = {}

    class _StubService:
        def __init__(self) -> None:
            self.last_error: Optional[str] = None

        def analyze_stock(self, **kwargs: Any) -> Dict[str, Any]:
            captured.update(kwargs)
            return {"stock_code": kwargs["stock_code"], "report": {}}

    # Patch on the real module so the local import inside _execute_task
    # picks up the stub.
    import src.services.analysis_service as _as_mod
    monkeypatch.setattr(_as_mod, "AnalysisService", _StubService, raising=False)
    # Inject a stub queue directly to side-step executor setup.
    queue = _tq.AnalysisTaskQueue.__new__(_tq.AnalysisTaskQueue)
    queue._tasks = {}  # type: ignore[attr-defined]
    queue._data_lock = __import__("threading").Lock()  # type: ignore[attr-defined]
    queue._analyzing_stocks = {}  # type: ignore[attr-defined]
    queue._futures = {}  # type: ignore[attr-defined]
    queue._executor = None  # type: ignore[attr-defined]
    queue._broadcast_event = lambda *a, **kw: None  # type: ignore[attr-defined]
    queue.update_task_progress = lambda *a, **kw: None  # type: ignore[attr-defined]
    queue._cleanup_old_tasks = lambda: None  # type: ignore[attr-defined]

    # Build a fake task — _execute_task only needs a record in _tasks.
    task_id = "stub-task"
    queue._tasks[task_id] = _tq.TaskInfo(  # type: ignore[attr-defined]
        task_id=task_id,
        stock_code="600519",
        stock_name=None,
        status=_tq.TaskStatus.PENDING,
        message="pending",
        report_type="detailed",
    )
    queue._execute_task(
        task_id,
        "600519",
        "detailed",
        False,
        True,
        None,
        False,
        2,
        True,  # enable_decision_journal_reflection
    )
    assert captured.get("enable_decision_journal_reflection") is True
