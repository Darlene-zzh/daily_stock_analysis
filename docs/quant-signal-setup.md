# Quant Signal — Setup Runbook (Sprint 3)

This runbook walks through enabling the optional Qlib Alpha158 + LightGBM auxiliary signal.  By default the feature is OFF; the main app boots fine without any of the steps below.

> **TL;DR**: install `requirements-quant.txt`, run `scripts/setup_qlib_data.sh` once, run `scripts/train_alpha158_lightgbm.py` once a week, and pass `enable_quant_signal: true` on API requests where you want the auxiliary block.

---

## 1. Pre-flight checks

```bash
# In the repo root
python -m pip install -r requirements.txt          # main deps (unchanged)
python -c "from src.services.quant_signal_service import QuantSignalService; \
           print(QuantSignalService().get_factor_quantiles('600519', 'cn'))"
# Expected: None  (no qlib yet, no model — silent no-op)
```

If that prints `None` without raising, the lazy-import path is working as designed.

## 2. Install the quant-only dependencies

```bash
pip install -r requirements-quant.txt
# Installs:
#   pyqlib  >= 0.9.0
#   lightgbm >= 4.0
```

We keep these OUT of `requirements.txt` because qlib has heavy C compilation steps that you don't want in the default Docker build or CI.

## 3. Download the qlib bulk data (one-off, ~GB-scale)

```bash
bash scripts/setup_qlib_data.sh        # cn + us (default)
# bash scripts/setup_qlib_data.sh cn   # only A-share
# bash scripts/setup_qlib_data.sh us   # only US

# Custom location:
QLIB_DATA_DIR=/big-disk/qlib bash scripts/setup_qlib_data.sh
```

The script is idempotent — re-running triggers qlib's incremental updater.  The resulting layout:

```
data/qlib/
  cn_data/
    calendars/
    instruments/
    features/...
  us_data/
    ...
```

`data/qlib/**` is gitignored (only `.gitkeep` is tracked).

## 4. Train the first LightGBM × Alpha158 model

```bash
python scripts/train_alpha158_lightgbm.py
# or per-region:
python scripts/train_alpha158_lightgbm.py --region cn
python scripts/train_alpha158_lightgbm.py --region us --horizon 10
```

Produces (per region, per ISO week):

```
data/quant_models/<region>/<YYYY-Wxx>/
  model.pkl              # full LightGBM artifact
  predictions.json       # {qlib_symbol: {score, rank}} consumed by the service at runtime
  ic.json                # {as_of, ic_current, ic_ma_4w} for the gating check
  factor_quantiles.json  # OPTIONAL cross-sectional factor quantiles
```

A single region takes ~20 min on a modern laptop.

## 5. Automate weekly retrains (optional)

`.github/workflows/qlib-retrain.yml` has the same logic packaged for GitHub-hosted runners:

* The `schedule:` trigger is commented out by default — uncomment it to enable.  Suggested cron: `0 2 * * 6` (Saturday 02:00 UTC).
* `workflow_dispatch` is always on so you can manually run it the first time to confirm the artifact uploads.
* Each run uploads `quant-models-<YYYY-Wxx>.tar.gz` to a GitHub Release (pre-release) AND keeps a 60-day Action artifact copy.

## 6. Enable the signal per request

```bash
curl -X POST http://localhost:8000/api/v1/analysis/analyze \
  -H 'Content-Type: application/json' \
  -d '{
        "stock_code": "600519",
        "report_type": "detailed",
        "enable_quant_signal": true,
        "quant_forecast_horizon": 10
      }'
```

The auxiliary block appears in the LLM prompt under `## Quant Context (auxiliary)` and renders in the Web report as `QuantContextPanel`.

Standalone fetch:

```bash
curl http://localhost:8000/api/v1/quant-signal/600519?market=cn
# 200 with { factors, forecast } when everything is set up,
# 204 No Content when not (stock outside universe / no artifact / low IC).
```

## 7. Verify the gating logic

You can force the silent no-op path to confirm there's no leakage:

```bash
# Move the model dir away and confirm the API returns 204:
mv data/quant_models data/quant_models.bak
curl -i http://localhost:8000/api/v1/quant-signal/600519?market=cn
# HTTP/1.1 204 No Content
mv data/quant_models.bak data/quant_models
```

## 8. Configuration knobs

All optional; sensible defaults live in `.env.example`.

| Knob | Default | Meaning |
|------|---------|---------|
| `QUANT_SIGNAL_ENABLED` | `false` | Global default for the feature flag (only documentation today; API uses per-request `enable_quant_signal`) |
| `QUANT_MODEL_DIR` | `data/quant_models` | Where weekly artifacts live |
| `QUANT_FORECAST_HORIZON` | `10` | Default forecast horizon in trading days |
| `QUANT_IC_GATING_THRESHOLD` | `0.02` | 4-week Rank IC MA below this → forecast hidden |
| `QLIB_DATA_DIR` | `data/qlib` | Where `setup_qlib_data.sh` puts the bulk data |
| `QLIB_PROVIDER_URI_CN` | (unset) | Override CN data dir (high-priority) |
| `QLIB_PROVIDER_URI_US` | (unset) | Override US data dir (high-priority) |

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| API returns 204 even though I trained a model | Stock not in CSI 300 / S&P 500 | This is a locked decision — the prompt and Web both silently skip non-universe stocks |
| `get_factor_quantiles` returns None but qlib is installed | Data dir empty | Run `scripts/setup_qlib_data.sh` |
| Forecast missing but factors visible | IC below the 0.02 gate | Wait for the next weekly retrain; or override `QUANT_IC_GATING_THRESHOLD` (not recommended) |
| Forecast missing AND factor block missing | No model artifact yet | Run `scripts/train_alpha158_lightgbm.py` |
| Training script exits with code 0 and a warning | Either `pyqlib` or `lightgbm` not installed | `pip install -r requirements-quant.txt` |

## 10. Rollback

* Set per-request `enable_quant_signal: false` (the default) — quant block disappears immediately.
* Remove `data/quant_models/` to force silent no-op everywhere.
* `git revert` the Sprint 3 merge commit if you want to delete the feature entirely; the main app and existing tests are unaffected.
