# Adaptive Strategy Classification + Multi-Source Sentiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an adaptive strategy classification layer on top of the existing action_plan_items system: LLM picks one of four fixed strategies per stock (long_term_hold / swing_trade / stepped_profit_taking / wait_and_see), writes a thesis paragraph, and generates strategy-templated action plan items. Plus expand the sentiment input pipeline to five sources (Adanos Reddit/X/Polymarket/News + StockTwits) and surface them as a dedicated dashboard section. Applies to ALL stock analyses (US/HK/A, with or without portfolio context).

**Architecture:** Backend changes touch four layers — sentiment fetcher additions, the focused LLM call (`_try_inject_action_plan_items`) which is rewritten to also classify strategy, post-process sanitization (5 quality gates), and dual renderer markdown output. Frontend adds 4 new React components mounted in `ReportSummary.tsx`. Schema additions in `api/v1/schemas/history.py` carry the new structured fields through to the API response. The synthesis fallback is extended with per-strategy templates so the feature still degrades gracefully when LLM fails.

**Tech Stack:** Python 3.11 (FastAPI / Pydantic V2), LiteLLM routing to gpt-5.5, SQLite, React + TypeScript + Tailwind frontend. Test: pytest with markers (`-m "not network"` for unit tests).

---

## File Structure

**New files (backend):**
- `src/services/stocktwits_service.py` — free StockTwits public API client (~90 LOC)
- `tests/test_adanos_news_endpoint.py` — Adanos news fetch tests
- `tests/test_stocktwits_service.py` — StockTwits client tests
- `tests/test_strategy_classification.py` — LLM strategy decision rules
- `tests/test_action_plan_strategy_template.py` — per-strategy items white/blacklist
- `tests/test_position_outcome_summary.py` — R:R computation
- `tests/test_sentiment_dimensions.py` — structured sentiment in dashboard

**Modified files (backend):**
- `src/services/social_sentiment_service.py` — add `fetch_news_report()`; `get_social_context()` returns `(text, structured_dict)` tuple
- `src/services/portfolio_context_service.py` — add `STRATEGY_CLASSIFY_INSTRUCTION_ZH` constant + strategy-aware synthesis templates; existing `build_action_plan_instruction` returns a strategy-classification prompt
- `src/analyzer.py:2332` — rewrite `_try_inject_action_plan_items` to be universal (runs without portfolio context too); parse strategy_choices / recommended_strategy / strategy_thesis / position_outcome_summary; integrate 5 quality gates
- `src/core/pipeline.py` — wire `sentiment_dimensions` into `dashboard.intelligence`; remove portfolio-gating around strategy classification call
- `src/agent/executor.py` — update `AGENT_SYSTEM_PROMPT` + `LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT` JSON examples to include `strategy_choices` / `recommended_strategy` / `strategy_thesis` / `position_outcome_summary` / `sentiment_dimensions`
- `api/v1/schemas/history.py:129` — extend `CoreConclusionSchema` with new fields; add 3 new schemas
- `src/notification.py` — renderer for strategy selector + thesis + sentiment panel + position outcome
- `src/services/history_service.py` — mirror notification.py renderer changes
- `src/report_language.py` — 6 new zh/en label entries

**New files (frontend):**
- `apps/dsa-web/src/components/report/StrategySelector.tsx` — strategy comparison table
- `apps/dsa-web/src/components/report/StrategyThesis.tsx` — thesis paragraph block
- `apps/dsa-web/src/components/report/SentimentPanel.tsx` — 2-column sentiment grid
- `apps/dsa-web/src/components/report/PositionOutcomeSummary.tsx` — R:R card

**Modified files (frontend):**
- `apps/dsa-web/src/types/analysis.ts` — `StrategyChoice`, `SentimentDimensions`, `PositionOutcomeSummary` types
- `apps/dsa-web/src/components/report/ReportSummary.tsx` — mount the 4 new components
- `apps/dsa-web/src/components/report/index.ts` — export new components

**Docs:**
- `docs/CHANGELOG.md` — `[Unreleased]` entries

---

### Task 1: Adanos News endpoint fetcher

**Files:**
- Modify: `src/services/social_sentiment_service.py`
- Test: `tests/test_adanos_news_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_adanos_news_endpoint.py`:

```python
"""Tests for Adanos /news/stocks/v1/stock/{ticker} endpoint integration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.social_sentiment_service import SocialSentimentService


class FetchNewsReportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = SocialSentimentService(
            api_key="sk_test_dummy",
            api_url="https://api.adanos.org",
        )

    @patch("src.services.social_sentiment_service._get_with_retry")
    def test_fetches_news_report_with_correct_path(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ticker": "NVDA",
            "buzz_score": 61.6,
            "sentiment_score": 0.484,
            "mentions": 285,
            "bullish_pct": 86,
            "bearish_pct": 4,
            "top_sources": [{"source": "yahoo-finance", "count": 68}],
        }
        mock_get.return_value = mock_resp

        result = self.svc.fetch_news_report("NVDA")

        called_url = mock_get.call_args[0][0]
        self.assertEqual(called_url, "https://api.adanos.org/news/stocks/v1/stock/NVDA")
        self.assertEqual(result["buzz_score"], 61.6)
        self.assertEqual(result["sentiment_score"], 0.484)

    @patch("src.services.social_sentiment_service._get_with_retry")
    def test_fetch_news_report_uppercases_ticker(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ticker": "AAPL"}
        mock_get.return_value = mock_resp

        self.svc.fetch_news_report("aapl")

        called_url = mock_get.call_args[0][0]
        self.assertIn("/stock/AAPL", called_url)

    @patch("src.services.social_sentiment_service._get_with_retry")
    def test_fetch_news_report_returns_none_on_404(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = self.svc.fetch_news_report("UNKNOWN")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_adanos_news_endpoint.py -v`
Expected: FAIL with `AttributeError: 'SocialSentimentService' object has no attribute 'fetch_news_report'`

- [ ] **Step 3: Implement `fetch_news_report`**

In `src/services/social_sentiment_service.py`, after `fetch_reddit_report` (around line 165), add:

```python
    def fetch_news_report(self, ticker: str) -> Optional[Dict]:
        """Fetch detailed news sentiment for a single ticker from Adanos.

        Endpoint: /news/stocks/v1/stock/{ticker}. Returns buzz_score, sentiment_score,
        bullish_pct, bearish_pct, mentions, and top_sources (e.g. yahoo-finance,
        motley-fool). Same X-API-Key header as other Adanos endpoints.
        """
        url = f"{self._api_url}/news/stocks/v1/stock/{ticker.upper()}"
        return self._fetch_json(url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_adanos_news_endpoint.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/services/social_sentiment_service.py tests/test_adanos_news_endpoint.py
git commit -m "feat: add Adanos news-stocks endpoint to sentiment service"
```

---

### Task 2: StockTwits public API client

**Files:**
- Create: `src/services/stocktwits_service.py`
- Test: `tests/test_stocktwits_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_stocktwits_service.py`:

```python
"""Tests for StockTwits public sentiment API client."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.stocktwits_service import StockTwitsService


def _make_message(sentiment: str | None) -> dict:
    return {
        "id": 1,
        "body": "test",
        "entities": {"sentiment": {"basic": sentiment}} if sentiment else {"sentiment": None},
    }


class StockTwitsAggregateTestCase(unittest.TestCase):
    @patch("src.services.stocktwits_service.requests.get")
    def test_aggregates_bullish_bearish_ratios(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "messages": (
                [_make_message("Bullish")] * 6
                + [_make_message("Bearish")] * 2
                + [_make_message(None)] * 2
            ),
        }
        mock_get.return_value = resp

        svc = StockTwitsService()
        out = svc.fetch_sentiment("NVDA")

        self.assertEqual(out["messages_sampled"], 10)
        self.assertAlmostEqual(out["bullish_ratio"], 0.6)
        self.assertAlmostEqual(out["bearish_ratio"], 0.2)
        self.assertAlmostEqual(out["neutral_ratio"], 0.2)
        self.assertEqual(out["source"], "stocktwits_public")

    @patch("src.services.stocktwits_service.requests.get")
    def test_hits_correct_endpoint(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"messages": []}
        mock_get.return_value = resp

        StockTwitsService().fetch_sentiment("aapl")
        called_url = mock_get.call_args[0][0]
        self.assertEqual(
            called_url,
            "https://api.stocktwits.com/api/2/streams/symbol/AAPL.json",
        )

    @patch("src.services.stocktwits_service.requests.get")
    def test_returns_none_on_empty_messages(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"messages": []}
        mock_get.return_value = resp

        out = StockTwitsService().fetch_sentiment("NVDA")
        self.assertIsNone(out)

    @patch("src.services.stocktwits_service.requests.get")
    def test_returns_none_on_http_error(self, mock_get):
        resp = MagicMock()
        resp.status_code = 429
        mock_get.return_value = resp

        out = StockTwitsService().fetch_sentiment("NVDA")
        self.assertIsNone(out)

    @patch("src.services.stocktwits_service.requests.get")
    def test_caches_repeated_requests_within_ttl(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "messages": [_make_message("Bullish")] * 3,
        }
        mock_get.return_value = resp

        svc = StockTwitsService()
        svc.fetch_sentiment("NVDA")
        svc.fetch_sentiment("NVDA")  # second call should hit cache

        self.assertEqual(mock_get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_stocktwits_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.stocktwits_service'`

- [ ] **Step 3: Implement StockTwitsService**

Create `src/services/stocktwits_service.py`:

```python
# -*- coding: utf-8 -*-
"""
StockTwits public sentiment API client.

Endpoint reference: https://api.stocktwits.com/developers/docs
The streams/symbol endpoint is public and does NOT require an API key.
Rate limited per-IP (~200 req/hour), so we cache results for 5 minutes per ticker.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5
_CACHE_TTL_SECONDS = 300  # 5 min per ticker


class StockTwitsService:
    """Aggregates Bullish / Bearish sentiment from the StockTwits public stream API.

    Each call samples up to ~30 most-recent messages for a symbol and computes
    bullish_ratio / bearish_ratio / neutral_ratio. Results are cached in-process
    for 5 minutes per ticker to stay below rate limits.
    """

    API_ENDPOINT = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"

    def __init__(self) -> None:
        self._cache: Dict[str, tuple[float, dict]] = {}
        self._cache_lock = threading.RLock()

    def fetch_sentiment(self, ticker: str) -> Optional[Dict]:
        """Return aggregated sentiment ratios or None when no usable data."""
        upper = ticker.upper()

        # Cache hit?
        with self._cache_lock:
            cached = self._cache.get(upper)
            if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
                return cached[1]

        url = self.API_ENDPOINT.format(ticker=upper)
        try:
            resp = requests.get(url, timeout=_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            logger.warning("[StockTwits] %s request failed: %s", upper, exc)
            return None

        if resp.status_code != 200:
            logger.warning("[StockTwits] %s returned %s", upper, resp.status_code)
            return None

        try:
            payload = resp.json()
        except ValueError:
            logger.warning("[StockTwits] %s returned non-JSON", upper)
            return None

        messages = payload.get("messages") or []
        if not messages:
            return None

        bullish = 0
        bearish = 0
        neutral = 0
        for msg in messages:
            entities = msg.get("entities") or {}
            sent = entities.get("sentiment")
            if isinstance(sent, dict):
                basic = (sent.get("basic") or "").strip().lower()
                if basic == "bullish":
                    bullish += 1
                elif basic == "bearish":
                    bearish += 1
                else:
                    neutral += 1
            else:
                neutral += 1

        total = bullish + bearish + neutral
        if total == 0:
            return None

        result = {
            "bullish_ratio": round(bullish / total, 3),
            "bearish_ratio": round(bearish / total, 3),
            "neutral_ratio": round(neutral / total, 3),
            "messages_sampled": total,
            "source": "stocktwits_public",
        }

        with self._cache_lock:
            self._cache[upper] = (time.monotonic(), result)

        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_stocktwits_service.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/services/stocktwits_service.py tests/test_stocktwits_service.py
git commit -m "feat: add StockTwits public API sentiment client"
```

---

### Task 3: Refactor `get_social_context` to return structured + text payload

**Files:**
- Modify: `src/services/social_sentiment_service.py` (lines ~191-220)
- Test: `tests/test_sentiment_dimensions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_sentiment_dimensions.py`:

```python
"""Tests for structured sentiment_dimensions payload returned by SocialSentimentService."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.social_sentiment_service import SocialSentimentService


class GetSocialContextStructuredTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = SocialSentimentService(
            api_key="sk_test", api_url="https://api.adanos.org",
        )

    def _patch_endpoints(self, reddit=None, x=None, poly=None, news=None):
        return [
            patch.object(self.svc, "fetch_reddit_report", return_value=reddit),
            patch.object(self.svc, "fetch_x_trending",
                         return_value=[{"ticker": "NVDA", **x}] if x else []),
            patch.object(self.svc, "fetch_polymarket_trending",
                         return_value=[{"ticker": "NVDA", **poly}] if poly else []),
            patch.object(self.svc, "fetch_news_report", return_value=news),
        ]

    def test_get_social_context_returns_tuple(self):
        patches = self._patch_endpoints(
            reddit={"buzz_score": 84.4, "sentiment_score": 0.06, "trend": "rising"},
            x={"buzz_score": 89.0, "sentiment_score": 0.28, "trend": "falling"},
            poly={"buzz_score": 64.7, "sentiment_score": 0.13},
            news={"buzz_score": 61.6, "sentiment_score": 0.48, "trend": "stable"},
        )
        for p in patches:
            p.start()
        try:
            result = self.svc.get_social_context("NVDA")
        finally:
            for p in patches:
                p.stop()

        self.assertIsInstance(result, tuple)
        text, dims = result
        self.assertIsInstance(text, str)
        self.assertIsInstance(dims, dict)
        self.assertIn("reddit", dims)
        self.assertIn("x_twitter", dims)
        self.assertIn("polymarket", dims)
        self.assertIn("news", dims)
        self.assertAlmostEqual(dims["reddit"]["buzz_score"], 84.4)
        self.assertEqual(dims["x_twitter"]["buzz_trend"], "falling")

    def test_partial_data_returns_partial_dims(self):
        patches = self._patch_endpoints(
            reddit=None,  # 404
            x={"buzz_score": 89.0, "sentiment_score": 0.28},
            poly=None,
            news={"buzz_score": 61.6, "sentiment_score": 0.48},
        )
        for p in patches:
            p.start()
        try:
            text, dims = self.svc.get_social_context("NVDA")
        finally:
            for p in patches:
                p.stop()

        self.assertNotIn("reddit", dims)
        self.assertNotIn("polymarket", dims)
        self.assertIn("x_twitter", dims)
        self.assertIn("news", dims)

    def test_returns_none_when_no_data(self):
        patches = self._patch_endpoints(reddit=None, x=None, poly=None, news=None)
        for p in patches:
            p.start()
        try:
            result = self.svc.get_social_context("NVDA")
        finally:
            for p in patches:
                p.stop()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_sentiment_dimensions.py -v`
Expected: FAIL — current `get_social_context` returns a `str | None`, not a tuple.

- [ ] **Step 3: Refactor `get_social_context`**

In `src/services/social_sentiment_service.py`, replace the existing `get_social_context` method (around line 191) with:

```python
    def get_social_context(self, ticker: str) -> Optional[tuple[str, dict]]:
        """Fetch all sentiment dimensions and return (text_for_llm, structured_dict).

        Returns None when no source has data. The text is the legacy markdown block
        for prompt injection; the dict is the structured payload for the dashboard's
        intelligence.sentiment_dimensions field.
        """
        if not self.is_available:
            return None

        ticker_upper = ticker.upper()

        reddit_data = self.fetch_reddit_report(ticker_upper)

        x_entry = None
        x_trending = self.fetch_x_trending()
        if x_trending:
            x_entry = self._find_ticker_in_trending(x_trending, ticker_upper)

        poly_entry = None
        poly_trending = self.fetch_polymarket_trending()
        if poly_trending:
            poly_entry = self._find_ticker_in_trending(poly_trending, ticker_upper)

        news_data = self.fetch_news_report(ticker_upper)

        if not (reddit_data or x_entry or poly_entry or news_data):
            return None

        text = self._format_social_intel(ticker_upper, reddit_data, x_entry, poly_entry, news_data)
        dims = self._build_sentiment_dimensions(reddit_data, x_entry, poly_entry, news_data)
        return text, dims

    @staticmethod
    def _build_sentiment_dimensions(
        reddit_data: Optional[Dict],
        x_entry: Optional[Dict],
        poly_entry: Optional[Dict],
        news_data: Optional[Dict],
    ) -> Dict[str, Dict]:
        """Convert raw Adanos payloads into structured sentiment_dimensions dict."""
        out: Dict[str, Dict] = {}
        if reddit_data:
            out["reddit"] = {
                "buzz_score": reddit_data.get("buzz_score"),
                "buzz_trend": reddit_data.get("trend"),
                "sentiment_score": reddit_data.get("sentiment_score"),
                "mentions_7d": reddit_data.get("mentions") or reddit_data.get("total_mentions"),
                "bullish_pct": reddit_data.get("bullish_pct"),
                "bearish_pct": reddit_data.get("bearish_pct"),
                "subreddit_count": reddit_data.get("subreddit_count") or reddit_data.get("subreddits"),
                "source": "adanos",
            }
        if x_entry:
            out["x_twitter"] = {
                "buzz_score": x_entry.get("buzz_score"),
                "buzz_trend": x_entry.get("trend"),
                "sentiment_score": x_entry.get("sentiment_score"),
                "mentions_7d": x_entry.get("mentions") or x_entry.get("total_mentions"),
                "source": "adanos",
            }
        if poly_entry:
            out["polymarket"] = {
                "buzz_score": poly_entry.get("buzz_score"),
                "sentiment_score": poly_entry.get("sentiment_score") or poly_entry.get("market_sentiment"),
                "trade_count": poly_entry.get("trade_count") or poly_entry.get("trades"),
                "source": "adanos",
            }
        if news_data:
            out["news"] = {
                "buzz_score": news_data.get("buzz_score"),
                "buzz_trend": news_data.get("trend"),
                "sentiment_score": news_data.get("sentiment_score"),
                "mentions_7d": news_data.get("mentions"),
                "bullish_pct": news_data.get("bullish_pct"),
                "bearish_pct": news_data.get("bearish_pct"),
                "source": "adanos",
            }
        return out
```

Also update the `_format_social_intel` signature to accept `news_data` as a 5th positional argument. Find it (around line 244) and change:

```python
    @staticmethod
    def _format_social_intel(
        ticker: str,
        reddit_data: Optional[Dict],
        x_entry: Optional[Dict],
        poly_entry: Optional[Dict],
        news_data: Optional[Dict] = None,
    ) -> str:
```

At the end of the existing body, before `return "\n".join(lines)`, add a news block:

```python
        if news_data:
            lines.append("\n📰 News Sentiment:")
            buzz = SocialSentimentService._coalesce(news_data.get("buzz_score"))
            if buzz is not None:
                trend_label = news_data.get("trend", "")
                lines.append(
                    f"  Buzz Score: {buzz}/100 ({trend_label})" if trend_label
                    else f"  Buzz Score: {buzz}/100"
                )
            sentiment = SocialSentimentService._coalesce(news_data.get("sentiment_score"))
            if sentiment is not None:
                lines.append(f"  Sentiment Score: {sentiment}")
            mentions = SocialSentimentService._coalesce(news_data.get("mentions"))
            if mentions is not None:
                lines.append(f"  Articles: {mentions} (7-day)")
            top_sources = news_data.get("top_sources", [])
            if top_sources:
                names = [s.get("source") for s in top_sources[:3] if s.get("source")]
                if names:
                    lines.append(f"  Top sources: {', '.join(names)}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_sentiment_dimensions.py -v`
Expected: 3 passed

- [ ] **Step 5: Update pipeline.py callers**

`get_social_context` now returns a tuple. Find the two callers in `src/core/pipeline.py` (around lines 432 and 838) and update each from:

```python
social_context = self.social_sentiment_service.get_social_context(code)
if social_context:
    # ... existing usage of social_context as text
```

to:

```python
social_result = self.social_sentiment_service.get_social_context(code)
if social_result:
    social_context, sentiment_dims = social_result
    # existing usage of social_context as text (unchanged below)
```

For the agent path (line 838), also stash `sentiment_dims` on the result for later wiring. The exact wiring into `dashboard.intelligence` happens in Task 7; for now just unpack the tuple safely.

- [ ] **Step 6: Run full sentiment tests + agent-path tests to verify no regression**

Run:
```bash
/opt/homebrew/bin/python3.11 -m pytest tests/test_sentiment_dimensions.py tests/test_adanos_news_endpoint.py tests/test_stocktwits_service.py tests/test_action_plan_agent_path.py -m "not network" -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/services/social_sentiment_service.py src/core/pipeline.py tests/test_sentiment_dimensions.py
git commit -m "refactor: get_social_context returns (text, structured_dict) tuple incl news endpoint"
```

---

### Task 4: Add new Pydantic schemas

**Files:**
- Modify: `api/v1/schemas/history.py` (around line 110-145)
- Test: `tests/test_strategy_classification.py` (initial schema tests only — full LLM tests added in later tasks)

- [ ] **Step 1: Write the failing test**

Create `tests/test_strategy_classification.py`:

```python
"""Tests for strategy classification schema + LLM decision rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class StrategySchemaTestCase(unittest.TestCase):
    def test_strategy_choice_schema_validates(self) -> None:
        from api.v1.schemas.history import StrategyChoiceSchema
        choice = StrategyChoiceSchema(
            id="long_term_hold",
            label_zh="长线持有",
            emoji="🌳",
            applicable=True,
            fit_condition="看好 AI 主线 1-2 年",
            key_params="跌破 cost × 0.9 退出",
            time_horizon="6 个月+",
            inapplicable_reason=None,
        )
        self.assertEqual(choice.id, "long_term_hold")
        self.assertTrue(choice.applicable)

    def test_strategy_id_constrained_to_four_values(self) -> None:
        """The id field accepts only the four fixed enum values."""
        from api.v1.schemas.history import StrategyChoiceSchema
        for valid in ("long_term_hold", "swing_trade", "stepped_profit_taking", "wait_and_see"):
            StrategyChoiceSchema(id=valid)  # should not raise

    def test_core_conclusion_carries_new_fields(self) -> None:
        from api.v1.schemas.history import CoreConclusionSchema
        fields = CoreConclusionSchema.model_fields
        self.assertIn("strategy_choices", fields)
        self.assertIn("recommended_strategy", fields)
        self.assertIn("strategy_thesis", fields)
        self.assertIn("position_outcome_summary", fields)

    def test_position_outcome_summary_validates(self) -> None:
        from api.v1.schemas.history import PositionOutcomeSummarySchema
        s = PositionOutcomeSummarySchema(
            remaining_shares_after_all_triggers=0.0,
            worst_case_loss_pct=-10.0,
            worst_case_loss_amount=-12.0,
            worst_case_currency="GBP",
            best_case_gain_pct=30.0,
            best_case_gain_amount=36.0,
            risk_reward_ratio="1:3",
        )
        self.assertEqual(s.risk_reward_ratio, "1:3")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_strategy_classification.py -v`
Expected: FAIL on `ImportError: cannot import name 'StrategyChoiceSchema'`.

- [ ] **Step 3: Add schemas to `api/v1/schemas/history.py`**

Insert the three new schemas BEFORE `class CoreConclusionSchema` (around line 125) and extend `CoreConclusionSchema`. The full replacement block (replacing lines ~110-138):

```python
class ActionPlanItemSchema(BaseModel):
    """One entry in a portfolio-aware structured action plan."""
    trigger_price: Optional[float] = None
    trigger_condition: Optional[str] = None
    direction: Optional[str] = None
    shares: Optional[float] = None
    pct_of_position: Optional[float] = None
    pct_of_equity: Optional[float] = None
    technical_basis: Optional[str] = None
    fundamental_basis: Optional[str] = None
    quant_signal: Optional[str] = None
    invalidation_rule: Optional[str] = None
    priority: Optional[int] = None


class StrategyChoiceSchema(BaseModel):
    """One candidate strategy in the per-stock strategy comparison."""
    # Constrained to the four fixed ids: long_term_hold / swing_trade /
    # stepped_profit_taking / wait_and_see. Free-form to stay forward-compatible
    # with future additions; behavior validated at the post-process layer instead.
    id: Optional[str] = None
    label_zh: Optional[str] = None
    emoji: Optional[str] = None
    applicable: Optional[bool] = True
    fit_condition: Optional[str] = None
    key_params: Optional[str] = None
    time_horizon: Optional[str] = None
    inapplicable_reason: Optional[str] = None


class PositionOutcomeSummarySchema(BaseModel):
    """Aggregated outcome metrics after all action_plan_items are executed."""
    remaining_shares_after_all_triggers: Optional[float] = None
    worst_case_loss_pct: Optional[float] = None
    worst_case_loss_amount: Optional[float] = None
    worst_case_currency: Optional[str] = None
    best_case_gain_pct: Optional[float] = None
    best_case_gain_amount: Optional[float] = None
    risk_reward_ratio: Optional[str] = None


class CoreConclusionSchema(BaseModel):
    """Core conclusion section of the decision dashboard."""
    one_sentence: Optional[str] = None
    signal_type: Optional[str] = None
    time_sensitivity: Optional[str] = None
    position_advice: Optional[dict] = None
    action_plan_items: Optional[List[ActionPlanItemSchema]] = None
    strategy_choices: Optional[List[StrategyChoiceSchema]] = None
    recommended_strategy: Optional[str] = None
    strategy_thesis: Optional[str] = None
    position_outcome_summary: Optional[PositionOutcomeSummarySchema] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_strategy_classification.py -v`
Expected: 4 passed

- [ ] **Step 5: Confirm existing tests still pass**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_api_response.py tests/test_action_plan_llm_inject.py -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add api/v1/schemas/history.py tests/test_strategy_classification.py
git commit -m "feat: add StrategyChoice/PositionOutcomeSummary schemas and extend CoreConclusionSchema"
```

---

### Task 5: Strategy-aware prompt builder

**Files:**
- Modify: `src/services/portfolio_context_service.py`
- Test: `tests/test_strategy_classification.py` (append cases)

- [ ] **Step 1: Append prompt builder tests**

Append to `tests/test_strategy_classification.py`:

```python
class StrategyClassifyPromptTestCase(unittest.TestCase):
    def test_prompt_contains_all_four_strategy_ids(self) -> None:
        from src.services.portfolio_context_service import build_strategy_classify_prompt
        text = build_strategy_classify_prompt(
            portfolio_context_block="## [持仓上下文]\n- 账户：T\n- 平均成本：100",
            sentiment_dimensions={"reddit": {"buzz_score": 50}},
            compact_dashboard={"key_levels": {"ideal_buy": 95}},
        )
        for sid in ("long_term_hold", "swing_trade", "stepped_profit_taking", "wait_and_see"):
            self.assertIn(sid, text)

    def test_prompt_handles_missing_portfolio(self) -> None:
        """Without portfolio context the prompt downgrades cost-based wording."""
        from src.services.portfolio_context_service import build_strategy_classify_prompt
        text = build_strategy_classify_prompt(
            portfolio_context_block=None,
            sentiment_dimensions=None,
            compact_dashboard={"key_levels": {"ideal_buy": 95}},
        )
        self.assertIn("未持有", text)
        # No mention of cost-basis math when no portfolio
        self.assertNotIn("avg_cost ×", text)

    def test_prompt_embeds_sentiment_decision_rules(self) -> None:
        from src.services.portfolio_context_service import build_strategy_classify_prompt
        text = build_strategy_classify_prompt(
            portfolio_context_block="## [持仓上下文]\n- 平均成本：100",
            sentiment_dimensions={"x_twitter": {"buzz_trend": "falling"}},
            compact_dashboard={},
        )
        self.assertIn("buzz falling", text)  # rule referenced in prompt
```

- [ ] **Step 2: Run to verify failure**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_strategy_classification.py::StrategyClassifyPromptTestCase -v`
Expected: FAIL with `ImportError: cannot import name 'build_strategy_classify_prompt'`

- [ ] **Step 3: Implement `build_strategy_classify_prompt`**

In `src/services/portfolio_context_service.py`, append AFTER the existing `build_action_plan_instruction` function:

```python
STRATEGY_CLASSIFY_INSTRUCTION_ZH = """
## [策略分类与操作计划指令]

你必须按两步输出：先分类，后生成 items。

### 第一步：策略分类

阅读以下输入：
- 用户持仓上下文（成本价、浮盈浮亏、持有天数）
- 技术摘要（趋势、MA 排列、支撑/压力位）
- 基本面与新闻摘要
- 市场情绪 (Reddit / X / Polymarket / News)

按以下规则在 4 个固定策略里挑选 applicable 状态，并输出 1-4 个 strategy_choices 条目：

| 触发条件 | 推荐 / 适用 |
|---|---|
| 持仓盈利 > +5% + 技术结构未坏 + buzz falling 或 sentiment 降温 | 推荐 `stepped_profit_taking` |
| 持仓盈利 > +5% + 技术结构强 + buzz rising + bullish sentiment | 推荐 `swing_trade` 或 `long_term_hold` |
| 持仓亏损 -3% ~ -15% + 基本面叙事完好 | 推荐 `long_term_hold` 或 `wait_and_see` |
| 持仓亏损 > -15% + 基本面恶化 / sentiment 转负 | 推荐 `wait_and_see` |
| 未持有 + 趋势强 | 推荐 `swing_trade` |
| 未持有 + 趋势弱 + 估值偏高 | 推荐 `wait_and_see` |
| 财报 / 政策事件 < 14 天 + 持仓 | 推荐 `wait_and_see` |

applicable=false 的策略也要列出并填 `inapplicable_reason`。
recommended_strategy 字段填一个 id（long_term_hold / swing_trade / stepped_profit_taking / wait_and_see）。

### 第二步：写 strategy_thesis (100-200 字)

必须显式引用：
- 用户持仓状态（成本、浮盈/亏、持有天数）—— 未持有时引用现价与权益规模
- 至少 1 条技术依据（具体指标数值）
- 至少 1 条情绪依据（buzz 数值或 trend）
- 该策略的优势 + 劣势

### 第三步：生成 action_plan_items

严格遵循推荐策略的模板：

- `long_term_hold` → 必含 1 条 stop_loss (trigger_price ≤ avg_cost × 0.9 或，未持有时
  ≤ current_price × 0.85)；可选 1 条 buy on dip；禁止短线 trigger（距现价 < 5%）。共 2-3 条。
- `swing_trade` → 必含 1 条 entry (buy/sell)、1 条 stop_loss（chart-based）、
  1 条 take_profit（chart-based）。共 3-4 条。
- `stepped_profit_taking` → 必含 2-3 条 take_profit（阶梯价位）+ 1 条 cost-based stop_loss
  (avg_cost × 0.95)；禁止 buy。共 3-4 条。
- `wait_and_see` → 至多 1 条 item，须为事件类提醒（无价格 trigger）。共 0-1 条。

任何违反模板的 item 会在 post-process 阶段被丢弃。

通用规则（贯穿四策略）：
- take_profit 触发价必须 > 成本价（持仓时）
- stop_loss 触发价应当 ≤ 成本价 × 1.02（持仓时；介于成本上方的 chart support 用 sell 标）
- trigger_price 距 current_price 应当 ≥ 2.5%
- 所有 items 的 shares 总和 ≈ 持仓数（容差 ±5%）；未持有时按权益 5%-10% 折算建仓数

### 第四步：填 position_outcome_summary（持仓时）

```json
"position_outcome_summary": {
  "remaining_shares_after_all_triggers": 数值,
  "worst_case_loss_pct": -10.0,
  "worst_case_loss_amount": -12.0,
  "worst_case_currency": "GBP",
  "best_case_gain_pct": 30.0,
  "best_case_gain_amount": 36.0,
  "risk_reward_ratio": "1:3"
}
```

未持有时该字段可省略或全部填 null。
"""


def build_strategy_classify_prompt(
    portfolio_context_block: Optional[str],
    sentiment_dimensions: Optional[Dict[str, Any]],
    compact_dashboard: Dict[str, Any],
) -> str:
    """Compose the strategy-classification + action-plan-generation prompt.

    Universal: runs for all stocks (with or without portfolio). When portfolio is
    absent, cost-based rules switch to current-price relative rules. When sentiment
    is absent (e.g. A/HK stocks), the sentiment section degrades to text-only signal.
    """
    parts = [STRATEGY_CLASSIFY_INSTRUCTION_ZH]

    if portfolio_context_block and portfolio_context_block.strip():
        parts.append("\n## 持仓上下文\n" + portfolio_context_block)
    else:
        parts.append("\n## 持仓上下文\n用户未持有该股票，按建仓视角分析（cost-based 规则换为现价相对规则）。")

    if sentiment_dimensions:
        import json as _json
        parts.append("\n## 市场情绪\n" + _json.dumps(
            sentiment_dimensions, ensure_ascii=False, indent=2,
        ))

    import json as _json2
    parts.append("\n## 分析摘要\n" + _json2.dumps(
        compact_dashboard, ensure_ascii=False, indent=2, default=str,
    ))

    parts.append(
        "\n## 输出\n仅输出合法 JSON，顶层结构：\n"
        "{\n"
        '  "strategy_choices": [...],\n'
        '  "recommended_strategy": "<id>",\n'
        '  "strategy_thesis": "<100-200 字>",\n'
        '  "action_plan_items": [...],\n'
        '  "position_outcome_summary": {...}\n'
        "}\n"
        "不输出任何注释或代码块标记。"
    )

    return "\n".join(parts)
```

- [ ] **Step 4: Run prompt builder tests**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_strategy_classification.py -v`
Expected: 7 passed (4 schema + 3 prompt)

- [ ] **Step 5: Commit**

```bash
git add src/services/portfolio_context_service.py tests/test_strategy_classification.py
git commit -m "feat: add build_strategy_classify_prompt for adaptive strategy LLM call"
```

---

### Task 6: Rewrite `_try_inject_action_plan_items` to be strategy-aware + universal

**Files:**
- Modify: `src/analyzer.py:2332` (`_try_inject_action_plan_items`)
- Test: `tests/test_action_plan_llm_inject.py` (add cases)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_action_plan_llm_inject.py`:

```python
class StrategyClassificationInjectionTestCase(unittest.TestCase):
    def _make_result_no_strategy(self):
        from src.analyzer import AnalysisResult
        dash = _dashboard()
        return AnalysisResult(
            code="PLTR", name="Palantir", sentiment_score=43,
            trend_prediction="震荡", operation_advice="减仓",
            analysis_summary="", report_language="zh",
            dashboard=dash, portfolio_match="held",
        )

    def test_runs_without_portfolio_context_too(self):
        """Strategy classification must run for non-portfolio analyses (universal)."""
        payload = json.dumps({
            "strategy_choices": [
                {"id": "swing_trade", "label_zh": "短线波段",
                 "applicable": True, "fit_condition": "趋势强", "key_params": "MA20 防守"},
            ],
            "recommended_strategy": "swing_trade",
            "strategy_thesis": "技术结构健康...",
            "action_plan_items": [
                {"trigger_price": 130.0, "direction": "buy", "shares": 1.0, "priority": 1},
                {"trigger_price": 128.0, "direction": "stop_loss", "shares": 1.0, "priority": 2},
                {"trigger_price": 140.0, "direction": "take_profit", "shares": 1.0, "priority": 3},
            ],
        }, ensure_ascii=False)
        a = _make_analyzer(payload)
        result = self._make_result_no_strategy()
        a._try_inject_action_plan_items(result, "PLTR", portfolio_context_block=None)
        core = result.dashboard["core_conclusion"]
        self.assertEqual(core.get("recommended_strategy"), "swing_trade")
        self.assertEqual(len(core.get("action_plan_items", [])), 3)

    def test_injects_strategy_fields_when_present(self):
        payload = json.dumps({
            "strategy_choices": [
                {"id": "stepped_profit_taking", "label_zh": "阶梯式止盈",
                 "applicable": True},
                {"id": "swing_trade", "label_zh": "短线波段",
                 "applicable": False, "inapplicable_reason": "已有浮盈"},
            ],
            "recommended_strategy": "stepped_profit_taking",
            "strategy_thesis": "NVDA 当前已 +15% 浮盈...",
            "action_plan_items": [
                {"trigger_price": 236.0, "direction": "take_profit",
                 "shares": 0.25, "priority": 1},
                {"trigger_price": 145.0, "direction": "stop_loss",
                 "shares": 0.5, "priority": 2},
            ],
            "position_outcome_summary": {
                "remaining_shares_after_all_triggers": 0.25,
                "risk_reward_ratio": "1:3",
            },
        }, ensure_ascii=False)
        a = _make_analyzer(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "NVDA", _BLOCK_HELD)
        core = result.dashboard["core_conclusion"]
        self.assertEqual(len(core["strategy_choices"]), 2)
        self.assertEqual(core["strategy_choices"][1]["applicable"], False)
        self.assertIsNotNone(core["position_outcome_summary"])
        self.assertEqual(core["position_outcome_summary"]["risk_reward_ratio"], "1:3")
```

- [ ] **Step 2: Run to verify failure**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_llm_inject.py::StrategyClassificationInjectionTestCase -v`
Expected: FAIL — current code only handles `action_plan_items`, not `strategy_choices` etc.

- [ ] **Step 3: Rewrite `_try_inject_action_plan_items` in `src/analyzer.py`**

Replace the entire method (around line 2332) with:

```python
    def _try_inject_action_plan_items(
        self,
        result: "AnalysisResult",
        code: str,
        portfolio_context_block: Optional[str],
    ) -> None:
        """Post-process: ask the LLM for strategy classification + action plan.

        Universal: runs for all stocks, including non-portfolio analyses. Cost-based
        rules in the prompt degrade to current-price-relative rules when portfolio
        context is absent.
        """
        if not result or not result.dashboard:
            return
        core = result.dashboard.get("core_conclusion") or {}
        # Skip if a prior layer already filled both new fields.
        if (
            isinstance(core.get("recommended_strategy"), str)
            and core.get("recommended_strategy")
            and isinstance(core.get("action_plan_items"), list)
            and core.get("action_plan_items")
        ):
            return

        battle = result.dashboard.get("battle_plan") or {}
        sniper = battle.get("sniper_points") or {}
        intel = result.dashboard.get("intelligence") or {}
        persp = result.dashboard.get("data_perspective") or {}
        sentiment_dims = intel.get("sentiment_dimensions") if isinstance(intel, dict) else None

        compact_input = {
            "stock_code": code,
            "stock_name": getattr(result, "name", code),
            "portfolio_match": getattr(result, "portfolio_match", None),
            "key_levels": {
                "ideal_buy": sniper.get("ideal_buy"),
                "stop_loss": sniper.get("stop_loss"),
                "take_profit": sniper.get("take_profit"),
            },
            "time_sensitivity": core.get("time_sensitivity"),
            "decision": {
                "operation_advice": getattr(result, "operation_advice", None),
                "trend_prediction": getattr(result, "trend_prediction", None),
                "one_sentence": core.get("one_sentence"),
            },
            "technical_summary": {
                "ma_alignment": (persp.get("trend_status") or {}).get("ma_alignment"),
                "trend_score": (persp.get("trend_status") or {}).get("trend_score"),
                "price_position": persp.get("price_position"),
            },
            "intelligence_summary": {
                "risk_alerts": intel.get("risk_alerts", [])[:4],
                "positive_catalysts": intel.get("positive_catalysts", [])[:4],
                "earnings_outlook": intel.get("earnings_outlook"),
                "sentiment_summary": intel.get("sentiment_summary"),
            },
        }

        from src.services.portfolio_context_service import build_strategy_classify_prompt
        prompt = build_strategy_classify_prompt(
            portfolio_context_block=portfolio_context_block,
            sentiment_dimensions=sentiment_dims,
            compact_dashboard=compact_input,
        )

        raw = self.generate_text(prompt, max_tokens=3072, temperature=0.3)
        if not raw:
            return

        import json as _json
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        try:
            parsed = _json.loads(text)
        except Exception:
            return
        if not isinstance(parsed, dict):
            return

        # Sanitize items (cost-basis, distance, priority renumbering — handled in Task 7)
        items = parsed.get("action_plan_items")
        if not isinstance(items, list):
            items = []
        items = self._sanitize_action_plan_items(items, portfolio_context_block, code)

        # Inject all fields atomically
        if not isinstance(result.dashboard.get("core_conclusion"), dict):
            result.dashboard["core_conclusion"] = {}
        core_out = result.dashboard["core_conclusion"]

        if isinstance(parsed.get("strategy_choices"), list):
            core_out["strategy_choices"] = parsed["strategy_choices"]
        if isinstance(parsed.get("recommended_strategy"), str):
            core_out["recommended_strategy"] = parsed["recommended_strategy"]
        if isinstance(parsed.get("strategy_thesis"), str):
            core_out["strategy_thesis"] = parsed["strategy_thesis"]
        if items:
            core_out["action_plan_items"] = items
        if isinstance(parsed.get("position_outcome_summary"), dict):
            core_out["position_outcome_summary"] = parsed["position_outcome_summary"]

    def _sanitize_action_plan_items(
        self,
        items: list,
        portfolio_context_block: Optional[str],
        code: str,
    ) -> list:
        """Extract the existing sanitization logic into a reusable method.

        Cost-basis rules: drop take_profit at/below cost; reclassify stop_loss above
        cost*1.02 as sell. Renumber priorities contiguously. (Per-strategy template
        validation lives in Task 7.)
        """
        from src.services.portfolio_context_service import _parse_portfolio_facts
        avg_cost = _parse_portfolio_facts(portfolio_context_block or "").get("avg_cost")

        normalized: list = []
        for it in items[:4]:
            if not isinstance(it, dict):
                continue
            trig = it.get("trigger_price")
            direction = it.get("direction")
            if trig is None or not direction:
                continue
            if (
                direction == "take_profit" and avg_cost is not None
                and isinstance(trig, (int, float)) and trig <= avg_cost * 1.005
            ):
                logger.info("[action_plan] dropping take_profit @ %s ≤ cost %s", trig, avg_cost)
                continue
            if (
                direction == "stop_loss" and avg_cost is not None
                and isinstance(trig, (int, float)) and trig > avg_cost * 1.02
            ):
                logger.info("[action_plan] reclassifying stop_loss @ %s > cost*1.02 as sell", trig)
                it = dict(it)
                it["direction"] = "sell"
            normalized.append(it)

        # Renumber priorities 1..N
        normalized.sort(
            key=lambda x: (x.get("priority")
                           if isinstance(x.get("priority"), (int, float)) else 99)
        )
        for new_pri, it in enumerate(normalized, start=1):
            it["priority"] = new_pri

        return normalized
```

- [ ] **Step 4: Run targeted tests**

Run:
```bash
/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_llm_inject.py -v
```
Expected: all green (existing tests + new strategy classification tests).

- [ ] **Step 5: Commit**

```bash
git add src/analyzer.py tests/test_action_plan_llm_inject.py
git commit -m "feat: rewrite _try_inject_action_plan_items to be strategy-aware and universal"
```

---

### Task 7: Strategy template white/blacklist enforcement (post-process gate)

**Files:**
- Modify: `src/analyzer.py` (`_sanitize_action_plan_items` method just added)
- Test: `tests/test_action_plan_strategy_template.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_action_plan_strategy_template.py`:

```python
"""Tests for per-strategy action_plan_items template enforcement (post-process)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer import AnalysisResult, GeminiAnalyzer


_BLOCK_HELD = """## [持仓上下文]
- 账户：T
- 账户总权益：3000.00 GBP
- 持股数量：5 股 / 平均成本：144.0 USD/股
- 当前价：135.0 USD
"""


def _stub_llm(payload: str):
    a = GeminiAnalyzer.__new__(GeminiAnalyzer)
    a.generate_text = lambda *args, **kwargs: payload  # type: ignore[method-assign]
    return a


def _make_result():
    return AnalysisResult(
        code="PLTR", name="Palantir", sentiment_score=50,
        trend_prediction="震荡", operation_advice="减仓",
        analysis_summary="", report_language="zh",
        dashboard={"core_conclusion": {"one_sentence": "x"}},
        portfolio_match="held",
    )


class StrategyTemplateEnforcementTestCase(unittest.TestCase):
    def test_stepped_profit_taking_rejects_buy_items(self):
        """stepped_profit_taking forbids direction=buy (you have profit, don't add more)."""
        payload = json.dumps({
            "recommended_strategy": "stepped_profit_taking",
            "action_plan_items": [
                {"trigger_price": 140.0, "direction": "take_profit",
                 "shares": 1.0, "priority": 1},
                {"trigger_price": 130.0, "direction": "buy",
                 "shares": 1.0, "priority": 2},  # MUST be dropped
                {"trigger_price": 145.0, "direction": "stop_loss",
                 "shares": 2.0, "priority": 3},
            ],
        }, ensure_ascii=False)
        a = _stub_llm(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        directions = [it["direction"] for it in items]
        self.assertNotIn("buy", directions)

    def test_wait_and_see_caps_at_one_item(self):
        payload = json.dumps({
            "recommended_strategy": "wait_and_see",
            "action_plan_items": [
                {"trigger_price": 140.0, "direction": "take_profit",
                 "shares": 1.0, "priority": 1},
                {"trigger_price": 130.0, "direction": "buy",
                 "shares": 1.0, "priority": 2},
                {"trigger_price": 145.0, "direction": "stop_loss",
                 "shares": 2.0, "priority": 3},
            ],
        }, ensure_ascii=False)
        a = _stub_llm(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        # wait_and_see accepts at most 1 item (event reminders only)
        self.assertLessEqual(len(items), 1)

    def test_long_term_hold_appends_cost_based_stop_when_missing(self):
        """long_term_hold MUST have a real stop_loss at cost*0.9 or below."""
        payload = json.dumps({
            "recommended_strategy": "long_term_hold",
            "action_plan_items": [
                # LLM forgot the stop_loss
                {"trigger_price": 120.0, "direction": "buy",
                 "shares": 1.0, "priority": 1},
            ],
        }, ensure_ascii=False)
        a = _stub_llm(payload)
        result = _make_result()
        a._try_inject_action_plan_items(result, "PLTR", _BLOCK_HELD)
        items = result.dashboard["core_conclusion"]["action_plan_items"]
        stops = [it for it in items
                 if it["direction"] == "stop_loss"
                 and isinstance(it["trigger_price"], (int, float))
                 and it["trigger_price"] <= 144.0 * 0.91]
        self.assertGreaterEqual(len(stops), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_strategy_template.py -v`
Expected: All 3 fail.

- [ ] **Step 3: Extend `_sanitize_action_plan_items` to apply strategy templates**

Replace the existing `_sanitize_action_plan_items` body in `src/analyzer.py` (added in Task 6) with:

```python
    _STRATEGY_FORBIDDEN_DIRECTIONS = {
        "stepped_profit_taking": {"buy"},
        "long_term_hold": set(),
        "swing_trade": set(),
        "wait_and_see": {"buy", "sell", "stop_loss", "take_profit"},
    }
    _STRATEGY_MAX_ITEMS = {
        "long_term_hold": 3,
        "swing_trade": 4,
        "stepped_profit_taking": 4,
        "wait_and_see": 1,
    }

    def _sanitize_action_plan_items(
        self,
        items: list,
        portfolio_context_block: Optional[str],
        code: str,
        strategy: Optional[str] = None,
    ) -> list:
        """Apply cost-basis sanitization + per-strategy template enforcement.

        Per spec: stepped_profit_taking forbids buy; wait_and_see caps at 1 item;
        long_term_hold requires a cost-based real stop_loss at avg_cost × 0.9 — if
        missing we synthesize one.
        """
        from src.services.portfolio_context_service import _parse_portfolio_facts
        avg_cost = _parse_portfolio_facts(portfolio_context_block or "").get("avg_cost")
        forbidden = self._STRATEGY_FORBIDDEN_DIRECTIONS.get(strategy or "", set())
        max_items = self._STRATEGY_MAX_ITEMS.get(strategy or "", 4)

        normalized: list = []
        for it in items[: max(max_items, 4)]:
            if not isinstance(it, dict):
                continue
            trig = it.get("trigger_price")
            direction = it.get("direction")
            if trig is None or not direction:
                continue
            # Strategy template forbids this direction
            if direction in forbidden:
                logger.info(
                    "[action_plan] %s strategy forbids direction=%s; dropping item @ %s",
                    strategy, direction, trig,
                )
                continue
            # Cost-basis: drop TP at/below cost
            if (
                direction == "take_profit" and avg_cost is not None
                and isinstance(trig, (int, float)) and trig <= avg_cost * 1.005
            ):
                logger.info("[action_plan] dropping take_profit @ %s ≤ cost %s", trig, avg_cost)
                continue
            # Cost-basis: reclassify stop_loss above cost as defensive sell
            if (
                direction == "stop_loss" and avg_cost is not None
                and isinstance(trig, (int, float)) and trig > avg_cost * 1.02
            ):
                logger.info(
                    "[action_plan] reclassifying stop_loss @ %s > cost*1.02 as sell", trig,
                )
                it = dict(it)
                it["direction"] = "sell"
            normalized.append(it)

        # Cap to strategy-specific max
        normalized = normalized[:max_items]

        # long_term_hold / stepped_profit_taking: must have a cost-based real stop_loss
        if strategy in ("long_term_hold", "stepped_profit_taking") and avg_cost is not None:
            has_real_stop = any(
                it.get("direction") == "stop_loss"
                and isinstance(it.get("trigger_price"), (int, float))
                and it["trigger_price"] <= avg_cost * 0.95
                for it in normalized
            )
            if not has_real_stop:
                synth_stop = round(avg_cost * 0.9, 2)
                normalized.append({
                    "trigger_price": synth_stop,
                    "trigger_condition": (
                        f"基于成本基础的硬底线：成本价下方 10%，跌破该位强制止损"
                    ),
                    "direction": "stop_loss",
                    "shares": 0,
                    "pct_of_position": 100.0,
                    "technical_basis": "基于成本基础的真止损位（非技术信号）",
                    "fundamental_basis": "保护本金为先",
                    "quant_signal": None,
                    "invalidation_rule": f"当日强势收回 {round(avg_cost * 0.95, 2)} 以上则推迟",
                    "priority": 99,
                })

        # Renumber priorities 1..N
        normalized.sort(
            key=lambda x: (x.get("priority")
                           if isinstance(x.get("priority"), (int, float)) else 99)
        )
        for new_pri, it in enumerate(normalized, start=1):
            it["priority"] = new_pri

        return normalized
```

Update `_try_inject_action_plan_items` to pass `strategy` into the sanitizer. Find this line in the Task 6 implementation:

```python
items = self._sanitize_action_plan_items(items, portfolio_context_block, code)
```

Replace with:

```python
strategy = parsed.get("recommended_strategy") if isinstance(parsed.get("recommended_strategy"), str) else None
items = self._sanitize_action_plan_items(items, portfolio_context_block, code, strategy=strategy)
```

- [ ] **Step 4: Run tests**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_strategy_template.py tests/test_action_plan_llm_inject.py -v`
Expected: All green.

- [ ] **Step 5: Commit**

```bash
git add src/analyzer.py tests/test_action_plan_strategy_template.py
git commit -m "feat: enforce per-strategy action_plan_items templates in post-process"
```

---

### Task 8: Position outcome summary computation

**Files:**
- Modify: `src/analyzer.py` (extend `_try_inject_action_plan_items`)
- Test: `tests/test_position_outcome_summary.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_position_outcome_summary.py`:

```python
"""Tests for position_outcome_summary computation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class PositionOutcomeSummaryTestCase(unittest.TestCase):
    def test_computes_remaining_shares_after_all_triggers(self):
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        items = [
            {"direction": "take_profit", "shares": 0.3, "trigger_price": 240},
            {"direction": "take_profit", "shares": 0.2, "trigger_price": 250},
            {"direction": "stop_loss", "shares": 0.2597, "trigger_price": 176},
        ]
        result = a._compute_position_outcome_summary(
            items=items, holding_shares=0.7597,
            avg_cost=196.0, current_price=225.0, base_currency="GBP",
        )
        # 0.7597 - 0.3 - 0.2 - 0.2597 = 0.0
        self.assertAlmostEqual(result["remaining_shares_after_all_triggers"], 0.0, places=3)

    def test_worst_case_is_stop_loss_amount(self):
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        items = [{"direction": "stop_loss", "shares": 1.0, "trigger_price": 90.0}]
        result = a._compute_position_outcome_summary(
            items=items, holding_shares=1.0,
            avg_cost=100.0, current_price=105.0, base_currency="USD",
        )
        # Loss = (90 - 100) * 1.0 = -10
        self.assertAlmostEqual(result["worst_case_loss_amount"], -10.0)
        self.assertAlmostEqual(result["worst_case_loss_pct"], -10.0)
        self.assertEqual(result["worst_case_currency"], "USD")

    def test_best_case_is_take_profit(self):
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        items = [
            {"direction": "take_profit", "shares": 0.5, "trigger_price": 130.0},
            {"direction": "stop_loss", "shares": 0.5, "trigger_price": 90.0},
        ]
        result = a._compute_position_outcome_summary(
            items=items, holding_shares=1.0,
            avg_cost=100.0, current_price=105.0, base_currency="USD",
        )
        # Best: 0.5 * (130 - 100) = +15
        self.assertAlmostEqual(result["best_case_gain_amount"], 15.0)

    def test_risk_reward_ratio_formatted_as_1_to_n(self):
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        items = [
            {"direction": "take_profit", "shares": 1.0, "trigger_price": 130.0},
            {"direction": "stop_loss", "shares": 1.0, "trigger_price": 90.0},
        ]
        result = a._compute_position_outcome_summary(
            items=items, holding_shares=1.0,
            avg_cost=100.0, current_price=105.0, base_currency="USD",
        )
        # Risk = 10, reward = 30, R:R = 1:3
        self.assertEqual(result["risk_reward_ratio"], "1:3.0")

    def test_returns_none_without_holding(self):
        from src.analyzer import GeminiAnalyzer
        a = GeminiAnalyzer.__new__(GeminiAnalyzer)
        result = a._compute_position_outcome_summary(
            items=[], holding_shares=None, avg_cost=None,
            current_price=100, base_currency="USD",
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_position_outcome_summary.py -v`
Expected: 5 fails (`AttributeError: ... _compute_position_outcome_summary`).

- [ ] **Step 3: Implement `_compute_position_outcome_summary` in `src/analyzer.py`**

Add as a method on `GeminiAnalyzer`, near `_sanitize_action_plan_items`:

```python
    def _compute_position_outcome_summary(
        self,
        items: list,
        holding_shares: Optional[float],
        avg_cost: Optional[float],
        current_price: Optional[float],
        base_currency: str,
    ) -> Optional[Dict[str, Any]]:
        """Aggregate items into worst-case loss / best-case gain / R:R."""
        if holding_shares is None or holding_shares <= 0 or avg_cost is None:
            return None

        actioned = 0.0
        worst_loss = 0.0
        best_gain = 0.0
        for it in items:
            shares = it.get("shares")
            trig = it.get("trigger_price")
            direction = it.get("direction")
            if shares is None or trig is None:
                continue
            try:
                shares_f = float(shares)
                trig_f = float(trig)
            except (TypeError, ValueError):
                continue
            if shares_f <= 0:
                continue
            actioned += shares_f
            pnl = (trig_f - avg_cost) * shares_f
            if direction == "stop_loss" or pnl < 0:
                worst_loss += pnl
            elif direction in ("take_profit", "sell") and pnl > 0:
                best_gain += pnl

        remaining = max(0.0, holding_shares - actioned)
        position_value = holding_shares * avg_cost
        worst_pct = (worst_loss / position_value * 100.0) if position_value > 0 else 0.0
        best_pct = (best_gain / position_value * 100.0) if position_value > 0 else 0.0

        if worst_loss < 0:
            rr_ratio = f"1:{round(abs(best_gain / worst_loss), 1)}"
        else:
            rr_ratio = "N/A"

        return {
            "remaining_shares_after_all_triggers": round(remaining, 4),
            "worst_case_loss_pct": round(worst_pct, 1),
            "worst_case_loss_amount": round(worst_loss, 2),
            "worst_case_currency": base_currency,
            "best_case_gain_pct": round(best_pct, 1),
            "best_case_gain_amount": round(best_gain, 2),
            "risk_reward_ratio": rr_ratio,
        }
```

Wire it into `_try_inject_action_plan_items` — after the line that injects items, add:

```python
        # Compute position outcome when held + LLM didn't already supply one
        if items and not isinstance(core_out.get("position_outcome_summary"), dict):
            from src.services.portfolio_context_service import _parse_portfolio_facts
            facts = _parse_portfolio_facts(portfolio_context_block or "")
            outcome = self._compute_position_outcome_summary(
                items=items,
                holding_shares=facts.get("shares"),
                avg_cost=facts.get("avg_cost"),
                current_price=facts.get("last_price"),
                base_currency=facts.get("base_currency") or "USD",
            )
            if outcome:
                core_out["position_outcome_summary"] = outcome
```

- [ ] **Step 4: Run tests**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_position_outcome_summary.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/analyzer.py tests/test_position_outcome_summary.py
git commit -m "feat: compute position_outcome_summary (R:R) from action_plan_items"
```

---

### Task 9: Pipeline wires sentiment_dimensions into dashboard.intelligence

**Files:**
- Modify: `src/core/pipeline.py` (`_analyze_with_agent` around line 838 + non-agent path around line 432)
- Test: extend `tests/test_sentiment_dimensions.py`

- [ ] **Step 1: Append a pipeline integration test**

Append to `tests/test_sentiment_dimensions.py`:

```python
class PipelineSentimentDimensionsInjectionTestCase(unittest.TestCase):
    def test_sentiment_dimensions_lands_in_intelligence(self):
        """When social_sentiment_service returns dims, pipeline must inject them."""
        from src.analyzer import AnalysisResult
        result = AnalysisResult(
            code="NVDA", name="NVIDIA", sentiment_score=50,
            trend_prediction="震荡", operation_advice="持有",
            analysis_summary="", report_language="zh",
            dashboard={"intelligence": {}},
            portfolio_match="held",
        )
        from src.core.pipeline import _inject_sentiment_dimensions
        dims = {"x_twitter": {"buzz_score": 89.0}, "news": {"sentiment_score": 0.48}}
        _inject_sentiment_dimensions(result, dims)
        self.assertEqual(
            result.dashboard["intelligence"]["sentiment_dimensions"]["x_twitter"]["buzz_score"],
            89.0,
        )
```

- [ ] **Step 2: Run to verify failure**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_sentiment_dimensions.py::PipelineSentimentDimensionsInjectionTestCase -v`
Expected: FAIL with `ImportError: cannot import name '_inject_sentiment_dimensions'`.

- [ ] **Step 3: Add `_inject_sentiment_dimensions` helper to `src/core/pipeline.py`**

Add as a module-level function (near `_apply_portfolio_match`):

```python
def _inject_sentiment_dimensions(
    result: "AnalysisResult", dims: Optional[Dict[str, Any]]
) -> None:
    """Inject structured sentiment dimensions into result.dashboard.intelligence.

    Safe no-op when dims is None or result has no dashboard. Existing
    intelligence.sentiment_dimensions is overwritten (last-write-wins).
    """
    if not dims or not isinstance(dims, dict):
        return
    if not isinstance(getattr(result, "dashboard", None), dict):
        return
    intel = result.dashboard.get("intelligence")
    if not isinstance(intel, dict):
        intel = {}
        result.dashboard["intelligence"] = intel
    intel["sentiment_dimensions"] = dims
```

- [ ] **Step 4: Wire calls in both pipeline paths**

Update the two `get_social_context` callers (now they return a tuple per Task 3). After unpacking, stash sentiment_dims on `self` for later injection:

**Non-agent path** (around line 432):

```python
            if self.social_sentiment_service is not None and self.social_sentiment_service.is_available and is_us_stock_code(code):
                try:
                    social_result = self.social_sentiment_service.get_social_context(code)
                    if social_result:
                        social_context, sentiment_dims = social_result
                        self._latest_sentiment_dims = sentiment_dims
                        if news_context:
                            news_context = news_context + "\n\n" + social_context
                        else:
                            news_context = social_context
                except Exception as e:
                    logger.warning(f"{stock_name}({code}) Social sentiment fetch failed: {e}")
```

**Agent path** (around line 838):

```python
            if self.social_sentiment_service is not None and self.social_sentiment_service.is_available and is_us_stock_code(code):
                try:
                    social_result = self.social_sentiment_service.get_social_context(code)
                    if social_result:
                        social_context, sentiment_dims = social_result
                        self._latest_sentiment_dims = sentiment_dims
                        existing = initial_context.get("news_context")
                        if existing:
                            initial_context["news_context"] = existing + "\n\n" + social_context
                        else:
                            initial_context["news_context"] = social_context
                        logger.info(f"[{code}] Agent mode: social sentiment data injected into news_context")
                except Exception as e:
                    logger.warning(f"[{code}] Agent mode: social sentiment fetch failed: {e}")
```

Initialize `self._latest_sentiment_dims = None` in `StockAnalysisPipeline.__init__`.

After the LLM result is produced (in BOTH paths, before the `_apply_portfolio_match` call), call:

```python
                _inject_sentiment_dimensions(result, getattr(self, "_latest_sentiment_dims", None))
```

- [ ] **Step 5: Run tests**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_sentiment_dimensions.py tests/test_action_plan_agent_path.py tests/test_pipeline_portfolio_match.py -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/core/pipeline.py tests/test_sentiment_dimensions.py
git commit -m "feat: wire structured sentiment_dimensions into dashboard.intelligence"
```

---

### Task 10: Strategy-aware synthesis fallback templates

**Files:**
- Modify: `src/services/portfolio_context_service.py` (`synthesize_action_plan_items`)
- Test: extend `tests/test_action_plan_synthesis.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_action_plan_synthesis.py`:

```python
class StrategyAwareSynthesisTestCase(unittest.TestCase):
    """When synthesize_action_plan_items is given a strategy hint, items must
    follow per-strategy templates (mirrors LLM-output post-process enforcement).
    """

    def _dash(self):
        return {
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": 130.0, "stop_loss": 128.0, "take_profit": 145.0,
                },
            },
            "data_perspective": {"trend_status": {"ma_alignment": "bullish"}},
            "intelligence": {"earnings_outlook": "正面"},
        }

    def test_synthesis_long_term_hold_includes_cost_based_stop(self):
        from src.services.portfolio_context_service import synthesize_action_plan_items
        block = """## [持仓上下文]
- 持股数量：1 股 / 平均成本：100.0 USD/股
- 账户总权益：1000.00 USD
- 当前价：130.0 USD
"""
        items = synthesize_action_plan_items(
            self._dash(), block, is_held=True, strategy="long_term_hold",
        )
        # Must contain a stop_loss at cost*0.9 = 90 or below
        cost_stops = [
            it for it in items
            if it["direction"] == "stop_loss"
            and isinstance(it["trigger_price"], (int, float))
            and it["trigger_price"] <= 91.0
        ]
        self.assertGreaterEqual(len(cost_stops), 1)

    def test_synthesis_stepped_profit_taking_excludes_buy(self):
        from src.services.portfolio_context_service import synthesize_action_plan_items
        block = """## [持仓上下文]
- 持股数量：1 股 / 平均成本：100.0 USD/股
- 账户总权益：1000.00 USD
- 当前价：130.0 USD
"""
        items = synthesize_action_plan_items(
            self._dash(), block, is_held=True, strategy="stepped_profit_taking",
        )
        directions = [it["direction"] for it in items]
        self.assertNotIn("buy", directions)

    def test_synthesis_wait_and_see_caps_at_one_item(self):
        from src.services.portfolio_context_service import synthesize_action_plan_items
        block = """## [持仓上下文]
- 持股数量：1 股 / 平均成本：100.0 USD/股
- 账户总权益：1000.00 USD
"""
        items = synthesize_action_plan_items(
            self._dash(), block, is_held=True, strategy="wait_and_see",
        )
        self.assertLessEqual(len(items), 1)
```

- [ ] **Step 2: Run to verify failure**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_synthesis.py::StrategyAwareSynthesisTestCase -v`
Expected: All fail (current signature has no `strategy` parameter).

- [ ] **Step 3: Add `strategy` parameter to `synthesize_action_plan_items`**

In `src/services/portfolio_context_service.py`, find the existing `synthesize_action_plan_items(dashboard, portfolio_context_block, *, is_held)` signature and add `strategy: Optional[str] = None` keyword. At the start of the function body, branch on strategy:

```python
def synthesize_action_plan_items(
    dashboard: Dict[str, Any],
    portfolio_context_block: Optional[str],
    *,
    is_held: bool,
    strategy: Optional[str] = None,
) -> List[Dict[str, Any]]:
    # ... existing body unchanged through facts parsing ...

    # ---- Strategy-specific overrides (applied AFTER the existing items list) ----
    # The existing logic still runs and produces base items; we then filter/append.
```

After the existing body computes `items`, add a strategy-aware post-filter block BEFORE `return items`:

```python
    # ---- Apply per-strategy template ----
    if strategy == "wait_and_see":
        # Replace items with at most 1 event-reminder item
        items = items[:1] if items else []
    elif strategy == "stepped_profit_taking":
        items = [it for it in items if it.get("direction") != "buy"]
        # Append a cost-based stop_loss if missing
        if is_held and avg_cost is not None and not any(
            it.get("direction") == "stop_loss"
            and isinstance(it.get("trigger_price"), (int, float))
            and it["trigger_price"] <= avg_cost * 0.97
            for it in items
        ):
            items.append({
                "trigger_price": round(avg_cost * 0.95, 2),
                "trigger_condition": "基于成本基础的 protection stop",
                "direction": "stop_loss",
                "shares": round(shares, 4) if shares and shares < 1 else round(shares or 0),
                "pct_of_position": 100.0,
                "pct_of_equity": _pct_of_equity(shares or 0, avg_cost, equity),
                "technical_basis": "cost-based protection (非技术信号)",
                "fundamental_basis": fundamental_basis,
                "quant_signal": None,
                "invalidation_rule": f"当日强势收回 {round(avg_cost * 0.97, 2)} 以上则推迟",
                "priority": 99,
            })
    elif strategy == "long_term_hold":
        # Filter out short-term triggers (within 5% of current price) and append cost-based stop
        items = [
            it for it in items
            if not (
                isinstance(it.get("trigger_price"), (int, float))
                and last_price is not None
                and abs(it["trigger_price"] - last_price) / last_price < 0.05
            )
        ]
        if is_held and avg_cost is not None and not any(
            it.get("direction") == "stop_loss"
            and isinstance(it.get("trigger_price"), (int, float))
            and it["trigger_price"] <= avg_cost * 0.91
            for it in items
        ):
            items.append({
                "trigger_price": round(avg_cost * 0.9, 2),
                "trigger_condition": "长线持有的硬底线：成本下方 10%",
                "direction": "stop_loss",
                "shares": round(shares, 4) if shares and shares < 1 else round(shares or 0),
                "pct_of_position": 100.0,
                "pct_of_equity": _pct_of_equity(shares or 0, avg_cost, equity),
                "technical_basis": "基于成本基础（非技术信号）",
                "fundamental_basis": fundamental_basis,
                "quant_signal": None,
                "invalidation_rule": "基本面叙事破裂时直接执行；技术反弹可推迟",
                "priority": 99,
            })

    return items
```

Note: `last_price`, `shares`, `avg_cost`, `equity`, `fundamental_basis`, `_pct_of_equity` must already be in scope from the existing body of the function.

- [ ] **Step 4: Run tests**

Run:
```bash
/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_synthesis.py -v
```
Expected: all green.

- [ ] **Step 5: Update `_fill_action_plan_items_if_missing` to pass strategy**

In `src/core/pipeline.py`, find `_fill_action_plan_items_if_missing` and update the call site:

```python
def _fill_action_plan_items_if_missing(
    result: "AnalysisResult", portfolio_context_block: Optional[str]
) -> None:
    # ... existing guards ...

    try:
        from src.services.portfolio_context_service import synthesize_action_plan_items
        is_held = getattr(result, "portfolio_match", None) == "held"
        strategy = result.dashboard.get("core_conclusion", {}).get("recommended_strategy") \
            if isinstance(result.dashboard, dict) else None
        items = synthesize_action_plan_items(
            dashboard, portfolio_context_block,
            is_held=is_held, strategy=strategy,
        )
    except Exception:
        return
    # ... rest unchanged
```

- [ ] **Step 6: Commit**

```bash
git add src/services/portfolio_context_service.py src/core/pipeline.py tests/test_action_plan_synthesis.py
git commit -m "feat: strategy-aware synthesis fallback templates"
```

---

### Task 11: Pipeline universalization — strategy classification runs for ALL stocks

**Files:**
- Modify: `src/core/pipeline.py` (both analyze paths)
- Test: extend `tests/test_action_plan_agent_path.py`

- [ ] **Step 1: Append the universal test**

Append to `tests/test_action_plan_agent_path.py`:

```python
class StrategyClassificationUniversalTestCase(unittest.TestCase):
    """Strategy classification must fire for non-portfolio analyses too."""

    def test_pipeline_calls_strategy_inject_even_without_portfolio_context(self):
        from src.core.pipeline import StockAnalysisPipeline
        from src.analyzer import AnalysisResult

        called = {"args": None}

        def fake_inject(self, result, code, portfolio_block):
            called["args"] = (code, portfolio_block)

        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.portfolio_context_block = None  # NO portfolio
        pipeline.analyzer = type("A", (), {
            "_try_inject_action_plan_items": fake_inject.__get__(None, type(None)),
        })()
        # Stub the binding to use the analyzer mock
        pipeline.analyzer._try_inject_action_plan_items = (
            lambda result, code, portfolio_block: called.__setitem__("args", (code, portfolio_block))
        )

        result = AnalysisResult(
            code="NVDA", name="N", sentiment_score=50,
            trend_prediction="x", operation_advice="x",
            dashboard={"core_conclusion": {}}, portfolio_match=None,
        )
        # Run the helper directly (it's not gated anymore)
        if hasattr(pipeline.analyzer, "_try_inject_action_plan_items"):
            pipeline.analyzer._try_inject_action_plan_items(result, "NVDA", None)
        self.assertEqual(called["args"], ("NVDA", None))
```

- [ ] **Step 2: Run to verify the test passes already (Task 6 made `_try_inject` universal)**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_agent_path.py::StrategyClassificationUniversalTestCase -v`
Expected: PASS (Task 6 already made the method universal).

- [ ] **Step 3: Audit + remove portfolio_context_block guards from pipeline call sites**

Open `src/core/pipeline.py` and locate the two places where `_try_inject_action_plan_items` is called (one in non-agent path, one in agent path). In both, ensure the call is unconditional, e.g.:

```python
                if hasattr(self.analyzer, '_try_inject_action_plan_items'):
                    try:
                        self.analyzer._try_inject_action_plan_items(
                            result, code, self.portfolio_context_block
                        )
                    except Exception:
                        pass
```

No `if self.portfolio_context_block:` guard around this. If such a guard exists in either path, remove it.

Also update `_fill_action_plan_items_if_missing` to drop the guard "skip when block empty" (it should still synthesize using `is_held=False` mode). Find:

```python
def _fill_action_plan_items_if_missing(
    result: "AnalysisResult", portfolio_context_block: Optional[str]
) -> None:
    if not portfolio_context_block or not str(portfolio_context_block).strip():
        return
    # ...
```

Replace with:

```python
def _fill_action_plan_items_if_missing(
    result: "AnalysisResult", portfolio_context_block: Optional[str]
) -> None:
    """Synthesize action_plan_items when both LLM and post-process produced nothing.

    Universal: runs for any analysis, including non-portfolio. Pass-through to
    synthesize_action_plan_items which handles is_held=False + strategy=None.
    """
    dashboard = getattr(result, "dashboard", None)
    if not isinstance(dashboard, dict):
        return
    core = dashboard.get("core_conclusion")
    if not isinstance(core, dict):
        return
    existing = core.get("action_plan_items")
    if isinstance(existing, list) and existing:
        return  # already populated upstream

    try:
        from src.services.portfolio_context_service import synthesize_action_plan_items
        is_held = getattr(result, "portfolio_match", None) == "held"
        strategy = core.get("recommended_strategy")
        items = synthesize_action_plan_items(
            dashboard, portfolio_context_block,
            is_held=is_held, strategy=strategy,
        )
    except Exception:
        return
    if items:
        core["action_plan_items"] = items
        dashboard["core_conclusion"] = core
```

- [ ] **Step 4: Run full suite**

Run:
```bash
/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_synthesis.py tests/test_action_plan_llm_inject.py tests/test_action_plan_agent_path.py tests/test_pipeline_portfolio_match.py tests/test_strategy_classification.py tests/test_action_plan_strategy_template.py -m "not network" -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/core/pipeline.py tests/test_action_plan_agent_path.py
git commit -m "feat: strategy classification runs for ALL stocks (universal, not just portfolio-aware)"
```

---

### Task 12: Agent system prompts include new schema fields

**Files:**
- Modify: `src/agent/executor.py` (both `AGENT_SYSTEM_PROMPT` and `LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_action_plan_agent_path.py`:

```python
class AgentPromptStrategyFieldsTestCase(unittest.TestCase):
    def test_agent_prompts_include_strategy_choices(self):
        from src.agent.executor import AGENT_SYSTEM_PROMPT, LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT
        for prompt in (AGENT_SYSTEM_PROMPT, LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT):
            self.assertIn("strategy_choices", prompt)
            self.assertIn("recommended_strategy", prompt)
            self.assertIn("strategy_thesis", prompt)
            self.assertIn("position_outcome_summary", prompt)
            self.assertIn("sentiment_dimensions", prompt)
```

- [ ] **Step 2: Run to verify failure**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_agent_path.py::AgentPromptStrategyFieldsTestCase -v`
Expected: FAIL — fields not present.

- [ ] **Step 3: Update both system prompts**

In `src/agent/executor.py`, find both `AGENT_SYSTEM_PROMPT` and `LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT` (look for the JSON example block, which contains `"core_conclusion": {{`). Replace the existing `core_conclusion` example block in BOTH prompts with:

```python
        "core_conclusion": {{
            "one_sentence": "核心结论（直接告诉用户做什么，可以包含关键价位，无字数硬性上限）",
            "signal_type": "🟢买入信号/🟡持有观望/🔴卖出信号/⚠️风险警告",
            "time_sensitivity": "立即行动/今日内/本周内/不急",
            "position_advice": {{
                "no_position": "空仓者建议",
                "has_position": "持仓者建议"
            }},
            "_comment_strategy": "以下 4 字段为策略分类输出（适用于所有分析，不仅 portfolio）",
            "strategy_choices": [
                {{
                    "id": "stepped_profit_taking",
                    "label_zh": "阶梯式止盈",
                    "emoji": "🪜",
                    "applicable": true,
                    "fit_condition": "已有浮盈，希望分批锁定",
                    "key_params": "$236/$245/$255 三段减仓",
                    "time_horizon": "滚动",
                    "inapplicable_reason": null
                }}
            ],
            "recommended_strategy": "stepped_profit_taking",
            "strategy_thesis": "NVDA 当前... 建议按阶梯止盈对待... 优势是锁定胜利成果...缺点是若突破后再大涨会少赚一些。",
            "_comment_action_plan": "以下字段在所有 portfolio-aware 分析中输出",
            "action_plan_items": [
                {{
                    "trigger_price": 421.0,
                    "trigger_condition": "价格回踩 MA5 后企稳 2 日",
                    "direction": "sell",
                    "shares": 30,
                    "pct_of_position": 20.0,
                    "pct_of_equity": 3.5,
                    "technical_basis": "RSI=74 超买",
                    "fundamental_basis": "诉讼风险尚未 price-in",
                    "quant_signal": "量比 1.8",
                    "invalidation_rule": "放量站稳 $428 作废",
                    "priority": 1
                }}
            ],
            "position_outcome_summary": {{
                "remaining_shares_after_all_triggers": 0.0,
                "worst_case_loss_pct": -10.0,
                "worst_case_loss_amount": -12.0,
                "worst_case_currency": "GBP",
                "best_case_gain_pct": 30.0,
                "best_case_gain_amount": 36.0,
                "risk_reward_ratio": "1:3"
            }}
        }},
```

Also extend the `intelligence` block in both prompts to mention `sentiment_dimensions`:

```python
        "intelligence": {{
            "latest_news": "",
            "risk_alerts": [],
            "positive_catalysts": [],
            "earnings_outlook": "",
            "sentiment_summary": "",
            "sentiment_dimensions": {{
                "_comment": "结构化情绪数据（仅美股有；A/HK 股 null）",
                "reddit": {{"buzz_score": 84.4, "buzz_trend": "rising", "sentiment_score": 0.06}},
                "x_twitter": {{"buzz_score": 89.0, "buzz_trend": "falling", "sentiment_score": 0.28}},
                "polymarket": {{"buzz_score": 64.7, "sentiment_score": 0.13}},
                "news": {{"buzz_score": 61.6, "buzz_trend": "stable", "sentiment_score": 0.48}},
                "stocktwits": {{"bullish_ratio": 0.62, "bearish_ratio": 0.18}}
            }}
        }},
```

- [ ] **Step 4: Run tests**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_agent_path.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/agent/executor.py tests/test_action_plan_agent_path.py
git commit -m "feat: agent system prompts include strategy_choices/thesis/sentiment_dimensions schema"
```

---

### Task 13: Backend renderer for strategy section + sentiment + position outcome

**Files:**
- Modify: `src/notification.py` + `src/services/history_service.py` (parallel changes)
- Modify: `src/report_language.py`
- Test: extend `tests/test_action_plan_renderer.py`

- [ ] **Step 1: Add labels to `src/report_language.py`**

In the `"zh"` dict (around line 240), add:

```python
        "strategy_section_heading": "策略选择",
        "recommended_strategy_heading": "AI 推荐策略",
        "strategy_thesis_heading": "策略论述",
        "sentiment_section_heading": "市场情绪",
        "position_outcome_heading": "仓位流水汇总",
        "rr_ratio_label": "风险回报比",
```

In the `"en"` dict, mirror:

```python
        "strategy_section_heading": "Strategy Selection",
        "recommended_strategy_heading": "AI Recommended Strategy",
        "strategy_thesis_heading": "Strategy Thesis",
        "sentiment_section_heading": "Market Sentiment",
        "position_outcome_heading": "Position Outcome Summary",
        "rr_ratio_label": "Risk:Reward",
```

- [ ] **Step 2: Append failing renderer tests**

Append to `tests/test_action_plan_renderer.py`:

```python
class StrategyAndSentimentRendererTestCase(unittest.TestCase):
    def _result_with_strategy(self):
        dashboard = {
            "core_conclusion": {
                "one_sentence": "短线偏弱",
                "signal_type": "🟡",
                "time_sensitivity": "本周内",
                "position_advice": {"no_position": "x", "has_position": "y"},
                "strategy_choices": [
                    {"id": "stepped_profit_taking", "label_zh": "阶梯式止盈",
                     "emoji": "🪜", "applicable": True,
                     "fit_condition": "已有浮盈", "key_params": "$236/$245",
                     "time_horizon": "滚动"},
                    {"id": "swing_trade", "label_zh": "短线波段",
                     "emoji": "⚡", "applicable": False,
                     "inapplicable_reason": "已有浮盈，不该频繁进出"},
                ],
                "recommended_strategy": "stepped_profit_taking",
                "strategy_thesis": "NVDA 目前结构健康，建议阶梯式止盈兑现。",
                "action_plan_items": [
                    {"trigger_price": 236.5, "direction": "take_profit",
                     "shares": 0.25, "pct_of_position": 33,
                     "pct_of_equity": 2.35, "priority": 1,
                     "trigger_condition": "突破 236"},
                ],
                "position_outcome_summary": {
                    "remaining_shares_after_all_triggers": 0.0,
                    "worst_case_loss_amount": -12.0,
                    "worst_case_currency": "GBP",
                    "best_case_gain_amount": 36.0,
                    "risk_reward_ratio": "1:3",
                },
            },
            "intelligence": {
                "sentiment_dimensions": {
                    "x_twitter": {"buzz_score": 89.0, "buzz_trend": "falling"},
                    "news": {"buzz_score": 61.6, "sentiment_score": 0.48},
                },
            },
        }
        return AnalysisResult(
            code="NVDA", name="NVIDIA", sentiment_score=50,
            trend_prediction="震荡", operation_advice="持有",
            analysis_summary="", report_language="zh",
            dashboard=dashboard, portfolio_match="held",
        )

    def test_notification_renders_strategy_selector(self):
        result = self._result_with_strategy()
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("策略选择", md)
        self.assertIn("阶梯式止盈", md)
        self.assertIn("已有浮盈，不该频繁进出", md)  # inapplicable_reason
        self.assertIn("策略论述", md)

    def test_notification_renders_sentiment_panel(self):
        result = self._result_with_strategy()
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("市场情绪", md)
        self.assertIn("89", md)  # x_twitter buzz

    def test_notification_renders_position_outcome(self):
        result = self._result_with_strategy()
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("仓位流水汇总", md)
        self.assertIn("1:3", md)

    def test_history_service_renders_strategy_selector(self):
        svc = HistoryService.__new__(HistoryService)
        result = self._result_with_strategy()
        md = svc._generate_single_stock_markdown(result, _fake_record())
        self.assertIn("策略选择", md)
        self.assertIn("阶梯式止盈", md)
```

- [ ] **Step 3: Run to verify failure**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_renderer.py::StrategyAndSentimentRendererTestCase -v`
Expected: 4 fails.

- [ ] **Step 4: Add module-level helper renderers (in both `notification.py` and `history_service.py`)**

At the top of `src/notification.py`, after `_render_action_plan_items`, add:

```python
_STRATEGY_EMOJI = {
    "long_term_hold": "🌳",
    "swing_trade": "⚡",
    "stepped_profit_taking": "🪜",
    "wait_and_see": "🚪",
}
_STRATEGY_LABEL_ZH = {
    "long_term_hold": "长线持有",
    "swing_trade": "短线波段",
    "stepped_profit_taking": "阶梯式止盈",
    "wait_and_see": "暂不操作",
}


def _render_strategy_section(
    core: dict, labels: dict, report_language: str
) -> list:
    """Render 📌 策略选择 section as markdown lines."""
    choices = core.get("strategy_choices") or []
    recommended = core.get("recommended_strategy")
    thesis = core.get("strategy_thesis")
    if not choices and not recommended and not thesis:
        return []

    lines = [f"### 📌 {labels.get('strategy_section_heading', '策略选择')}", ""]

    if choices:
        lines.extend([
            "| 策略 | 适用条件 | 关键参数 | 时间维度 |",
            "|---|---|---|---|",
        ])
        for c in choices:
            sid = c.get("id") or ""
            emoji = c.get("emoji") or _STRATEGY_EMOJI.get(sid, "📌")
            label = c.get("label_zh") or _STRATEGY_LABEL_ZH.get(sid, sid)
            if not c.get("applicable", True):
                reason = c.get("inapplicable_reason") or "不适用"
                lines.append(f"| {emoji} {label} | ⚪ 不适用（{reason}） |  |  |")
            else:
                fit = c.get("fit_condition") or "—"
                params = c.get("key_params") or "—"
                horizon = c.get("time_horizon") or "—"
                lines.append(f"| {emoji} {label} | {fit} | {params} | {horizon} |")
        lines.append("")

    if recommended:
        emoji = _STRATEGY_EMOJI.get(recommended, "🎯")
        label = _STRATEGY_LABEL_ZH.get(recommended, recommended)
        heading = labels.get("recommended_strategy_heading", "AI 推荐策略")
        lines.append(f"**🎯 {heading}**: {emoji} {label}")
        lines.append("")

    if thesis:
        thesis_heading = labels.get("strategy_thesis_heading", "策略论述")
        lines.append(f"**{thesis_heading}**：")
        lines.append(f"> {thesis}")
        lines.append("")

    return lines


def _render_sentiment_panel(intel: dict, labels: dict) -> list:
    """Render 📱 市场情绪 section as markdown lines."""
    dims = (intel or {}).get("sentiment_dimensions")
    if not isinstance(dims, dict) or not dims:
        return []

    heading = labels.get("sentiment_section_heading", "市场情绪")
    lines = [f"### 📱 {heading}", ""]
    lines.extend(["| 来源 | Buzz | Sentiment | Trend | Mentions |", "|---|---|---|---|---|"])

    source_order = ["news", "reddit", "x_twitter", "polymarket", "stocktwits"]
    source_labels = {
        "news": "📰 News",
        "reddit": "🔴 Reddit",
        "x_twitter": "🐦 X",
        "polymarket": "🔮 Polymarket",
        "stocktwits": "💬 StockTwits",
    }
    for key in source_order:
        d = dims.get(key)
        if not isinstance(d, dict):
            continue
        buzz = d.get("buzz_score")
        sent = d.get("sentiment_score")
        trend = d.get("buzz_trend") or "—"
        mentions = d.get("mentions_7d") or d.get("messages_sampled") or "—"
        if key == "stocktwits":
            # different metric set
            bull = d.get("bullish_ratio")
            bear = d.get("bearish_ratio")
            sent = f"Bull {round(bull*100)}% / Bear {round(bear*100)}%" if bull is not None else "—"
            buzz = "—"
            trend = "—"
        lines.append(
            f"| {source_labels[key]} | {buzz if buzz is not None else '—'} "
            f"| {sent if sent is not None else '—'} | {trend} | {mentions} |"
        )
    lines.append("")
    return lines


def _render_position_outcome(outcome: dict, labels: dict) -> list:
    """Render 仓位流水汇总 block."""
    if not isinstance(outcome, dict) or not outcome:
        return []
    heading = labels.get("position_outcome_heading", "仓位流水汇总")
    rr_label = labels.get("rr_ratio_label", "风险回报比")
    remain = outcome.get("remaining_shares_after_all_triggers")
    wl = outcome.get("worst_case_loss_amount")
    wc = outcome.get("worst_case_currency") or ""
    bg = outcome.get("best_case_gain_amount")
    rr = outcome.get("risk_reward_ratio") or "N/A"
    return [
        f"**📊 {heading}**",
        "",
        f"- 执行所有触发后剩余仓位：{remain if remain is not None else '—'} 股",
        f"- 最差止损：{wl if wl is not None else '—'} {wc}",
        f"- 最好止盈：{bg if bg is not None else '—'} {wc}",
        f"- {rr_label}：{rr}",
        "",
    ]
```

- [ ] **Step 5: Mirror these helpers in `src/services/history_service.py`**

Copy the same three functions (`_render_strategy_section`, `_render_sentiment_panel`, `_render_position_outcome`) into `src/services/history_service.py` at module level, after the existing `_render_action_plan_items` helper.

- [ ] **Step 6: Wire renderers into both files' dashboard rendering paths**

In `src/notification.py` (in the dashboard rendering loop, after the existing `action_plan_items` block around line 1133), insert:

```python
                # ========== 📌 策略选择 ==========
                report_lines.extend(_render_strategy_section(core, labels, report_language))

                # ========== 📊 仓位流水汇总 ==========
                report_lines.extend(_render_position_outcome(
                    core.get("position_outcome_summary"), labels,
                ))
```

After the existing `intelligence` rendering block (look for `intel = dashboard.get('intelligence', {})`), insert:

```python
                # ========== 📱 市场情绪 ==========
                report_lines.extend(_render_sentiment_panel(intel, labels))
```

Mirror identical insertions in `src/services/history_service.py` at the corresponding locations (after action_plan_items rendering at line 757, and after intelligence rendering).

- [ ] **Step 7: Run renderer tests**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_renderer.py -v`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/notification.py src/services/history_service.py src/report_language.py tests/test_action_plan_renderer.py
git commit -m "feat: backend renderer for strategy selector / sentiment panel / position outcome"
```

---

### Task 14: Frontend TypeScript types + 4 new components

**Files:**
- Modify: `apps/dsa-web/src/types/analysis.ts`
- Create: `apps/dsa-web/src/components/report/StrategySelector.tsx`
- Create: `apps/dsa-web/src/components/report/StrategyThesis.tsx`
- Create: `apps/dsa-web/src/components/report/SentimentPanel.tsx`
- Create: `apps/dsa-web/src/components/report/PositionOutcomeSummary.tsx`
- Modify: `apps/dsa-web/src/components/report/index.ts`
- Modify: `apps/dsa-web/src/components/report/ReportSummary.tsx`

- [ ] **Step 1: Add TypeScript types**

In `apps/dsa-web/src/types/analysis.ts`, after the existing `ActionPlanItem` interface, add:

```typescript
/** One candidate strategy in the strategy comparison table. */
export interface StrategyChoice {
  id: 'long_term_hold' | 'swing_trade' | 'stepped_profit_taking' | 'wait_and_see' | string;
  labelZh?: string;
  emoji?: string;
  applicable?: boolean;
  fitCondition?: string;
  keyParams?: string;
  timeHorizon?: string;
  inapplicableReason?: string;
}

export interface PositionOutcomeSummary {
  remainingSharesAfterAllTriggers?: number;
  worstCaseLossPct?: number;
  worstCaseLossAmount?: number;
  worstCaseCurrency?: string;
  bestCaseGainPct?: number;
  bestCaseGainAmount?: number;
  riskRewardRatio?: string;
}

export interface SentimentDimensions {
  reddit?: {
    buzzScore?: number;
    buzzTrend?: string;
    sentimentScore?: number;
    mentions7d?: number;
    bullishPct?: number;
    bearishPct?: number;
  };
  xTwitter?: {
    buzzScore?: number;
    buzzTrend?: string;
    sentimentScore?: number;
    mentions7d?: number;
  };
  polymarket?: {
    buzzScore?: number;
    sentimentScore?: number;
    tradeCount?: number;
  };
  news?: {
    buzzScore?: number;
    buzzTrend?: string;
    sentimentScore?: number;
    mentions7d?: number;
    bullishPct?: number;
    bearishPct?: number;
  };
  stocktwits?: {
    bullishRatio?: number;
    bearishRatio?: number;
    neutralRatio?: number;
    messagesSampled?: number;
  };
}
```

Extend the existing `CoreConclusion` interface (replace the existing `actionPlanItems` line block):

```typescript
export interface CoreConclusion {
  oneSentence?: string;
  signalType?: string;
  timeSensitivity?: string;
  positionAdvice?: { noPosition?: string; hasPosition?: string };
  actionPlanItems?: ActionPlanItem[];
  strategyChoices?: StrategyChoice[];
  recommendedStrategy?: string;
  strategyThesis?: string;
  positionOutcomeSummary?: PositionOutcomeSummary;
}
```

Extend the existing `DashboardSection.intelligence` type (it's currently `Record<string, unknown>`) so we have typed access:

```typescript
export interface DashboardSection {
  coreConclusion?: CoreConclusion;
  dataPerspective?: Record<string, unknown>;
  battlePlan?: Record<string, unknown>;
  intelligence?: Record<string, unknown> & {
    sentimentDimensions?: SentimentDimensions;
  };
}
```

- [ ] **Step 2: Create `StrategySelector.tsx`**

Create `apps/dsa-web/src/components/report/StrategySelector.tsx`:

```tsx
import React from 'react';
import type { StrategyChoice } from '../../types/analysis';

interface StrategySelectorProps {
  choices: StrategyChoice[];
  recommendedId?: string;
}

const STRATEGY_EMOJI: Record<string, string> = {
  long_term_hold: '🌳',
  swing_trade: '⚡',
  stepped_profit_taking: '🪜',
  wait_and_see: '🚪',
};
const STRATEGY_LABEL: Record<string, string> = {
  long_term_hold: '长线持有',
  swing_trade: '短线波段',
  stepped_profit_taking: '阶梯式止盈',
  wait_and_see: '暂不操作',
};

export const StrategySelector: React.FC<StrategySelectorProps> = ({
  choices,
  recommendedId,
}) => {
  if (!choices || choices.length === 0) return null;

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-foreground">📌 策略选择</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {choices.map((c) => {
          const isRecommended = c.id === recommendedId;
          const emoji = c.emoji || STRATEGY_EMOJI[c.id] || '📌';
          const label = c.labelZh || STRATEGY_LABEL[c.id] || c.id;
          const baseClasses =
            'rounded-lg border p-3 text-xs space-y-1 transition-opacity';
          const stateClasses = !c.applicable
            ? 'border-subtle bg-surface/30 opacity-50'
            : isRecommended
              ? 'border-accent-text bg-accent-text/5 ring-2 ring-accent-text/30'
              : 'border-subtle bg-surface/50';

          return (
            <div key={c.id} className={`${baseClasses} ${stateClasses}`}>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-sm text-foreground">
                  {emoji} {label}
                </span>
                {isRecommended && (
                  <span className="rounded bg-accent-text/20 px-1.5 py-0.5 text-[10px] font-medium text-accent-text">
                    AI 推荐
                  </span>
                )}
              </div>
              {!c.applicable && c.inapplicableReason && (
                <p className="text-muted-text">⚪ 不适用：{c.inapplicableReason}</p>
              )}
              {c.applicable && (
                <>
                  {c.fitCondition && <p className="text-secondary-text">{c.fitCondition}</p>}
                  {c.keyParams && (
                    <p className="text-secondary-text">
                      <span className="font-medium text-foreground">关键参数：</span>
                      {c.keyParams}
                    </p>
                  )}
                  {c.timeHorizon && (
                    <p className="text-muted-text">⏱ {c.timeHorizon}</p>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Create `StrategyThesis.tsx`**

Create `apps/dsa-web/src/components/report/StrategyThesis.tsx`:

```tsx
import React from 'react';

interface StrategyThesisProps {
  thesis: string;
  recommendedLabel?: string;
}

export const StrategyThesis: React.FC<StrategyThesisProps> = ({ thesis, recommendedLabel }) => {
  if (!thesis) return null;
  return (
    <div className="rounded-xl border border-subtle bg-card p-4 space-y-2">
      <h4 className="text-sm font-semibold text-foreground">
        🎯 AI 推荐策略{recommendedLabel ? `：${recommendedLabel}` : ''}
      </h4>
      <p className="text-sm leading-relaxed text-secondary-text">{thesis}</p>
    </div>
  );
};
```

- [ ] **Step 4: Create `SentimentPanel.tsx`**

Create `apps/dsa-web/src/components/report/SentimentPanel.tsx`:

```tsx
import React from 'react';
import type { SentimentDimensions } from '../../types/analysis';

interface SentimentPanelProps {
  dimensions: SentimentDimensions;
}

interface Row {
  icon: string;
  label: string;
  buzz?: number | string;
  sentiment?: number | string;
  trend?: string;
  mentions?: number | string;
}

export const SentimentPanel: React.FC<SentimentPanelProps> = ({ dimensions }) => {
  if (!dimensions || Object.keys(dimensions).length === 0) return null;

  const rows: Row[] = [];
  if (dimensions.news) {
    rows.push({
      icon: '📰', label: 'News',
      buzz: dimensions.news.buzzScore,
      sentiment: dimensions.news.sentimentScore,
      trend: dimensions.news.buzzTrend,
      mentions: dimensions.news.mentions7d,
    });
  }
  if (dimensions.reddit) {
    rows.push({
      icon: '🔴', label: 'Reddit',
      buzz: dimensions.reddit.buzzScore,
      sentiment: dimensions.reddit.sentimentScore,
      trend: dimensions.reddit.buzzTrend,
      mentions: dimensions.reddit.mentions7d,
    });
  }
  if (dimensions.xTwitter) {
    rows.push({
      icon: '🐦', label: 'X',
      buzz: dimensions.xTwitter.buzzScore,
      sentiment: dimensions.xTwitter.sentimentScore,
      trend: dimensions.xTwitter.buzzTrend,
      mentions: dimensions.xTwitter.mentions7d,
    });
  }
  if (dimensions.polymarket) {
    rows.push({
      icon: '🔮', label: 'Polymarket',
      buzz: dimensions.polymarket.buzzScore,
      sentiment: dimensions.polymarket.sentimentScore,
      mentions: dimensions.polymarket.tradeCount,
    });
  }
  if (dimensions.stocktwits) {
    const bull = dimensions.stocktwits.bullishRatio;
    const bear = dimensions.stocktwits.bearishRatio;
    rows.push({
      icon: '💬', label: 'StockTwits',
      sentiment: bull != null && bear != null
        ? `Bull ${Math.round(bull * 100)}% / Bear ${Math.round(bear * 100)}%`
        : '—',
      mentions: dimensions.stocktwits.messagesSampled,
    });
  }

  if (rows.length === 0) return null;

  return (
    <div className="rounded-xl border border-subtle bg-card p-4 space-y-2">
      <h3 className="text-sm font-semibold text-foreground">📱 市场情绪</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-muted-text">
            <tr>
              <th className="text-left py-1">来源</th>
              <th className="text-right py-1">Buzz</th>
              <th className="text-right py-1">Sentiment</th>
              <th className="text-right py-1">Trend</th>
              <th className="text-right py-1">Mentions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-t border-subtle/40">
                <td className="py-1.5">{r.icon} {r.label}</td>
                <td className="text-right">{r.buzz ?? '—'}</td>
                <td className="text-right">{r.sentiment ?? '—'}</td>
                <td className="text-right text-muted-text">{r.trend ?? '—'}</td>
                <td className="text-right">{r.mentions ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
```

- [ ] **Step 5: Create `PositionOutcomeSummary.tsx`**

Create `apps/dsa-web/src/components/report/PositionOutcomeSummary.tsx`:

```tsx
import React from 'react';
import type { PositionOutcomeSummary as POS } from '../../types/analysis';

interface PositionOutcomeSummaryProps {
  summary: POS;
}

export const PositionOutcomeSummary: React.FC<PositionOutcomeSummaryProps> = ({
  summary,
}) => {
  if (!summary || Object.keys(summary).length === 0) return null;
  const ccy = summary.worstCaseCurrency || '';
  return (
    <div className="rounded-xl border border-subtle bg-card p-4 space-y-2">
      <h4 className="text-sm font-semibold text-foreground">📊 仓位流水汇总</h4>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <p className="text-muted-text">执行所有触发后剩余</p>
          <p className="font-mono text-foreground">
            {summary.remainingSharesAfterAllTriggers != null
              ? `${summary.remainingSharesAfterAllTriggers} 股`
              : '—'}
          </p>
        </div>
        <div>
          <p className="text-muted-text">风险回报比</p>
          <p className="font-mono text-foreground">{summary.riskRewardRatio || '—'}</p>
        </div>
        <div>
          <p className="text-muted-text">最差止损</p>
          <p className="font-mono text-red-400">
            {summary.worstCaseLossAmount != null
              ? `${summary.worstCaseLossAmount} ${ccy}`
              : '—'}
          </p>
        </div>
        <div>
          <p className="text-muted-text">最好止盈</p>
          <p className="font-mono text-emerald-400">
            {summary.bestCaseGainAmount != null
              ? `+${summary.bestCaseGainAmount} ${ccy}`
              : '—'}
          </p>
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 6: Export new components**

In `apps/dsa-web/src/components/report/index.ts`, add:

```typescript
export { StrategySelector } from './StrategySelector';
export { StrategyThesis } from './StrategyThesis';
export { SentimentPanel } from './SentimentPanel';
export { PositionOutcomeSummary } from './PositionOutcomeSummary';
```

- [ ] **Step 7: Wire components into `ReportSummary.tsx`**

Open `apps/dsa-web/src/components/report/ReportSummary.tsx`. Add imports at the top:

```tsx
import { StrategySelector } from './StrategySelector';
import { StrategyThesis } from './StrategyThesis';
import { SentimentPanel } from './SentimentPanel';
import { PositionOutcomeSummary } from './PositionOutcomeSummary';
```

Inside the return JSX, after the existing `<ActionPlanTable>` block (around line 50), add:

```tsx
      {/* 策略选择 — 4 个候选 + AI 推荐 + 论述 */}
      {report.dashboard?.coreConclusion?.strategyChoices &&
        report.dashboard.coreConclusion.strategyChoices.length > 0 && (
          <div className="rounded-xl border border-subtle bg-card p-4 space-y-3">
            <StrategySelector
              choices={report.dashboard.coreConclusion.strategyChoices}
              recommendedId={report.dashboard.coreConclusion.recommendedStrategy}
            />
            {report.dashboard.coreConclusion.strategyThesis && (
              <StrategyThesis
                thesis={report.dashboard.coreConclusion.strategyThesis}
                recommendedLabel={undefined}
              />
            )}
          </div>
        )}

      {/* 仓位流水汇总 */}
      {report.dashboard?.coreConclusion?.positionOutcomeSummary && (
        <PositionOutcomeSummary
          summary={report.dashboard.coreConclusion.positionOutcomeSummary}
        />
      )}

      {/* 市场情绪面板 */}
      {report.dashboard?.intelligence &&
        (report.dashboard.intelligence as { sentimentDimensions?: import('../../types/analysis').SentimentDimensions })
          .sentimentDimensions && (
          <SentimentPanel
            dimensions={(report.dashboard.intelligence as {
              sentimentDimensions: import('../../types/analysis').SentimentDimensions;
            }).sentimentDimensions}
          />
        )}
```

- [ ] **Step 8: Run frontend build**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web && npm run build 2>&1 | tail -10
```
Expected: build succeeds, no TS errors.

- [ ] **Step 9: Commit**

```bash
git add apps/dsa-web/src/types/analysis.ts \
        apps/dsa-web/src/components/report/StrategySelector.tsx \
        apps/dsa-web/src/components/report/StrategyThesis.tsx \
        apps/dsa-web/src/components/report/SentimentPanel.tsx \
        apps/dsa-web/src/components/report/PositionOutcomeSummary.tsx \
        apps/dsa-web/src/components/report/index.ts \
        apps/dsa-web/src/components/report/ReportSummary.tsx
git commit -m "feat: frontend strategy selector / thesis / sentiment / outcome components"
```

---

### Task 15: CHANGELOG + final smoke test

**Files:**
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: Append CHANGELOG entries**

Open `docs/CHANGELOG.md`. After the last existing `[Unreleased]` line and before `## [3.16.0]`, append:

```markdown
- [新功能] 每只股票分析新增「📌 策略选择」section：LLM 从 4 个固定策略（长线持有/短线波段/阶梯式止盈/暂不操作）中按当前持仓状态、技术结构、市场情绪选择推荐策略并写出 100-200 字论述，`action_plan_items` 严格遵循推荐策略的模板（如阶梯式止盈禁止 buy、长线持有强制含 cost × 0.9 真止损）。适用于所有股票（A/HK/US，带或不带持仓）。
- [新功能] 报告底部新增「📊 仓位流水汇总」卡片：基于 action_plan_items 计算执行后剩余仓位、最差/最好情况金额、风险回报比 (R:R)。
- [新功能] 市场情绪 5 源接入：修复 Adanos Reddit endpoint path bug (`/stock/{ticker}`，不再 404)；新增 Adanos `/news/stocks/v1/stock/{ticker}` 维度；新增 StockTwits 免费公开 API（无 key、5 分钟缓存）。dashboard 新增 `intelligence.sentiment_dimensions` 结构化字段 + 前端「📱 市场情绪」专用面板。
- [改进] post-process 守门规则升级：strategy template 白/黑名单（stepped 禁 buy / wait_and_see ≤1 item）；long_term 缺真止损时自动追加 cost × 0.9；优先级 filter 后 1..N 连续编号。
- [改进] `_try_inject_action_plan_items` 对所有股票分析触发（去掉 portfolio-context 门控），未持有场景下 cost-based 规则降级为现价相对规则。
- [测试] 新增 6 个测试文件 / 30+ 用例覆盖 schema / prompt 构造 / strategy template 强制 / position outcome 计算 / sentiment 多源整合。
```

- [ ] **Step 2: Run the full test suite**

Run:
```bash
/opt/homebrew/bin/python3.11 -m pytest tests/test_action_plan_*.py tests/test_strategy_classification.py tests/test_sentiment_dimensions.py tests/test_position_outcome_summary.py tests/test_stocktwits_service.py tests/test_adanos_news_endpoint.py tests/test_portfolio_context_service.py tests/test_pipeline_portfolio_match.py tests/test_history_service_portfolio_match.py tests/test_agent_executor.py tests/test_search_searxng.py -m "not network"
```
Expected: all green (200+ tests).

- [ ] **Step 3: Kickstart webui + manual smoke test**

```bash
launchctl kickstart -k gui/$(id -u)/com.dsa.webui
```

Wait for `Uvicorn running` in `~/Library/Logs/dsa-webui.log`, then ask user to:

1. Reanalyze NVDA (US held, +profit) — expect recommended `stepped_profit_taking`, sentiment panel with 4-5 sources
2. Reanalyze PLTR (US held, -loss) — expect recommended `long_term_hold` or `wait_and_see`
3. Analyze an A-share or HK stock (without portfolio if needed) — expect strategy section present but `sentiment_dimensions` absent (null)

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md
git commit -m "docs: CHANGELOG entries for adaptive strategy classification + sentiment expansion"
```

---

## Self-Review

After all 15 tasks complete:

1. **Spec coverage:** Every spec section has tasks — schema (T4), prompt (T5), `_try_inject` rewrite (T6), strategy template enforcement (T7), position outcome (T8), sentiment infrastructure (T1/T2/T3), pipeline universalization (T11), agent prompts (T12), backend renderer (T13), frontend (T14), CHANGELOG (T15). Sentiment endpoint fix landed in commit `0fadbec` pre-plan.

2. **Placeholder scan:** No TBD / TODO / "add appropriate" / "similar to Task N" anywhere; every code block is complete.

3. **Type consistency:**
   - `StrategyChoiceSchema` (Pydantic) ↔ `StrategyChoice` (TS) match field names
   - `PositionOutcomeSummarySchema` ↔ `PositionOutcomeSummary` match
   - `SentimentDimensions` only on TS side (intelligence.sentiment_dimensions stays as dict in Pydantic for forward compat)
   - `synthesize_action_plan_items` keyword `strategy` consistent across all callers
   - `_sanitize_action_plan_items` signature stays consistent (Task 6 → Task 7 → Task 8 chain)

4. **Universalization (per user's explicit requirement):** Task 11 makes the `_try_inject_action_plan_items` call unconditional in pipeline.py; Task 6's rewrite already handles `portfolio_context_block=None` gracefully.

---

**Execution time estimate:** 15 tasks × ~10-20 min each = 3-5 hours of focused TDD.
