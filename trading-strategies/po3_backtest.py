#!/usr/bin/env python3
"""PO3 backtest — the 10:00 / 14:00 ET 4H candle open model.

Usage:
    python po3_backtest.py                              # every dataset, defaults
    python po3_backtest.py --data data/etf/QQQ_5m_2yr.csv
    python po3_backtest.py --min-confs 3 --trim-frac 0.8
    python po3_backtest.py --hours 10                   # AM window only
    python po3_backtest.py --blackout news_dates.txt    # CPI/FOMC blackouts
    python po3_backtest.py --csv results/po3_trades.csv

Data must be OHLCV bars at the entry timeframe (1–5m is what the model is built
for; 15m works but is coarse). See `data/README.md` for the accepted schemas.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

from po3 import (
    BiasConfig,
    GateConfig,
    PO3Config,
    RunConfig,
    format_report,
    load_bars,
    load_blackout_dates,
    run_backtest,
    skips_frame,
    summarize,
    trades_frame,
)

# 5m ETF proxies are the default: they are the only series in `data/` fine
# enough to resolve accumulation → manipulation → three confirmations inside a
# single 4H window. ES 15m is included as a futures cross-check.
# Third field is the per-side execution cost in price units.
DEFAULT_DATASETS = [
    ("QQQ 5m (NQ proxy)", "data/etf/QQQ_5m_2yr.csv", 0.01),
    ("SPY 5m (ES proxy)", "data/etf/SPY_5m_2yr.csv", 0.01),
    ("GLD 5m (GC proxy)", "data/etf/GLD_5m_2yr.csv", 0.01),
    ("ES 15m (futures)", "data/ES_15m.csv", 0.25),
]

# Two starting points.
#   bible  — the model exactly as the PO3 Bible states it: at least 2 of the 3
#            confirmations, previous day's high/low as the draw, >= 1:2.
#   robust — the only region of the grid that stayed positive out-of-sample on
#            all four instruments: all three confirmations, a fixed 3R target.
#            See results/po3_findings.md for why.
PRESETS = {
    "bible": {},
    "robust": {
        "bias_min_score": 2.0,
        "min_confs": 3,
        "accum_minutes": 30,
        "fvg_lookback": 24,
        "target_mode": "rr",
        "rr_target": 3.0,
        "hours": "10",
    },
}


def build_cfg(a: argparse.Namespace) -> RunConfig:
    blackout = load_blackout_dates(a.blackout)
    return RunConfig(
        bias=BiasConfig(
            min_score=a.bias_min_score,
            structure_tfs=tuple(a.structure_tfs.split(",")),
            pd_tfs=tuple(a.pd_tfs.split(",")),
        ),
        gate=GateConfig(
            trade_hours=tuple(int(h) for h in a.hours.split(",")),
            skip_dows=tuple(int(d) for d in a.skip_dows.split(",")) if a.skip_dows else (),
            blackout_dates=blackout,
            am_max_on_range_atr=a.am_max_on_range_atr,
            am_max_gap_atr=a.am_max_gap_atr,
            pm_require_big_day=not a.pm_no_big_day,
            pm_big_day_range_atr=a.pm_big_day_range_atr,
            pm_only_if_am_flat=not a.pm_allow_after_am,
            max_trades_per_day=a.max_trades_per_day,
        ),
        po3=PO3Config(
            accum_minutes=a.accum_minutes,
            require_fvg_tap=not a.no_fvg_tap,
            fvg_tf=a.fvg_tf,
            fvg_lookback=a.fvg_lookback,
            min_confs=a.min_confs,
            stop_buf_atr=a.stop_buf_atr,
            min_rr=a.min_rr,
            target_mode=a.target_mode,
            rr_target=a.rr_target,
            trim_frac=a.trim_frac,
            trim_r=a.trim_r,
            cost_per_side=a.cost_per_side,
            min_stop_atr=a.min_stop_atr,
        ),
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--preset", choices=sorted(PRESETS), default="bible",
                   help="'bible' = the model as written; 'robust' = the "
                        "sweep-validated config (see results/po3_findings.md)")
    p.add_argument("--data", action="append", help="CSV path (repeatable)")
    p.add_argument("--csv", help="write the trade log here")

    g = p.add_argument_group("bias")
    g.add_argument("--bias-min-score", type=float, default=2.0)
    g.add_argument("--structure-tfs", default="1h,4h")
    g.add_argument("--pd-tfs", default="1h,4h")

    g = p.add_argument_group("gate")
    g.add_argument("--hours", default="10,14", help="4H opens to trade")
    g.add_argument("--skip-dows", default="", help="e.g. 0 to skip Mondays")
    g.add_argument("--blackout", help="file of CPI/FOMC dates to block")
    g.add_argument("--am-max-on-range-atr", type=float, default=1.50)
    g.add_argument("--am-max-gap-atr", type=float, default=1.25)
    g.add_argument("--pm-big-day-range-atr", type=float, default=0.75)
    g.add_argument("--pm-no-big-day", action="store_true",
                   help="stop requiring a big day for the 14:00 window")
    g.add_argument("--pm-allow-after-am", action="store_true",
                   help="allow 14:00 even when 10:00 already traded")
    g.add_argument("--max-trades-per-day", type=int, default=1)

    g = p.add_argument_group("entry model")
    g.add_argument("--accum-minutes", type=int, default=30)
    g.add_argument("--no-fvg-tap", action="store_true",
                   help="don't require the sweep to tap a recent 15m FVG")
    g.add_argument("--fvg-tf", default="15min")
    g.add_argument("--fvg-lookback", type=int, default=12)
    g.add_argument("--min-confs", type=int, default=2, choices=[1, 2, 3])
    g.add_argument("--stop-buf-atr", type=float, default=0.10)
    g.add_argument("--min-rr", type=float, default=2.0)
    g.add_argument("--target-mode", default="pdh_pdl", choices=["pdh_pdl", "rr"])
    g.add_argument("--rr-target", type=float, default=3.0)
    g.add_argument("--trim-frac", type=float, default=0.0,
                   help="fraction trimmed at --trim-r (Bible uses 0.8)")
    g.add_argument("--trim-r", type=float, default=2.0)

    g = p.add_argument_group("execution reality")
    g.add_argument("--cost-per-side", type=float, default=0.0,
                   help="slippage+commission per side in PRICE units "
                        "(ETFs ~0.01; ES/NQ ~0.25 = 1 tick)")
    g.add_argument("--min-stop-atr", type=float, default=0.25,
                   help="refuse setups whose stop is tighter than this xATR")

    a = p.parse_args()

    # A preset only fills in options the caller did not pass explicitly.
    given = {arg.lstrip("-").replace("-", "_") for arg in sys.argv[1:] if arg.startswith("--")}
    for k, v in PRESETS[a.preset].items():
        if k not in given:
            setattr(a, k, v)

    cfg = build_cfg(a)

    datasets = (
        [(Path(d).stem, d, a.cost_per_side) for d in a.data]
        if a.data
        else DEFAULT_DATASETS
    )

    all_trades = []
    any_data = False

    for label, path, default_cost in datasets:
        fp = Path(path)
        if not fp.exists():
            print(f"skip {label}: {path} not found", file=sys.stderr)
            continue
        any_data = True

        # Per-dataset cost unless the caller overrode it.
        run_cfg = cfg
        if "cost_per_side" not in given:
            run_cfg = replace(cfg, po3=replace(cfg.po3, cost_per_side=default_cost))

        bars = load_bars(fp)
        trades, skips = run_backtest(bars, run_cfg)
        tdf, sdf = trades_frame(trades), skips_frame(skips)

        span = f"{bars.index[0].date()} → {bars.index[-1].date()}  ({len(bars):,} bars)"
        print(format_report(tdf, sdf, f"{label}   {span}"))

        if not tdf.empty:
            tdf = tdf.copy()
            tdf.insert(0, "dataset", label)
            all_trades.append(tdf)

    if not any_data:
        print("no datasets found — pass --data", file=sys.stderr)
        return 1

    if all_trades:
        combined = pd.concat(all_trades, ignore_index=True)
        print(f"\n{'=' * 68}\n  COMBINED   (preset: {a.preset})\n{'=' * 68}")
        for k, v in summarize(combined).items():
            print(f"  {k:<20} {v}")
        if a.csv:
            out = Path(a.csv)
            out.parent.mkdir(parents=True, exist_ok=True)
            combined.to_csv(out, index=False)
            print(f"\n  trade log → {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
