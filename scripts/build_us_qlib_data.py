#!/usr/bin/env python3
"""
Sprint 3 — Build S&P 500 qlib binary data from yfinance.

Background
----------
``qlib.tests.data.GetData`` only ships Microsoft's frozen 2020 bundle for
US tickers, and the qlib ecosystem has no actively-maintained free US data
mirror equivalent to chenditc/investment_data for CN. This helper fills
that gap so weekly retrains have fresh prices instead of 6-year-old ones.

What it does
------------
1. Pulls the S&P 500 constituents from Wikipedia.
2. Bulk-downloads ~3 years of daily OHLCV via yfinance.
3. Writes one CSV per ticker (qlib's expected ``dump_all`` layout).
4. Invokes qlib's ``dump_bin.py dump_all`` to materialise the binary
   feature files.
5. Writes ``instruments/sp500.txt`` so Alpha158's ``instruments='sp500'``
   handler can find the universe.

Configuration knobs (all optional)
----------------------------------
``QLIB_DATA_DIR``      target root, default ``data/qlib`` (relative to
                       this script's parent).
``QLIB_TOOLS_DIR``     path to a local clone of microsoft/qlib whose
                       ``scripts/dump_bin.py`` will be used. If unset,
                       defaults to ``~/reference_repos/qlib``; if that
                       doesn't exist either, falls back to a shallow git
                       clone into ``./.qlib_tools/qlib``.
``US_DATA_START``      ISO date for the earliest training row,
                       default ``2022-12-01``.
``US_STAGING_DIR``     temp CSV staging dir, default
                       ``./.qlib_staging/us_csv``.

This script is opt-in. Failing prerequisites (missing yfinance,
missing pandas) cause a friendly skip — the rest of the daily app
still works fine when this hasn't been run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from io import StringIO
from pathlib import Path


def _log(msg: str) -> None:
    print(f"[build_us_qlib_data] {msg}", flush=True)


REPO_ROOT = Path(__file__).resolve().parent.parent

QLIB_DATA_DIR = Path(os.getenv("QLIB_DATA_DIR", str(REPO_ROOT / "data" / "qlib")))
US_QLIB_DIR = QLIB_DATA_DIR / "us_data"

STAGING_CSV = Path(os.getenv("US_STAGING_DIR", str(REPO_ROOT / ".qlib_staging" / "us_csv")))

START = os.getenv("US_DATA_START", "2022-12-01")
END = datetime.utcnow().strftime("%Y-%m-%d")


def resolve_dump_bin() -> Path:
    """Locate (or fetch) qlib's ``scripts/dump_bin.py``."""

    explicit = os.getenv("QLIB_TOOLS_DIR")
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path.home() / "reference_repos" / "qlib")
    candidates.append(REPO_ROOT / ".qlib_tools" / "qlib")

    for c in candidates:
        dump = c / "scripts" / "dump_bin.py"
        if dump.is_file():
            return dump

    # None present — shallow clone microsoft/qlib into ./.qlib_tools/qlib.
    fallback = REPO_ROOT / ".qlib_tools" / "qlib"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    _log(f"cloning microsoft/qlib (shallow) into {fallback}")
    subprocess.run(
        [
            "git", "clone", "--depth", "1",
            "https://github.com/microsoft/qlib.git",
            str(fallback),
        ],
        check=True,
    )
    return fallback / "scripts" / "dump_bin.py"


def get_sp500_tickers() -> list[str]:
    import pandas as pd
    import requests

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(StringIO(r.text))
    df = tables[0]
    tickers = [str(t).replace(".", "-").upper() for t in df["Symbol"].tolist()]
    _log(f"Wikipedia returned {len(tickers)} S&P 500 constituents")
    return tickers


def download_bulk(tickers: list[str]):
    import yfinance as yf

    _log(f"yfinance downloading {len(tickers)} tickers {START}..{END}")
    df = yf.download(
        tickers,
        start=START,
        end=END,
        group_by="ticker",
        progress=False,
        auto_adjust=False,
        threads=True,
    )
    if df is None or df.empty:
        _log("empty yfinance result, aborting")
        sys.exit(1)
    _log(f"bulk frame shape={df.shape}")
    return df


def write_per_ticker_csvs(bulk, tickers: list[str]) -> list[str]:
    import pandas as pd

    if STAGING_CSV.exists():
        for old in STAGING_CSV.glob("*.csv"):
            old.unlink()
    STAGING_CSV.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for t in tickers:
        try:
            sub = bulk[t] if t in bulk.columns.get_level_values(0) else None
        except Exception:
            sub = None
        if sub is None or sub.empty:
            continue
        sub = sub.dropna(how="all")
        if sub.empty:
            continue
        df = sub.reset_index()
        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
        if "adj_close" not in df.columns or "close" not in df.columns:
            continue
        df["factor"] = df["adj_close"] / df["close"]
        df = df[["date", "open", "high", "low", "close", "volume", "factor"]].dropna(
            subset=["open", "close"]
        )
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df.to_csv(STAGING_CSV / f"{t}.csv", index=False)
        written.append(t)

    _log(f"wrote {len(written)} ticker CSVs to {STAGING_CSV}")
    return written


def run_dump_bin(dump_bin: Path) -> None:
    if US_QLIB_DIR.exists():
        for child in US_QLIB_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    US_QLIB_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(dump_bin),
        "dump_all",
        "--data_path", str(STAGING_CSV),
        "--qlib_dir", str(US_QLIB_DIR),
        "--include_fields", "open,high,low,close,volume,factor",
        "--max_workers", "8",
    ]
    _log(" ".join(cmd))
    subprocess.run(cmd, check=True)


def write_sp500_instrument_file(written: list[str]) -> None:
    inst_dir = US_QLIB_DIR / "instruments"
    inst_dir.mkdir(parents=True, exist_ok=True)
    out = inst_dir / "sp500.txt"
    lines = [f"{t}\t{START}\t{END}" for t in sorted(written)]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _log(f"wrote {len(lines)} lines to {out}")


def main() -> int:
    try:
        import pandas  # noqa: F401
        import yfinance  # noqa: F401
        import requests  # noqa: F401
    except ImportError as exc:
        _log(f"missing dependency: {exc}; skipping US build (install: pip install -r requirements-quant.txt yfinance yahooquery beautifulsoup4 lxml)")
        return 0

    dump_bin = resolve_dump_bin()
    tickers = get_sp500_tickers()
    bulk = download_bulk(tickers)
    written = write_per_ticker_csvs(bulk, tickers)
    if not written:
        _log("no CSVs written; nothing to dump")
        return 1

    run_dump_bin(dump_bin)
    write_sp500_instrument_file(written)
    _log(f"done — us_data ready at {US_QLIB_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
