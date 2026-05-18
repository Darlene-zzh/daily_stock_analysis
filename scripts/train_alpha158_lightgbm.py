#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sprint 3 — Weekly LightGBM × Alpha158 trainer.

Runs the qlib workflow that produces:

* ``data/quant_models/<region>/<YYYY-WW>/model.pkl`` — pickled LightGBM
* ``data/quant_models/<region>/<YYYY-WW>/predictions.json`` — per-symbol
  forecast snapshot consumed by :class:`QuantSignalService`
* ``data/quant_models/<region>/<YYYY-WW>/ic.json`` — current + 4-week
  Rank IC stats consumed by the IC gating check
* ``data/quant_models/<region>/<YYYY-WW>/factor_quantiles.json``
  (optional) — cross-sectional factor quantiles consumed by the prompt

This script is **opt-in**.  It needs:
    pip install -r requirements-quant.txt
    bash scripts/setup_qlib_data.sh

When qlib / lightgbm aren't available the script logs a friendly
message and exits 0 — the GitHub Action / cron job that runs it should
treat that as a no-op, not a failure.

Locked decisions (P9):
    Q2 — Rolling 3-year window, retrained weekly
    Q3 — 10-day horizon by default
    Q4 — Rank IC + 60-day MA
    Q5 — IC gate (< 0.02 = forecast hidden)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger("train_alpha158_lightgbm")


SUPPORTED_REGIONS = ("cn", "us")


def _safe_import_qlib():
    try:
        import qlib  # noqa: F401
        return qlib
    except ImportError:
        return None


def _safe_import_lightgbm():
    try:
        import lightgbm  # noqa: F401
        return lightgbm
    except ImportError:
        return None


def _iso_week(today: date) -> str:
    """ISO-week tag used for the artifact subdir (e.g. ``2026-W20``)."""
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


def _provider_uri(region: str) -> Optional[str]:
    base = os.getenv("QLIB_DATA_DIR", "data/qlib")
    candidate = os.path.join(base, f"{region}_data")
    return candidate if os.path.isdir(candidate) else None


def _model_dir(region: str, week_tag: str) -> str:
    base = os.getenv("QUANT_MODEL_DIR", "data/quant_models")
    return os.path.join(base, region, week_tag)


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def train_one_region(region: str, *, horizon: int = 10, training_years: int = 3) -> int:
    """Train + dump artifacts for one region.

    Returns exit code: 0 on success, 0 on graceful no-op (no qlib /
    no data / no lightgbm), 1 only on hard failure during training.
    """
    region = region.strip().lower()
    if region not in SUPPORTED_REGIONS:
        logger.warning("[train] skipping unsupported region: %s", region)
        return 0

    qlib = _safe_import_qlib()
    if qlib is None:
        logger.warning(
            "[train] qlib not installed; skipping %s training. "
            "Run: pip install -r requirements-quant.txt",
            region,
        )
        return 0

    lgb = _safe_import_lightgbm()
    if lgb is None:
        logger.warning("[train] lightgbm not installed; skipping %s training.", region)
        return 0

    provider_uri = _provider_uri(region)
    if provider_uri is None:
        logger.warning(
            "[train] no qlib data for region=%s; run scripts/setup_qlib_data.sh first.",
            region,
        )
        return 0

    today = date.today()
    week_tag = _iso_week(today)
    out_dir = _model_dir(region, week_tag)
    os.makedirs(out_dir, exist_ok=True)

    train_end = today - timedelta(days=7)            # walk-forward gap
    train_start = train_end - timedelta(days=int(training_years * 365.25))

    logger.info(
        "[train] region=%s week=%s window=%s..%s horizon=%dd",
        region, week_tag, train_start, train_end, horizon,
    )

    try:
        qlib.init(provider_uri=provider_uri, region=region)

        # Imports deferred until after init: qlib's handler/model
        # modules expect a live runtime.
        from qlib.contrib.data.handler import Alpha158  # type: ignore
        from qlib.contrib.model.gbdt import LGBModel    # type: ignore
        from qlib.data.dataset import DatasetH          # type: ignore
        from qlib.utils import flatten_dict             # type: ignore  # noqa: F401

        instrument_pool = "csi300" if region == "cn" else "sp500"

        handler = Alpha158(
            instruments=instrument_pool,
            start_time=train_start.isoformat(),
            end_time=today.isoformat(),
            fit_start_time=train_start.isoformat(),
            fit_end_time=train_end.isoformat(),
            label=[f"Ref($close, -{horizon}) / $close - 1"],
        )

        dataset = DatasetH(
            handler=handler,
            segments={
                "train": (train_start.isoformat(), train_end.isoformat()),
                "valid": (train_end.isoformat(), today.isoformat()),
                "test":  (today.isoformat(), today.isoformat()),
            },
        )

        model = LGBModel(
            loss="mse",
            colsample_bytree=0.8879,
            learning_rate=0.0421,
            subsample=0.8789,
            lambda_l1=205.6999,
            lambda_l2=580.9768,
            max_depth=8,
            num_leaves=210,
            num_threads=20,
        )
        model.fit(dataset)

        # Persist pickle for next week's incremental fits / debugging.
        import pickle
        with open(os.path.join(out_dir, "model.pkl"), "wb") as fh:
            pickle.dump(model, fh)

        # Predictions for the latest date — flatten to a {symbol: {score, rank}}
        # dict so the runtime service can read it without lightgbm.
        preds = model.predict(dataset, segment="test")
        try:
            preds = preds.dropna()
            ranks = preds.rank(pct=True)
            predictions: Dict[str, Dict[str, float]] = {}
            for (dt, sym), score in preds.items():  # MultiIndex (date, symbol)
                predictions[sym] = {
                    "score": float(score),
                    "rank": float(ranks.loc[(dt, sym)]),
                }
        except Exception as exc:
            logger.warning("[train] prediction flattening failed for %s: %s", region, exc)
            predictions = {}
        _write_json(os.path.join(out_dir, "predictions.json"), predictions)

        # Rank IC (Spearman) — current + 4-week MA, computed against
        # the validation segment.
        ic_payload: Dict[str, Any] = {
            "as_of": today.isoformat(),
            "ic_current": None,
            "ic_ma_4w": None,
        }
        try:
            valid_pred = model.predict(dataset, segment="valid")
            valid_label = dataset.prepare("valid", col_set="label")
            joined = valid_pred.to_frame("pred").join(
                valid_label.iloc[:, 0].to_frame("label")
            ).dropna()
            grouped = joined.groupby(level=0)
            daily_ic = grouped.apply(
                lambda g: g["pred"].corr(g["label"], method="spearman")
            ).dropna()
            ic_payload["ic_current"] = float(daily_ic.iloc[-1]) if len(daily_ic) else None
            ic_payload["ic_ma_4w"] = (
                float(daily_ic.tail(20).mean()) if len(daily_ic) >= 5 else None
            )
        except Exception as exc:
            logger.warning("[train] IC computation failed for %s: %s", region, exc)
        _write_json(os.path.join(out_dir, "ic.json"), ic_payload)

        logger.info(
            "[train] %s done — ic_current=%s ic_ma_4w=%s preds=%d",
            region,
            ic_payload.get("ic_current"),
            ic_payload.get("ic_ma_4w"),
            len(predictions),
        )
        return 0

    except Exception as exc:
        logger.exception("[train] hard failure for region=%s: %s", region, exc)
        return 1


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument(
        "--region", "-r",
        choices=list(SUPPORTED_REGIONS) + ["all"],
        default="all",
        help="region to train (default: all)",
    )
    p.add_argument(
        "--horizon", type=int, default=int(os.getenv("QUANT_FORECAST_HORIZON", "10")),
        help="forecast horizon in trading days (default: env QUANT_FORECAST_HORIZON or 10)",
    )
    p.add_argument(
        "--training-years", type=int, default=3,
        help="rolling training window in years (default: 3)",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args(argv)
    regions = SUPPORTED_REGIONS if args.region == "all" else (args.region,)
    rc = 0
    for r in regions:
        rc = train_one_region(r, horizon=args.horizon, training_years=args.training_years) or rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
