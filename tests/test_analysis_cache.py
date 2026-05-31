"""Tests for `AnalysisService._lookup_recent_cache_response` — the 24h same-stock
cache that short-circuits the LLM call when a recent analysis exists.

Reason this matters: Gemini's free tier has a 20 RPD shared bucket. A user who
re-clicks "analyze" on the same stock would otherwise burn 5-10 calls per re-run.
The cache lets the dashboard re-open without re-billing.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _fake_recent_record(*, age_hours: float, success: bool = True):
    """Build a mock AnalysisHistory row close enough to satisfy the helper."""
    rec = MagicMock()
    rec.created_at = datetime.now() - timedelta(hours=age_hours)
    rec.query_id = "cached-query-123"
    rec.stock_name = "Microsoft Corporation"
    rec.raw_result = {
        "code": "MSFT",
        "name": "Microsoft Corporation",
        "sentiment_score": 76,
        "trend_prediction": "看多",
        "operation_advice": "持有",
        "decision_type": "hold",
        "success": success,
        "current_price": 421.92,
        "change_pct": 0.5,
        "model_used": "gemini/gemini-2.5-flash",
        "report_language": "zh",
        "dashboard": {"core_conclusion": {"recommended_strategy": "stepped_profit_taking"}},
    }
    return rec


class AnalysisCacheLookupTestCase(unittest.TestCase):

    def setUp(self) -> None:
        os.environ.pop("ANALYSIS_CACHE_HOURS", None)

    def test_hit_when_recent_record_exists_within_window(self):
        from src.services.analysis_service import AnalysisService

        os.environ["ANALYSIS_CACHE_HOURS"] = "24"
        service = AnalysisService()
        with patch.object(service.repo, "get_list", return_value=[_fake_recent_record(age_hours=3)]):
            response = service._lookup_recent_cache_response("MSFT", "detailed")
        self.assertIsNotNone(response)
        meta = response["report"]["meta"]
        self.assertTrue(meta["cached"])
        self.assertGreater(meta["cache_age_seconds"], 0)
        self.assertIn("cached_at", meta)

    def test_miss_when_record_older_than_window(self):
        from src.services.analysis_service import AnalysisService

        os.environ["ANALYSIS_CACHE_HOURS"] = "24"
        service = AnalysisService()
        with patch.object(service.repo, "get_list", return_value=[_fake_recent_record(age_hours=48)]):
            response = service._lookup_recent_cache_response("MSFT", "detailed")
        self.assertIsNone(response)

    def test_miss_when_caching_disabled(self):
        from src.services.analysis_service import AnalysisService

        os.environ["ANALYSIS_CACHE_HOURS"] = "0"
        service = AnalysisService()
        with patch.object(service.repo, "get_list", return_value=[_fake_recent_record(age_hours=1)]):
            response = service._lookup_recent_cache_response("MSFT", "detailed")
        self.assertIsNone(response)

    def test_miss_when_no_recent_records(self):
        from src.services.analysis_service import AnalysisService

        os.environ["ANALYSIS_CACHE_HOURS"] = "24"
        service = AnalysisService()
        with patch.object(service.repo, "get_list", return_value=[]):
            response = service._lookup_recent_cache_response("MSFT", "detailed")
        self.assertIsNone(response)

    def test_miss_when_recent_record_was_a_failed_analysis(self):
        """Failed analyses must not be cached — re-running could succeed."""
        from src.services.analysis_service import AnalysisService

        os.environ["ANALYSIS_CACHE_HOURS"] = "24"
        service = AnalysisService()
        with patch.object(
            service.repo, "get_list",
            return_value=[_fake_recent_record(age_hours=2, success=False)]
        ):
            response = service._lookup_recent_cache_response("MSFT", "detailed")
        self.assertIsNone(response)

    def test_invalid_env_value_disables_cache_gracefully(self):
        from src.services.analysis_service import AnalysisService

        os.environ["ANALYSIS_CACHE_HOURS"] = "not-a-number"
        service = AnalysisService()
        with patch.object(service.repo, "get_list", return_value=[_fake_recent_record(age_hours=1)]):
            response = service._lookup_recent_cache_response("MSFT", "detailed")
        self.assertIsNone(response)


def _fake_recent_record_with_committee(*, age_hours: float):
    """Mock AnalysisHistory row whose dashboard carries the late-bound
    committee + risk_assessment payloads. Mirrors what
    ``update_committee_minutes`` writes back after a prior run with
    ``enable_investment_committee=True`` succeeded."""
    rec = _fake_recent_record(age_hours=age_hours)
    rec.raw_result["dashboard"] = {
        "core_conclusion": {"recommended_strategy": "stepped_profit_taking"},
        "committee": {
            "version": "1",
            "status": "ok",
            "pm_verdict": "buy",
            "pm_score": 7.5,
            "masters": [{"persona": "warren_buffett", "verdict": "buy", "score": 7.0}],
            "debate": [],
            "pm_dissents": [],
        },
        "risk_assessment": {
            "severity": "soft",
            "suggested_position_pct": 0.3,
            "red_flags": [],
        },
    }
    return rec


class AnalysisCacheCommitteeLiftTestCase(unittest.TestCase):
    """Regression: the 24h same-stock cache path must surface ``committee`` and
    ``risk_assessment`` at the report top level just like the live + history
    paths. Without this lift, the frontend ``ReportSummary`` destructure
    (``{committee, riskAssessment} = report``) silently misses the panels on
    cache hits — even though the same data renders fine after a manual
    refresh (which routes through GET /history/{id}, where the lift already
    exists)."""

    def setUp(self) -> None:
        os.environ.pop("ANALYSIS_CACHE_HOURS", None)
        os.environ["ANALYSIS_CACHE_HOURS"] = "24"

    def test_committee_lifted_to_report_top_level_on_cache_hit(self):
        from src.services.analysis_service import AnalysisService

        service = AnalysisService()
        with patch.object(
            service.repo, "get_list",
            return_value=[_fake_recent_record_with_committee(age_hours=2)],
        ):
            response = service._lookup_recent_cache_response("MSFT", "detailed")

        self.assertIsNotNone(response)
        report = response["report"]
        self.assertIn("committee", report,
                      "committee must be lifted to report top level for the "
                      "frontend destructure to find it")
        self.assertIsInstance(report["committee"], dict)
        self.assertEqual(report["committee"]["pm_verdict"], "buy")
        self.assertEqual(report["committee"]["pm_score"], 7.5)
        self.assertEqual(len(report["committee"]["masters"]), 1)

    def test_risk_assessment_lifted_to_report_top_level_on_cache_hit(self):
        from src.services.analysis_service import AnalysisService

        service = AnalysisService()
        with patch.object(
            service.repo, "get_list",
            return_value=[_fake_recent_record_with_committee(age_hours=2)],
        ):
            response = service._lookup_recent_cache_response("MSFT", "detailed")

        self.assertIsNotNone(response)
        report = response["report"]
        self.assertIn("risk_assessment", report,
                      "risk_assessment must be lifted to report top level "
                      "for StructuredRiskCallout to render")
        self.assertEqual(report["risk_assessment"]["severity"], "soft")
        self.assertEqual(report["risk_assessment"]["suggested_position_pct"], 0.3)

    def test_no_committee_in_dashboard_means_top_level_stays_unset(self):
        """When the cached dashboard does not carry committee (user did not opt
        in on the prior run), the lift is a no-op — ``report.committee`` stays
        absent so the optional panel renders nothing."""
        from src.services.analysis_service import AnalysisService

        service = AnalysisService()
        with patch.object(
            service.repo, "get_list",
            return_value=[_fake_recent_record(age_hours=2)],
        ):
            response = service._lookup_recent_cache_response("MSFT", "detailed")

        self.assertIsNotNone(response)
        report = response["report"]
        self.assertNotIn("committee", report)
        self.assertNotIn("risk_assessment", report)

    def test_committee_still_in_dashboard_after_lift(self):
        """The lift copies, not moves — dashboard.committee must remain so
        Markdown renderers (notification.py, history_service.py) can still
        pick it up via ``dashboard.committee`` like other dashboard sections."""
        from src.services.analysis_service import AnalysisService

        service = AnalysisService()
        with patch.object(
            service.repo, "get_list",
            return_value=[_fake_recent_record_with_committee(age_hours=2)],
        ):
            response = service._lookup_recent_cache_response("MSFT", "detailed")

        dashboard = response["report"]["dashboard"]
        self.assertIn("committee", dashboard)
        self.assertEqual(dashboard["committee"]["pm_verdict"], "buy")


if __name__ == "__main__":
    unittest.main()
