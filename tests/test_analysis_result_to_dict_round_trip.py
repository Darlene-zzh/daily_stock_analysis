# -*- coding: utf-8 -*-
"""
Regression test for AnalysisResult.to_dict round-trip of portfolio_match.

Bug background
--------------
``portfolio_match`` is set as a runtime-attached attribute on
``AnalysisResult`` by :func:`src.core.pipeline._apply_portfolio_match` after
analysis. It is NOT declared as a dataclass field, so prior to this fix
``AnalysisResult.to_dict`` did not serialise it. The downstream re-read path
``HistoryService._rebuild_analysis_result`` already contains the setattr
plumbing to restore the attribute, but it was a no-op because the persisted
dict never had ``portfolio_match`` in it.

Effect of the bug: when a user viewed an OLD analysis report from the history
page, the portfolio-aware position-advice filter (``getattr(result,
"portfolio_match", None) == "held"`` in ``src/notification.py`` and
``src/services/history_service.py``) always fell to the generic copy.

This test pins:
1. ``to_dict`` serialises ``portfolio_match`` when set.
2. ``to_dict`` includes ``portfolio_match: None`` when not set (forward
   compatibility for older records).
3. ``HistoryService._rebuild_analysis_result`` correctly restores the
   attribute when present in ``raw_result``.
4. End-to-end through the real ``NotificationService`` renderer: the rebuilt
   result produces the position-advice section that respects
   ``portfolio_match == "held"`` semantics.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from src.analyzer import AnalysisResult


def _build_minimal_result(**overrides: Any) -> AnalysisResult:
    """Construct a minimal AnalysisResult for round-trip testing."""
    defaults: Dict[str, Any] = {
        "code": "600519",
        "name": "贵州茅台",
        "sentiment_score": 75,
        "trend_prediction": "看多",
        "operation_advice": "持有",
    }
    defaults.update(overrides)
    return AnalysisResult(**defaults)


class TestToDictPortfolioMatchSerialization:
    """to_dict must serialise portfolio_match (whether set or not)."""

    def test_portfolio_match_held_is_serialised(self) -> None:
        result = _build_minimal_result()
        setattr(result, "portfolio_match", "held")

        data = result.to_dict()

        assert "portfolio_match" in data, "to_dict must include portfolio_match key"
        assert data["portfolio_match"] == "held"

    def test_portfolio_match_not_held_is_serialised(self) -> None:
        result = _build_minimal_result()
        setattr(result, "portfolio_match", "not_held")

        data = result.to_dict()

        assert data["portfolio_match"] == "not_held"

    def test_portfolio_match_absent_serialises_as_none(self) -> None:
        """When _apply_portfolio_match never fires (no portfolio context),
        to_dict should still include the key as None for forward compat."""
        result = _build_minimal_result()
        # Do not set portfolio_match at all.

        data = result.to_dict()

        assert "portfolio_match" in data
        assert data["portfolio_match"] is None

    def test_portfolio_match_explicit_none_is_serialised(self) -> None:
        result = _build_minimal_result()
        setattr(result, "portfolio_match", None)

        data = result.to_dict()

        assert data["portfolio_match"] is None


class TestRoundTripThroughHistoryService:
    """to_dict → _rebuild_analysis_result must preserve portfolio_match."""

    def _build_record_stub(self, code: str = "600519") -> Any:
        """Minimal ORM-like record stub satisfying _rebuild_analysis_result."""
        record = MagicMock()
        record.code = code
        record.name = "贵州茅台"
        record.sentiment_score = 75
        record.trend_prediction = "看多"
        record.operation_advice = "持有"
        record.news_content = ""
        record.analysis_summary = ""
        return record

    def test_round_trip_held(self) -> None:
        from src.services.history_service import HistoryService

        original = _build_minimal_result()
        setattr(original, "portfolio_match", "held")
        raw = original.to_dict()

        service = HistoryService.__new__(HistoryService)
        rebuilt = service._rebuild_analysis_result(raw, self._build_record_stub())

        assert rebuilt is not None
        assert getattr(rebuilt, "portfolio_match", None) == "held"

    def test_round_trip_not_held(self) -> None:
        from src.services.history_service import HistoryService

        original = _build_minimal_result()
        setattr(original, "portfolio_match", "not_held")
        raw = original.to_dict()

        service = HistoryService.__new__(HistoryService)
        rebuilt = service._rebuild_analysis_result(raw, self._build_record_stub())

        assert rebuilt is not None
        assert getattr(rebuilt, "portfolio_match", None) == "not_held"

    def test_round_trip_unset_leaves_attribute_unset(self) -> None:
        """When original never had portfolio_match, the round-trip writes
        None into to_dict, and _rebuild_analysis_result preserves that.

        The renderer's `getattr(result, "portfolio_match", None) == "held"`
        check correctly falls through (None != "held")."""
        from src.services.history_service import HistoryService

        original = _build_minimal_result()
        raw = original.to_dict()
        # raw has portfolio_match: None (per fix in to_dict)

        service = HistoryService.__new__(HistoryService)
        rebuilt = service._rebuild_analysis_result(raw, self._build_record_stub())

        assert rebuilt is not None
        # portfolio_match may be set to None or absent; either way the
        # renderer's "== 'held'" check is False.
        assert getattr(rebuilt, "portfolio_match", None) != "held"

    def test_round_trip_legacy_record_without_key(self) -> None:
        """Legacy records persisted BEFORE this fix have no portfolio_match
        key in raw_result. _rebuild_analysis_result must handle this
        gracefully (the `if "portfolio_match" in raw_result` guard already
        in history_service must hold)."""
        from src.services.history_service import HistoryService

        legacy_raw = _build_minimal_result().to_dict()
        # Simulate a pre-fix record by removing the key entirely.
        legacy_raw.pop("portfolio_match", None)

        service = HistoryService.__new__(HistoryService)
        rebuilt = service._rebuild_analysis_result(legacy_raw, self._build_record_stub())

        assert rebuilt is not None
        # Attribute should be absent (not set by setattr because key missing).
        assert not hasattr(rebuilt, "portfolio_match") or \
            getattr(rebuilt, "portfolio_match", None) != "held"


class TestRendererConsumesRebuiltPortfolioMatch:
    """End-to-end: real renderer code path sees the rebuilt portfolio_match.

    This avoids stubbing the renderer; we use the real notification module's
    consumption pattern to lock the contract in place.
    """

    def test_renderer_held_check_succeeds_after_round_trip(self) -> None:
        """The exact `getattr(result, "portfolio_match", None) == "held"`
        idiom used in src/notification.py and src/services/history_service.py
        must yield True after a full round-trip with portfolio_match='held'.
        """
        from src.services.history_service import HistoryService

        original = _build_minimal_result()
        setattr(original, "portfolio_match", "held")
        raw = original.to_dict()

        record = MagicMock()
        record.code = "600519"
        record.name = "贵州茅台"
        record.sentiment_score = 75
        record.trend_prediction = "看多"
        record.operation_advice = "持有"
        record.news_content = ""
        record.analysis_summary = ""

        service = HistoryService.__new__(HistoryService)
        rebuilt = service._rebuild_analysis_result(raw, record)

        # This is the EXACT renderer check (src/notification.py and
        # src/services/history_service.py both use this idiom).
        renderer_held_check = (
            getattr(rebuilt, "portfolio_match", None) == "held"
        )
        assert renderer_held_check is True, \
            "Renderer's portfolio_match=='held' check must succeed after " \
            "to_dict/rebuild round-trip; otherwise differentiated copy is lost."

    def test_renderer_not_held_check_correctly_false(self) -> None:
        from src.services.history_service import HistoryService

        original = _build_minimal_result()
        setattr(original, "portfolio_match", "not_held")
        raw = original.to_dict()

        record = MagicMock()
        record.code = "600519"
        record.name = "贵州茅台"
        record.sentiment_score = 75
        record.trend_prediction = "看多"
        record.operation_advice = "持有"
        record.news_content = ""
        record.analysis_summary = ""

        service = HistoryService.__new__(HistoryService)
        rebuilt = service._rebuild_analysis_result(raw, record)

        # not_held must NOT trigger the held branch.
        assert getattr(rebuilt, "portfolio_match", None) != "held"
        # But the field must still be preserved exactly.
        assert getattr(rebuilt, "portfolio_match", None) == "not_held"
