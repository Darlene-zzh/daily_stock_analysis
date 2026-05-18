#!/usr/bin/env bash
# ------------------------------------------------------------------
# Sprint 3 — Qlib bulk data setup (CN + US)
# ------------------------------------------------------------------
#
# Sources:
#
#   CN — chenditc/investment_data GitHub Release (daily-updated).
#        Downloaded as a single ``qlib_bin.tar.gz`` and extracted
#        into ``${QLIB_DATA_DIR}/cn_data``. Microsoft's official
#        bundle has been frozen at 2020-09 for years and is
#        unusable for fresh weekly retrains.
#
#   US — ``scripts/build_us_qlib_data.py`` (yfinance + qlib dump_bin).
#        chenditc only covers CN; the build helper downloads the S&P
#        500 from yfinance, factor-adjusts, and writes qlib binaries.
#
# Usage:
#   bash scripts/setup_qlib_data.sh             # both cn + us
#   bash scripts/setup_qlib_data.sh cn          # cn only
#   bash scripts/setup_qlib_data.sh us          # us only
#   QLIB_DATA_DIR=/big-disk/qlib bash scripts/setup_qlib_data.sh
#
# Idempotent: re-running replaces the regional dataset cleanly.
#
# Requirements (install separately, NOT in main requirements.txt):
#   pip install -r requirements-quant.txt
#   (US only:) pip install yfinance yahooquery beautifulsoup4 lxml setuptools_scm
# ------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${QLIB_DATA_DIR:-${REPO_ROOT}/data/qlib}"
PYBIN="${PYTHON:-python3}"

# Verify pyqlib is importable before anything else; the message
# explicitly tells the user where to find the optional requirements
# file so they don't waste time on the main one.
if ! "${PYBIN}" -c "import qlib" 2>/dev/null; then
    echo "[setup_qlib_data] ERROR: pyqlib not importable with '${PYBIN}'."
    echo "    Try: pip install -r requirements-quant.txt"
    echo "    Or:  PYTHON=python3.11 bash scripts/setup_qlib_data.sh"
    exit 1
fi

REGIONS=("$@")
if [ ${#REGIONS[@]} -eq 0 ]; then
    REGIONS=(cn us)
fi

mkdir -p "${DATA_DIR}"


# -----------------------------------------------------------------
# CN — chenditc/investment_data Release
# -----------------------------------------------------------------
fetch_cn_chenditc() {
    local target="${DATA_DIR}/cn_data"
    local staging="${DATA_DIR}/.chenditc_staging"
    local archive="${staging}/qlib_bin.tar.gz"

    echo "[setup_qlib_data] CN — querying chenditc/investment_data latest release"
    mkdir -p "${staging}"

    local url
    url="$(curl -sL https://api.github.com/repos/chenditc/investment_data/releases/latest \
        | "${PYBIN}" -c 'import json,sys; r=json.load(sys.stdin); assets=r.get("assets",[]); urls=[a["browser_download_url"] for a in assets if a["name"].endswith("qlib_bin.tar.gz")]; print(urls[0] if urls else "")')"

    if [ -z "${url}" ]; then
        echo "[setup_qlib_data] ERROR: could not resolve chenditc qlib_bin.tar.gz asset URL."
        exit 2
    fi

    echo "[setup_qlib_data] CN — downloading ${url}"
    curl -L --fail -o "${archive}" "${url}"

    echo "[setup_qlib_data] CN — extracting into ${target}"
    rm -rf "${target}"
    mkdir -p "${target}"
    tar xzf "${archive}" -C "${target}" --strip-components=1
    rm -rf "${staging}"

    if [ ! -f "${target}/calendars/day.txt" ]; then
        echo "[setup_qlib_data] ERROR: extracted archive is missing calendars/day.txt."
        exit 3
    fi
    echo "[setup_qlib_data] CN — done. Last calendar entry: $(tail -1 "${target}/calendars/day.txt")"
}


# -----------------------------------------------------------------
# US — yfinance + qlib dump_bin via scripts/build_us_qlib_data.py
# -----------------------------------------------------------------
build_us_yfinance() {
    echo "[setup_qlib_data] US — invoking scripts/build_us_qlib_data.py"
    QLIB_DATA_DIR="${DATA_DIR}" "${PYBIN}" "${REPO_ROOT}/scripts/build_us_qlib_data.py"
    local target="${DATA_DIR}/us_data"
    if [ -f "${target}/calendars/day.txt" ]; then
        echo "[setup_qlib_data] US — done. Last calendar entry: $(tail -1 "${target}/calendars/day.txt")"
    else
        echo "[setup_qlib_data] WARNING: us_data/calendars/day.txt missing after build."
    fi
}


for REGION in "${REGIONS[@]}"; do
    case "${REGION}" in
        cn)
            fetch_cn_chenditc
            ;;
        us)
            build_us_yfinance
            ;;
        *)
            echo "[setup_qlib_data] skipping unknown region: ${REGION} (supported: cn, us)"
            ;;
    esac
done

echo "[setup_qlib_data] complete. Run: ${PYBIN} scripts/train_alpha158_lightgbm.py"
