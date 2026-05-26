"""Backtest every strategy in strategies_lib.py against local ETF bars.

Strategies are mapped to Tradier-tradable ETFs (the live broker can only
trade equities/ETFs, so futures-only setups in Pine map to their ETF
proxies: NQ→QQQ, GC→GLD, ES→SPY).

Resamples the 5m ETF data to each strategy's native timeframe.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from backtest import load_csv, resample
from backtest_generic import backtest_strategy
from strategies_lib import (
    BigJohnson, InverseFVG, ICTFVGSessionTap, MACDTrendStack,
    FiveBarPullback, BBSqueeze, ConnorsRSI2, NearysIFVG,
)

DATA = Path("data/etf")
RESAMPLE = {"5m": None, "15m": "15min", "1h": "60min", "4h": "240min", "1d": "1D"}


def load_etf(sym: str, tf: str) -> pd.DataFrame:
    df = load_csv(DATA / f"{sym}_5m_2yr.csv")
    rule = RESAMPLE[tf]
    return resample(df, rule) if rule else df


CONFIGS = [
    # (Strategy class, kwargs, symbol, timeframe, warmup)
    (MACDTrendStack,    dict(),                                            "QQQ", "1h",  300),
    (MACDTrendStack,    dict(),                                            "GLD", "4h",  300),
    (MACDTrendStack,    dict(),                                            "SPY", "1d",  300),
    (BBSqueeze,         dict(),                                            "QQQ", "1h",  100),
    (BBSqueeze,         dict(),                                            "SPY", "1h",  100),
    (FiveBarPullback,   dict(),                                            "QQQ", "15m", 100),
    (FiveBarPullback,   dict(),                                            "SPY", "15m", 100),
    (BigJohnson,        dict(sessions=("ny",)),                            "GLD", "5m",  100),
    (BigJohnson,        dict(sessions=("ny",)),                            "QQQ", "5m",  100),
    (InverseFVG,        dict(tick_size=0.01, min_gap_ticks=10),            "GLD", "5m",  150),
    (InverseFVG,        dict(tick_size=0.01, min_gap_ticks=10),            "QQQ", "5m",  150),
    (ICTFVGSessionTap,  dict(session_start_h=9.5,  session_end_h=11.5,
                             htf="60"),                                    "QQQ", "5m",  300),
    (ICTFVGSessionTap,  dict(session_start_h=2.0,  session_end_h=5.0,
                             htf="240"),                                   "GLD", "5m",  300),
    (ConnorsRSI2,       dict(),                                            "SPY", "15m", 100),
    (ConnorsRSI2,       dict(),                                            "QQQ", "15m", 100),
    (ConnorsRSI2,       dict(),                                            "GLD", "15m", 100),
    (NearysIFVG,        dict(),                                            "QQQ", "5m",  150),
    (NearysIFVG,        dict(),                                            "GLD", "5m",  150),
]


def main():
    results = []
    print(f"{'strategy':<22} {'sym':>3} {'tf':>4} {'N':>4} {'WR':>5} {'Exp':>6} {'TotR':>7}  time")
    print("─" * 70)
    for cls, kw, sym, tf, warmup in CONFIGS:
        try:
            df = load_etf(sym, tf)
        except FileNotFoundError:
            print(f"{cls.__name__:<22} {sym:>3} {tf:>4}  -- missing data --")
            continue
        s = cls(name=f"{cls.__name__}_{sym}_{tf}", symbol=sym, timeframe=tf, **kw)
        t0 = time.time()
        r = backtest_strategy(s, df, warmup=warmup)
        dt = time.time() - t0
        print(f"{cls.__name__:<22} {sym:>3} {tf:>4} {r['trades']:>4} "
              f"{r['win_rate']:>5.1f} {r['expectancy']:>+6.3f} "
              f"{r['total_R']:>+7.2f}  {dt:>4.1f}s")
        results.append({
            "strategy": cls.__name__, "symbol": sym, "timeframe": tf,
            "trades": r["trades"], "win_rate": r["win_rate"],
            "expectancy": r["expectancy"], "total_R": r["total_R"],
        })
    out_dir = Path("results"); out_dir.mkdir(exist_ok=True)
    pd.DataFrame(results).to_csv(out_dir / "strategies_lib_summary.csv", index=False)
    print(f"\nWrote results/strategies_lib_summary.csv")


if __name__ == "__main__":
    main()
