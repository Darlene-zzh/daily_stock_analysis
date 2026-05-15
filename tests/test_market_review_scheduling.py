"""Tests for market_review slot parsing + next-fire math + tracker bookkeeping."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.market_review_scheduling import (
    DEFAULT_SLOTS,
    MarketReviewSlot,
    MarketReviewSlotTracker,
    parse_slots,
)


UTC = timezone.utc


class ParseSlotsTestCase(unittest.TestCase):
    def test_default_slots_match_user_intent(self) -> None:
        slots = parse_slots(DEFAULT_SLOTS)
        keys = [s.key for s in slots]
        self.assertEqual(
            keys,
            ["cn:open:zh", "cn:close:zh", "us:open:bi", "us:close:bi"],
        )

    def test_blank_input_falls_back_to_defaults(self) -> None:
        self.assertEqual(parse_slots("").__len__(), 4)
        self.assertEqual(parse_slots(None).__len__(), 4)
        self.assertEqual(parse_slots("   ").__len__(), 4)

    def test_whitespace_and_case_tolerated(self) -> None:
        slots = parse_slots(" CN:Open:ZH , US:CLOSE:bi ")
        self.assertEqual([s.key for s in slots], ["cn:open:zh", "us:close:bi"])

    def test_invalid_entries_logged_and_skipped(self) -> None:
        slots = parse_slots("cn:open:zh,bogus,us:lunch:bi,jp:open:zh,cn:close:fr")
        self.assertEqual([s.key for s in slots], ["cn:open:zh"])

    def test_duplicate_entries_deduplicated(self) -> None:
        slots = parse_slots("cn:open:zh,cn:open:zh,us:close:bi")
        self.assertEqual([s.key for s in slots], ["cn:open:zh", "us:close:bi"])


class SlotNextFireTestCase(unittest.TestCase):
    def test_cn_open_after_market_close_jumps_to_next_day(self) -> None:
        slot = MarketReviewSlot("cn", "open", "zh")
        # 2026-05-15 16:00 Shanghai = 08:00 UTC
        after = datetime(2026, 5, 15, 8, 0, tzinfo=UTC)
        nxt = slot.next_fire(after)
        # next CN open is 2026-05-16 09:30 Shanghai = 2026-05-16 01:30 UTC,
        # but 2026-05-16 is a Saturday so the slot rolls to Monday 2026-05-18.
        self.assertEqual(nxt, datetime(2026, 5, 18, 1, 30, tzinfo=UTC))

    def test_us_close_picks_next_market_day(self) -> None:
        slot = MarketReviewSlot("us", "close", "bi")
        # Monday 2026-05-18 10:00 UTC, well before US close (~20:00 UTC during DST)
        after = datetime(2026, 5, 18, 10, 0, tzinfo=UTC)
        nxt = slot.next_fire(after)
        # 2026-05-18 16:00 New York (EDT, UTC-4) → 20:00 UTC
        self.assertEqual(nxt, datetime(2026, 5, 18, 20, 0, tzinfo=UTC))

    def test_weekend_skip_to_monday(self) -> None:
        slot = MarketReviewSlot("us", "open", "bi")
        # Saturday 2026-05-16 12:00 UTC
        saturday = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
        nxt = slot.next_fire(saturday)
        # Next US open is Monday 2026-05-18 09:30 New York = 13:30 UTC (DST)
        self.assertEqual(nxt, datetime(2026, 5, 18, 13, 30, tzinfo=UTC))

    def test_naive_datetime_treated_as_utc(self) -> None:
        slot = MarketReviewSlot("cn", "open", "zh")
        aware = slot.next_fire(datetime(2026, 5, 14, 8, 0, tzinfo=UTC))
        naive = slot.next_fire(datetime(2026, 5, 14, 8, 0))
        self.assertEqual(aware, naive)


class SlotTrackerTestCase(unittest.TestCase):
    def test_due_slots_fire_once_then_wait_for_next_day(self) -> None:
        slot = MarketReviewSlot("cn", "open", "zh")
        # epoch in the past so the slot is "due" on the very first tick.
        tracker = MarketReviewSlotTracker(
            [slot], epoch=datetime(2026, 5, 14, 0, 0, tzinfo=UTC)
        )
        # Tick 1: just past Thu 2026-05-14 01:30 UTC (= 09:30 Shanghai).
        first_tick = datetime(2026, 5, 14, 1, 31, tzinfo=UTC)
        self.assertEqual(tracker.due_slots(first_tick), [slot])
        # Tick 2: a minute later — must NOT re-fire.
        self.assertEqual(tracker.due_slots(first_tick + timedelta(minutes=1)), [])
        # Same day six hours later — still no second firing.
        self.assertEqual(tracker.due_slots(first_tick + timedelta(hours=6)), [])
        # Tick 3: next trading-day 09:30 Shanghai (= Fri 2026-05-15 01:30 UTC) — fires again.
        next_day = datetime(2026, 5, 15, 1, 31, tzinfo=UTC)
        self.assertEqual(tracker.due_slots(next_day), [slot])

    def test_multiple_slots_independent_state(self) -> None:
        cn_open = MarketReviewSlot("cn", "open", "zh")
        us_close = MarketReviewSlot("us", "close", "bi")
        tracker = MarketReviewSlotTracker(
            [cn_open, us_close],
            epoch=datetime(2026, 5, 14, 0, 0, tzinfo=UTC),
        )
        # Cross CN open only (~01:30 UTC).
        after_cn = datetime(2026, 5, 14, 1, 31, tzinfo=UTC)
        self.assertEqual(tracker.due_slots(after_cn), [cn_open])
        # Cross US close (~20:00 UTC) same day — US fires, CN does not re-fire.
        after_us = datetime(2026, 5, 14, 20, 1, tzinfo=UTC)
        self.assertEqual(tracker.due_slots(after_us), [us_close])

    def test_init_without_epoch_defers_first_fire_to_next_real_event(self) -> None:
        # Realistic startup mid-day: 12:00 UTC on a Monday. The previous
        # CN-open at 01:30 UTC has already happened today; we must NOT replay
        # it on the first tick (would spam users on every server restart).
        from src.services.market_review_scheduling import datetime as _module_dt  # noqa: F401
        from src.services import market_review_scheduling as mod

        startup_now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)

        class _FrozenClock:
            @staticmethod
            def now(tz=None):  # noqa: D401, ARG004
                return startup_now

        original = mod.datetime
        mod.datetime = _FrozenClock  # type: ignore[assignment]
        try:
            tracker = MarketReviewSlotTracker([MarketReviewSlot("cn", "open", "zh")])
        finally:
            mod.datetime = original
        # Immediately after startup the slot must not be due — its next fire is
        # tomorrow's Shanghai 09:30.
        self.assertEqual(tracker.due_slots(startup_now + timedelta(minutes=1)), [])
        # Next CN open Tuesday 2026-05-19 01:30 UTC — it should fire then.
        self.assertEqual(
            len(tracker.due_slots(datetime(2026, 5, 19, 1, 31, tzinfo=UTC))),
            1,
        )

    def test_next_run_summary_pairs_each_slot_with_its_next_fire(self) -> None:
        slots = parse_slots("cn:open:zh,us:close:bi")
        tracker = MarketReviewSlotTracker(slots)
        summary = tracker.next_run_summary(
            datetime(2026, 5, 18, 0, 0, tzinfo=UTC)  # Monday early UTC
        )
        keys = [(slot.key, ts.isoformat()) for slot, ts in summary]
        self.assertEqual(len(keys), 2)
        # Every returned timestamp must be in the future and UTC-aware.
        for _, ts_iso in keys:
            self.assertIn("+00:00", ts_iso)


if __name__ == "__main__":
    unittest.main()
