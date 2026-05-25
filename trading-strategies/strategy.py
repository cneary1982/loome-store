"""Signal logic exposed for streaming and the dashboard.

The same regime-flip + ATR exit logic from backtest.py, but factored so the
dashboard and the live monitor can call it bar-by-bar and get back a list
of trades with full entry/exit details (not just summary stats).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import filters as F
from backtest import ATR_LEN, atr, label


@dataclass
class Trade:
    entry_time:  pd.Timestamp
    side:        str          # 'long' or 'short'
    entry_price: float
    exit_time:   pd.Timestamp
    exit_price:  float
    r_multiple:  float        # +1 R = take-profit hit, -1 R = stop hit, fractional = forced exit
    atr_at_entry: float
    forced:      bool = False


def run_strategy(
    df: pd.DataFrame,
    lookback:        int,
    threshold:       float,
    atr_mult:        float,
    symbol:          str   = "",
    timeframe:       str   = "",
    trend_filter_on: bool  = False,
    session_window:  str   = "all_hours",
    session_windows: list  = None,        # explicit window list overrides session_window code
    bias_map:        dict  = None,        # for trend_filter; if None and trend_filter_on, computed here
) -> list[Trade]:
    """Walk the bars and emit Trade objects.

    The session window can be passed either as a preset name (looked up in
    SESSION_WINDOW_PRESETS) or directly as `session_windows`. See
    sweep_all.SESSION_PRESETS for available preset names.
    """
    times  = df.index
    open_a = df["Open"].values.astype(float)
    close  = df["Close"].values.astype(float)
    high   = df["High"].values.astype(float)
    low    = df["Low"].values.astype(float)
    atr_a  = atr(df["High"], df["Low"], df["Close"]).values.astype(float)
    labels = label(df["Close"], lookback, threshold)
    offset = len(close) - len(labels)
    lab    = labels.values.astype(int)

    if trend_filter_on and bias_map is None:
        # Build a single-symbol bias map for the higher TFs we have in `df`'s frequency
        # context. In practice the dashboard passes one in via load_dataset.
        bias_map = {}

    sess_windows = session_windows
    force_flat   = (session_window == "us_market_hours" and symbol in ("ES", "NQ"))

    trades: list[Trade] = []
    skip_until = 0
    for k in range(1, len(lab)):
        pos = k + offset
        if pos < skip_until:
            continue
        prev_r, curr_r = lab[k - 1], lab[k]
        if prev_r == curr_r or curr_r == 1:
            continue
        a = atr_a[pos]
        if np.isnan(a) or a == 0:
            continue
        ts   = times[pos]
        long = curr_r == 2
        side = "long" if long else "short"

        # Session window gate
        if sess_windows is not None and not _in_any_window(ts, sess_windows):
            continue

        # HTF trend filter
        if trend_filter_on and bias_map:
            if not F.aligned(symbol, timeframe, side, ts, bias_map):
                continue

        entry = close[pos]
        tp = entry + atr_mult * a if long else entry - atr_mult * a
        sl = entry - atr_mult * a if long else entry + atr_mult * a

        for j in range(pos + 1, len(close)):
            if force_flat and F.esnq_force_flat(times[j]):
                exit_px = open_a[j]
                r = (exit_px - entry) / (atr_mult * a) * (1.0 if long else -1.0)
                trades.append(Trade(ts, side, entry, times[j], exit_px, r, a, forced=True))
                skip_until = j + 1
                break
            h, l = high[j], low[j]
            if long:
                if h >= tp:
                    trades.append(Trade(ts, side, entry, times[j], tp, +1.0, a))
                    skip_until = j + 1; break
                if l <= sl:
                    trades.append(Trade(ts, side, entry, times[j], sl, -1.0, a))
                    skip_until = j + 1; break
            else:
                if l <= tp:
                    trades.append(Trade(ts, side, entry, times[j], tp, +1.0, a))
                    skip_until = j + 1; break
                if h >= sl:
                    trades.append(Trade(ts, side, entry, times[j], sl, -1.0, a))
                    skip_until = j + 1; break

    return trades


def _in_any_window(ts, windows) -> bool:
    """ts is tz-aware UTC; windows are list of (start_min, end_min) in NY-tz minutes."""
    ny = ts.tz_convert(F.NY)
    wd = ny.weekday()
    m  = ny.hour * 60 + ny.minute
    if wd == 5:                                   # Saturday
        return False
    if wd == 6 and m < 18 * 60:                   # Sunday before 18:00 ET reopen
        return False
    return any(start <= m < end for start, end in windows)


def trades_to_dataframe(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=[
            "entry_time", "side", "entry_price",
            "exit_time", "exit_price", "r_multiple", "forced"
        ])
    return pd.DataFrame([t.__dict__ for t in trades])


def summary(trades: list[Trade]) -> dict:
    if not trades:
        return {"trades": 0, "win_rate": 0.0, "expectancy": 0.0, "total_R": 0.0}
    rs = np.array([t.r_multiple for t in trades])
    wins = int((rs > 0).sum())
    return {
        "trades":     len(trades),
        "win_rate":   round(wins / len(trades) * 100, 1),
        "expectancy": round(rs.mean(), 3),
        "total_R":    round(rs.sum(), 2),
    }
