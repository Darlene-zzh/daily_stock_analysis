#!/usr/bin/env bash
# ------------------------------------------------------------------
# Sprint 3 — Qlib bulk data setup (CN + US)
# ------------------------------------------------------------------
#
# Downloads qlib's bulk price/volume datasets into ``data/qlib`` so the
# Quant Signal service (Alpha158 + LightGBM) has a working data layer.
#
# Run this manually the first time you want to enable the quant context;
# the per-region download is several gigabytes, so we deliberately keep
# it out of the default boot path and the docker image.
#
# Usage:
#   bash scripts/setup_qlib_data.sh             # both cn + us
#   bash scripts/setup_qlib_data.sh cn          # cn only
#   bash scripts/setup_qlib_data.sh us          # us only
#   QLIB_DATA_DIR=/tmp/qlib bash scripts/setup_qlib_data.sh
#
# Requirements (install separately, NOT in main requirements.txt):
#   pip install -r requirements-quant.txt
#
# Idempotent: re-runs trigger qlib's incremental updater rather than a
# full re-download.
# ------------------------------------------------------------------

set -euo pipefail

DATA_DIR="${QLIB_DATA_DIR:-data/qlib}"
REGIONS=("$@")

if [ ${#REGIONS[@]} -eq 0 ]; then
    REGIONS=(cn us)
fi

# Verify qlib is installed before doing anything else; otherwise the
# error message points the user to the right requirements file.
if ! python3 -c "import qlib" 2>/dev/null; then
    echo "[setup_qlib_data] ERROR: qlib not installed."
    echo "    Run: pip install -r requirements-quant.txt"
    exit 1
fi

mkdir -p "${DATA_DIR}"

for REGION in "${REGIONS[@]}"; do
    case "${REGION}" in
        cn|us)
            TARGET="${DATA_DIR}/${REGION}_data"
            echo "[setup_qlib_data] downloading qlib ${REGION} data into ${TARGET}"
            python3 -m qlib.run.get_data qlib_data \
                --target_dir "${TARGET}" \
                --region "${REGION}" \
                --interval 1d
            echo "[setup_qlib_data] ${REGION} done"
            ;;
        *)
            echo "[setup_qlib_data] skipping unknown region: ${REGION} (supported: cn, us)"
            ;;
    esac
done

echo "[setup_qlib_data] complete. You can now run scripts/train_alpha158_lightgbm.py."
