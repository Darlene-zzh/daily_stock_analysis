"""Agent-path progress mapping: the agent loop must move the progress bar.

US stocks run the Agent path, which emits 58% ("切换 Agent 分析链路") and then
runs a multi-step tool-calling loop (+ committee) for minutes with no progress —
the bar froze at 58% and looked hung. `_agent_event_progress` maps the agent
runner's own loop events into a monotonic [59, 92] window.
"""
from __future__ import annotations

import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.pipeline import (
    _agent_event_progress,
    _AGENT_PROGRESS_LO,
    _AGENT_PROGRESS_HI,
)


def test_first_thinking_step_advances_past_58():
    p = _agent_event_progress({"type": "thinking", "step": 1}, 58)
    assert p > 58
    assert _AGENT_PROGRESS_LO <= p <= _AGENT_PROGRESS_HI


def test_progress_is_monotonic_across_steps():
    last = 58
    seen = []
    for step in range(1, 11):
        last = _agent_event_progress({"type": "thinking", "step": step}, last)
        seen.append(last)
    assert seen == sorted(seen)  # never goes backward
    assert all(_AGENT_PROGRESS_LO <= p <= _AGENT_PROGRESS_HI for p in seen)


def test_generating_event_jumps_to_high():
    assert _agent_event_progress({"type": "generating", "step": 3}, 65) == _AGENT_PROGRESS_HI


def test_capped_at_high_never_exceeds():
    p = _agent_event_progress({"type": "thinking", "step": 50}, 90)
    assert p == _AGENT_PROGRESS_HI


def test_signalless_event_still_nudges_forward():
    # stage_start / stage_done carry no step — must still move so long tool
    # stretches don't look frozen.
    p = _agent_event_progress({"type": "stage_start"}, 70)
    assert p > 70


def test_never_below_floor_even_from_low_last():
    p = _agent_event_progress({"type": "stage_done"}, 0)
    assert p >= _AGENT_PROGRESS_LO


def test_bool_step_not_treated_as_int():
    # bool is an int subclass; a stray True must not map to step=1.
    p = _agent_event_progress({"type": "thinking", "step": True}, 70)
    assert p == 72  # last + 2 nudge, not 59 + 1*3


def test_at_ceiling_stays_at_ceiling():
    p = _agent_event_progress({"type": "thinking", "step": 2}, _AGENT_PROGRESS_HI)
    assert p == _AGENT_PROGRESS_HI
