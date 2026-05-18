# -*- coding: utf-8 -*-
"""Unit tests for ``src/services/quant_signal_service.py`` (Sprint 3).

Covers the P9-locked behaviour:

* No qlib installed → None across the board
* No model artifact → factor quantiles MAY work, forecast is None
* Stock outside CSI 300 / S&P 500 → silent no-op
* IC below the 4-week gate → forecast suppressed, factors keep
  "uncertain" tag
* HK stock → silent no-op
* Prompt block always carries the "auxiliary, not a recommendation"
  caveat
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.services.quant_signal_service import (
    QUANT_MARKETS,
    QuantSignalService,
    default_forecast_horizon,
    ic_gating_threshold,
    infer_market_from_code,
    quant_signal_enabled_default,
)


# ---------------------------------------------------------------------
# Env helpers — defaults respect overrides
# ---------------------------------------------------------------------

def test_quant_signal_enabled_default_off_when_unset(monkeypatch):
    monkeypatch.delenv("QUANT_SIGNAL_ENABLED", raising=False)
    assert quant_signal_enabled_default() is False


def test_quant_signal_enabled_default_respects_env(monkeypatch):
    monkeypatch.setenv("QUANT_SIGNAL_ENABLED", "true")
    assert quant_signal_enabled_default() is True
    monkeypatch.setenv("QUANT_SIGNAL_ENABLED", "0")
    assert quant_signal_enabled_default() is False


def test_default_forecast_horizon_is_ten(monkeypatch):
    monkeypatch.delenv("QUANT_FORECAST_HORIZON", raising=False)
    assert default_forecast_horizon() == 10


def test_ic_gating_threshold_default(monkeypatch):
    monkeypatch.delenv("QUANT_IC_GATING_THRESHOLD", raising=False)
    assert ic_gating_threshold() == pytest.approx(0.02)


# ---------------------------------------------------------------------
# Market inference
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "code, market",
    [
        ("600519", "cn"),
        ("SH600519", "cn"),
        ("000001", "cn"),
        ("AAPL", "us"),
        ("BRK.B", "us"),
        ("hk00700", "hk"),
        ("00700.HK", "hk"),
        ("", "unknown"),
    ],
)
def test_infer_market_from_code(code, market):
    assert infer_market_from_code(code) == market


# ---------------------------------------------------------------------
# get_factor_quantiles paths
# ---------------------------------------------------------------------

def test_get_factor_quantiles_returns_none_for_hk():
    """HK is unsupported by qlib — silent no-op (Q1 locked decision)."""
    svc = QuantSignalService()
    with patch.object(svc, "is_in_universe", return_value=False):
        assert svc.get_factor_quantiles("hk00700", "hk") is None


def test_get_factor_quantiles_returns_none_outside_universe(monkeypatch):
    svc = QuantSignalService()
    with patch.object(svc, "is_in_universe", return_value=False):
        assert svc.get_factor_quantiles("600519", "cn") is None


def test_get_factor_quantiles_uses_live_fetcher_when_no_sidecar(monkeypatch, tmp_path):
    svc = QuantSignalService()
    monkeypatch.setenv("QUANT_MODEL_DIR", str(tmp_path))  # no artifacts on disk
    with patch.object(svc, "is_in_universe", return_value=True), \
         patch("data_provider.qlib_fetcher.normalize_to_qlib_symbol",
               return_value="SH600519"), \
         patch("data_provider.qlib_fetcher.get_alpha158_factors",
               return_value={"ret_5d": 0.01, "ret_20d": 0.04}):
        result = svc.get_factor_quantiles("600519", "cn")
    assert result is not None
    assert result["stock_code"] == "600519"
    assert result["market"] == "cn"
    assert result["quantiles"] == {"ret_5d": 0.01, "ret_20d": 0.04}


def test_get_factor_quantiles_prefers_sidecar(monkeypatch, tmp_path):
    """When the trainer dumped factor_quantiles.json we use those values
    over the live fetcher (they're cross-sectional, much cleaner)."""
    week_dir = tmp_path / "cn" / "2026-W20"
    week_dir.mkdir(parents=True)
    sidecar = week_dir / "factor_quantiles.json"
    sidecar.write_text(json.dumps({"SH600519": {"ret_5d": 0.85, "ret_20d": 0.71}}))
    monkeypatch.setenv("QUANT_MODEL_DIR", str(tmp_path))

    svc = QuantSignalService()
    with patch.object(svc, "is_in_universe", return_value=True), \
         patch("data_provider.qlib_fetcher.normalize_to_qlib_symbol",
               return_value="SH600519"), \
         patch("data_provider.qlib_fetcher.get_alpha158_factors") as live_fetcher:
        result = svc.get_factor_quantiles("600519", "cn")
        live_fetcher.assert_not_called()
    assert result["quantiles"] == {"ret_5d": 0.85, "ret_20d": 0.71}


# ---------------------------------------------------------------------
# get_forecast gating
# ---------------------------------------------------------------------

def _seed_artifact(tmp_path: Path, market: str, week_tag: str, *,
                   predictions: dict, ic_current: float | None = None,
                   ic_ma_4w: float | None = None):
    week_dir = tmp_path / market / week_tag
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / "predictions.json").write_text(json.dumps(predictions))
    (week_dir / "ic.json").write_text(json.dumps({
        "as_of": "2026-05-18",
        "ic_current": ic_current,
        "ic_ma_4w": ic_ma_4w,
    }))
    return week_dir


def test_get_forecast_returns_none_for_hk_market():
    svc = QuantSignalService()
    assert svc.get_forecast("hk00700", "hk") is None


def test_get_forecast_returns_none_outside_universe():
    svc = QuantSignalService()
    with patch.object(svc, "is_in_universe", return_value=False):
        assert svc.get_forecast("600519", "cn") is None


def test_get_forecast_returns_none_when_no_artifact(monkeypatch, tmp_path):
    """No model dir at all → forecast is None (factor block may still work)."""
    monkeypatch.setenv("QUANT_MODEL_DIR", str(tmp_path / "void"))
    svc = QuantSignalService()
    with patch.object(svc, "is_in_universe", return_value=True), \
         patch("data_provider.qlib_fetcher.normalize_to_qlib_symbol",
               return_value="SH600519"):
        assert svc.get_forecast("600519", "cn") is None


def test_get_forecast_suppressed_when_ic_below_gate(monkeypatch, tmp_path):
    """Q5 locked decision: 4-week IC < 0.02 → hide forecast."""
    _seed_artifact(
        tmp_path, "cn", "2026-W20",
        predictions={"SH600519": {"score": 0.05, "rank": 0.91}},
        ic_current=0.015, ic_ma_4w=0.012,
    )
    monkeypatch.setenv("QUANT_MODEL_DIR", str(tmp_path))
    monkeypatch.setenv("QUANT_IC_GATING_THRESHOLD", "0.02")
    svc = QuantSignalService()
    with patch.object(svc, "is_in_universe", return_value=True), \
         patch("data_provider.qlib_fetcher.normalize_to_qlib_symbol",
               return_value="SH600519"):
        assert svc.get_forecast("600519", "cn") is None


def test_get_forecast_passes_when_ic_above_gate(monkeypatch, tmp_path):
    _seed_artifact(
        tmp_path, "cn", "2026-W20",
        predictions={"SH600519": {"score": 0.0182, "rank": 0.84}},
        ic_current=0.05, ic_ma_4w=0.04,
    )
    monkeypatch.setenv("QUANT_MODEL_DIR", str(tmp_path))
    monkeypatch.setenv("QUANT_IC_GATING_THRESHOLD", "0.02")
    monkeypatch.setenv("QUANT_FORECAST_HORIZON", "10")
    svc = QuantSignalService()
    with patch.object(svc, "is_in_universe", return_value=True), \
         patch("data_provider.qlib_fetcher.normalize_to_qlib_symbol",
               return_value="SH600519"):
        fcst = svc.get_forecast("600519", "cn")
    assert fcst is not None
    assert fcst["expected_excess_return"] == pytest.approx(0.0182)
    assert fcst["rank_in_universe"] == pytest.approx(0.84)
    assert fcst["ic_ma_4w"] == pytest.approx(0.04)
    assert fcst["horizon_days"] == 10
    assert fcst["model_version"] == "2026-W20"


# ---------------------------------------------------------------------
# build_quant_context_block (prompt-level surface)
# ---------------------------------------------------------------------

def test_build_quant_context_block_none_when_no_data():
    svc = QuantSignalService()
    with patch.object(svc, "get_factor_quantiles", return_value=None), \
         patch.object(svc, "get_forecast", return_value=None):
        assert svc.build_quant_context_block("600519", "cn") is None


def test_build_quant_context_block_carries_auxiliary_caveat_zh():
    svc = QuantSignalService()
    factors = {
        "stock_code": "600519",
        "market": "cn",
        "as_of": "2026-05-18",
        "quantiles": {"ret_5d": 0.012},
    }
    with patch.object(svc, "get_factor_quantiles", return_value=factors), \
         patch.object(svc, "get_forecast", return_value=None):
        block = svc.build_quant_context_block("600519", "cn", language="zh")
    assert block is not None
    assert "辅助" in block
    assert "不是买卖建议" in block
    assert "ret_5d" in block
    # No forecast → uncertain tag is present
    assert "当前模型不稳定" in block


def test_build_quant_context_block_carries_auxiliary_caveat_en():
    svc = QuantSignalService()
    factors = {
        "stock_code": "AAPL",
        "market": "us",
        "as_of": "2026-05-18",
        "quantiles": {"ret_5d": 0.012},
    }
    forecast = {
        "stock_code": "AAPL",
        "market": "us",
        "as_of": "2026-05-18",
        "horizon_days": 10,
        "expected_excess_return": 0.018,
        "rank_in_universe": 0.84,
        "ic_current": 0.05,
        "ic_ma_4w": 0.04,
        "model_version": "2026-W20",
    }
    with patch.object(svc, "get_factor_quantiles", return_value=factors), \
         patch.object(svc, "get_forecast", return_value=forecast):
        block = svc.build_quant_context_block("AAPL", "us", language="en")
    assert block is not None
    assert "auxiliary" in block.lower()
    assert "not a buy/sell recommendation" in block.lower()
    assert "Forecast" in block
    assert "10 trading days" in block


# ---------------------------------------------------------------------
# is_in_universe degrades gracefully
# ---------------------------------------------------------------------

def test_is_in_universe_false_when_universe_empty(monkeypatch):
    svc = QuantSignalService()
    with patch("data_provider.qlib_fetcher.normalize_to_qlib_symbol",
               return_value="SH600519"), \
         patch("data_provider.qlib_fetcher.csi300_universe", return_value=tuple()):
        assert svc.is_in_universe("600519", "cn") is False


def test_is_in_universe_true_for_member(monkeypatch):
    svc = QuantSignalService()
    with patch("data_provider.qlib_fetcher.normalize_to_qlib_symbol",
               return_value="SH600519"), \
         patch("data_provider.qlib_fetcher.csi300_universe",
               return_value=("SH600519", "SH600000")):
        assert svc.is_in_universe("600519", "cn") is True


def test_is_in_universe_false_for_hk():
    svc = QuantSignalService()
    assert svc.is_in_universe("hk00700", "hk") is False


# ---------------------------------------------------------------------
# QUANT_MARKETS exports CN + US only
# ---------------------------------------------------------------------

def test_quant_markets_cn_us_only():
    assert "cn" in QUANT_MARKETS
    assert "us" in QUANT_MARKETS
    assert "hk" not in QUANT_MARKETS
