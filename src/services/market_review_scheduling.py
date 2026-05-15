# -*- coding: utf-8 -*-
"""Market-review scheduling: parse slots, compute next firing in market-local time.

The legacy scheduler runs a single `--market-review` job at a single
`SCHEDULE_TIME` once per day in server-local time. That model can't express
"A-share open + close in Chinese, US open + close in bilingual, skip HK".

This module owns the new slot grammar and the per-slot "what's the next
firing time" calculation. The scheduler loop calls :func:`due_slots` once
per tick; whichever slots became due since the last tick are returned with
last-fired timestamps recorded so we never double-fire across loop
iterations or daylight-saving transitions.

Slot grammar
------------

``MARKET_REVIEW_SLOTS`` is a comma-separated list. Each slot is three
fields joined by ``:`` :

    <market>:<session>:<language>

* ``market``   — ``cn`` (Shanghai), ``us`` (NYSE/NASDAQ), ``hk`` (HKEX).
* ``session``  — ``open`` or ``close``. The market's local open/close
  time is hard-coded below; users pick the session, not a clock time.
* ``language`` — ``zh`` (Chinese), ``en`` (English), or ``bi`` (bilingual
  paragraph-by-paragraph English with Chinese translation underneath).

Whitespace around tokens is allowed; duplicate slots are deduplicated.
Markets are only fired Mon–Fri to avoid weekend phantom runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo  # type: ignore[import]
except ImportError:  # pragma: no cover - Python 3.9+ ships zoneinfo
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


MARKET_SESSIONS: Dict[str, Dict[str, Tuple[str, Tuple[int, int]]]] = {
    "cn": {
        "tz": "Asia/Shanghai",
        "open": (9, 30),
        "close": (15, 0),
    },
    "us": {
        "tz": "America/New_York",
        "open": (9, 30),
        "close": (16, 0),
    },
    "hk": {
        "tz": "Asia/Hong_Kong",
        "open": (9, 30),
        "close": (16, 0),
    },
}

VALID_SESSIONS = {"open", "close"}
VALID_LANGUAGES = {"zh", "en", "bi"}

DEFAULT_SLOTS = "cn:open:zh,cn:close:zh,us:open:bi,us:close:bi"


@dataclass(frozen=True)
class MarketReviewSlot:
    """One scheduled market-review firing: (market, session, language)."""

    market: str
    session: str
    language: str

    @property
    def key(self) -> str:
        return f"{self.market}:{self.session}:{self.language}"

    def next_fire(self, after: datetime) -> datetime:
        """Return the next UTC datetime this slot should fire after ``after``.

        ``after`` may be naive or aware; we treat naive datetimes as UTC.
        Weekends are skipped (open/close don't happen Sat/Sun in practice
        for these markets — the scheduler shouldn't run reports then).
        """
        sess = MARKET_SESSIONS[self.market]
        market_tz = ZoneInfo(sess["tz"])
        hour, minute = sess[self.session]

        after_utc = _ensure_utc(after)
        cursor = after_utc.astimezone(market_tz).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if cursor <= after_utc.astimezone(market_tz):
            cursor += timedelta(days=1)
        # Skip weekends; cap at 7 iterations to avoid pathological loops.
        for _ in range(7):
            if cursor.weekday() < 5:
                break
            cursor += timedelta(days=1)
        return cursor.astimezone(timezone.utc)


def parse_slots(raw: Optional[str]) -> List[MarketReviewSlot]:
    """Parse a ``MARKET_REVIEW_SLOTS`` value into slot objects.

    Malformed / unknown tokens are logged at WARNING level and skipped so
    one typo can't kill the whole scheduler.
    """
    if raw is None or not raw.strip():
        raw = DEFAULT_SLOTS

    slots: List[MarketReviewSlot] = []
    seen: set = set()
    for token in raw.split(","):
        cleaned = token.strip().lower()
        if not cleaned:
            continue
        parts = cleaned.split(":")
        if len(parts) != 3:
            logger.warning(
                "MARKET_REVIEW_SLOTS: skipping malformed entry %r "
                "(expected <market>:<session>:<language>)",
                token,
            )
            continue
        market, session, language = parts
        if market not in MARKET_SESSIONS:
            logger.warning(
                "MARKET_REVIEW_SLOTS: skipping entry %r (unknown market %r)",
                token, market,
            )
            continue
        if session not in VALID_SESSIONS:
            logger.warning(
                "MARKET_REVIEW_SLOTS: skipping entry %r (unknown session %r)",
                token, session,
            )
            continue
        if language not in VALID_LANGUAGES:
            logger.warning(
                "MARKET_REVIEW_SLOTS: skipping entry %r (unknown language %r)",
                token, language,
            )
            continue
        slot = MarketReviewSlot(market=market, session=session, language=language)
        if slot.key in seen:
            continue
        seen.add(slot.key)
        slots.append(slot)
    return slots


@dataclass
class SlotFiringState:
    """Per-slot bookkeeping: when did we last fire it?"""

    slot: MarketReviewSlot
    last_fired_utc: Optional[datetime] = None


class MarketReviewSlotTracker:
    """Owns the slot list + last-fired timestamps; emits ``due_slots`` per tick.

    Designed for an outer scheduler loop that calls :meth:`due_slots(now)` on
    every pass. Each slot's ``next_fire`` is computed relative to its own last
    firing (or, for fresh slots, relative to startup ``epoch``). When ``now``
    has crossed the next-fire instant the slot is returned and its last-fired
    timestamp is bumped to ``now``. Crossing two firings within one tick is
    impossible in practice because the loop ticks every 30 seconds.
    """

    def __init__(
        self,
        slots: Iterable[MarketReviewSlot],
        *,
        epoch: Optional[datetime] = None,
    ) -> None:
        # ``epoch=None`` means "start fresh as of now" — slots that already passed
        # earlier today will NOT replay when the server restarts mid-day. Tests can
        # pass an explicit past epoch to exercise the "fire on first tick" path.
        if epoch is None:
            epoch_utc = datetime.now(tz=timezone.utc)
        else:
            epoch_utc = _ensure_utc(epoch)
        self._states: List[SlotFiringState] = [
            SlotFiringState(slot=slot, last_fired_utc=epoch_utc) for slot in slots
        ]

    @property
    def slots(self) -> List[MarketReviewSlot]:
        return [s.slot for s in self._states]

    def due_slots(self, now: datetime) -> List[MarketReviewSlot]:
        """Return slots whose next_fire <= now since their last firing.

        Mutates state: each returned slot's last-fired timestamp becomes ``now``.
        """
        now_utc = _ensure_utc(now)
        due: List[MarketReviewSlot] = []
        for state in self._states:
            baseline = state.last_fired_utc or (now_utc - timedelta(days=1))
            next_fire = state.slot.next_fire(baseline)
            if now_utc >= next_fire:
                due.append(state.slot)
                state.last_fired_utc = now_utc
        return due

    def next_run_summary(self, now: datetime) -> List[Tuple[MarketReviewSlot, datetime]]:
        """Return ``[(slot, next_fire_utc)]`` for logging/diagnostics."""
        now_utc = _ensure_utc(now)
        out: List[Tuple[MarketReviewSlot, datetime]] = []
        for state in self._states:
            baseline = state.last_fired_utc or (now_utc - timedelta(days=1))
            out.append((state.slot, state.slot.next_fire(baseline)))
        return out


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
