"""Library of Strategy ports from Pine Script.

Each strategy is a faithful port of a TradingView Pine script. They all
share the same `signal(bars, now_utc) -> Optional[StrategySignal]` contract
defined in `orchestrator.Strategy`, so the orchestrator can run all of them
in parallel and the per-symbol lock decides which one actually trades.

Ports included:
  S01   Connors RSI(2)       Mean-reversion: RSI(2) extreme + SMA50 trend
  S07   Nearys IFVG MTF      Daily bias filter + FVG/IFVG midline entry
  S08   Big Johnson 4.0      RSI exhaustion + MACD cross + ADX filter
  S09   IFVG Inverse FVG     3-candle gap detection → inversion → close-inside
  S10   ICT FVG Midline Tap  Track 1H/4H FVGs, fire on midline tap in session
  S11   MACD × 200 SMA       MACD hist zero-cross with triple trend stack
  T5    5-Bar Trend Pullback 5 consec trend bars, 1-2 counter, then resumption
  T6    BB Squeeze + EMA50   20-bar BB width minimum, then expansion + EMA bias

All strategies emit `StrategySignal(side, entry_estimate, atr_at_signal,
tp_distance, sl_distance, bar_ts)`. The orchestrator handles position
sizing (vol-targeted via shares_for_risk), per-symbol locking, and the
global 9:30-13:00 ET entry window with 16:00 ET EOD flat.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from orchestrator import Strategy, StrategySignal


# ─── Indicator helpers (no external deps beyond pandas/numpy) ───────────────
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _atr(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14) -> pd.Series:
    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(c: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9):
    m = _ema(c, fast) - _ema(c, slow)
    s = _ema(m, sig)
    return m, s, m - s


def _adx(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14) -> pd.Series:
    up   = h.diff()
    down = -l.diff()
    plus_dm  = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.rolling(n).mean()
    plus_di  = 100 * pd.Series(plus_dm,  index=h.index).rolling(n).mean() / atr_
    minus_di = 100 * pd.Series(minus_dm, index=h.index).rolling(n).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(n).mean()


def _bb(c: pd.Series, n: int = 20, k: float = 2.0):
    m = c.rolling(n).mean()
    sd = c.rolling(n).std(ddof=0)
    return m + k * sd, m, m - k * sd


def _ny_time(ts: pd.Timestamp):
    ny = ts.tz_convert("America/New_York")
    return ny.hour + ny.minute / 60.0, ny.weekday()


# ─── S08 — Big Johnson 4.0 ──────────────────────────────────────────────────
class BigJohnson(Strategy):
    """Session-aware RSI + MACD + ADX exhaustion reversal.

    Long: MACD crosses up AND RSI was ≤ rsi_long in last `lookback` bars
          AND ADX ≥ threshold AND in trading session.
    Short: mirrored.
    """
    def __init__(self, name, symbol, timeframe,
                 rsi_len=14, rsi_long=25, rsi_short=75,
                 macd_fast=12, macd_slow=26, macd_signal=9,
                 adx_len=7, adx_threshold=25.0,
                 lookback_bars=5, atr_len=14, sl_mult=1.5, tp_mult=2.0,
                 sessions=("asia", "ny")):
        super().__init__(name, symbol, timeframe)
        self.p = dict(rsi_len=rsi_len, rsi_long=rsi_long, rsi_short=rsi_short,
                      macd_fast=macd_fast, macd_slow=macd_slow, macd_signal=macd_signal,
                      adx_len=adx_len, adx_threshold=adx_threshold,
                      lookback_bars=lookback_bars, atr_len=atr_len,
                      sl_mult=sl_mult, tp_mult=tp_mult, sessions=sessions)

    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp) -> Optional[StrategySignal]:
        p = self.p
        need = max(p["macd_slow"] + p["macd_signal"], p["adx_len"] * 2, p["lookback_bars"] + 5)
        if len(bars) < need:
            return None
        c, h, l = bars["Close"], bars["High"], bars["Low"]
        rsi  = _rsi(c, p["rsi_len"])
        macd, sig, _ = _macd(c, p["macd_fast"], p["macd_slow"], p["macd_signal"])
        adx  = _adx(h, l, c, p["adx_len"])
        atr_ = _atr(h, l, c, p["atr_len"])
        i = -1
        a = float(atr_.iloc[i])
        if not np.isfinite(a) or a <= 0 or not np.isfinite(adx.iloc[i]):
            return None
        if adx.iloc[i] < p["adx_threshold"]:
            return None
        # Session gate
        td, wd = _ny_time(bars.index[i])
        in_asia   = td >= 19.0 or td < 1.0
        in_london = 2.0 <= td < 8.0
        in_ny     = 6.0 <= td < 17.0
        ok = (("asia" in p["sessions"] and in_asia)
              or ("london" in p["sessions"] and in_london)
              or ("ny" in p["sessions"] and in_ny))
        if not ok or wd >= 5:
            return None
        # MACD crosses
        macd_up   = macd.iloc[i]   > sig.iloc[i]   and macd.iloc[i-1] <= sig.iloc[i-1]
        macd_down = macd.iloc[i]   < sig.iloc[i]   and macd.iloc[i-1] >= sig.iloc[i-1]
        # RSI lookback
        lookback = rsi.iloc[-p["lookback_bars"]:]
        rsi_at_low  = (lookback <= p["rsi_long"]).any()
        rsi_at_high = (lookback >= p["rsi_short"]).any()
        side = None
        if macd_up and rsi_at_low:
            side = "long"
        elif macd_down and rsi_at_high:
            side = "short"
        if side is None:
            return None
        return StrategySignal(side=side, entry_estimate=float(c.iloc[i]),
                              atr_at_signal=a,
                              tp_distance=p["tp_mult"] * a,
                              sl_distance=p["sl_mult"] * a,
                              bar_ts=str(bars.index[i]))


# ─── S09 — IFVG Inverse FVG ─────────────────────────────────────────────────
class InverseFVG(Strategy):
    """Detect 3-candle FVGs, watch for inversion, fire when next bar closes inside.

    Logic re-derives FVGs from history each call (O(N) per call where N = bars).
    """
    def __init__(self, name, symbol, timeframe,
                 min_gap_ticks=10, fvg_extend=50,
                 atr_len=14, sl_mult=1.5, tp_mult=2.0,
                 sessions=("ny",),  # NY open by default
                 tick_size=0.01):
        super().__init__(name, symbol, timeframe)
        self.p = dict(min_gap_ticks=min_gap_ticks, fvg_extend=fvg_extend,
                      atr_len=atr_len, sl_mult=sl_mult, tp_mult=tp_mult,
                      sessions=sessions, tick_size=tick_size)

    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp) -> Optional[StrategySignal]:
        p = self.p
        if len(bars) < max(p["atr_len"] + 5, p["fvg_extend"] + 5):
            return None
        h, l, c, o = bars["High"], bars["Low"], bars["Close"], bars["Open"]
        atr_ = _atr(h, l, c, p["atr_len"])
        i = len(bars) - 1
        a = float(atr_.iloc[i])
        if not np.isfinite(a) or a <= 0:
            return None
        td, wd = _ny_time(bars.index[i])
        in_ny    = 9.5 <= td < 11.5
        in_lon   = 2.0 <= td < 5.0
        in_asia  = td >= 20.0 or td < 0.5
        ok = (("ny" in p["sessions"] and in_ny)
              or ("london" in p["sessions"] and in_lon)
              or ("asia" in p["sessions"] and in_asia))
        if not ok or wd >= 5:
            return None
        # Build FVG zones from history (last ~fvg_extend+3 bars is enough)
        n = len(bars)
        start = max(2, n - p["fvg_extend"] - 5)
        min_gap = p["min_gap_ticks"] * p["tick_size"]
        # zones: list of dicts {dir, hi, lo, inverted, traded, created_idx}
        zones = []
        for k in range(start, n):
            # FVG up (bull): l[k] > h[k-2] and c[k-1] > h[k-2]
            if l.iloc[k] > h.iloc[k-2] and c.iloc[k-1] > h.iloc[k-2]:
                if (l.iloc[k] - h.iloc[k-2]) >= min_gap:
                    zones.append({"dir": 1, "hi": l.iloc[k], "lo": h.iloc[k-2],
                                  "inverted": False, "traded": False, "idx": k})
            # FVG down (bear)
            if h.iloc[k] < l.iloc[k-2] and c.iloc[k-1] < l.iloc[k-2]:
                if (l.iloc[k-2] - h.iloc[k]) >= min_gap:
                    zones.append({"dir": -1, "hi": l.iloc[k-2], "lo": h.iloc[k],
                                  "inverted": False, "traded": False, "idx": k})
        # Walk forward, mark inversions and find entry on last bar
        for k in range(2, n):
            ctop = max(o.iloc[k], c.iloc[k])
            cbot = min(o.iloc[k], c.iloc[k])
            for z in zones:
                if z["idx"] >= k or z["traded"]:
                    continue
                if k > z["idx"] + p["fvg_extend"]:
                    z["traded"] = True
                    continue
                if not z["inverted"]:
                    if z["dir"] == 1 and cbot < z["lo"]:
                        z["inverted"] = True; z["dir"] = -1
                    elif z["dir"] == -1 and ctop > z["hi"]:
                        z["inverted"] = True; z["dir"] = 1
        # Entry: last bar closes inside an inverted zone, not yet traded
        side = None
        last_close = float(c.iloc[i])
        for z in zones:
            if z["inverted"] and not z["traded"] and z["idx"] < i:
                if z["lo"] < last_close < z["hi"]:
                    side = "long" if z["dir"] == 1 else "short"
                    break
        if side is None:
            return None
        return StrategySignal(side=side, entry_estimate=last_close,
                              atr_at_signal=a,
                              tp_distance=p["tp_mult"] * a,
                              sl_distance=p["sl_mult"] * a,
                              bar_ts=str(bars.index[i]))


# ─── S10 — ICT FVG Session Midline Tap ──────────────────────────────────────
class ICTFVGSessionTap(Strategy):
    """Track 1H FVGs (from resampled bars), fire when price taps midline in window.

    Simplified port: one session window, 1H FVGs only. The Pine version has 3
    session/timeframe variants — we expose one cleanly here and register
    multiple instances in strategies.py for the other windows.
    """
    def __init__(self, name, symbol, timeframe,
                 session_start_h=20.0, session_end_h=21.0,   # default: Asia 8pm ET
                 htf="60",                                    # FVG TF in minutes
                 atr_len=14, sl_mult=0.5, tp_mult=2.0,
                 fvg_extend=120):
        super().__init__(name, symbol, timeframe)
        self.p = dict(session_start_h=session_start_h, session_end_h=session_end_h,
                      htf=htf, atr_len=atr_len, sl_mult=sl_mult, tp_mult=tp_mult,
                      fvg_extend=fvg_extend)

    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp) -> Optional[StrategySignal]:
        p = self.p
        if len(bars) < p["atr_len"] + 50:
            return None
        i = len(bars) - 1
        td, wd = _ny_time(bars.index[i])
        if wd >= 5 or not (p["session_start_h"] <= td < p["session_end_h"]):
            return None
        h, l, c, o = bars["High"], bars["Low"], bars["Close"], bars["Open"]
        atr_ = _atr(h, l, c, p["atr_len"])
        a = float(atr_.iloc[i])
        if not np.isfinite(a) or a <= 0:
            return None
        # Resample to HTF
        rule = f"{p['htf']}min"
        htf = bars.resample(rule).agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
        ).dropna()
        if len(htf) < 5:
            return None
        # Find latest unfilled 1H FVG
        bull = None; bear = None  # (hi, lo, mid, created_ts)
        for k in range(2, len(htf)):
            hk, lk, ck = htf["High"].iloc[k], htf["Low"].iloc[k], htf["Close"].iloc[k]
            if lk > htf["High"].iloc[k-2] and ck > htf["High"].iloc[k-2]:
                bull = (lk, htf["High"].iloc[k-2], (lk + htf["High"].iloc[k-2]) / 2, htf.index[k])
            if hk < htf["Low"].iloc[k-2] and ck < htf["Low"].iloc[k-2]:
                bear = (htf["Low"].iloc[k-2], hk, (htf["Low"].iloc[k-2] + hk) / 2, htf.index[k])
        # Invalidate if price has closed beyond the FVG since creation
        if bull is not None:
            tail = c.loc[bull[3]:]
            if (tail < bull[1]).any():
                bull = None
        if bear is not None:
            tail = c.loc[bear[3]:]
            if (tail > bear[0]).any():
                bear = None
        side = None
        last_low, last_high, last_close = float(l.iloc[i]), float(h.iloc[i]), float(c.iloc[i])
        if bull is not None and last_low <= bull[2] and bull[1] <= last_close <= bull[0]:
            side = "long"
        elif bear is not None and last_high >= bear[2] and bear[1] <= last_close <= bear[0]:
            side = "short"
        if side is None:
            return None
        return StrategySignal(side=side, entry_estimate=last_close,
                              atr_at_signal=a,
                              tp_distance=p["tp_mult"] * a,
                              sl_distance=p["sl_mult"] * a,
                              bar_ts=str(bars.index[i]))


# ─── S11 — MACD × 200 SMA Rivit ─────────────────────────────────────────────
class MACDTrendStack(Strategy):
    """MACD histogram zero-cross with triple trend stack.

    Long: hist crosses up through zero AND macd > 0 AND fast_sma > slow_sma
          AND close[slow] > sma200.
    """
    def __init__(self, name, symbol, timeframe,
                 fast_len=12, slow_len=26, signal_len=9, vslow_len=200,
                 atr_len=14, sl_mult=1.0, tp_mult=2.0):
        super().__init__(name, symbol, timeframe)
        self.p = dict(fast_len=fast_len, slow_len=slow_len, signal_len=signal_len,
                      vslow_len=vslow_len, atr_len=atr_len, sl_mult=sl_mult, tp_mult=tp_mult)

    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp) -> Optional[StrategySignal]:
        p = self.p
        if len(bars) < p["vslow_len"] + p["slow_len"] + 2:
            return None
        c, h, l = bars["Close"], bars["High"], bars["Low"]
        fast  = _sma(c, p["fast_len"])
        slow  = _sma(c, p["slow_len"])
        vslow = _sma(c, p["vslow_len"])
        macd_v = fast - slow
        macd_s = _sma(macd_v, p["signal_len"])
        macd_h = macd_v - macd_s
        atr_ = _atr(h, l, c, p["atr_len"])
        i = -1
        a = float(atr_.iloc[i])
        if not np.isfinite(a) or a <= 0:
            return None
        slow_close_ago = c.iloc[i - p["slow_len"]]
        bull = (macd_h.iloc[i] > 0 and macd_h.iloc[i-1] <= 0
                and macd_v.iloc[i] > 0
                and fast.iloc[i] > slow.iloc[i]
                and slow_close_ago > vslow.iloc[i])
        bear = (macd_h.iloc[i] < 0 and macd_h.iloc[i-1] >= 0
                and macd_v.iloc[i] < 0
                and fast.iloc[i] < slow.iloc[i]
                and slow_close_ago < vslow.iloc[i])
        side = "long" if bull else ("short" if bear else None)
        if side is None:
            return None
        return StrategySignal(side=side, entry_estimate=float(c.iloc[i]),
                              atr_at_signal=a,
                              tp_distance=p["tp_mult"] * a,
                              sl_distance=p["sl_mult"] * a,
                              bar_ts=str(bars.index[i]))


# ─── T5 — 5-Bar Trend + Pullback ────────────────────────────────────────────
class FiveBarPullback(Strategy):
    """5 consecutive directional bars, 1-2 counter bars, resumption candle."""
    def __init__(self, name, symbol, timeframe,
                 trend_bars=5, ema_len=50, rsi_len=14,
                 rsi_long_max=65.0, rsi_short_min=35.0,
                 atr_len=14, sl_mult=2.0, tp_mult=1.5):
        super().__init__(name, symbol, timeframe)
        self.p = dict(trend_bars=trend_bars, ema_len=ema_len, rsi_len=rsi_len,
                      rsi_long_max=rsi_long_max, rsi_short_min=rsi_short_min,
                      atr_len=atr_len, sl_mult=sl_mult, tp_mult=tp_mult)

    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp) -> Optional[StrategySignal]:
        p = self.p
        if len(bars) < p["ema_len"] + p["trend_bars"] + 5:
            return None
        c, o, h, l = bars["Close"], bars["Open"], bars["High"], bars["Low"]
        ema   = _ema(c, p["ema_len"])
        rsi   = _rsi(c, p["rsi_len"])
        atr_  = _atr(h, l, c, p["atr_len"])
        i = len(c) - 1
        a = float(atr_.iloc[i])
        if not np.isfinite(a) or a <= 0:
            return None
        # 5-bar run ended `trend_bars + 2` bars ago (bars i-trend_bars-2 ... i-3)
        # then 1-2 counter bars at i-2, i-1, then resumption at i.
        bull_run = True; bear_run = True
        for j in range(p["trend_bars"]):
            k = i - (j + 3)
            if c.iloc[k] <= o.iloc[k]:
                bull_run = False
            if c.iloc[k] >= o.iloc[k]:
                bear_run = False
        bull_pb = c.iloc[i-2] < o.iloc[i-2] or c.iloc[i-1] < o.iloc[i-1]
        bear_pb = c.iloc[i-2] > o.iloc[i-2] or c.iloc[i-1] > o.iloc[i-1]
        bull_resume = (c.iloc[i] > o.iloc[i] and c.iloc[i] > ema.iloc[i]
                       and rsi.iloc[i] < p["rsi_long_max"])
        bear_resume = (c.iloc[i] < o.iloc[i] and c.iloc[i] < ema.iloc[i]
                       and rsi.iloc[i] > p["rsi_short_min"])
        side = ("long" if (bull_run and bull_pb and bull_resume)
                else "short" if (bear_run and bear_pb and bear_resume)
                else None)
        if side is None:
            return None
        return StrategySignal(side=side, entry_estimate=float(c.iloc[i]),
                              atr_at_signal=a,
                              tp_distance=p["tp_mult"] * a,
                              sl_distance=p["sl_mult"] * a,
                              bar_ts=str(bars.index[i]))


# ─── T6 — BB Squeeze + EMA50 ────────────────────────────────────────────────
class BBSqueeze(Strategy):
    """BB width hits 20-bar minimum, then expands; EMA50 picks direction."""
    def __init__(self, name, symbol, timeframe,
                 bb_len=20, bb_mult=2.0, squeeze_bars=20, ema_len=50,
                 atr_len=14, sl_mult=2.0, tp_mult=1.5):
        super().__init__(name, symbol, timeframe)
        self.p = dict(bb_len=bb_len, bb_mult=bb_mult, squeeze_bars=squeeze_bars,
                      ema_len=ema_len, atr_len=atr_len,
                      sl_mult=sl_mult, tp_mult=tp_mult)

    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp) -> Optional[StrategySignal]:
        p = self.p
        need = max(p["ema_len"], p["bb_len"]) + p["squeeze_bars"] + 5
        if len(bars) < need:
            return None
        c, h, l = bars["Close"], bars["High"], bars["Low"]
        u, m, lb = _bb(c, p["bb_len"], p["bb_mult"])
        width = u - lb
        width_min = width.rolling(p["squeeze_bars"]).min()
        ema   = _ema(c, p["ema_len"])
        atr_  = _atr(h, l, c, p["atr_len"])
        i = len(c) - 1
        a = float(atr_.iloc[i])
        if not np.isfinite(a) or a <= 0:
            return None
        was_in_squeeze = width.iloc[i-1] <= width_min.iloc[i-1] * 1.001
        is_expanding   = width.iloc[i]   > width.iloc[i-1]
        if not (was_in_squeeze and is_expanding):
            return None
        bull = c.iloc[i] > ema.iloc[i] and c.iloc[i] > m.iloc[i]
        bear = c.iloc[i] < ema.iloc[i] and c.iloc[i] < m.iloc[i]
        side = "long" if bull else ("short" if bear else None)
        if side is None:
            return None
        return StrategySignal(side=side, entry_estimate=float(c.iloc[i]),
                              atr_at_signal=a,
                              tp_distance=p["tp_mult"] * a,
                              sl_distance=p["sl_mult"] * a,
                              bar_ts=str(bars.index[i]))


# ─── S01 — Connors RSI(2) Mean Reversion ────────────────────────────────────
class ConnorsRSI2(Strategy):
    """Larry Connors' RSI(2) mean-reversion. Fires when RSI(2) crosses below 10
    while above the trend SMA. Exit is handled by the framework's ATR exit,
    so we set TP relatively wide and SL tight (mean-reversion edge).
    """
    def __init__(self, name, symbol, timeframe,
                 rsi_len=2, rsi_buy=10.0,
                 trend_ma_len=50, use_trend_filter=True,
                 atr_len=14, sl_mult=1.0, tp_mult=2.0):
        super().__init__(name, symbol, timeframe)
        self.p = dict(rsi_len=rsi_len, rsi_buy=rsi_buy,
                      trend_ma_len=trend_ma_len, use_trend_filter=use_trend_filter,
                      atr_len=atr_len, sl_mult=sl_mult, tp_mult=tp_mult)

    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp) -> Optional[StrategySignal]:
        p = self.p
        if len(bars) < max(p["trend_ma_len"], p["atr_len"]) + 5:
            return None
        c, h, l = bars["Close"], bars["High"], bars["Low"]
        rsi = _rsi(c, p["rsi_len"])
        ma  = _sma(c, p["trend_ma_len"])
        atr_ = _atr(h, l, c, p["atr_len"])
        i = -1
        a = float(atr_.iloc[i])
        if not np.isfinite(a) or a <= 0:
            return None
        uptrend = (not p["use_trend_filter"]) or (c.iloc[i] > ma.iloc[i])
        crossed_under = rsi.iloc[i] < p["rsi_buy"] and rsi.iloc[i-1] >= p["rsi_buy"]
        if not (uptrend and crossed_under):
            return None
        return StrategySignal(side="long", entry_estimate=float(c.iloc[i]),
                              atr_at_signal=a,
                              tp_distance=p["tp_mult"] * a,
                              sl_distance=p["sl_mult"] * a,
                              bar_ts=str(bars.index[i]))


# ─── S07 — Nearys IFVG × FVG + MTF Bias ────────────────────────────────────
class NearysIFVG(Strategy):
    """FVG/IFVG entry with daily directional bias from prior-day close.

    Bias rule (Prior Close Simple): bullish if today's prior daily close >
    the day-before's daily close. Only take longs on bullish days, shorts on
    bearish days. Entry fires when current bar closes inside the middle 50%
    of an active FVG (or after inversion of one).
    """
    def __init__(self, name, symbol, timeframe,
                 atr_len=14, atr_gap_mult=0.5,
                 sl_mult=1.5, tp_mult=2.0,
                 use_daily_bias=True, fvg_extend=120):
        super().__init__(name, symbol, timeframe)
        self.p = dict(atr_len=atr_len, atr_gap_mult=atr_gap_mult,
                      sl_mult=sl_mult, tp_mult=tp_mult,
                      use_daily_bias=use_daily_bias, fvg_extend=fvg_extend)

    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp) -> Optional[StrategySignal]:
        p = self.p
        if len(bars) < max(p["atr_len"] + 5, p["fvg_extend"] + 5):
            return None
        h, l, c, o = bars["High"], bars["Low"], bars["Close"], bars["Open"]
        atr_ = _atr(h, l, c, p["atr_len"])
        i = len(bars) - 1
        a = float(atr_.iloc[i])
        if not np.isfinite(a) or a <= 0:
            return None
        min_gap = p["atr_gap_mult"] * a
        # Daily bias from prior close vs the day before
        bias = 0
        if p["use_daily_bias"]:
            daily = bars.resample("1D").agg(
                {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
            ).dropna()
            if len(daily) >= 3:
                bias = 1 if daily["Close"].iloc[-2] > daily["Close"].iloc[-3] else -1
        # Scan recent bars for active FVGs
        n = len(bars)
        start = max(2, n - p["fvg_extend"] - 5)
        bull_fvg = bear_fvg = None  # (top, bot, mid, created_idx, inverted, inv_dir)
        for k in range(start, n):
            if l.iloc[k] > h.iloc[k-2] and c.iloc[k-1] > h.iloc[k-2]:
                if (l.iloc[k] - h.iloc[k-2]) >= min_gap:
                    bull_fvg = [l.iloc[k], h.iloc[k-2], (l.iloc[k] + h.iloc[k-2]) / 2, k, False, 1]
            if h.iloc[k] < l.iloc[k-2] and c.iloc[k-1] < l.iloc[k-2]:
                if (l.iloc[k-2] - h.iloc[k]) >= min_gap:
                    bear_fvg = [l.iloc[k-2], h.iloc[k], (l.iloc[k-2] + h.iloc[k]) / 2, k, False, -1]
        # Mark inversions on most recent FVG-pair
        for z in (bull_fvg, bear_fvg):
            if z is None:
                continue
            for k in range(z[3] + 1, n):
                cbot = min(o.iloc[k], c.iloc[k]); ctop = max(o.iloc[k], c.iloc[k])
                if z[5] == 1 and cbot < z[1]:
                    z[4] = True; z[5] = -1
                elif z[5] == -1 and ctop > z[0]:
                    z[4] = True; z[5] = 1
        last_close = float(c.iloc[i])
        side = None
        for z in (bull_fvg, bear_fvg):
            if z is None:
                continue
            zone_size = z[0] - z[1]
            zone25 = z[1] + zone_size * 0.25
            zone75 = z[1] + zone_size * 0.75
            if zone25 <= last_close <= zone75:
                proposed_side = "long" if z[5] == 1 else "short"
                if p["use_daily_bias"]:
                    if bias == 1 and proposed_side == "short":
                        continue
                    if bias == -1 and proposed_side == "long":
                        continue
                    if bias == 0:
                        continue
                side = proposed_side
                break
        if side is None:
            return None
        return StrategySignal(side=side, entry_estimate=last_close,
                              atr_at_signal=a,
                              tp_distance=p["tp_mult"] * a,
                              sl_distance=p["sl_mult"] * a,
                              bar_ts=str(bars.index[i]))


# ─── ORB — Opening Range Breakout (Toby Crabel style) ───────────────────────
class OpeningRangeBreakout(Strategy):
    """First N-minute Opening Range Breakout.

    Range is defined by the first `range_minutes` of the NY session
    (9:30 ET onward). After the range closes, the first bar that closes
    above the range high triggers a long; first bar below the low triggers
    a short. One trade per day per symbol — second-breakout signals are
    suppressed.

    Stop = opposite side of the range (range_height).
    Target = `tp_mult_range` × range height (default 1.5).
    """
    def __init__(self, name, symbol, timeframe,
                 range_minutes=30,
                 tp_mult_range=1.5,
                 atr_len=14):
        super().__init__(name, symbol, timeframe)
        self.p = dict(range_minutes=range_minutes,
                      tp_mult_range=tp_mult_range,
                      atr_len=atr_len)

    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp) -> Optional[StrategySignal]:
        p = self.p
        if len(bars) < p["atr_len"] + 5:
            return None
        # Last bar's NY date — we only care about today's range
        last_idx = bars.index[-1]
        ny_last = last_idx.tz_convert("America/New_York")
        if ny_last.weekday() >= 5:
            return None
        ny_date = ny_last.date()
        # Today's bars only (NY-local)
        ny_index = bars.index.tz_convert("America/New_York")
        today_mask = ny_index.date == ny_date
        today = bars.loc[today_mask]
        if today.empty:
            return None
        # Define the opening range: 9:30 → 9:30 + range_minutes
        ny_today = today.index.tz_convert("America/New_York")
        td_min = ny_today.hour * 60 + ny_today.minute  # NY-minute of day per bar
        in_range_mask  = (td_min >= 9 * 60 + 30) & (td_min < 9 * 60 + 30 + p["range_minutes"])
        post_range_mask= td_min >= 9 * 60 + 30 + p["range_minutes"]
        range_bars     = today.loc[in_range_mask]
        post_bars      = today.loc[post_range_mask]
        if range_bars.empty or post_bars.empty:
            return None
        rng_hi = float(range_bars["High"].max())
        rng_lo = float(range_bars["Low"].min())
        rng_h  = rng_hi - rng_lo
        if rng_h <= 0:
            return None
        # Is THIS bar (the last one) the first breakout bar of the day?
        last_close = float(today["Close"].iloc[-1])
        last_ts    = today.index[-1]
        # Bars in today's post-range slice that came before the current bar
        prior_post = post_bars.iloc[:-1] if post_bars.index[-1] == last_ts else post_bars
        if not prior_post.empty:
            already_broke = (prior_post["Close"] > rng_hi).any() or (prior_post["Close"] < rng_lo).any()
            if already_broke:
                return None
        side = None
        if last_close > rng_hi:
            side = "long"
        elif last_close < rng_lo:
            side = "short"
        if side is None:
            return None
        # Use the range height as our risk unit, but report ATR for sizing too
        atr_ = _atr(bars["High"], bars["Low"], bars["Close"], p["atr_len"])
        a = float(atr_.iloc[-1])
        if not np.isfinite(a) or a <= 0:
            a = rng_h  # fallback so shares_for_risk has something sane
        return StrategySignal(side=side, entry_estimate=last_close,
                              atr_at_signal=a,
                              tp_distance=p["tp_mult_range"] * rng_h,
                              sl_distance=rng_h,
                              bar_ts=str(last_ts))
