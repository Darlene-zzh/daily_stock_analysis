# -*- coding: utf-8 -*-
"""Decision Journal API endpoint (Sprint 2).

Exposes the per-stock journal entries + realised alpha summary so the Web
``复盘 / Decision Tracking`` tab can render a track record next to the
current analysis.

Contract: ``GET /api/v1/decision-journal/{stock_code}?market=<m>&limit=<n>``

* ``market`` defaults to inferred from the stock code (cn/hk/us).
* ``limit`` defaults to 20 (web tab listing); we cap at 100.
* Best-effort: a missing journal returns ``entries=[]`` rather than 404.
* Realised alpha is computed lazily — benchmark fetch failures degrade
  to ``alpha=None`` instead of raising.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.services.decision_journal_service import (
    DecisionJournalService,
    infer_market_from_code,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{stock_code}")
def get_decision_journal(
    stock_code: str,
    market: Optional[str] = Query(
        None,
        description="Market scope: cn / hk / us. Inferred from the code when omitted.",
    ),
    limit: int = Query(20, ge=1, le=100, description="Max entries (newest first)"),
) -> Dict[str, Any]:
    """Return the last N journal entries + realised alpha summary."""
    code = (stock_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="stock_code is required")

    market_norm = market or infer_market_from_code(code)
    try:
        service = DecisionJournalService()
        entries = service.load_recent_entries(
            stock_code=code,
            market=market_norm,
            max_entries=limit,
        )
        payload: List[Dict[str, Any]] = []
        for entry in entries:
            stats = service.compute_realised_alpha(
                stock_code=code,
                market=market_norm,
                decision_at=entry.decision_at,
                price_at_decision=entry.price_at_decision,
            )
            payload.append({**entry.to_dict(), **stats})
        return {
            "stock_code": code,
            "market": market_norm,
            "count": len(payload),
            "entries": payload,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "[decision-journal] endpoint failed for %s/%s: %s",
            market_norm,
            code,
            exc,
            exc_info=True,
        )
        # Surface a 500 with a stable error_code so the Web client can
        # render a graceful empty state.
        raise HTTPException(
            status_code=500,
            detail={
                "error": "decision_journal_unavailable",
                "message": str(exc),
            },
        )
