"""Stitch raw Databento outright contracts into continuous front-month CSVs.

Input:
    data/_raw_daily.csv   ts_event,...,open,high,low,close,volume,symbol  (1d bars, mixed contracts)
    data/_raw_240m.csv    ts_event,open,high,low,close,volume,symbol      (4h bars, mixed contracts)

For each timestamp, picks the highest-volume outright contract per root (ES/NQ/GC)
to build a "most-active continuous" series. Spreads (symbol contains '-') and
non-target roots are dropped.

Output:
    data/{ES,NQ,GC}_1d.csv     timestamp,open,high,low,close,volume
    data/{ES,NQ,GC}_240m.csv   same
"""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd

DATA  = Path("data")
ROOTS = ["ES", "NQ", "GC"]
CONTRACT_RE = re.compile(r"^(ES|NQ|GC)[FGHJKMNQUVXZ]\d+$")


def stitch(raw_path: Path, out_suffix: str) -> None:
    print(f"\n=== {raw_path.name} ===")
    df = pd.read_csv(raw_path, parse_dates=["ts_event"])
    df["symbol"] = df["symbol"].astype(str)

    keep = df["symbol"].str.match(CONTRACT_RE)
    df   = df[keep].copy()
    df["root"] = df["symbol"].str[:2]
    print(f"  outright bars: {len(df):,}")

    for root in ROOTS:
        sub = df[df["root"] == root]
        if sub.empty:
            print(f"  {root}: 0 bars (skipped)")
            continue
        # For each timestamp pick the contract with the highest volume.
        idx = sub.groupby("ts_event")["volume"].idxmax()
        cont = sub.loc[idx].sort_values("ts_event").set_index("ts_event")
        out  = cont[["open", "high", "low", "close", "volume"]].copy()
        out.index.name = "timestamp"

        path = DATA / f"{root}_{out_suffix}.csv"
        out.to_csv(path)
        n_contracts = cont["symbol"].nunique()
        print(f"  {root}: {len(out):,} bars, {n_contracts} contracts, "
              f"{out.index.min()} → {out.index.max()}  -> {path.name}")


def main():
    stitch(DATA / "_raw_daily.csv", "1d")
    stitch(DATA / "_raw_240m.csv",  "240m")
    print("\nDone. Re-run: python backtest.py")


if __name__ == "__main__":
    main()
