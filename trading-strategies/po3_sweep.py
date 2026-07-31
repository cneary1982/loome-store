#!/usr/bin/env python3
"""Parameter sweep for the PO3 model.

Every config is scored twice — on the first 60% of the span and on the held-out
last 40%. A config that only works in-sample is a fitted config, and the split
columns are there to make that obvious rather than to hide it.

Usage:
    python po3_sweep.py                      # default grid, all datasets
    python po3_sweep.py --full               # wider grid
    python po3_sweep.py --jobs 4
    python po3_sweep.py --out results/po3_sweep.csv
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

from po3 import (
    BiasConfig,
    GateConfig,
    PO3Config,
    RunConfig,
    load_bars,
    summarize,
    trades_frame,
)
from po3.runner import PO3Session

# (label, path, cost per side in price units). ETFs pay about a cent of
# half-spread plus commission; ES is charged a full tick.
DATASETS = [
    ("QQQ_5m", "data/etf/QQQ_5m_2yr.csv", 0.01),
    ("SPY_5m", "data/etf/SPY_5m_2yr.csv", 0.01),
    ("GLD_5m", "data/etf/GLD_5m_2yr.csv", 0.01),
    ("ES_15m", "data/ES_15m.csv", 0.25),
]

BASE_GRID = {
    "bias_min_score": [1.0, 2.0, 3.0],
    "min_confs": [1, 2, 3],
    "require_fvg_tap": [True, False],
    "accum_minutes": [15, 30, 60],
    "target_mode": ["pdh_pdl", "rr"],
    "hours": [(10,), (10, 14)],
}

FULL_EXTRA = {
    "min_rr": [1.5, 2.0, 3.0],
    "fvg_lookback": [12, 24, 48],
    "pm_big_day_range_atr": [0.5, 0.75, 1.0],
}

DEFAULTS = {
    "min_rr": 2.0,
    "fvg_lookback": 24,
    "pm_big_day_range_atr": 0.75,
    "min_stop_atr": 0.25,
}


def expand(full: bool) -> list[dict]:
    grid = dict(BASE_GRID)
    if full:
        grid.update(FULL_EXTRA)
    keys = list(grid)
    out = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        d = dict(DEFAULTS)
        d.update(dict(zip(keys, combo)))
        out.append(d)
    return out


def to_run_config(p: dict, cost: float) -> RunConfig:
    return RunConfig(
        bias=BiasConfig(min_score=p["bias_min_score"]),
        gate=GateConfig(
            trade_hours=p["hours"],
            pm_big_day_range_atr=p["pm_big_day_range_atr"],
        ),
        po3=PO3Config(
            accum_minutes=p["accum_minutes"],
            require_fvg_tap=p["require_fvg_tap"],
            fvg_lookback=p["fvg_lookback"],
            min_confs=p["min_confs"],
            min_rr=p["min_rr"],
            target_mode=p["target_mode"],
            cost_per_side=cost,
            min_stop_atr=p["min_stop_atr"],
        ),
    )


def _metrics(df: pd.DataFrame, prefix: str) -> dict:
    s = summarize(df)
    if s["trades"] == 0:
        return {f"{prefix}trades": 0, f"{prefix}total_R": 0.0,
                f"{prefix}avg_R": 0.0, f"{prefix}win_rate": 0.0}
    return {
        f"{prefix}trades": s["trades"],
        f"{prefix}total_R": s["total_R"],
        f"{prefix}avg_R": s["avg_R"],
        f"{prefix}win_rate": s["win_rate"],
    }


def _worker(task):
    label, path, cost, params_chunk = task
    bars = load_bars(path)
    session = PO3Session(bars)

    # 60/40 split on the calendar span, not on trade count.
    span = bars.index[-1] - bars.index[0]
    split = (bars.index[0] + span * 0.6).tz_convert("America/New_York").date()

    rows = []
    for p in params_chunk:
        trades, _ = session.run(to_run_config(p, cost))
        df = trades_frame(trades)

        row = {"dataset": label, **{k: (",".join(map(str, v)) if isinstance(v, tuple) else v)
                                    for k, v in p.items()}}
        row.update(_metrics(df, ""))
        if df.empty:
            row.update(_metrics(df, "is_"))
            row.update(_metrics(df, "oos_"))
        else:
            d = pd.to_datetime(df["ny_date"]).dt.date
            row.update(_metrics(df[d <= split], "is_"))
            row.update(_metrics(df[d > split], "oos_"))
        row["split_date"] = str(split)
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true", help="wider grid")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--out", default="results/po3_sweep.csv")
    ap.add_argument("--min-trades", type=int, default=20,
                    help="ignore configs with fewer trades when ranking")
    a = ap.parse_args()

    params = expand(a.full)
    datasets = [(lbl, p, c) for lbl, p, c in DATASETS if Path(p).exists()]
    if not datasets:
        print("no datasets found", file=sys.stderr)
        return 1

    # One task per (dataset, chunk) so each worker builds its session once.
    chunks = max(1, a.jobs // len(datasets)) if a.jobs >= len(datasets) else 1
    size = max(1, len(params) // chunks)
    tasks = [
        (lbl, path, cost, params[i : i + size])
        for lbl, path, cost in datasets
        for i in range(0, len(params), size)
    ]

    print(f"{len(params)} configs x {len(datasets)} datasets = "
          f"{len(params) * len(datasets)} runs in {len(tasks)} tasks "
          f"on {a.jobs} workers", flush=True)

    rows = []
    with Pool(a.jobs) as pool:
        for i, res in enumerate(pool.imap_unordered(_worker, tasks), 1):
            rows.extend(res)
            print(f"  task {i}/{len(tasks)} done ({len(rows)} rows)", flush=True)

    df = pd.DataFrame(rows)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nwrote {len(df)} rows → {out}")

    ranked = df[df["trades"] >= a.min_trades].copy()
    if ranked.empty:
        print(f"\nno config reached {a.min_trades} trades")
        return 0

    show = ["dataset", "hours", "bias_min_score", "min_confs", "require_fvg_tap",
            "accum_minutes", "target_mode", "trades", "win_rate", "total_R",
            "avg_R", "is_total_R", "oos_trades", "oos_total_R", "oos_avg_R"]

    print("\n── top 15 by out-of-sample total R ──")
    print(ranked.sort_values("oos_total_R", ascending=False).head(15)[show].to_string(index=False))

    print("\n── best per dataset (out-of-sample total R) ──")
    best = ranked.loc[ranked.groupby("dataset")["oos_total_R"].idxmax()]
    print(best[show].to_string(index=False))

    print("\n── configs positive in BOTH halves ──")
    both = ranked[(ranked["is_total_R"] > 0) & (ranked["oos_total_R"] > 0)]
    if both.empty:
        print("  none")
    else:
        print(both.sort_values("total_R", ascending=False).head(15)[show].to_string(index=False))

    # The ranking that actually matters. A config that tops one instrument is
    # usually just fitted to it; one that holds up across all four, in both
    # halves, is the only kind worth trading.
    print("\n── most robust across instruments ──")
    keys = [k for k in BASE_GRID if k in df.columns] + ["min_stop_atr"]
    agg = df.groupby(keys, dropna=False).agg(
        datasets=("dataset", "nunique"),
        trades=("trades", "sum"),
        total_R=("total_R", "sum"),
        avg_R=("avg_R", "mean"),
        is_R=("is_total_R", "sum"),
        oos_R=("oos_total_R", "sum"),
        n_pos_oos=("oos_total_R", lambda s: int((s > 0).sum())),
        worst_ds_R=("total_R", "min"),
    ).reset_index()
    agg = agg[(agg["trades"] >= a.min_trades * 2) & (agg["is_R"] > 0) & (agg["oos_R"] > 0)]
    if agg.empty:
        print("  no config is positive in both halves across the pooled datasets")
    else:
        agg = agg.sort_values(["n_pos_oos", "oos_R"], ascending=False)
        print(agg.head(15).round(2).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
