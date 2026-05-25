"""Generic backtester — runs any `Strategy` subclass against historical bars.

Unlike backtest.py (which has the regime breakout logic baked in), this walker
just calls `strategy.signal(bars_so_far, now)` on each closed bar and simulates
TP/SL exits using whatever the signal returned.

Usage:
    from strategies_lib import MACDTrendStack
    from backtest_generic import backtest_strategy

    s = MACDTrendStack(name="x", symbol="QQQ", timeframe="60m")
    summary = backtest_strategy(s, df_qqq_60m, warmup=300)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from orchestrator import Strategy


@dataclass
class GenericTrade:
    entry_time:  pd.Timestamp
    side:        str
    entry_price: float
    exit_time:   pd.Timestamp
    exit_price:  float
    r_multiple:  float


def backtest_strategy(strategy: Strategy, df: pd.DataFrame,
                      warmup: int = 250, window: int = 500) -> dict:
    """Walk closed bars; on each, call strategy.signal(); simulate exits.

    `window`: only the last `window` bars are passed to signal(). This matches
    how live trading works (broker fetches a bounded window) and keeps the
    backtester O(n) instead of O(n²) when strategies re-derive state each call.
    """
    if len(df) <= warmup + 2:
        return _empty()
    h = df["High"].values.astype(float)
    l = df["Low"].values.astype(float)
    o = df["Open"].values.astype(float)
    trades: list[GenericTrade] = []
    i = warmup
    while i < len(df) - 1:
        start = max(0, i + 1 - window)
        view = df.iloc[start: i + 1]
        sig  = strategy.signal(view, view.index[-1])
        if sig is None:
            i += 1
            continue
        entry = sig.entry_estimate
        if sig.side == "long":
            tp = entry + sig.tp_distance
            sl = entry - sig.sl_distance
        else:
            tp = entry - sig.tp_distance
            sl = entry + sig.sl_distance
        # Walk forward bars looking for TP or SL hit
        exit_idx = None
        exit_px  = None
        r        = None
        for j in range(i + 1, len(df)):
            hj, lj = h[j], l[j]
            if sig.side == "long":
                if hj >= tp:
                    exit_idx = j; exit_px = tp; r = +sig.tp_distance / sig.sl_distance; break
                if lj <= sl:
                    exit_idx = j; exit_px = sl; r = -1.0; break
            else:
                if lj <= tp:
                    exit_idx = j; exit_px = tp; r = +sig.tp_distance / sig.sl_distance; break
                if hj >= sl:
                    exit_idx = j; exit_px = sl; r = -1.0; break
        if exit_idx is None:
            # Open at end of series — discard
            break
        trades.append(GenericTrade(
            entry_time=df.index[i], side=sig.side, entry_price=entry,
            exit_time=df.index[exit_idx], exit_price=exit_px, r_multiple=r))
        # Don't allow overlapping trades — resume after exit
        i = exit_idx + 1
    return _summarize(trades)


def _empty() -> dict:
    return {"trades": 0, "win_rate": 0.0, "expectancy": 0.0, "total_R": 0.0,
            "rows": []}


def _summarize(trades: list[GenericTrade]) -> dict:
    if not trades:
        return _empty()
    rs = np.array([t.r_multiple for t in trades])
    wins = int((rs > 0).sum())
    return {
        "trades":     len(trades),
        "win_rate":   round(wins / len(trades) * 100, 1),
        "expectancy": round(float(rs.mean()), 3),
        "total_R":    round(float(rs.sum()), 2),
        "rows":       [t.__dict__ for t in trades],
    }
