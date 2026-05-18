# -*- coding: utf-8 -*-
"""Unit tests for ``src.services.decision_journal_service`` — Sprint 2.

These tests are intentionally pure-Python and never touch the network.
They cover:

* atomic single-file append + read round-trip
* concurrent writes from two threads on the same stock (does not corrupt)
* rotation safety — sub-bullet truncation when the entry would exceed
  ``_MAX_ENTRY_BYTES``
* alpha computation with a synthetic price source — covers split-safe
  adjusted-close behaviour, missing benchmark, and missing price
* reflection block formatting + token-budget enforcement
* the "partial / half-written entry" tolerance on the read path
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import pytest

from src.services.decision_journal_service import (
    DecisionJournalService,
    DEFAULT_REFLECTION_ENTRIES,
    JournalEntry,
    _enforce_token_budget,
    infer_market_from_code,
)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def journal_dir(tmp_path: Path) -> Path:
    d = tmp_path / "decision_journals"
    d.mkdir()
    return d


class _StaticFetcherManager:
    """Mock fetcher manager — returns canned ``(DataFrame, source)`` pairs
    keyed by ``stock_code``.  Mimics the real ``DataFetcherManager`` shape
    closely enough for ``compute_realised_alpha``."""

    def __init__(self, frames: Dict[str, pd.DataFrame]):
        self._frames = frames

    def get_daily_data(self, code: str, start_date: Optional[str] = None,
                       end_date: Optional[str] = None, days: int = 30
                       ) -> Tuple[pd.DataFrame, str]:
        df = self._frames.get(code)
        if df is None:
            raise RuntimeError(f"no canned frame for {code}")
        return df, "mock"


def _make_frame(rows: List[Tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"date": d, "close": c} for d, c in rows]
    )


# ---------------------------------------------------------------------------
# Path / market normalisation
# ---------------------------------------------------------------------------


def test_normalise_market_accepts_aliases(journal_dir: Path) -> None:
    svc = DecisionJournalService(base_dir=journal_dir)
    p1 = svc._journal_path("A", "600519")
    p2 = svc._journal_path("CN", "600519")
    p3 = svc._journal_path("china", "600519")
    assert p1 == p2 == p3
    assert p1.parent.name == "cn"


def test_safe_code_strips_path_separators(journal_dir: Path) -> None:
    svc = DecisionJournalService(base_dir=journal_dir)
    p = svc._journal_path("us", "../../etc/passwd")
    # No path traversal — the file must live under the cn/hk/us subdir.
    assert journal_dir in p.parents
    assert p.suffix == ".md"


def test_infer_market_from_code_us() -> None:
    assert infer_market_from_code("AAPL") == "us"


def test_infer_market_from_code_cn() -> None:
    assert infer_market_from_code("600519") == "cn"


# ---------------------------------------------------------------------------
# Write + read round-trip
# ---------------------------------------------------------------------------


def test_write_then_load_round_trip(journal_dir: Path) -> None:
    svc = DecisionJournalService(base_dir=journal_dir)
    ts = datetime(2026, 5, 17, 9, 30, 0, tzinfo=timezone.utc)
    svc.write_entry(
        stock_code="600519",
        market="cn",
        verdict="买入",
        score=72,
        one_sentence="护城河稳健，估值合理。",
        price_at_decision=1620.5,
        report_language="zh",
        committee_pm_verdict="buy",
        key_catalysts=["云业务回暖", "ROIC 21%"],
        key_risks=["监管不确定性", "毛利率收窄"],
        analysis_query_id="q-xyz",
        decision_at=ts,
    )

    entries = svc.load_recent_entries(stock_code="600519", market="cn")
    assert len(entries) == 1
    e = entries[0]
    assert e.verdict == "买入"
    assert e.score == 72
    assert e.committee_pm_verdict == "buy"
    assert e.key_catalysts[:2] == ["云业务回暖", "ROIC 21%"]
    assert e.key_risks[:2] == ["监管不确定性", "毛利率收窄"]
    assert e.analysis_query_id == "q-xyz"
    assert e.price_at_decision == pytest.approx(1620.5)


def test_write_appends_newest_at_bottom_and_load_returns_newest_first(
    journal_dir: Path,
) -> None:
    svc = DecisionJournalService(base_dir=journal_dir)
    base = datetime(2026, 5, 1, 9, 30, 0, tzinfo=timezone.utc)
    for i in range(3):
        svc.write_entry(
            stock_code="AAPL",
            market="us",
            verdict="买入" if i % 2 == 0 else "持有",
            score=70 + i,
            one_sentence=f"entry {i}",
            price_at_decision=100.0 + i,
            decision_at=base + timedelta(days=i),
        )
    entries = svc.load_recent_entries(stock_code="AAPL", market="us")
    # newest first
    assert [e.score for e in entries] == [72, 71, 70]


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_parallel_writes_dont_corrupt_journal(journal_dir: Path) -> None:
    svc = DecisionJournalService(base_dir=journal_dir)
    base = datetime(2026, 5, 1, 9, 30, 0, tzinfo=timezone.utc)

    def _writer(idx: int) -> None:
        svc.write_entry(
            stock_code="600519",
            market="cn",
            verdict="买入",
            score=70 + idx,
            one_sentence=f"thread {idx} thesis",
            price_at_decision=100.0 + idx,
            decision_at=base + timedelta(seconds=idx),
        )

    threads = [threading.Thread(target=_writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    entries = svc.load_recent_entries(
        stock_code="600519", market="cn", max_entries=20
    )
    # All 8 entries must parse cleanly.
    scores = sorted(e.score for e in entries if e.score is not None)
    assert scores == list(range(70, 78))


# ---------------------------------------------------------------------------
# Tolerance to half-written entries
# ---------------------------------------------------------------------------


def test_read_skips_malformed_section(journal_dir: Path) -> None:
    svc = DecisionJournalService(base_dir=journal_dir)
    ts = datetime(2026, 5, 17, 10, 0, 0, tzinfo=timezone.utc)
    svc.write_entry(
        stock_code="600519",
        market="cn",
        verdict="买入",
        score=72,
        one_sentence="thesis A",
        price_at_decision=100.0,
        decision_at=ts,
    )
    # Append a half-written section right before the real header.
    path = svc._journal_path("cn", "600519")
    corrupted = path.read_text(encoding="utf-8")
    bad = "## 2026-05-18 09:00:00 UTC\n- decision_at: 2026-05-18T09:00:00+00:00\n- score: nope\n"
    path.write_text(corrupted + bad, encoding="utf-8")

    entries = svc.load_recent_entries(stock_code="600519", market="cn")
    # The bad section parses (header is well-formed) but score remains None.
    bad_entry = next((e for e in entries if e.decision_at.startswith("2026-05-18")), None)
    assert bad_entry is not None
    assert bad_entry.score is None
    # The clean entry still parses correctly.
    clean = next(
        (e for e in entries if e.decision_at.startswith("2026-05-17")), None
    )
    assert clean is not None
    assert clean.score == 72


def test_read_skips_completely_unparseable_section(journal_dir: Path) -> None:
    svc = DecisionJournalService(base_dir=journal_dir)
    path = svc._journal_path("cn", "600519")
    # Force a file that only contains garbage before the first real header.
    ts = datetime(2026, 5, 17, 10, 0, 0, tzinfo=timezone.utc)
    svc.write_entry(
        stock_code="600519",
        market="cn",
        verdict="买入",
        score=72,
        one_sentence="thesis A",
        price_at_decision=100.0,
        decision_at=ts,
    )
    existing = path.read_text(encoding="utf-8")
    # Prepend chaos — must not raise.
    path.write_text("blah blah no header here\n" + existing, encoding="utf-8")
    entries = svc.load_recent_entries(stock_code="600519", market="cn")
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# Alpha computation
# ---------------------------------------------------------------------------


def test_compute_realised_alpha_with_benchmark(journal_dir: Path) -> None:
    frames = {
        "600519": _make_frame(
            [
                ("2026-05-01", 100.0),
                ("2026-05-15", 120.0),  # current adj close
            ]
        ),
        "000300": _make_frame(
            [
                ("2026-04-30", 4000.0),  # decision date is 2026-05-01 — picks this row's NEXT trading day
                ("2026-05-01", 4000.0),
                ("2026-05-15", 4200.0),
            ]
        ),
    }
    svc = DecisionJournalService(
        base_dir=journal_dir,
        fetcher_manager=_StaticFetcherManager(frames),
    )
    stats = svc.compute_realised_alpha(
        stock_code="600519",
        market="cn",
        decision_at="2026-05-01 09:30:00",
        price_at_decision=100.0,
    )
    assert stats["raw_return"] == pytest.approx(0.20)
    assert stats["benchmark_return"] == pytest.approx(0.05)
    assert stats["alpha"] == pytest.approx(0.15)


def test_compute_realised_alpha_when_benchmark_unavailable(journal_dir: Path) -> None:
    frames = {
        "600519": _make_frame(
            [
                ("2026-05-01", 100.0),
                ("2026-05-15", 110.0),
            ]
        ),
        # benchmark deliberately missing — fetcher raises
    }
    svc = DecisionJournalService(
        base_dir=journal_dir,
        fetcher_manager=_StaticFetcherManager(frames),
    )
    stats = svc.compute_realised_alpha(
        stock_code="600519",
        market="cn",
        decision_at="2026-05-01 09:30:00",
        price_at_decision=100.0,
    )
    assert stats["raw_return"] == pytest.approx(0.10)
    assert stats["benchmark_return"] is None
    assert stats["alpha"] is None


def test_compute_realised_alpha_split_safe_via_adjusted_close(
    journal_dir: Path,
) -> None:
    """A 2-for-1 split on the security halves the raw price.  Because the
    journal stores ``price_at_decision`` *captured at decision time* (post-
    qfq) and the fetcher returns split-adjusted current data, the realised
    return should still reflect the *true* move, not the cosmetic drop."""
    # Decision: 100 on 2026-05-01.  Today: 60 (post-split equivalent of 120).
    # If we used raw close (60) we'd see -40%; using adjusted close we
    # correctly see +20% — the fetcher in production already returns
    # ``qfq`` for us, so this test simply asserts that we read whatever
    # the fetcher gives without re-adjusting.
    frames = {
        "600519": _make_frame(
            [
                ("2026-05-01", 100.0),
                ("2026-05-15", 120.0),  # already adjusted by the fetcher
            ]
        ),
        "000300": _make_frame(
            [
                ("2026-05-01", 4000.0),
                ("2026-05-15", 4000.0),
            ]
        ),
    }
    svc = DecisionJournalService(
        base_dir=journal_dir,
        fetcher_manager=_StaticFetcherManager(frames),
    )
    stats = svc.compute_realised_alpha(
        stock_code="600519",
        market="cn",
        decision_at="2026-05-01 09:30:00",
        price_at_decision=100.0,
    )
    assert stats["raw_return"] == pytest.approx(0.20)
    assert stats["alpha"] == pytest.approx(0.20)


def test_compute_realised_alpha_returns_none_for_missing_price(
    journal_dir: Path,
) -> None:
    svc = DecisionJournalService(
        base_dir=journal_dir,
        fetcher_manager=_StaticFetcherManager({}),
    )
    stats = svc.compute_realised_alpha(
        stock_code="600519",
        market="cn",
        decision_at="2026-05-01 09:30:00",
        price_at_decision=None,
    )
    assert stats == {"raw_return": None, "benchmark_return": None, "alpha": None}


# ---------------------------------------------------------------------------
# Reflection block + token budget
# ---------------------------------------------------------------------------


def test_build_reflection_block_returns_none_when_no_entries(journal_dir: Path) -> None:
    svc = DecisionJournalService(base_dir=journal_dir)
    assert svc.build_reflection_block(stock_code="ZZZZ", market="cn") is None


def test_build_reflection_block_contains_directive_and_data(
    journal_dir: Path,
) -> None:
    frames = {
        "600519": _make_frame(
            [
                ("2026-05-01", 100.0),
                ("2026-05-15", 110.0),
            ]
        ),
        "000300": _make_frame(
            [
                ("2026-05-01", 4000.0),
                ("2026-05-15", 4040.0),
            ]
        ),
    }
    svc = DecisionJournalService(
        base_dir=journal_dir,
        fetcher_manager=_StaticFetcherManager(frames),
    )
    svc.write_entry(
        stock_code="600519",
        market="cn",
        verdict="买入",
        score=72,
        one_sentence="护城河稳健，估值合理。",
        price_at_decision=100.0,
        decision_at=datetime(2026, 5, 1, 9, 30, 0, tzinfo=timezone.utc),
    )
    block = svc.build_reflection_block(stock_code="600519", market="cn")
    assert block is not None
    assert "Reflection" in block
    assert "prior verdict" in block
    assert "raw return" in block
    assert "alpha vs benchmark" in block
    assert "calibrate" in block  # closing directive
    # ratio: 110/100 - 1 = 0.10; bench: 4040/4000 - 1 = 0.01; alpha = 0.09
    assert "+10.00%" in block
    assert "+9.00%" in block


def test_enforce_token_budget_drops_oldest_entries() -> None:
    header = "## Reflection — header"
    closing = "Closing directive sentence."
    body = [
        "- 2026-05-15: prior verdict **buy**; realised raw return +5.00%, alpha vs benchmark +1.00%. " + ("x" * 400),
        "- 2026-05-10: prior verdict **hold**; realised raw return +3.00%, alpha vs benchmark +0.20%. " + ("x" * 400),
        "- 2026-05-05: prior verdict **sell**; realised raw return -1.00%, alpha vs benchmark -2.00%. " + ("x" * 400),
    ]
    text = "\n".join([header] + body + [closing])
    # Set a tight budget so at least one entry MUST be dropped.
    result = _enforce_token_budget(text, [header] + body + [closing], 150)
    assert "calibrate" not in result  # only the seeded closing here
    assert result.count("prior verdict") < 3
    # Header must remain
    assert "Reflection" in result


# ---------------------------------------------------------------------------
# Truncation safety
# ---------------------------------------------------------------------------


def test_write_entry_shrinks_when_too_large(journal_dir: Path) -> None:
    """Catalysts + risks padded to exceed the 3.5 KB cap should be
    truncated before the write touches disk so the atomic-write
    invariant holds."""
    svc = DecisionJournalService(base_dir=journal_dir)
    catalysts = ["x" * 200 for _ in range(20)]
    risks = ["y" * 200 for _ in range(20)]
    svc.write_entry(
        stock_code="AAPL",
        market="us",
        verdict="buy",
        score=70,
        one_sentence="thesis " + ("z" * 5000),
        price_at_decision=100.0,
        key_catalysts=catalysts,
        key_risks=risks,
    )
    path = svc._journal_path("us", "AAPL")
    raw = path.read_bytes()
    assert len(raw) <= 3600  # generous slack on top of 3500 cap
    entries = svc.load_recent_entries(stock_code="AAPL", market="us")
    assert entries[0].verdict == "buy"
    assert entries[0].score == 70


# ---------------------------------------------------------------------------
# Misc — JournalEntry serialisation
# ---------------------------------------------------------------------------


def test_journal_entry_to_dict_round_trip() -> None:
    e = JournalEntry(
        decision_at="2026-05-17 09:30:00",
        verdict="buy",
        score=72,
        key_catalysts=["a"],
        key_risks=["b"],
    )
    d = e.to_dict()
    assert d["decision_at"] == "2026-05-17 09:30:00"
    assert d["verdict"] == "buy"
    assert d["key_catalysts"] == ["a"]
    assert d["key_risks"] == ["b"]
    # Ensure we got a copy — mutating the dict shouldn't affect the entry.
    d["key_catalysts"].append("zzz")
    assert e.key_catalysts == ["a"]
