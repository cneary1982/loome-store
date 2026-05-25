"""Entry/exit filters for the breakout backtest.

Three components:
  1. Session filter (ES/NQ RTH; GC 3 killzones; HTFs unrestricted)
  2. Force-flat at 16:00 ET for ES/NQ intraday
  3. Multi-timeframe trend alignment using HTF EMA20 + slope

All times in the data are assumed tz-aware UTC. Conversions to America/New_York
go through zoneinfo so DST is handled correctly.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo
import pandas as pd

NY = ZoneInfo("America/New_York")

# Which HTFs gate which entry TF. 1d has no gate (it IS the HTF).
BIAS_TFS = {
    "15m": ["1h", "4h"],
    "1h":  ["4h", "1d"],
    "4h":  ["1d"],
    "1d":  [],
}

EMA_SPAN  = 20
SLOPE_LAG = 3   # bars used to measure EMA slope


# ─── Session windows ────────────────────────────────────────────────────────
def _ny_minutes(ts) -> tuple[int, int]:
    """(weekday, minute-of-day in NY tz)."""
    ny = ts.tz_convert(NY)
    return ny.weekday(), ny.hour * 60 + ny.minute


def in_esnq_entry_window(ts) -> bool:
    """ES/NQ: 09:30 ≤ t < 15:30 ET, Mon–Fri."""
    wd, m = _ny_minutes(ts)
    if wd >= 5:
        return False
    return 9 * 60 + 30 <= m < 15 * 60 + 30


def esnq_force_flat(ts) -> bool:
    """True once we've reached 16:00 ET (or weekend) — close any open position."""
    wd, m = _ny_minutes(ts)
    if wd >= 5:
        return True
    return m >= 16 * 60


def in_gc_killzone(ts) -> bool:
    """GC: London 02–05, NY AM 08–11, Asia 20–23 ET. No Sat. Skip Sun (Asia reopen noise)."""
    wd, m = _ny_minutes(ts)
    if wd == 5:                        # Saturday: market closed
        return False
    if wd == 6 and m < 18 * 60:        # Sunday before 18:00 ET reopen
        return False
    return (
        (2  * 60 <= m < 5  * 60) or    # London
        (8  * 60 <= m < 11 * 60) or    # NY AM
        (20 * 60 <= m < 23 * 60)       # Asia
    )


def session_entry_ok(sym: str, tf: str, ts) -> bool:
    if tf in ("4h", "1d"):
        return True
    if sym in ("ES", "NQ"):
        return in_esnq_entry_window(ts)
    if sym == "GC":
        return in_gc_killzone(ts)
    return True


def session_force_flat(sym: str, tf: str, ts) -> bool:
    if tf in ("4h", "1d"):
        return False
    if sym in ("ES", "NQ"):
        return esnq_force_flat(ts)
    return False                       # GC runs 24h, no forced exit


# ─── MTF trend alignment ────────────────────────────────────────────────────
def _bias_series(df: pd.DataFrame) -> pd.Series:
    """+1 / -1 / 0 trend bias from close vs EMA20 plus slope. Shifted by 1 bar
    so callers see only fully-closed HTF bars (no lookahead)."""
    ema = df["Close"].ewm(span=EMA_SPAN, adjust=False).mean()
    slope_up = ema > ema.shift(SLOPE_LAG)
    bias = pd.Series(0, index=df.index, dtype="int8")
    bias[(df["Close"] > ema) &  slope_up] = 1
    bias[(df["Close"] < ema) & ~slope_up] = -1
    return bias.shift(1)


def build_bias_map(data: dict) -> dict:
    """{(sym, tf) → shifted bias series} for every HTF in BIAS_TFS."""
    out = {}
    for (sym, tf), df in data.items():
        if tf in ("1h", "4h", "1d"):
            out[(sym, tf)] = _bias_series(df)
    return out


def aligned(sym: str, entry_tf: str, side: str, ts, bias_map: dict) -> bool:
    """True if every HTF above entry_tf agrees with `side` ('long'/'short')."""
    want = 1 if side == "long" else -1
    for htf in BIAS_TFS[entry_tf]:
        s = bias_map.get((sym, htf))
        if s is None:                  # HTF data missing → fail safe
            return False
        v = s.asof(ts)
        if pd.isna(v) or int(v) != want:
            return False
    return True
