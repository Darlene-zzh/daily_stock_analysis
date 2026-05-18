# -*- coding: utf-8 -*-
"""Notification renderer contract tests (Sprint 1A Task 1A-5).

Covers spec §10:
- ``_render_committee_minutes`` emits a properly formatted section in both
  zh and en modes (heading, status banner, PM verdict, risk, debate, lens grid).
- Returns ``[]`` when the committee dict is missing / empty (graceful opt-out).
- ``status='partial'`` adds the partial banner + 'absent' badge for missing
  master lenses.
- ``status='failed'`` adds the inconclusive banner and suppresses the verdict
  card.
- Uses the single-source-of-truth ``PERSONA_DISPLAY`` mapping for lens names.
- The Discord empty-trailing-chunk guard (memory rule) is preserved — the
  renderer never emits a trailing empty list element by itself.
"""
from __future__ import annotations

import pytest

from src.notification import _render_committee_minutes


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


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
            {"side": "bull", "round_index": 2, "claim": "Buybacks compounding",
             "evidence": ["1", "2", "3"], "rebuttal_to": None, "confidence": 0.65, "status": "ok"},
            {"side": "bear", "round_index": 2, "claim": "Decel growth",
             "evidence": ["p", "q", "r"], "rebuttal_to": None, "confidence": 0.55, "status": "ok"},
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


def _failed_committee():
    payload = _ok_committee()
    payload["status"] = "failed"
    payload["pm_verdict"] = None
    payload["pm_rationale"] = None
    payload["error_summary"] = "PM crashed"
    return payload


# --------------------------------------------------------------------------- #
# Empty / opt-out behaviour
# --------------------------------------------------------------------------- #


def test_render_returns_empty_for_missing_data():
    assert _render_committee_minutes(None, labels={}, report_language="zh") == []
    assert _render_committee_minutes({}, labels={}, report_language="zh") == []


# --------------------------------------------------------------------------- #
# Happy path (status='ok')
# --------------------------------------------------------------------------- #


def test_render_happy_path_zh():
    lines = _render_committee_minutes(_ok_committee(), labels={}, report_language="zh")
    text = "\n".join(lines)
    # Heading
    assert "投委会会议纪要" in text
    # No status banner when ok
    assert "状态：部分完成" not in text
    assert "状态：未达成结论" not in text
    # PM verdict card
    assert "PM 决议" in text
    assert "`buy`" in text
    # Debate timeline rendered as `Round N — Bull: ...; Bear: ...`
    assert "Round 1 — Bull:" in text
    assert "Round 2 — Bull:" in text
    # Lens grid: persona display strings
    assert "Buffett-inspired value lens" in text
    assert "Cathie Wood-inspired innovation lens" in text
    # Chinese subtitle on first mention in zh mode
    assert "巴菲特式价值视角" in text
    # Budget footnote
    assert "LLM 调用预算：10/12" in text


def test_render_happy_path_en():
    lines = _render_committee_minutes(_ok_committee(), labels={}, report_language="en")
    text = "\n".join(lines)
    assert "Investment Committee Minutes" in text
    assert "PM verdict:" in text
    assert "Round 1 — Bull:" in text
    # English mode does NOT render the zh subtitle in parens
    assert "巴菲特式价值视角" not in text
    assert "Lens views" in text
    assert "LLM call budget: 10/12" in text


# --------------------------------------------------------------------------- #
# Partial status
# --------------------------------------------------------------------------- #


def test_render_partial_adds_banner_and_absent_badge():
    lines = _render_committee_minutes(_partial_committee(), labels={}, report_language="zh")
    text = "\n".join(lines)
    # Status banner
    assert "状态：部分完成" in text
    # Burry lens flagged as absent
    assert "Burry-inspired contrarian lens" in text
    assert "缺席" in text
    # PM verdict still rendered
    assert "PM 决议" in text


def test_render_partial_english_banner():
    lines = _render_committee_minutes(_partial_committee(), labels={}, report_language="en")
    text = "\n".join(lines)
    assert "Status: partial" in text
    assert "_(absent)_" in text


# --------------------------------------------------------------------------- #
# Failed status — verdict card suppressed
# --------------------------------------------------------------------------- #


def test_render_failed_suppresses_verdict_card():
    lines = _render_committee_minutes(_failed_committee(), labels={}, report_language="zh")
    text = "\n".join(lines)
    assert "状态：未达成结论" in text
    # No PM verdict card
    assert "PM 决议" not in text
    # The other sections (debate, lens grid) still render — informational
    assert "Round 1 — Bull:" in text


# --------------------------------------------------------------------------- #
# Risk section
# --------------------------------------------------------------------------- #


def test_render_risk_section_includes_severity_and_pos_pct():
    lines = _render_committee_minutes(_ok_committee(), labels={}, report_language="zh")
    text = "\n".join(lines)
    assert "severity=soft" in text
    # 0.15 → 15.0%
    assert "15.0%" in text


def test_render_risk_section_shows_veto_when_true():
    payload = _ok_committee()
    payload["risk"]["severity"] = "hard"
    payload["risk"]["veto"] = True
    lines = _render_committee_minutes(payload, labels={}, report_language="en")
    text = "\n".join(lines)
    assert "veto=true" in text


# --------------------------------------------------------------------------- #
# Discord empty-trailing-chunk guard (memory rule)
# --------------------------------------------------------------------------- #


def test_render_does_not_produce_only_empty_strings():
    """The function must not return a list whose only contents are empty strings.

    The Discord empty-chunk guard (user memory) relies on at least one
    meaningful line existing in any non-empty rendered section.
    """
    lines = _render_committee_minutes(_ok_committee(), labels={}, report_language="zh")
    non_empty = [l for l in lines if l.strip()]
    assert len(non_empty) > 0
    # And the section never starts with an empty line (heading is first)
    assert lines[0].startswith("### ")


# --------------------------------------------------------------------------- #
# Lens grid uses PERSONA_DISPLAY single source of truth
# --------------------------------------------------------------------------- #


def test_lens_grid_uses_persona_display_mapping():
    from src.agent.agents.master_personas import PERSONA_DISPLAY

    lines = _render_committee_minutes(_ok_committee(), labels={}, report_language="en")
    text = "\n".join(lines)
    # Every persona's display_en must appear in the rendered grid
    for pid, entry in PERSONA_DISPLAY.items():
        assert entry["display_en"] in text, (
            f"persona {pid} display_en {entry['display_en']!r} missing"
        )


# --------------------------------------------------------------------------- #
# PM dissents are surfaced
# --------------------------------------------------------------------------- #


def test_pm_dissents_are_rendered():
    lines = _render_committee_minutes(_ok_committee(), labels={}, report_language="zh")
    text = "\n".join(lines)
    assert "PM 异议" in text
    assert "michael_burry" in text
