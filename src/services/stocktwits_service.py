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
