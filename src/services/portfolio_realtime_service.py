# -*- coding: utf-8 -*-
"""Realtime price lookup with a tiny in-memory TTL cache.

Snapshot generation already calls into the data-provider stack once per
position when a portfolio snapshot is requested. The page wants to refresh
just the prices (without recomputing FIFO lots, FX-converting cash, or
hitting the DB), so this module exposes a small batch endpoint backed by
:func:`PortfolioService._fetch_realtime_position_price` with a per-symbol
memoization to keep the upstream fetcher away from rate limits when many
clients (or a single client polling every 30-60s) hit it at once.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.services.portfolio_service import PortfolioService

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_SECONDS = 30.0


class _PriceCache:
    """Thread-safe (symbol, currency_hint) → (timestamp, payload) cache."""

    def __init__(self, ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS) -> None:
        self._ttl = float(ttl_seconds)
        self._lock = threading.Lock()
        self._entries: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}

    def get(self, key: Tuple[str, str], *, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        ts_now = float(now) if now is not None else time.time()
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                return None
            ts, payload = entry
            if ts_now - ts > self._ttl:
                return None
            return payload

    def put(self, key: Tuple[str, str], payload: Dict[str, Any], *, now: Optional[float] = None) -> None:
        ts_now = float(now) if now is not None else time.time()
        with self._lock:
            self._entries[key] = (ts_now, payload)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_CACHE = _PriceCache()


def _normalize_request_item(item: Any) -> Tuple[str, str]:
    if isinstance(item, dict):
        symbol = str(item.get("symbol") or "").strip()
        currency = str(item.get("currency") or item.get("currency_hint") or "").strip().upper()
    else:
        symbol = str(getattr(item, "symbol", "") or "").strip()
        currency_attr = getattr(item, "currency", None) or getattr(item, "currency_hint", None)
        currency = str(currency_attr or "").strip().upper()
    return symbol, currency


class PortfolioRealtimePriceService:
    """Stateless service: takes a list of (symbol, currency_hint) and returns prices."""

    def __init__(self, *, cache: Optional[_PriceCache] = None) -> None:
        self._cache = cache or _CACHE

    def lookup(
        self,
        positions: Iterable[Any],
        *,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        as_of_iso = (as_of or date.today()).isoformat()
        seen: Dict[Tuple[str, str], int] = {}
        ordered_keys: List[Tuple[str, str]] = []
        for raw in positions:
            symbol, currency = _normalize_request_item(raw)
            if not symbol:
                continue
            key = (symbol, currency)
            if key in seen:
                continue
            seen[key] = len(ordered_keys)
            ordered_keys.append(key)

        items: List[Dict[str, Any]] = []
        cache_hits = 0
        cache_misses = 0
        for key in ordered_keys:
            cached = self._cache.get(key)
            if cached is not None:
                cache_hits += 1
                items.append(cached)
                continue

            symbol, currency_hint = key
            price, provider = PortfolioService._fetch_realtime_position_price(
                symbol,
                currency_hint=currency_hint or None,
            )

            now_iso = _now_iso()
            payload: Dict[str, Any] = {
                "symbol": symbol,
                "currency_hint": currency_hint or None,
                "last_price": float(price) if price is not None else 0.0,
                "price_provider": provider,
                "price_source": "realtime_quote" if price is not None else "missing",
                "price_date": as_of_iso,
                "price_available": price is not None,
                "price_stale": price is None,
                "fetched_at": now_iso,
            }
            cache_misses += 1
            self._cache.put(key, payload)
            items.append(payload)

        return {
            "as_of": as_of_iso,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "items": items,
        }


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
