# -*- coding: utf-8 -*-
"""Quant Signal API endpoint (Sprint 3).

Exposes the per-stock factor quantiles + LightGBM forecast so the Web
``Quant Context`` panel can render an auxiliary statistical view next
to the standard analysis.

Contract: ``GET /api/v1/quant-signal/{stock_code}?market=<m>&horizon=<n>``

* ``market`` defaults to inferred from the stock code (cn/hk/us).
* ``horizon`` defaults to the env-configured value (10 trading days).
* Best-effort: when qlib isn't installed, the model artifact is
  missing, the stock is outside the locked universe (CSI 300 / S&P 500),
  or the 4-week IC moving average is below the gate threshold, we
  return ``204 No Content`` with no body — the Web panel reads that
  status and renders nothing.

Failure modes return 204 on purpose: quant context is strictly
auxiliary, so a missing artifact must not look like an API error.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Response

from src.services.quant_signal_service import (
    QuantSignalService,
    default_forecast_horizon,
    infer_market_from_code,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{stock_code}")
def get_quant_signal(
    stock_code: str,
    market: Optional[str] = Query(
        None,
        description="Market scope: cn / hk / us. Inferred from the code when omitted.",
    ),
    horizon: Optional[int] = Query(
        None,
        ge=1,
        le=60,
        description="Forecast horizon in trading days. Falls back to QUANT_FORECAST_HORIZON.",
    ),
) -> Response:
    """Return factor quantiles + forecast for one stock, or 204 if none.

    The payload is intentionally minimal — the Web panel renders a
    factor strip + a forecast banner, nothing else.  We return 204 (not
    404) when there's no quant data so it's clearly "no signal yet"
    rather than "this stock doesn't exist".
    """
    code = (stock_code or "").strip()
    if not code:
        return Response(status_code=400, content='{"detail":"stock_code is required"}',
                        media_type="application/json")

    market_norm = (market or infer_market_from_code(code)).lower()
    horizon_norm = horizon or default_forecast_horizon()

    try:
        service = QuantSignalService()
        factors = service.get_factor_quantiles(code, market_norm)
        forecast = service.get_forecast(code, market_norm, horizon=horizon_norm)

        if factors is None and forecast is None:
            # No signal — silent no-op (Q6 locked decision)
            return Response(status_code=204)

        payload: Dict[str, Any] = {
            "stock_code": code,
            "market": market_norm,
            "horizon_days": horizon_norm,
            "factors": factors,
            "forecast": forecast,
        }
        import json
        return Response(
            status_code=200,
            content=json.dumps(payload, ensure_ascii=False),
            media_type="application/json",
        )
    except Exception as exc:
        # Defensive: even an internal error in the quant pipeline should
        # not break the consuming client.  Log and 204 — the Web panel
        # already handles "no data" gracefully.
        logger.warning("[quant-signal] handler error for %s: %s", code, exc)
        return Response(status_code=204)
