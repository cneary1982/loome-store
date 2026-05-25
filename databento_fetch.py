"""Pull daily + 4h history for ES, NQ, GC from Databento.

Usage:
    export DATABENTO_API_KEY=db-xxxxxxxxxxxx
    python databento_fetch.py

Writes:
    data/{ES,NQ,GC}_1d.csv      (5 years of daily bars)
    data/{ES,NQ,GC}_240m.csv    (3 years of 4-hour bars, resampled from 1h)

Schema written matches the yfinance-style loader in backtest.py:
    timestamp,open,high,low,close,volume   (UTC, ascending, ISO 8601)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

try:
    import databento as db
except ImportError:
    print("Missing dependency. Run: pip install databento", file=sys.stderr)
    sys.exit(1)


DATASET   = "GLBX.MDP3"            # CME Globex
SYMBOLS   = ["ES.c.0", "NQ.c.0", "GC.c.0"]   # continuous front-month
SHORT     = {"ES.c.0": "ES", "NQ.c.0": "NQ", "GC.c.0": "GC"}
DATA      = Path("data")

YEARS_1D  = 5
YEARS_4H  = 3


def fetch(client: db.Historical, symbol: str, schema: str, start, end) -> pd.DataFrame:
    print(f"  [{schema}] {symbol}  {start.date()} → {end.date()}", flush=True)
    data = client.timeseries.get_range(
        dataset  = DATASET,
        symbols  = [symbol],
        schema   = schema,
        stype_in = "continuous",
        start    = start,
        end      = end,
    )
    df = data.to_df()
    if df.empty:
        return df
    # Databento gives ts_event index in UTC. Normalize column names + scale price.
    # ohlcv-* schemas already give human-readable prices when using .to_df() with default pretty_px=True.
    df = df.rename(columns={"open": "open", "high": "high", "low": "low",
                            "close": "close", "volume": "volume"})
    df.index = df.index.tz_convert("UTC")
    df.index.name = "timestamp"
    return df[["open", "high", "low", "close", "volume"]]


def resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()


def main():
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        print("ERROR: set DATABENTO_API_KEY in the environment.", file=sys.stderr)
        sys.exit(1)

    DATA.mkdir(exist_ok=True)
    client = db.Historical(key)

    now      = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_1d = now - timedelta(days=365 * YEARS_1D + 7)
    start_1h = now - timedelta(days=365 * YEARS_4H + 7)

    print(f"Daily window: {start_1d.date()} → {now.date()}  ({YEARS_1D}y)")
    print(f"1h window:    {start_1h.date()} → {now.date()}  ({YEARS_4H}y, will resample to 4h)")
    print()

    for sym in SYMBOLS:
        short = SHORT[sym]
        print(f"=== {short} ===")

        # Daily
        df_d = fetch(client, sym, "ohlcv-1d", start_1d, now)
        out_d = DATA / f"{short}_1d.csv"
        df_d.to_csv(out_d)
        print(f"     -> {out_d}  ({len(df_d):,} bars)")

        # 1h → 4h
        df_h  = fetch(client, sym, "ohlcv-1h", start_1h, now)
        df_4h = resample_4h(df_h)
        out_4 = DATA / f"{short}_240m.csv"
        df_4h.to_csv(out_4)
        print(f"     -> {out_4}  ({len(df_4h):,} bars  from {len(df_h):,} 1h bars)")

        print()

    print("Done. Re-run: python backtest.py")


if __name__ == "__main__":
    main()
