# -*- coding: utf-8 -*-
"""
===================================
Quant signal service (Sprint 3 — Qlib Alpha158 + LightGBM auxiliary)
===================================

Public surface (P9-locked, see ``docs/superpowers/plans/2026-05-18-professional-upgrade.md``):

- :func:`QuantSignalService.get_factor_quantiles(stock_code, market)
  -> Optional[dict]`
- :func:`QuantSignalService.get_forecast(stock_code, market, horizon=10)
  -> Optional[dict]`
- :func:`QuantSignalService.build_quant_context_block(stock_code, market,
  horizon=10, language="zh") -> Optional[str]`

Behaviour contract (every public function returns ``None`` cleanly):

1. **qlib not installed** → ``None`` (with a single info log)
2. **No model artifact** on disk → ``None`` (factor quantiles MAY still
   work if qlib data is present, but forecast is gone)
3. **Stock outside the locked universe** (CSI 300 for cn, S&P 500 for us,
   HK silently skipped) → ``None``
4. **4-week IC moving average below ``QUANT_IC_GATING_THRESHOLD``
   (default 0.02)** → forecast hidden, factor quantiles still shown but
   tagged with "model currently uncertain"  (Q5 locked decision)
5. **Any internal exception** → caught and logged, return ``None`` so
   the broader pipeline never breaks because of the quant addon

The service exposes a **prompt block builder** so the analyzer doesn't
need to know about factor names or IC math — it just splices the
returned string between portfolio context and the dashboard data, the
same way it splices ``reflection_context_block`` in Sprint 2.

Heavy work (qlib init, factor materialisation, model load) lives in
``data_provider/qlib_fetcher.py`` and ``scripts/train_alpha158_lightgbm.py``.
This service is intentionally a thin orchestrator so unit tests can mock
the fetcher without spinning up qlib.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Env-driven defaults — every knob has a safe default so the codebase
# works out-of-the-box without ``.env`` edits.
# ---------------------------------------------------------------------

def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "y")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def quant_signal_enabled_default() -> bool:
    """Whether the global feature flag is on by default.

    The actual per-request opt-in lives in the API schema, but config
    can flip the default to ``true`` if the user wants to always
    include quant context for every API call.
    """
    return _env_bool("QUANT_SIGNAL_ENABLED", False)


def model_dir() -> str:
    """Where rolling weekly model artifacts live on disk."""
    return os.getenv("QUANT_MODEL_DIR", "data/quant_models")


def default_forecast_horizon() -> int:
    """Default forecast horizon in trading days (Q3 locked = 10)."""
    return _env_int("QUANT_FORECAST_HORIZON", 10)


def ic_gating_threshold() -> float:
    """4-week IC moving average gate (Q5 locked = 0.02)."""
    return _env_float("QUANT_IC_GATING_THRESHOLD", 0.02)


# ---------------------------------------------------------------------
# Light data classes — kept here (not in src/schemas) because Sprint 3
# is opt-in and we don't want to leak quant types into the default
# AnalysisResult contract.  Web surfaces use ``to_dict()`` over the wire.
# ---------------------------------------------------------------------

@dataclass
class FactorQuantiles:
    """Per-stock factor snapshot, normalised to cross-sectional quantiles
    (0.0–1.0 within the same universe on the same day).

    ``quantiles`` is a mapping of short factor name → quantile rank.
    Higher = stronger signal for that factor.
    """
    stock_code: str
    market: str
    as_of: str  # ISO date string
    quantiles: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "market": self.market,
            "as_of": self.as_of,
            "quantiles": dict(self.quantiles),
        }


@dataclass
class Forecast:
    """LightGBM-Alpha158 forecast snapshot.

    ``expected_excess_return`` is a *standardised* excess-return score
    (the LightGBM regressor's raw prediction; not a calibrated percentage).
    Web/prompt code presents it as a percentile-rank for sanity.
    """
    stock_code: str
    market: str
    as_of: str
    horizon_days: int
    expected_excess_return: float
    rank_in_universe: Optional[float] = None  # 0..1 quantile within universe
    ic_current: Optional[float] = None
    ic_ma_4w: Optional[float] = None
    model_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "market": self.market,
            "as_of": self.as_of,
            "horizon_days": self.horizon_days,
            "expected_excess_return": self.expected_excess_return,
            "rank_in_universe": self.rank_in_universe,
            "ic_current": self.ic_current,
            "ic_ma_4w": self.ic_ma_4w,
            "model_version": self.model_version,
        }


# ---------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------

# Markets supported by qlib bulk data (Q1 locked).  HK is intentionally
# excluded — qlib doesn't ship HK data, so HK stocks silently no-op.
QUANT_MARKETS = ("cn", "us")


def infer_market_from_code(stock_code: str) -> str:
    """Best-effort market inference from our internal code format.

    Returns one of ``"cn"`` / ``"us"`` / ``"hk"``.  Caller checks the
    return; ``"hk"`` triggers the silent no-op path.
    """
    code = (stock_code or "").strip()
    if not code:
        return "unknown"
    low = code.lower()
    # hk: hk00700, HK00700, 00700.HK
    if low.startswith("hk") or low.endswith(".hk"):
        return "hk"
    # cn: 6 digits (600519, 000001) or SH/SZ prefixed
    if low.startswith(("sh", "sz", "bj")):
        return "cn"
    if code.isdigit() and len(code) == 6:
        return "cn"
    # us: letters
    if code.replace(".", "").replace("-", "").isalpha():
        return "us"
    return "unknown"


class QuantSignalService:
    """Thin orchestrator that exposes quant context to the analyzer.

    The service is stateless across calls; each public method picks up
    config on every invocation so a config reload (e.g. flipping
    ``QUANT_SIGNAL_ENABLED``) takes effect without restarting the
    process.
    """

    # ------------------------------------------------------------
    # Universe gating (Q1)
    # ------------------------------------------------------------

    def is_in_universe(self, stock_code: str, market: str) -> bool:
        """Check whether the stock falls in CSI 300 (cn) or S&P 500 (us).

        Returns True only when we can positively confirm membership.
        Empty universes (qlib not installed / data missing) → False,
        which routes through the silent no-op path.
        """
        try:
            from data_provider import qlib_fetcher
        except Exception as exc:
            logger.debug("[quant] qlib_fetcher import failed: %s", exc)
            return False

        market = (market or "").strip().lower()
        if market not in QUANT_MARKETS:
            return False

        symbol = qlib_fetcher.normalize_to_qlib_symbol(stock_code, market)
        if symbol is None:
            return False

        try:
            if market == "cn":
                universe = qlib_fetcher.csi300_universe()
            else:
                universe = qlib_fetcher.sp500_universe()
        except Exception as exc:
            logger.warning("[quant] universe lookup failed for %s: %s", market, exc)
            return False

        if not universe:
            # universe unknown — be conservative and skip.  The user
            # can override by setting QUANT_UNIVERSE_GATE=loose (not
            # implemented in Sprint 3; documented in setup runbook).
            return False
        return symbol in universe

    # ------------------------------------------------------------
    # Factor quantiles (always allowed when qlib data is present)
    # ------------------------------------------------------------

    def get_factor_quantiles(
        self, stock_code: str, market: str
    ) -> Optional[Dict[str, Any]]:
        """Return the latest Alpha158 factor snapshot keyed by short name.

        Returns the dict form of :class:`FactorQuantiles` or ``None``
        when qlib unavailable / stock outside universe / fetcher error.

        Note: in the framework-only build this returns raw factor
        values, not strict cross-sectional quantiles — computing real
        quantiles requires the daily snapshot of the full universe,
        which is what the weekly training job materialises.  The
        sidecar ``factor_quantiles.json`` produced by
        ``scripts/train_alpha158_lightgbm.py`` (when present) replaces
        the raw values with proper quantiles.
        """
        try:
            if not self.is_in_universe(stock_code, market):
                return None

            from data_provider import qlib_fetcher
            symbol = qlib_fetcher.normalize_to_qlib_symbol(stock_code, market)
            if symbol is None:
                return None

            # If the training job dumped a per-day quantile sidecar use
            # that; otherwise fall back to live factor values.
            sidecar = self._load_factor_sidecar(market)
            if sidecar is not None and symbol in sidecar:
                snapshot = sidecar[symbol]
            else:
                raw = qlib_fetcher.get_alpha158_factors(symbol, market)
                if raw is None:
                    return None
                snapshot = raw

            from datetime import date
            fq = FactorQuantiles(
                stock_code=stock_code,
                market=market,
                as_of=date.today().isoformat(),
                quantiles=dict(snapshot),
            )
            return fq.to_dict()
        except Exception as exc:
            logger.warning(
                "[quant] get_factor_quantiles failed for %s/%s: %s",
                stock_code, market, exc,
            )
            return None

    # ------------------------------------------------------------
    # Forecast (gated by IC and artifact presence)
    # ------------------------------------------------------------

    def get_forecast(
        self,
        stock_code: str,
        market: str,
        horizon: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the LightGBM forecast for one stock, or ``None``.

        Gating order (P9-locked):
        1. Market must be cn or us (HK silent no-op).
        2. Stock must be in the locked universe.
        3. A model artifact for ``market`` must exist on disk.
        4. The model's 4-week IC moving average must be at or above
           :func:`ic_gating_threshold`.
        """
        try:
            market_l = (market or "").strip().lower()
            if market_l not in QUANT_MARKETS:
                return None
            if not self.is_in_universe(stock_code, market_l):
                return None

            artifact = self._load_model_artifact(market_l)
            if artifact is None:
                return None

            ic_ma_4w = artifact.get("ic_ma_4w")
            if ic_ma_4w is not None and ic_ma_4w < ic_gating_threshold():
                logger.info(
                    "[quant] forecast suppressed for %s/%s: ic_ma_4w=%.4f < gate=%.4f",
                    stock_code, market_l, ic_ma_4w, ic_gating_threshold(),
                )
                return None

            predictions = artifact.get("predictions") or {}
            from data_provider import qlib_fetcher
            symbol = qlib_fetcher.normalize_to_qlib_symbol(stock_code, market_l)
            if symbol is None or symbol not in predictions:
                return None

            pred_row = predictions[symbol]
            from datetime import date
            forecast = Forecast(
                stock_code=stock_code,
                market=market_l,
                as_of=artifact.get("as_of") or date.today().isoformat(),
                horizon_days=horizon or default_forecast_horizon(),
                expected_excess_return=float(pred_row.get("score", 0.0)),
                rank_in_universe=pred_row.get("rank"),
                ic_current=artifact.get("ic_current"),
                ic_ma_4w=ic_ma_4w,
                model_version=artifact.get("model_version"),
            )
            return forecast.to_dict()
        except Exception as exc:
            logger.warning(
                "[quant] get_forecast failed for %s/%s: %s",
                stock_code, market, exc,
            )
            return None

    # ------------------------------------------------------------
    # Prompt block (the only output the analyzer cares about)
    # ------------------------------------------------------------

    def build_quant_context_block(
        self,
        stock_code: str,
        market: str,
        horizon: Optional[int] = None,
        language: str = "zh",
    ) -> Optional[str]:
        """Build the markdown block spliced into the LLM prompt.

        Returns ``None`` when neither factor quantiles nor forecast are
        available — the analyzer then omits the whole section.  Always
        includes an explicit "auxiliary, not a recommendation" caveat
        (Q7 locked).
        """
        try:
            factors = self.get_factor_quantiles(stock_code, market)
            forecast = self.get_forecast(stock_code, market, horizon=horizon)
            if factors is None and forecast is None:
                return None

            lang = (language or "zh").lower()
            return self._render_block(factors, forecast, lang)
        except Exception as exc:
            logger.warning(
                "[quant] build_quant_context_block failed for %s/%s: %s",
                stock_code, market, exc,
            )
            return None

    # ------------------------------------------------------------
    # Helpers — kept private so the contract stays narrow
    # ------------------------------------------------------------

    def _render_block(
        self,
        factors: Optional[Dict[str, Any]],
        forecast: Optional[Dict[str, Any]],
        language: str,
    ) -> str:
        """Compose the markdown prompt block.

        Layout (Q7 locked — must include the auxiliary caveat):
            ## Quant Context (auxiliary)
            > Caveat line
            - factor rows
            - forecast line (when present)
        """
        is_zh = language == "zh"
        header = "## 量化辅助信号 (Quant Context — auxiliary)" if is_zh else "## Quant Context (auxiliary)"
        if is_zh:
            caveat = (
                "> 以下为统计模型输出的**辅助观察**，**不是买卖建议**。"
                "模型仅基于历史价量因子，未读今日新闻、不识别基本面拐点，"
                "权重应明显低于基本面/技术面/情绪面。"
            )
        else:
            caveat = (
                "> The following is an **auxiliary statistical signal**, "
                "**not a buy/sell recommendation**. The model is built on "
                "historical price-volume factors only, has no awareness of "
                "today's news or fundamentals, and should be weighted "
                "well below fundamental / technical / sentiment views."
            )

        lines: List[str] = [header, "", caveat, ""]

        if factors is not None and factors.get("quantiles"):
            lines.append("### 因子快照 / Factor snapshot" if is_zh else "### Factor snapshot")
            for name, value in factors["quantiles"].items():
                try:
                    lines.append(f"- `{name}`: {float(value):+.4f}")
                except (TypeError, ValueError):
                    continue
            lines.append("")

        if forecast is not None:
            lines.append("### 模型预测 / Forecast" if is_zh else "### Forecast")
            horizon = forecast.get("horizon_days")
            score = forecast.get("expected_excess_return")
            rank = forecast.get("rank_in_universe")
            ic_cur = forecast.get("ic_current")
            ic_ma = forecast.get("ic_ma_4w")
            mv = forecast.get("model_version")

            if is_zh:
                lines.append(f"- 预测期：{horizon} 个交易日（约 2 周）")
                if score is not None:
                    lines.append(f"- 模型预测分（原始）：`{float(score):+.4f}`")
                if rank is not None:
                    lines.append(f"- 池内排名分位：`{float(rank):.2%}`")
                if ic_cur is not None:
                    lines.append(f"- 当期 Rank IC：`{float(ic_cur):+.4f}`")
                if ic_ma is not None:
                    lines.append(f"- 4 周 IC 均线：`{float(ic_ma):+.4f}`")
                if mv:
                    lines.append(f"- 模型版本：`{mv}`")
            else:
                lines.append(f"- Horizon: {horizon} trading days (~2 weeks)")
                if score is not None:
                    lines.append(f"- Raw score: `{float(score):+.4f}`")
                if rank is not None:
                    lines.append(f"- Universe rank: `{float(rank):.2%}`")
                if ic_cur is not None:
                    lines.append(f"- Current Rank IC: `{float(ic_cur):+.4f}`")
                if ic_ma is not None:
                    lines.append(f"- 4-week IC MA: `{float(ic_ma):+.4f}`")
                if mv:
                    lines.append(f"- Model version: `{mv}`")
            lines.append("")
        else:
            if factors is not None:
                # Factor block present but forecast suppressed (gated or no artifact).
                # Add a low-confidence tag (Q5 locked).
                tag = (
                    "> ⚠️ 当前模型不稳定（IC 低于门限或暂无模型权重），仅展示因子，未给出预测。"
                    if is_zh
                    else "> ⚠️ Model currently uncertain (IC below gate or no artifact); "
                         "showing factors only, no forecast."
                )
                lines.append(tag)
                lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _load_model_artifact(self, market: str) -> Optional[Dict[str, Any]]:
        """Load the most recent weekly artifact for the given market.

        Looks under ``<QUANT_MODEL_DIR>/<market>/<YYYY-WW>/predictions.json``
        (the trainer script writes alongside the pickle so we can read
        predictions without needing lightgbm at runtime — predictions
        are just a flat ``{symbol: {score, rank}}`` map).

        Returns ``None`` when the directory is missing or empty.
        """
        try:
            base = os.path.join(model_dir(), market)
            if not os.path.isdir(base):
                return None

            # Pick the lexicographically last subdirectory (YYYY-WW
            # format sorts correctly through year transitions in
            # practice; the trainer is responsible for using ISO week).
            subdirs = sorted(
                d for d in os.listdir(base)
                if os.path.isdir(os.path.join(base, d))
            )
            if not subdirs:
                return None
            latest = subdirs[-1]

            pred_path = os.path.join(base, latest, "predictions.json")
            ic_path = os.path.join(base, latest, "ic.json")

            artifact: Dict[str, Any] = {"model_version": latest}
            if os.path.isfile(pred_path):
                with open(pred_path, "r", encoding="utf-8") as fh:
                    artifact["predictions"] = json.load(fh) or {}
            else:
                artifact["predictions"] = {}

            if os.path.isfile(ic_path):
                with open(ic_path, "r", encoding="utf-8") as fh:
                    ic_data = json.load(fh) or {}
                artifact["ic_current"] = ic_data.get("ic_current")
                artifact["ic_ma_4w"] = ic_data.get("ic_ma_4w")
                artifact["as_of"] = ic_data.get("as_of")

            return artifact
        except Exception as exc:
            logger.warning("[quant] model artifact load failed for %s: %s", market, exc)
            return None

    def _load_factor_sidecar(self, market: str) -> Optional[Dict[str, Dict[str, float]]]:
        """Load the optional ``factor_quantiles.json`` sidecar.

        When the weekly training job dumps cross-sectional quantiles,
        we prefer them over live factor values (live values are not
        normalised, which makes the prompt harder to read).
        """
        try:
            base = os.path.join(model_dir(), market)
            if not os.path.isdir(base):
                return None
            subdirs = sorted(
                d for d in os.listdir(base)
                if os.path.isdir(os.path.join(base, d))
            )
            if not subdirs:
                return None
            path = os.path.join(base, subdirs[-1], "factor_quantiles.json")
            if not os.path.isfile(path):
                return None
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh) or {}
        except Exception as exc:
            logger.warning("[quant] factor sidecar load failed for %s: %s", market, exc)
            return None


__all__ = [
    "QuantSignalService",
    "FactorQuantiles",
    "Forecast",
    "infer_market_from_code",
    "quant_signal_enabled_default",
    "default_forecast_horizon",
    "ic_gating_threshold",
    "model_dir",
    "QUANT_MARKETS",
]
