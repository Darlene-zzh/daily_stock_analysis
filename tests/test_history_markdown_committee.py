# -*- coding: utf-8 -*-
"""History renderer parallel-update contract test (Sprint 1A Task 1A-5).

Per the repo memory rule, ``src/notification.py`` and
``src/services/history_service.py`` must grow ``_render_committee_minutes``
*structurally identical* output.  Drift between the two is a known footgun
(history page must match the push notification it summarises).

These tests:
- Run the history version against the same fixtures as
  ``tests/test_notification_committee.py``.
- Diff the two renderers' output — they MUST be byte-identical to lock in
  the parallel-update invariant.
"""
from __future__ import annotations

import pytest

from src.notification import _render_committee_minutes as render_notif
from src.services.history_service import _render_committee_minutes as render_history


def _ok_committee():
    return {
        "version": "1",
        "status": "ok",
        "debate_rounds": 2,
        "debate": [
            {"side": "bull", "round_index": 1, "claim": "Moat + reasonable price",
             "evidence": ["a", "b", "c"], "rebuttal_to": None, "confidence": 0.7, "status": "ok"},
            {"side": "bear", "round_index": 1, "claim": "Regulatory headwinds",
             "evidence": ["x", "y", "z"], "rebuttal_to": None, "confidence": 0.6, "status": "ok"},
        ],
        "masters": [
            {"persona": "warren_buffett", "verdict": "buy", "score": 7.5,
             "headline": "Durable moat with margin of safety",
             "rationale": "x", "key_evidence": ["a"], "status": "ok"},
            {"persona": "michael_burry", "verdict": "hold", "score": 5.5,
             "headline": "Catalysts unclear",
             "rationale": "x", "key_evidence": ["a"], "status": "ok"},
            {"persona": "cathie_wood", "verdict": "buy", "score": 7.0,
             "headline": "Compounder under disruption umbrella",
             "rationale": "x", "key_evidence": ["a"], "status": "ok"},
            {"persona": "nassim_taleb", "verdict": "hold", "score": 6.0,
             "headline": "Symmetric payoff for now",
             "rationale": "x", "key_evidence": ["a"], "status": "ok"},
        ],
        "risk": {"severity": "soft", "red_flags": ["earnings next week"],
                 "suggested_position_pct": 0.15, "veto": False, "status": "ok"},
        "pm_verdict": "buy", "pm_score": 7.0,
        "pm_rationale": "Three lenses constructive, risk soft.",
        "pm_dissents": ["michael_burry"],
        "budget_used": 10, "budget_cap": 12,
        "missing_agents": [],
        "latency_ms": 1234,
    }


def _partial_committee():
    payload = _ok_committee()
    payload["status"] = "partial"
    payload["missing_agents"] = ["master_michael_burry"]
    payload["masters"][1] = {
        "persona": "michael_burry", "status": "failed",
        "error_summary": "timeout", "key_evidence": [],
    }
    return payload


# --------------------------------------------------------------------------- #
# Functional contract — history renderer behaves the same as notification
# --------------------------------------------------------------------------- #


def test_history_renderer_empty_for_missing_data():
    assert render_history(None, labels={}, report_language="zh") == []
    assert render_history({}, labels={}, report_language="zh") == []


@pytest.mark.parametrize("language", ["zh", "en"])
def test_history_renderer_happy_path(language):
    lines = render_history(_ok_committee(), labels={}, report_language=language)
    text = "\n".join(lines)
    if language == "zh":
        assert "投委会会议纪要" in text
        assert "PM 决议" in text
    else:
        assert "Investment Committee Minutes" in text
        assert "PM verdict:" in text
    # Debate timeline rendered
    assert "Round 1 — Bull:" in text


def test_history_renderer_partial_banner():
    lines = render_history(_partial_committee(), labels={}, report_language="zh")
    text = "\n".join(lines)
    assert "状态：部分完成" in text


# --------------------------------------------------------------------------- #
# Parallel-update invariant — outputs must match notification renderer
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize(
    "fixture_factory",
    [_ok_committee, _partial_committee],
    ids=["ok", "partial"],
)
def test_history_matches_notification_renderer(fixture_factory, language):
    """Both renderers MUST produce structurally identical markdown.

    This locks in the repo memory rule: any change to one renderer's
    committee section MUST be mirrored in the other.
    """
    payload = fixture_factory()
    notif_lines = render_notif(payload, labels={}, report_language=language)
    hist_lines = render_history(payload, labels={}, report_language=language)
    assert notif_lines == hist_lines, (
        f"Notification + history renderers must produce identical output "
        f"(memory rule: parallel-update invariant). Drift detected for "
        f"fixture={fixture_factory.__name__}, language={language!r}.\n"
        f"notification first-line: {notif_lines[0] if notif_lines else '<empty>'!r}\n"
        f"history first-line: {hist_lines[0] if hist_lines else '<empty>'!r}"
    )
