# -*- coding: utf-8 -*-
"""LLM call budget enforcement (Sprint 1A).

The Investment Committee fan-out can quickly burn quota.  Every node in the
LangGraph state machine **must** acquire a slot from the
:class:`LLMCallBudget` before invoking the LLM.

Cap is computed at runtime from ``INVESTMENT_COMMITTEE_BUDGET_BASE``:

::

    cap = base + 2 * (debate_rounds - 1)
    → 10 / 12 / 14 calls for 1 / 2 / 3 rounds

The Web UI surfaces this same arithmetic to the user before opt-in.

The budget is **best-effort, not transactional** — there is no rollback on
``release()``.  If a node times out and we fall back to a cached opinion, the
acquire is already accounted for; we will simply have one fewer slot for any
later node.  The graph's PM node short-circuits gracefully when budget is
exhausted (the spec marks this as ``budget_exhausted`` and the PM still
issues a verdict using whatever state did complete).
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Defaults — matches `.env.example` and spec §13 locked decisions.
DEFAULT_BUDGET_BASE = 12
DEFAULT_TIMEOUT_S = 90


def compute_effective_cap(debate_rounds: int, base: Optional[int] = None) -> int:
    """Return ``base + 2 * (rounds - 1)`` clamped to a positive integer.

    ``base`` defaults to the value in env var
    ``INVESTMENT_COMMITTEE_BUDGET_BASE`` (or :data:`DEFAULT_BUDGET_BASE` if
    unset).  ``rounds`` is clamped to [1, 3] to match the Web UI selector.
    """
    if base is None:
        try:
            base = int(os.getenv("INVESTMENT_COMMITTEE_BUDGET_BASE", str(DEFAULT_BUDGET_BASE)))
        except ValueError:
            base = DEFAULT_BUDGET_BASE
    # Clamp rounds to [1, 3] — invalid values (None/0/negative) treated as 1
    # round (minimum), not as the default; that way a stray 0 doesn't inflate
    # the budget back up to the 2-round cap.
    try:
        rounds_int = int(debate_rounds) if debate_rounds is not None else 1
    except (TypeError, ValueError):
        rounds_int = 1
    rounds = max(1, min(3, rounds_int))
    return max(1, base + 2 * (rounds - 1))


@dataclass
class LLMCallBudget:
    """Lightweight, thread-safe counter for committee LLM calls.

    Attributes
    ----------
    cap
        Hard cap on the number of acquisitions.
    used
        Total successful acquires (read-only externally).
    rejected
        Number of attempted acquires after the cap was reached.
    log
        Ordered list of ``(node_name, accepted)`` tuples for diagnostics.
    """

    cap: int = DEFAULT_BUDGET_BASE
    used: int = 0
    rejected: int = 0
    log: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        if self.cap <= 0:
            self.cap = max(1, DEFAULT_BUDGET_BASE)

    def acquire(self, node_name: str) -> bool:
        """Request a slot. Returns True if accepted."""
        with self._lock:
            if self.used >= self.cap:
                self.rejected += 1
                self.log.append({"node": node_name, "accepted": False, "used": self.used})
                logger.info(
                    "[budget] node=%s REJECTED (used=%d cap=%d)",
                    node_name, self.used, self.cap,
                )
                return False
            self.used += 1
            self.log.append({"node": node_name, "accepted": True, "used": self.used})
            return True

    def remaining(self) -> int:
        with self._lock:
            return max(0, self.cap - self.used)

    def exhausted(self) -> bool:
        return self.remaining() == 0

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "cap": self.cap,
                "used": self.used,
                "remaining": max(0, self.cap - self.used),
                "rejected": self.rejected,
            }


def resolve_timeout_s() -> int:
    """Return the orchestrator wall-clock timeout in seconds (env-driven)."""
    raw = os.getenv("INVESTMENT_COMMITTEE_TIMEOUT_S", str(DEFAULT_TIMEOUT_S))
    try:
        v = int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return max(10, v)


def committee_default_enabled() -> bool:
    """Return whether the committee is on by default (rarely; usually False)."""
    raw = os.getenv("INVESTMENT_COMMITTEE_ENABLED_BY_DEFAULT", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}
