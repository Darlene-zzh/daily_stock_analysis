# -*- coding: utf-8 -*-
"""Decision Journal Service — Sprint 2 reflection loop.

Every successful ``analyze_stock`` call writes a small append-only Markdown
entry to ``data/decision_journals/<market>/<stock_code>.md``.  On the *next*
analysis of the same stock, this module rebuilds a one-paragraph
"reflection block" that the LLM analyzer splices into its prompt — so the
system carries forward its own track record on the security and can
calibrate against realised alpha vs the appropriate benchmark.

Design notes
------------

* **Append-only Markdown**: one entry per analysis, header line is the UTC
  timestamp.  Single ``write()`` per entry keeps it atomic at the kernel
  level when the entry is < ~4 KB (POSIX guarantees pipe-buffer atomicity).
  We aggressively truncate ``key_catalysts`` / ``key_risks`` before writing
  so this invariant holds even for verbose LLM output.
* **No file locks**: the task queue can run parallel analyses on different
  stocks, but a single stock's queue is implicitly serialised by the
  ``_analyzing_stocks`` dedupe map in ``task_queue.py``.  We still tolerate
  a half-written entry on the *read* path by skipping malformed sections.
* **Adjusted close mandatory**: realised return + alpha are computed from
  ``Close`` after we explicitly ask the fetcher for ``qfq`` / adjusted
  data.  Raw close would be wrong by an order of magnitude after a split.
* **Benchmarks** map by market: ``cn → 000300`` (沪深 300, akshare),
  ``hk → ^HSI`` (恒生指数, yfinance), ``us → SPY`` (yfinance).
* **Best-effort**: every public method swallows network / parse failures
  and returns a degraded result.  A failing journal MUST NOT kill the
  caller's analysis.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Soft cap on the assembled entry text — must fit comfortably under the
# POSIX PIPE_BUF (typically 4096 on Linux / 512 minimum on macOS) so that a
# single ``write()`` is atomic against concurrent writers.  Hard-capped here.
_MAX_ENTRY_BYTES = 3500

# Default number of recent entries surfaced in the reflection block.
DEFAULT_REFLECTION_ENTRIES = 5

# Default token budget for the reflection block.  Rough heuristic of
# ~4 chars per token; we summarise / drop entries until under budget.
DEFAULT_REFLECTION_TOKEN_BUDGET = 1500

# Per-market benchmark symbol used for alpha computation.  ``cn`` keeps the
# six-digit canonical akshare form; ``hk`` / ``us`` use the yfinance ticker.
_BENCHMARK = {
    "cn": "000300",
    "hk": "^HSI",
    "us": "SPY",
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class JournalEntry:
    """A single parsed journal entry."""

    decision_at: str  # ISO-8601 UTC timestamp string
    price_at_decision: Optional[float] = None
    report_language: Optional[str] = None
    verdict: Optional[str] = None
    score: Optional[int] = None
    one_sentence: Optional[str] = None
    committee_pm_verdict: Optional[str] = None
    key_catalysts: List[str] = field(default_factory=list)
    key_risks: List[str] = field(default_factory=list)
    analysis_query_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_at": self.decision_at,
            "price_at_decision": self.price_at_decision,
            "report_language": self.report_language,
            "verdict": self.verdict,
            "score": self.score,
            "one_sentence": self.one_sentence,
            "committee_pm_verdict": self.committee_pm_verdict,
            "key_catalysts": list(self.key_catalysts),
            "key_risks": list(self.key_risks),
            "analysis_query_id": self.analysis_query_id,
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DecisionJournalService:
    """Per-stock append-only decision journal + reflection helper.

    The constructor's ``base_dir`` argument exists almost entirely for
    testability — production callers should let it default to
    ``data/decision_journals`` relative to the project root.
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        *,
        fetcher_manager: Optional[Any] = None,
    ) -> None:
        if base_dir is None:
            # repo_root / data / decision_journals — resolve relative to
            # this file so it works regardless of the caller's CWD.
            repo_root = Path(__file__).resolve().parents[2]
            base_dir = repo_root / "data" / "decision_journals"
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # Lazy-resolved DataFetcherManager — kept optional so unit tests
        # don't need to spin up the real fetcher stack.
        self._fetcher_manager = fetcher_manager

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_market(market: str) -> str:
        m = (market or "").strip().lower()
        if m in {"a", "cn", "china"}:
            return "cn"
        if m in {"hk", "hongkong"}:
            return "hk"
        if m in {"us", "usa", "america"}:
            return "us"
        # Fall back to "cn" — better to mis-classify than to lose the entry.
        return m or "cn"

    @staticmethod
    def _safe_code(stock_code: str) -> str:
        """Trim path separators / leading dots; the canonical code should
        already be sanitised but be paranoid here because the file name is
        derived from user input."""
        code = (stock_code or "").strip()
        code = re.sub(r"[\\/]+", "_", code)
        code = code.lstrip(".")
        return code or "unknown"

    def _journal_path(self, market: str, stock_code: str) -> Path:
        market_dir = self.base_dir / self._normalise_market(market)
        market_dir.mkdir(parents=True, exist_ok=True)
        return market_dir / f"{self._safe_code(stock_code)}.md"

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def write_entry(
        self,
        *,
        stock_code: str,
        market: str,
        verdict: Optional[str],
        score: Optional[int],
        one_sentence: Optional[str],
        price_at_decision: Optional[float],
        report_language: Optional[str] = None,
        committee_pm_verdict: Optional[str] = None,
        key_catalysts: Optional[List[str]] = None,
        key_risks: Optional[List[str]] = None,
        analysis_query_id: Optional[str] = None,
        decision_at: Optional[datetime] = None,
    ) -> Optional[Path]:
        """Append one entry to the journal for ``stock_code`` / ``market``.

        Returns the journal path on success, ``None`` on hard failure.  Hard
        failures are logged at WARNING — they MUST NOT propagate.
        """
        try:
            path = self._journal_path(market, stock_code)
            ts = (decision_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
            header = ts.strftime("## %Y-%m-%d %H:%M:%S UTC")

            catalysts = self._truncate_bullets(key_catalysts or [])
            risks = self._truncate_bullets(key_risks or [])

            lines: List[str] = [header]
            lines.append(f"- decision_at: {ts.isoformat()}")
            if price_at_decision is not None:
                try:
                    lines.append(f"- price_at_decision: {float(price_at_decision):.4f}")
                except (TypeError, ValueError):
                    lines.append(f"- price_at_decision: {price_at_decision}")
            lines.append(f"- report_language: {report_language or 'zh'}")
            if verdict is not None:
                lines.append(f"- verdict: {verdict}")
            if score is not None:
                lines.append(f"- score: {int(score)}")
            if one_sentence:
                # keep one sentence — strip newlines so the markdown parser
                # never sees a stray header midway through a bullet
                flat = re.sub(r"\s+", " ", str(one_sentence)).strip()
                lines.append(f"- one_sentence: {flat[:280]}")
            if committee_pm_verdict:
                lines.append(f"- committee_pm_verdict: {committee_pm_verdict}")
            if catalysts:
                lines.append("- key_catalysts:")
                for c in catalysts:
                    lines.append(f"  - {c}")
            if risks:
                lines.append("- key_risks:")
                for r in risks:
                    lines.append(f"  - {r}")
            if analysis_query_id:
                lines.append(f"- analysis_query_id: {analysis_query_id}")
            lines.append("")  # trailing blank line — entry separator

            entry = "\n".join(lines) + "\n"

            # If the assembled entry is too big, drop bullet bodies first
            # then truncate the one_sentence; this keeps the timestamp +
            # verdict + score (the fields the reflection needs).
            if len(entry.encode("utf-8")) > _MAX_ENTRY_BYTES:
                entry = self._shrink_entry(entry)

            # One write — POSIX guarantees this is atomic when the payload
            # fits in PIPE_BUF.  Append-mode + a single bytes write is the
            # crash-safe contract.
            with open(path, "ab") as fh:
                fh.write(entry.encode("utf-8"))

            logger.info(
                "[decision-journal] wrote entry for %s/%s (%d bytes)",
                market,
                stock_code,
                len(entry.encode("utf-8")),
            )
            return path
        except Exception as exc:
            logger.warning(
                "[decision-journal] write_entry failed for %s/%s: %s",
                market,
                stock_code,
                exc,
                exc_info=True,
            )
            return None

    @staticmethod
    def _truncate_bullets(items: List[str], max_items: int = 5, max_len: int = 160) -> List[str]:
        out: List[str] = []
        for raw in items[:max_items]:
            if raw is None:
                continue
            text = re.sub(r"\s+", " ", str(raw)).strip()
            if not text:
                continue
            if len(text) > max_len:
                text = text[: max_len - 3] + "..."
            out.append(text)
        return out

    @staticmethod
    def _shrink_entry(entry: str) -> str:
        """Drop bullet bodies / truncate one_sentence so the entry fits."""
        lines = entry.splitlines()
        # First pass: drop key_catalysts / key_risks bullets
        kept: List[str] = []
        drop_bullets = False
        for ln in lines:
            stripped = ln.strip()
            if stripped in {"- key_catalysts:", "- key_risks:"}:
                drop_bullets = True
                continue
            if drop_bullets and stripped.startswith("- "):
                if stripped.startswith("- key_") or stripped.startswith("- analysis_") \
                        or stripped.startswith("- committee_") or stripped.startswith("- score") \
                        or stripped.startswith("- verdict") or stripped.startswith("- decision_at") \
                        or stripped.startswith("- one_sentence") or stripped.startswith("- price_at_decision") \
                        or stripped.startswith("- report_language"):
                    drop_bullets = False
                    kept.append(ln)
                else:
                    # sub-bullet body — skip
                    continue
            else:
                kept.append(ln)
        result = "\n".join(kept) + "\n"
        if len(result.encode("utf-8")) <= _MAX_ENTRY_BYTES:
            return result

        # Last resort — truncate one_sentence aggressively
        result = re.sub(
            r"(- one_sentence: ).{200,}",
            lambda m: m.group(1) + "[truncated]",
            result,
        )
        if len(result.encode("utf-8")) > _MAX_ENTRY_BYTES:
            # absolute final clamp
            result = result.encode("utf-8")[:_MAX_ENTRY_BYTES].decode(
                "utf-8", errors="ignore"
            ) + "\n"
        return result

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def load_recent_entries(
        self,
        *,
        stock_code: str,
        market: str,
        max_entries: int = DEFAULT_REFLECTION_ENTRIES,
    ) -> List[JournalEntry]:
        """Parse the most-recent ``max_entries`` entries (newest first).

        Best-effort: malformed sections are skipped silently.  Returns an
        empty list if the file does not exist or all sections are corrupt.
        """
        path = self._journal_path(market, stock_code)
        if not path.exists():
            return []

        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("[decision-journal] read failed for %s: %s", path, exc)
            return []

        sections = self._split_sections(text)
        entries: List[JournalEntry] = []
        # Iterate newest-first (we wrote newest at the bottom) — preserves
        # the "most recent first" contract of the reflection block.
        for raw in reversed(sections):
            parsed = self._parse_section(raw)
            if parsed is not None:
                entries.append(parsed)
            if len(entries) >= max_entries:
                break
        return entries

    @staticmethod
    def _split_sections(text: str) -> List[str]:
        """Split on ``## YYYY-...`` headers — robust to half-written tail."""
        # Use a positive look-ahead so we don't consume the header on the
        # boundary.  ``re.split`` returns the header inside the next chunk.
        if not text.strip():
            return []
        # Match headers ``## 2026-05-18 ...`` at start-of-line
        parts = re.split(r"(?m)^(?=## \d{4}-\d{2}-\d{2})", text)
        return [p for p in parts if p.strip()]

    @staticmethod
    def _parse_section(raw: str) -> Optional[JournalEntry]:
        """Parse one section into a ``JournalEntry``.  Returns None on
        malformed input (best-effort — caller iterates past these)."""
        lines = raw.splitlines()
        if not lines:
            return None
        header = lines[0].strip()
        m = re.match(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC$", header)
        if not m:
            return None
        decision_at_default = m.group(1)
        entry = JournalEntry(decision_at=decision_at_default)

        # Two-pass for nested bullets under ``key_catalysts:`` / ``key_risks:``.
        current_bucket: Optional[str] = None
        for ln in lines[1:]:
            stripped = ln.strip()
            if not stripped:
                continue
            if stripped == "- key_catalysts:":
                current_bucket = "catalysts"
                continue
            if stripped == "- key_risks:":
                current_bucket = "risks"
                continue
            if current_bucket and stripped.startswith("- ") and not _looks_like_top_level(stripped):
                # sub-bullet line under the active bucket
                body = stripped[2:].strip()
                if body:
                    if current_bucket == "catalysts":
                        entry.key_catalysts.append(body)
                    else:
                        entry.key_risks.append(body)
                continue
            # any other line — top-level field, clear the bucket
            current_bucket = None
            if stripped.startswith("- "):
                kv = stripped[2:].split(":", 1)
                if len(kv) != 2:
                    continue
                key = kv[0].strip()
                value = kv[1].strip()
                if not key:
                    continue
                _apply_field(entry, key, value)
        return entry

    # ------------------------------------------------------------------
    # Alpha / realised return
    # ------------------------------------------------------------------

    def compute_realised_alpha(
        self,
        *,
        stock_code: str,
        market: str,
        decision_at: str,
        price_at_decision: Optional[float],
    ) -> Dict[str, Optional[float]]:
        """Compute (raw_return, benchmark_return, alpha) for one entry.

        Returns a dict with all-``None`` values when computation fails.
        Caller treats ``None`` alpha as "benchmark unavailable but raw
        return may still be present".
        """
        result = {"raw_return": None, "benchmark_return": None, "alpha": None}
        if price_at_decision is None or float(price_at_decision) <= 0:
            return result
        # Parse decision_at — accepts both isoformat and the
        # ``YYYY-MM-DD HH:MM:SS`` header form.
        decision_dt = _parse_decision_at(decision_at)
        if decision_dt is None:
            return result
        # Current adjusted price for the security.
        current_price = self._get_current_adj_close(stock_code, market)
        if current_price is None or current_price <= 0:
            return result
        try:
            raw_return = float(current_price) / float(price_at_decision) - 1.0
        except (TypeError, ValueError, ZeroDivisionError):
            return result
        result["raw_return"] = raw_return
        # Benchmark side — non-fatal if it fails.
        try:
            decision_bench, current_bench = self._get_benchmark_pair(
                market=market, decision_dt=decision_dt
            )
            if decision_bench and current_bench and decision_bench > 0:
                bench_return = float(current_bench) / float(decision_bench) - 1.0
                result["benchmark_return"] = bench_return
                result["alpha"] = raw_return - bench_return
        except Exception as exc:
            logger.debug(
                "[decision-journal] benchmark fetch failed for %s/%s: %s",
                market,
                stock_code,
                exc,
            )
        return result

    def _get_current_adj_close(self, stock_code: str, market: str) -> Optional[float]:
        df = self._fetch_adjusted_kline(stock_code, market, lookback_days=10)
        if df is None or df.empty:
            return None
        return _last_close(df)

    def _get_benchmark_pair(
        self, *, market: str, decision_dt: datetime
    ) -> Tuple[Optional[float], Optional[float]]:
        bench_code = _BENCHMARK.get(self._normalise_market(market))
        if not bench_code:
            return None, None
        # Pull enough history to cover the decision date with a 7-day buffer
        # for non-trading days.
        days = max(30, (datetime.now(timezone.utc).date() - decision_dt.date()).days + 14)
        df = self._fetch_adjusted_kline(bench_code, market, lookback_days=days)
        if df is None or df.empty:
            return None, None
        decision_price = _close_on_or_after(df, decision_dt)
        current_price = _last_close(df)
        return decision_price, current_price

    def _fetch_adjusted_kline(
        self, stock_code: str, market: str, lookback_days: int
    ) -> Optional[Any]:
        """Pull adjusted-close kline via DataFetcherManager (qfq for
        akshare; yfinance's Close is already split/dividend-adjusted)."""
        try:
            manager = self._get_fetcher_manager()
            if manager is None:
                return None
            from datetime import timedelta
            end = datetime.now(timezone.utc).date()
            start = end - timedelta(days=lookback_days)
            df, _src = manager.get_daily_data(
                stock_code,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                days=lookback_days,
            )
            return df
        except Exception as exc:
            logger.debug(
                "[decision-journal] daily fetch failed for %s: %s",
                stock_code,
                exc,
            )
            return None

    def _get_fetcher_manager(self) -> Optional[Any]:
        if self._fetcher_manager is not None:
            return self._fetcher_manager
        try:
            from data_provider.base import DataFetcherManager
            self._fetcher_manager = DataFetcherManager()
        except Exception as exc:
            logger.debug("[decision-journal] DataFetcherManager init failed: %s", exc)
            self._fetcher_manager = None
        return self._fetcher_manager

    # ------------------------------------------------------------------
    # Reflection block
    # ------------------------------------------------------------------

    def build_reflection_block(
        self,
        *,
        stock_code: str,
        market: str,
        max_entries: int = DEFAULT_REFLECTION_ENTRIES,
        token_budget: int = DEFAULT_REFLECTION_TOKEN_BUDGET,
    ) -> Optional[str]:
        """Build the multi-line reflection block.

        Returns ``None`` if there are no prior entries (caller treats that
        as "no reflection to inject — proceed with default prompt").
        """
        try:
            entries = self.load_recent_entries(
                stock_code=stock_code,
                market=market,
                max_entries=max_entries,
            )
            if not entries:
                return None
            blocks: List[str] = [
                "## Reflection — your prior analyses of this security",
            ]
            for entry in entries:
                stats = self.compute_realised_alpha(
                    stock_code=stock_code,
                    market=market,
                    decision_at=entry.decision_at,
                    price_at_decision=entry.price_at_decision,
                )
                blocks.append(_render_entry_line(entry, stats))
            blocks.append(
                "Use this track record to calibrate your current analysis. "
                "If your prior calls have under-performed the benchmark for "
                "this name, increase scepticism toward your default thesis."
            )
            text = "\n".join(blocks).strip() + "\n"
            # Token-budget guard — approximate 4 chars / token.
            return _enforce_token_budget(text, blocks, token_budget)
        except Exception as exc:
            logger.warning(
                "[decision-journal] build_reflection_block failed for %s/%s: %s",
                market,
                stock_code,
                exc,
                exc_info=True,
            )
            return None


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _looks_like_top_level(line: str) -> bool:
    """Heuristic to tell a top-level field bullet from a sub-bullet under
    ``key_catalysts:`` / ``key_risks:``.  Top-level fields are
    ``- key: value`` with a known field name."""
    if not line.startswith("- "):
        return False
    body = line[2:]
    if ":" not in body:
        return False
    key = body.split(":", 1)[0].strip()
    return key in {
        "decision_at",
        "price_at_decision",
        "report_language",
        "verdict",
        "score",
        "one_sentence",
        "committee_pm_verdict",
        "analysis_query_id",
        "key_catalysts",
        "key_risks",
    }


def _apply_field(entry: JournalEntry, key: str, value: str) -> None:
    if key == "decision_at":
        entry.decision_at = value or entry.decision_at
    elif key == "price_at_decision":
        try:
            entry.price_at_decision = float(value)
        except (TypeError, ValueError):
            entry.price_at_decision = None
    elif key == "report_language":
        entry.report_language = value or None
    elif key == "verdict":
        entry.verdict = value or None
    elif key == "score":
        try:
            entry.score = int(float(value))
        except (TypeError, ValueError):
            entry.score = None
    elif key == "one_sentence":
        entry.one_sentence = value or None
    elif key == "committee_pm_verdict":
        entry.committee_pm_verdict = value or None
    elif key == "analysis_query_id":
        entry.analysis_query_id = value or None


def _parse_decision_at(value: str) -> Optional[datetime]:
    if not value:
        return None
    candidates = [value]
    # ``YYYY-MM-DD HH:MM:SS`` -> insert ``T`` to make ``fromisoformat`` happy.
    if "T" not in value and " " in value:
        candidates.append(value.replace(" ", "T"))
    for cand in candidates:
        try:
            dt = datetime.fromisoformat(cand)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _close_on_or_after(df: Any, decision_dt: datetime) -> Optional[float]:
    """Find the first row on or after ``decision_dt`` and return its Close.

    Tolerant of date/datetime/string index types — picks whichever shape
    the fetcher returned without forcing a normalisation roundtrip."""
    if df is None or df.empty:
        return None
    try:
        import pandas as pd  # noqa: F401
        date_col = _resolve_date_column(df)
        if date_col is None:
            return None
        # Compare on date-of-day; benchmark prices are daily.
        target = decision_dt.date()
        series = df[date_col]
        # Convert column to datetime once for the boolean filter.
        dt_series = _to_date_series(series)
        if dt_series is None:
            return None
        mask = dt_series >= target
        if not mask.any():
            return None
        idx = mask.idxmax()  # first True
        close = _resolve_close(df.loc[idx])
        if close is None:
            return None
        return float(close)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("[decision-journal] _close_on_or_after failed: %s", exc)
        return None


def _last_close(df: Any) -> Optional[float]:
    try:
        row = df.iloc[-1]
        close = _resolve_close(row)
        return float(close) if close is not None else None
    except Exception:
        return None


def _resolve_date_column(df: Any) -> Optional[str]:
    for col in ("date", "trade_date", "日期", "Date"):
        if col in df.columns:
            return col
    return None


def _resolve_close(row: Any) -> Optional[float]:
    for col in ("close", "Close", "收盘", "收盘价"):
        if col in row.index:
            try:
                return float(row[col])
            except (TypeError, ValueError):
                continue
    return None


def _to_date_series(series: Any) -> Optional[Any]:
    try:
        import pandas as pd
        return pd.to_datetime(series).dt.date
    except Exception:
        return None


def _render_entry_line(entry: JournalEntry, stats: Dict[str, Optional[float]]) -> str:
    """One bullet per past entry, kept terse so a 5-entry block stays
    well under the token budget."""
    date_part = entry.decision_at.split(" ")[0] if entry.decision_at else "?"
    verdict = entry.verdict or "n/a"
    score_part = f", score {entry.score}" if entry.score is not None else ""
    raw = stats.get("raw_return")
    alpha = stats.get("alpha")
    raw_part = f"{raw:+.2%}" if isinstance(raw, (int, float)) else "n/a"
    if isinstance(alpha, (int, float)):
        alpha_part = f"{alpha:+.2%}"
    else:
        alpha_part = "n/a"
    summary = entry.one_sentence or ""
    summary_clip = summary if len(summary) <= 160 else (summary[:157] + "...")

    pieces = [
        f"- {date_part}: prior verdict **{verdict}**{score_part};",
        f"realised raw return {raw_part}, alpha vs benchmark {alpha_part}.",
    ]
    if summary_clip:
        pieces.append(f"Prior thesis: {summary_clip}")
    # Optional materialised catalyst/risk
    if entry.key_catalysts:
        pieces.append(f"Past catalysts: {entry.key_catalysts[0][:120]}")
    if entry.key_risks:
        pieces.append(f"Past risks: {entry.key_risks[0][:120]}")
    return " ".join(pieces)


def _enforce_token_budget(text: str, blocks: List[str], token_budget: int) -> str:
    """If estimated tokens > budget, summarise older entries first.

    Heuristic: 4 chars / token.  We drop the *oldest* entry bullets until
    we're under budget, but always keep the header + the closing
    directive line so the LLM sees the intent.
    """
    estimated = len(text) // 4
    if estimated <= token_budget:
        return text
    # Strip the closing directive — we'll re-add it.
    if not blocks:
        return text
    header = blocks[0]
    closing = blocks[-1]
    body = blocks[1:-1]
    # Drop oldest first; body is ordered newest-first.
    while body and (len("\n".join([header] + body + [closing])) // 4) > token_budget:
        body.pop()
    if not body:
        # Even a single entry exceeds budget — drop its long-form summary.
        return f"{header}\n- (prior entries trimmed for budget)\n{closing}\n"
    return "\n".join([header] + body + [closing]) + "\n"


# ---------------------------------------------------------------------------
# Convenience helpers consumed by analysis_service / API endpoint
# ---------------------------------------------------------------------------


def infer_market_from_code(stock_code: str) -> str:
    """Mirror the classifier used by ``analysis_service`` so callers don't
    have to import data_provider modules transitively."""
    code = (stock_code or "").strip()
    if not code:
        return "cn"
    try:
        from data_provider.akshare_fetcher import is_hk_stock_code
        from data_provider.base import normalize_stock_code
        from data_provider.us_index_mapping import is_us_stock_code
    except Exception:
        return "cn"
    normalised = normalize_stock_code(code)
    if is_hk_stock_code(normalised):
        return "hk"
    if is_us_stock_code(normalised):
        return "us"
    return "cn"


def is_reflection_enabled_globally() -> bool:
    """Default-off opt-in flag.  Mirrors the Sprint 1A pattern so the
    feature is invisible until explicitly toggled."""
    val = os.getenv("DECISION_JOURNAL_REFLECTION_ENABLED", "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def default_token_budget() -> int:
    raw = os.getenv("DECISION_JOURNAL_REFLECTION_TOKEN_BUDGET", "").strip()
    if not raw:
        return DEFAULT_REFLECTION_TOKEN_BUDGET
    try:
        return max(200, int(raw))
    except ValueError:
        return DEFAULT_REFLECTION_TOKEN_BUDGET


def default_retention_days() -> int:
    raw = os.getenv("DECISION_JOURNAL_RETENTION_DAYS", "").strip()
    if not raw:
        return 730
    try:
        return max(30, int(raw))
    except ValueError:
        return 730


__all__ = [
    "DecisionJournalService",
    "JournalEntry",
    "DEFAULT_REFLECTION_ENTRIES",
    "DEFAULT_REFLECTION_TOKEN_BUDGET",
    "infer_market_from_code",
    "is_reflection_enabled_globally",
    "default_token_budget",
    "default_retention_days",
]
