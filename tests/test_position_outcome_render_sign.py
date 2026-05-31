"""Check #Issue-2 — position-outcome renderer must be sign-aware.

A profit-protecting stop placed ABOVE cost yields a POSITIVE worst-case P&L
(observed on MSFT: stop $415.25 vs avg cost $396.81 -> +8.67, still profit).
The renderers previously printed the bare number under the "最差止损" label,
which the web UI painted red — making a gain look like a loss. The text
renderers now prefix a non-negative worst case with "+" so it reads as a gain;
the two renderers must stay byte-identical ([[repo-dual-renderers]]).
"""
from __future__ import annotations

import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.notification import _render_position_outcome as render_notif
from src.services.history_service import _render_position_outcome as render_hist


def _outcome(worst):
    return {
        "remaining_shares_after_all_triggers": 0.0124,
        "worst_case_loss_pct": 1.8,
        "worst_case_loss_amount": worst,
        "worst_case_currency": "GBP",
        "best_case_gain_pct": 9.9,
        "best_case_gain_amount": 46.51,
        "risk_reward_ratio": "N/A",
    }


def test_positive_worst_case_shown_as_gain_with_plus():
    lines = render_notif(_outcome(8.67), {})
    body = "\n".join(lines)
    assert "最差止损：+8.67 GBP" in body
    assert "最差止损：8.67 GBP" not in body  # no bare ambiguous number


def test_negative_worst_case_keeps_minus_no_plus():
    lines = render_notif(_outcome(-10.0), {})
    body = "\n".join(lines)
    assert "最差止损：-10.0 GBP" in body
    assert "+-10" not in body


def test_two_renderers_byte_identical_for_outcome_block():
    for worst in (8.67, -10.0, 0.0):
        assert render_notif(_outcome(worst), {}) == render_hist(_outcome(worst), {})
