"""Backtest the Holy Grail strategies only — fast validation run.

Runs ConnorsRSI2 (15m) and OpeningRangeBreakout (5m) across SPY/QQQ/GLD.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from backtest import load_csv, resample
from backtest_generic import backtest_strategy
from strategies_lib import ConnorsRSI2, OpeningRangeBreakout

DATA = Path("data/etf")


def load_etf(sym: str, tf: str) -> pd.DataFrame:
    df = load_csv(DATA / f"{sym}_5m_2yr.csv")
    rules = {"5m": None, "15m": "15min"}
    rule = rules[tf]
    return resample(df, rule) if rule else df


CONFIGS = [
    (ConnorsRSI2,          dict(),                                     "SPY", "15m", 100),
    (ConnorsRSI2,          dict(),                                     "QQQ", "15m", 100),
    (ConnorsRSI2,          dict(),                                     "GLD", "15m", 100),
    (OpeningRangeBreakout, dict(range_minutes=30, tp_mult_range=1.5),  "SPY", "5m",  100),
    (OpeningRangeBreakout, dict(range_minutes=30, tp_mult_range=1.5),  "QQQ", "5m",  100),
    (OpeningRangeBreakout, dict(range_minutes=30, tp_mult_range=1.5),  "GLD", "5m",  100),
]


def main():
    print("=" * 70)
    print("  HOLY GRAIL BACKTEST -- ConnorsRSI2 + OpeningRangeBreakout")
    print("=" * 70)
    print()
    hdr = "%-22s %3s %4s %4s %5s %6s %7s  %s" % (
        "strategy", "sym", "tf", "N", "WR", "Exp", "TotR", "time")
    print(hdr)
    print("-" * 70)

    total_r = 0.0
    total_trades = 0
    results = []

    for cls, kw, sym, tf, warmup in CONFIGS:
        df = load_etf(sym, tf)
        s = cls(name="%s_%s_%s" % (cls.__name__, sym, tf),
                symbol=sym, timeframe=tf, **kw)
        t0 = time.time()
        r = backtest_strategy(s, df, warmup=warmup)
        dt = time.time() - t0
        print("%-22s %3s %4s %4d %5.1f %+6.3f %+7.2f  %4.1fs" % (
            cls.__name__, sym, tf, r["trades"], r["win_rate"],
            r["expectancy"], r["total_R"], dt))
        total_r += r["total_R"]
        total_trades += r["trades"]
        results.append({
            "strategy": cls.__name__, "symbol": sym, "timeframe": tf,
            "trades": r["trades"], "win_rate": r["win_rate"],
            "expectancy": r["expectancy"], "total_R": r["total_R"],
        })

    print("-" * 70)
    avg_exp = total_r / max(total_trades, 1)
    print("%-22s %3s %4s %4d %5s %+6.3f %+7.2f" % (
        "TOTAL", "", "", total_trades, "", avg_exp, total_r))
    print()
    print("  %d trades | %+.1fR combined | %+.3f expectancy per trade" % (
        total_trades, total_r, avg_exp))

    out_dir = Path("results"); out_dir.mkdir(exist_ok=True)
    pd.DataFrame(results).to_csv(out_dir / "holy_grail_backtest.csv", index=False)
    print()
    print("  Wrote results/holy_grail_backtest.csv")


if __name__ == "__main__":
    main()
