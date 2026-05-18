# -*- coding: utf-8 -*-
"""Sprint 4 — both renderers produce byte-identical markdown for risk_assessment.

This enforces the long-standing repo invariant captured in memory:

    Two markdown renderers (``src/notification.py`` + ``src/services/history_service.py``)
    need parallel updates.

If either side drifts, the user sees a different report depending on whether
they read the push notification or the history page.  These tests fail loud
when that drift happens.
"""

from __future__ import annotations

import unittest

from src.notification import _render_structured_risk as render_notification
from src.services.history_service import _render_structured_risk as render_history


SAMPLE_PAYLOAD = {
    "severity": "soft",
    "red_flags": [
        "[earnings] EPS miss vs. consensus",
        "[lockup] Major shareholder unlock in 14 days",
    ],
    "suggested_position_pct": 0.12,
    "tail_risk_score": 6.5,
    "var_estimate_5pct": 0.034,
    "volatility_annualised": 0.32,
    "veto": False,
    "status": "ok",
    "rationale": "Mixed signals — concentration risk warrants a soft tier.",
}


HARD_PAYLOAD = {
    "severity": "hard",
    "red_flags": ["[regulatory] Active investigation"],
    "suggested_position_pct": 0.0,
    "tail_risk_score": 9.2,
    "var_estimate_5pct": 0.085,
    "volatility_annualised": 0.65,
    "veto": True,
    "status": "ok",
}


SPARSE_PAYLOAD = {
    "severity": "none",
    "red_flags": [],
    "suggested_position_pct": 0.25,
    # tail_risk_score / var_estimate_5pct / volatility_annualised intentionally
    # absent — the renderer must skip those metric lines.
    "veto": False,
    "status": "ok",
}


class TestRendererParity(unittest.TestCase):
    def test_zh_renderers_byte_identical_for_full_payload(self) -> None:
        zh_n = render_notification(SAMPLE_PAYLOAD, "zh")
        zh_h = render_history(SAMPLE_PAYLOAD, "zh")
        self.assertEqual(zh_n, zh_h)
        # Sanity: the section heading is present
        self.assertEqual(zh_n[0], "## 🛡️ 风险评估")
        # Severity badge line carries the soft tier and the suggested position
        joined = "\n".join(zh_n)
        self.assertIn("soft", joined)
        self.assertIn("12.0%", joined)
        # Tail-risk + VaR + vol all surface
        self.assertIn("尾部风险评分: 6.50 / 10", joined)
        self.assertIn("1 日 5% VaR: 3.40%", joined)
        self.assertIn("年化波动率: 32.0%", joined)
        # Red flags rendered as bullets
        self.assertIn("- [earnings] EPS miss vs. consensus", joined)

    def test_en_renderers_byte_identical_for_full_payload(self) -> None:
        en_n = render_notification(SAMPLE_PAYLOAD, "en")
        en_h = render_history(SAMPLE_PAYLOAD, "en")
        self.assertEqual(en_n, en_h)
        self.assertEqual(en_n[0], "## 🛡️ Risk Assessment")
        joined = "\n".join(en_n)
        self.assertIn("Tail-risk score: 6.50 / 10", joined)
        self.assertIn("1-day 5% VaR: 3.40%", joined)

    def test_hard_severity_renders_veto_in_both(self) -> None:
        for lang in ("zh", "en"):
            n = render_notification(HARD_PAYLOAD, lang)
            h = render_history(HARD_PAYLOAD, lang)
            self.assertEqual(n, h, f"{lang} mismatch on hard payload")
            joined = "\n".join(n)
            self.assertIn("hard", joined)
            self.assertIn("veto=true", joined)

    def test_sparse_payload_omits_optional_metrics_in_both(self) -> None:
        for lang in ("zh", "en"):
            n = render_notification(SPARSE_PAYLOAD, lang)
            h = render_history(SPARSE_PAYLOAD, lang)
            self.assertEqual(n, h, f"{lang} mismatch on sparse payload")
            joined = "\n".join(n)
            self.assertNotIn("VaR", joined)
            self.assertNotIn("尾部风险评分", joined)
            self.assertNotIn("Tail-risk", joined)
            self.assertNotIn("年化波动率", joined)
            # Position is still rendered because it's the primary number
            self.assertIn("25.0%", joined)

    def test_none_payload_renders_empty_in_both(self) -> None:
        for empty in (None, {}, [], 0, ""):
            n = render_notification(empty, "zh")  # type: ignore[arg-type]
            h = render_history(empty, "zh")  # type: ignore[arg-type]
            self.assertEqual(n, h)
            self.assertEqual(n, [])

    def test_missing_renderers_dont_emit_section_heading_for_empty(self) -> None:
        # Belt-and-suspenders: ``"## 🛡️"`` must NOT show up when there's no payload
        for empty in (None, {}):
            for lang in ("zh", "en"):
                n = render_notification(empty, lang)  # type: ignore[arg-type]
                self.assertEqual(n, [])


if __name__ == "__main__":
    unittest.main()
