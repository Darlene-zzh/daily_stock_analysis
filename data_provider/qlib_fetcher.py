# -*- coding: utf-8 -*-
"""
===================================
Qlib fetcher (Sprint 3 — Quant Anchor)
===================================

Thin wrapper around `pyqlib`'s data loader.  The point of this module is
**isolation**: every caller imports through here so the rest of the
codebase never directly touches ``import qlib`` and never has to deal
with qlib's heavy C dependencies at module-import time.

Design rules (P9-locked, see ``docs/superpowers/plans/2026-05-18-professional-upgrade.md``):

1. **Lazy import.**  We never ``import qlib`` at module load.  Every
   public function calls :func:`_try_import_qlib` first; if qlib is
   missing the function returns ``None`` and logs a warning.  This keeps
   ``requirements.txt`` clean (qlib lives in ``requirements-quant.txt``)
   and the main app boots even when the quant stack isn't installed.

2. **Region awareness.**  Qlib partitions data by ``cn`` / ``us``.  HK
   has no qlib coverage — callers must check :func:`is_supported_market`
   and silently no-op for hk symbols.

3. **No exceptions escape.**  Every public function wraps qlib calls in
   try/except and returns ``None`` on failure.  The quant context is
   strictly auxiliary; a broken qlib stack must never kill the main
   analysis pipeline.

4. **Idempotent init.**  Qlib's ``init()`` is process-global; calling it
   twice raises.  We track init state in a module-level flag.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Module-level state for the qlib runtime — qlib's init() must only be
# called once per process per region.  We allow re-init across regions
# because cn and us live in different provider URIs.
_qlib_init_lock = threading.Lock()
_qlib_initialized_region: Optional[str] = None


# Markets where qlib has bulk data downloads.  HK isn't shipped by qlib
# upstream, so HK stocks see a silent no-op (Q1 locked decision).
SUPPORTED_MARKETS = ("cn", "us")


def is_supported_market(market: str) -> bool:
    """Return True iff this market is in qlib's bulk data coverage.

    HK currently has no qlib bulk data — analyzer code should call this
    early and skip the whole quant pipeline for hk codes.
    """
    return (market or "").strip().lower() in SUPPORTED_MARKETS


def _try_import_qlib() -> Optional[Any]:
    """Best-effort qlib import.

    Returns the qlib module if installed, ``None`` otherwise.  Logs a
    one-time warning on first failure to keep the log signal clean.
    """
    try:
        import qlib  # noqa: F401 — we just need the import to succeed
        return qlib
    except ImportError:
        logger.debug(
            "[qlib_fetcher] pyqlib not installed; "
            "quant signal silently disabled. "
            "Install via `pip install -r requirements-quant.txt` to enable."
        )
        return None
    except Exception as exc:
        # Defensive: some environments raise non-ImportError on broken
        # native deps.  Treat as no-qlib and keep going.
        logger.warning("[qlib_fetcher] qlib import raised %s: %s", type(exc).__name__, exc)
        return None


def _resolve_provider_uri(region: str) -> Optional[str]:
    """Locate the qlib data directory for the given region.

    Precedence:
        1. ``QLIB_PROVIDER_URI_<REGION>`` env var (explicit override)
        2. ``QLIB_DATA_DIR`` env var with ``<region>_data`` subdir
        3. ``data/qlib/<region>_data`` (project default)

    Returns the resolved path string or ``None`` if no path exists on
    disk.  Callers should treat ``None`` as "qlib data not set up yet".
    """
    region = (region or "").strip().lower()
    if not region:
        return None

    explicit = os.getenv(f"QLIB_PROVIDER_URI_{region.upper()}")
    if explicit and os.path.isdir(explicit):
        return explicit

    base = os.getenv("QLIB_DATA_DIR", "data/qlib")
    candidate = os.path.join(base, f"{region}_data")
    if os.path.isdir(candidate):
        return candidate

    return None


def ensure_initialized(region: str) -> bool:
    """Initialise qlib for the given region (idempotent within a region).

    Returns True if qlib is ready to serve queries, False otherwise.
    Logs at WARNING when no data dir exists so the user can see why the
    quant context is silently missing.
    """
    global _qlib_initialized_region

    region = (region or "").strip().lower()
    if not is_supported_market(region):
        return False

    qlib = _try_import_qlib()
    if qlib is None:
        return False

    with _qlib_init_lock:
        if _qlib_initialized_region == region:
            return True

        provider_uri = _resolve_provider_uri(region)
        if provider_uri is None:
            logger.warning(
                "[qlib_fetcher] no qlib data dir for region=%s; "
                "run scripts/setup_qlib_data.sh to download. "
                "Quant context disabled.",
                region,
            )
            return False

        try:
            qlib.init(provider_uri=provider_uri, region=region)
        except Exception as exc:
            logger.warning(
                "[qlib_fetcher] qlib.init(region=%s) failed: %s",
                region, exc,
            )
            return False

        _qlib_initialized_region = region
        logger.info(
            "[qlib_fetcher] qlib initialised: region=%s provider_uri=%s",
            region, provider_uri,
        )
        return True


def get_alpha158_factors(
    stock_code: str,
    region: str,
    *,
    fields: Optional[List[str]] = None,
    lookback_days: int = 60,
) -> Optional[Dict[str, float]]:
    """Fetch the latest Alpha158 factor snapshot for one stock.

    Returns a dict mapping factor name -> latest value, or ``None`` if
    qlib is unavailable, the region is unsupported, or the data dir
    isn't downloaded yet.

    Args:
        stock_code: qlib-formatted instrument id (e.g. ``SH600519`` for
            CN, ``AAPL`` for US — the service layer normalises ours).
        region: ``"cn"`` or ``"us"``.
        fields: optional subset of Alpha158 expressions.  When None we
            return a small curated subset (the most commonly cited).
        lookback_days: trailing window passed to qlib.  60 is enough for
            Alpha158's longest-window factors (e.g. ROC60).
    """
    if not ensure_initialized(region):
        return None

    qlib = _try_import_qlib()
    if qlib is None:
        return None

    try:
        # Defer the inner imports — they touch C extensions and we want
        # the no-qlib path above to stay fast.
        from qlib.data import D  # type: ignore
        from datetime import datetime, timedelta

        # Use a curated subset by default.  These are the factors we
        # surface to the LLM as "quant context"; reducing the field
        # list keeps the prompt block small and the IC reporting honest.
        if fields is None:
            fields = [
                # Price momentum
                "$close / Ref($close, 5) - 1",      # 5-day return
                "$close / Ref($close, 20) - 1",     # 20-day return
                "$close / Ref($close, 60) - 1",     # 60-day return
                # Volume
                "$volume / Mean($volume, 20)",      # volume ratio vs 20-day avg
                # Volatility
                "Std($close / Ref($close, 1) - 1, 20)",  # 20-day vol of returns
            ]

        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=lookback_days)

        df = D.features(
            instruments=[stock_code],
            fields=fields,
            start_time=start_dt.strftime("%Y-%m-%d"),
            end_time=end_dt.strftime("%Y-%m-%d"),
        )

        if df is None or df.empty:
            return None

        # Take the latest row's values, keyed by short factor names so
        # the prompt block stays readable.
        short_names = [
            "ret_5d", "ret_20d", "ret_60d", "volume_ratio_20d", "vol_20d",
        ]
        latest = df.iloc[-1]
        out: Dict[str, float] = {}
        for short, expr in zip(short_names[: len(fields)], fields):
            try:
                v = latest[expr] if expr in latest.index else latest.iloc[short_names.index(short)]
                if v is None:
                    continue
                fv = float(v)
                # filter NaN/inf — qlib happily returns these on edges
                if fv != fv or fv in (float("inf"), float("-inf")):
                    continue
                out[short] = fv
            except Exception:
                continue
        return out or None

    except Exception as exc:
        logger.warning(
            "[qlib_fetcher] get_alpha158_factors failed for %s/%s: %s",
            stock_code, region, exc,
        )
        return None


def normalize_to_qlib_symbol(stock_code: str, market: str) -> Optional[str]:
    """Normalise our internal stock codes to qlib's convention.

    - cn: ``600519`` -> ``SH600519``, ``000001`` -> ``SZ000001``
    - us: ``AAPL`` -> ``AAPL`` (already canonical)
    - hk: unsupported, return None

    Returns None for unsupported markets or malformed codes.
    """
    market = (market or "").strip().lower()
    code = (stock_code or "").strip().upper()
    if not code:
        return None

    if market == "us":
        return code

    if market == "cn":
        # already prefixed?
        if code.startswith(("SH", "SZ", "BJ")):
            return code
        if code.isdigit() and len(code) == 6:
            # Shanghai: 600/601/603/605/688/689/900
            # Shenzhen: 000/001/002/003/300/301/200
            # Beijing:  4xx/8xx/9xx (post-2021)
            head = code[:1]
            if head == "6" or head == "9":
                return f"SH{code}"
            if head in ("0", "2", "3"):
                return f"SZ{code}"
            if head in ("4", "8"):
                return f"BJ{code}"
        return None

    # hk and anything else
    return None


def csi300_universe() -> Tuple[str, ...]:
    """Best-effort CSI 300 component list (Q1 locked universe for cn).

    We do NOT hard-code 300 tickers; instead we ask qlib for its
    ``csi300`` instrument group when available.  Returns an empty tuple
    when qlib is missing or the group can't be loaded — callers should
    treat empty as "universe unknown, skip universe check".
    """
    if not ensure_initialized("cn"):
        return tuple()
    qlib = _try_import_qlib()
    if qlib is None:
        return tuple()
    try:
        from qlib.data import D  # type: ignore
        instruments = D.instruments(market="csi300")
        if not instruments:
            return tuple()
        # qlib.instruments(...) returns a dict-like config; the actual
        # ticker list comes from D.list_instruments.
        codes = D.list_instruments(instruments=instruments, as_list=True)
        return tuple(codes or ())
    except Exception as exc:
        logger.warning("[qlib_fetcher] csi300 universe lookup failed: %s", exc)
        return tuple()


def sp500_universe() -> Tuple[str, ...]:
    """Best-effort S&P 500 component list (Q1 locked universe for us)."""
    if not ensure_initialized("us"):
        return tuple()
    qlib = _try_import_qlib()
    if qlib is None:
        return tuple()
    try:
        from qlib.data import D  # type: ignore
        instruments = D.instruments(market="sp500")
        if not instruments:
            return tuple()
        codes = D.list_instruments(instruments=instruments, as_list=True)
        return tuple(codes or ())
    except Exception as exc:
        logger.warning("[qlib_fetcher] sp500 universe lookup failed: %s", exc)
        return tuple()
