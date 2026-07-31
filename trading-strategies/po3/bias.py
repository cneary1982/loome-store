"""Daily bias engine — "which direction do we take the trade?"

The PO3 Bible sets bias by *stacking high-timeframe confluences* rather than by
one signal:

  1. Daily and weekly profiles (NY reversal vs NY continuation)
  2. HTF PD arrays, CISD, SMT
  3. HTF MMXM
  4. Daily OLHC
  5. ERL <-> IRL

Each is scored here as +1 (long) / -1 (short) / 0 (no read), summed with weights
and compared against a threshold. Below threshold the day is a **no-trade day** —
which is the point: the model only works when the higher timeframe says
something.

Causality
---------
Higher timeframes are resampled once over the whole series for speed, so the
partial bar straddling the moment of the query would leak the future. Every HTF
read therefore uses **fully-closed bars only**: a bar counts as visible at
`when` when `bar_open + timeframe <= when`. Swings inherit the same rule via
their confirming bar. Intraday reads slice strictly before `when`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .core import (
    NY,
    FVGBook,
    daily_from_intraday,
    ns,
    ns_array,
    ny_frame,
    resample,
    swings,
)


@dataclass
class BiasConfig:
    # Weight per confluence. Set one to 0.0 to drop it from the stack.
    w_structure: float = 1.0      # HH/HL vs LH/LL on the higher timeframes
    w_pd_array: float = 1.0       # nearest live HTF fair value gap
    w_daily_olhc: float = 1.0     # how the daily candle is delivering so far
    w_erl_irl: float = 1.0        # premium/discount + which ERL is still untapped
    w_profile: float = 1.0        # Asia/London daily profile
    w_cisd: float = 1.0           # HTF change in state of delivery

    # Timeframes for structure + PD arrays. These are UTC-anchored resamples used
    # only as a trend/array read — the PO3 candle itself is anchored on the NY
    # clock in `po3_windows`, which is the one that has to be exact.
    structure_tfs: tuple[str, ...] = ("1h", "4h")
    pd_tfs: tuple[str, ...] = ("1h", "4h")

    swing_left: int = 2
    swing_right: int = 2
    pd_lookback_bars: int = 20    # how far back an HTF FVG stays "recent"

    min_score: float = 2.0        # |score| must reach this to trade the day
    min_history_bars: int = 50


@dataclass
class BiasRead:
    bias: int                       # +1 long, -1 short, 0 no-trade
    score: float
    components: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return {1: "long", -1: "short", 0: "none"}[self.bias]


def _cisd_np(o: np.ndarray, c: np.ndarray, end: int, direction: str) -> float | None:
    """`core.cisd_level` over raw arrays; `end` is exclusive."""
    i = end - 1
    down = direction == "long"
    while i >= 0 and ((c[i] >= o[i]) if down else (c[i] <= o[i])):
        i -= 1
    if i < 0:
        return None
    j = i
    while j - 1 >= 0 and ((c[j - 1] < o[j - 1]) if down else (c[j - 1] > o[j - 1])):
        j -= 1
    return float(o[j])


@dataclass
class _TF:
    """Precomputed state for one higher timeframe."""
    bars: pd.DataFrame
    close_ns: np.ndarray          # when each bar becomes visible
    open_: np.ndarray
    close: np.ndarray
    book: FVGBook
    hi_ct: np.ndarray             # swing-high confirm times (ns)
    hi_px: np.ndarray
    lo_ct: np.ndarray
    lo_px: np.ndarray

    def visible(self, w: int) -> int:
        """Count of fully-closed bars at instant `w`."""
        return int(np.searchsorted(self.close_ns, w, side="right"))


class BiasEngine:
    """Scores the bias stack at a point in time from one intraday series."""

    def __init__(self, bars: pd.DataFrame, cfg: BiasConfig | None = None):
        self.bars = bars
        self.cfg = cfg or BiasConfig()

        self._idx = ns_array(bars.index)
        self._O = bars["Open"].to_numpy(float)
        self._H = bars["High"].to_numpy(float)
        self._L = bars["Low"].to_numpy(float)
        self._C = bars["Close"].to_numpy(float)

        f = ny_frame(bars)
        self._nydate = f["ny_date"].to_numpy()
        dates = pd.unique(f["ny_date"])
        # First positional index of each NY date (the frame is time-sorted).
        starts = np.searchsorted(
            np.arange(len(bars)),
            [np.argmax(self._nydate == d) for d in dates],
        )
        self._start = {d: int(s) for d, s in zip(dates, starts)}

        daily = daily_from_intraday(bars)
        self._pdh = daily["High"].shift(1)
        self._pdl = daily["Low"].shift(1)

        self._profile = self._precompute_profiles(f, dates)
        self._tf = {
            tf: self._build_tf(bars, tf)
            for tf in dict.fromkeys((*self.cfg.structure_tfs, *self.cfg.pd_tfs))
        }

    # ── precomputation ────────────────────────────────────────────────────
    def _build_tf(self, bars: pd.DataFrame, tf: str) -> _TF:
        b = resample(bars, tf)
        step = pd.Timedelta(tf)
        close_ns = ns_array(b.index) + int(step.value)

        sw = swings(b, self.cfg.swing_left, self.cfg.swing_right)
        if sw.empty:
            empty = np.empty(0)
            hi_ct = lo_ct = np.empty(0, dtype="int64")
            hi_px = lo_px = empty
        else:
            # A swing is knowable only once its confirming bar has closed.
            conf = ns_array(pd.DatetimeIndex(sw["confirm_ts"])) + int(step.value)
            sw = sw.assign(_c=conf)
            hi = sw[sw["kind"] == "high"].sort_values("_c")
            lo = sw[sw["kind"] == "low"].sort_values("_c")
            hi_ct = hi["_c"].to_numpy("int64")
            hi_px = hi["price"].to_numpy(float)
            lo_ct = lo["_c"].to_numpy("int64")
            lo_px = lo["price"].to_numpy(float)

        return _TF(
            bars=b,
            close_ns=close_ns,
            open_=b["Open"].to_numpy(float),
            close=b["Close"].to_numpy(float),
            book=FVGBook(b),
            hi_ct=hi_ct, hi_px=hi_px, lo_ct=lo_ct, lo_px=lo_px,
        )

    @staticmethod
    def _precompute_profiles(f: pd.DataFrame, dates) -> dict:
        """Asia/London profile per NY date — the NY continuation vs reversal read.

        Continuation ("NY life"): Asia builds a range, London never threatens the
        opposite extreme and distributes through one side; NY continues it. If
        London took both sides there is no clean profile. Both sessions close by
        05:00 ET, well before either PO3 window, so this is safe to precompute.
        """
        out: dict = {}
        by_date = {d: g for d, g in f.groupby("ny_date")}
        ordered = list(dates)
        for i, d in enumerate(ordered):
            if i == 0:
                out[d] = 0.0
                continue
            today = by_date[d]
            prev = by_date[ordered[i - 1]]
            asia = pd.concat(
                [prev[prev["ny_min"] >= 18 * 60], today[today["ny_min"] < 2 * 60]]
            )
            london = today[(today["ny_min"] >= 2 * 60) & (today["ny_min"] < 5 * 60)]
            if len(asia) < 3 or len(london) < 3:
                out[d] = 0.0
                continue
            a_hi, a_lo = float(asia["High"].max()), float(asia["Low"].min())
            up = float(london["High"].max()) > a_hi
            dn = float(london["Low"].min()) < a_lo
            out[d] = 1.0 if (up and not dn) else (-1.0 if (dn and not up) else 0.0)
        return out

    # ── components ────────────────────────────────────────────────────────
    def _structure(self, w: int) -> float:
        votes = []
        for tf in self.cfg.structure_tfs:
            s = self._tf[tf]
            kh = int(np.searchsorted(s.hi_ct, w, side="right"))
            kl = int(np.searchsorted(s.lo_ct, w, side="right"))
            if kh < 2 or kl < 2:
                continue
            hh = s.hi_px[kh - 1] > s.hi_px[kh - 2]
            hl = s.lo_px[kl - 1] > s.lo_px[kl - 2]
            votes.append(1 if (hh and hl) else (-1 if (not hh and not hl) else 0))
        return 0.0 if not votes else float(np.sign(sum(votes)))

    def _pd_array(self, when: pd.Timestamp, w: int, price: float) -> float:
        """Nearest still-live HTF fair value gap.

        Price above a live bullish gap means that array is unmitigated support
        and the HTF is delivering up (+1); below a live bearish gap is the
        mirror. New PD arrays on the higher timeframes are exactly what the
        Bible points at, so the closest live array wins.
        """
        best: tuple[float, int] | None = None
        for tf in self.cfg.pd_tfs:
            s = self._tf[tf]
            n = s.visible(w)
            if n < 5:
                continue
            # Ask the book as of the last fully-closed bar, never the live one.
            asof = s.bars.index[n - 1]
            for g in s.book.live(asof, self.cfg.pd_lookback_bars):
                if g.kind == "bull" and price > g.top:
                    d, vote = price - g.top, 1
                elif g.kind == "bear" and price < g.bottom:
                    d, vote = g.bottom - price, -1
                else:
                    continue  # price sits inside the array — no clean read
                if best is None or d < best[0]:
                    best = (d, vote)
        return 0.0 if best is None else float(best[1])

    def _daily_olhc(self, s: int, e: int) -> float:
        """Is today delivering as OLHC (low first, expand up) or OHLC?

        The daily-candle version of the same PO3 traded intraday: a bullish day
        prints its low early as the manipulation, then distributes.
        """
        if e - s < 3:
            return 0.0
        d_open = self._O[s]
        price = self._C[e - 1]
        lo_at = s + int(np.argmin(self._L[s:e]))
        hi_at = s + int(np.argmax(self._H[s:e]))
        if price > d_open and lo_at < hi_at:
            return 1.0
        if price < d_open and hi_at < lo_at:
            return -1.0
        return 0.0

    def _erl_irl(self, d, s: int, e: int) -> float:
        """ERL <-> IRL: where in the dealing range, and which pool is unswept?

        Inside the prior day's range a discount puts the untapped buyside
        (previous day high) as the draw → long; a premium reverses it. Once one
        side has been raided the remaining pool becomes the draw.
        """
        key = pd.Timestamp(d)
        hi, lo = self._pdh.get(key, np.nan), self._pdl.get(key, np.nan)
        if not (np.isfinite(hi) and np.isfinite(lo)) or hi <= lo or e <= s:
            return 0.0
        took_high = float(self._H[s:e].max()) > hi
        took_low = float(self._L[s:e].min()) < lo
        if took_high and not took_low:
            return -1.0   # buyside raided → draw flips to the low
        if took_low and not took_high:
            return 1.0    # sellside raided → draw flips to the high
        return 1.0 if self._C[e - 1] < (hi + lo) / 2.0 else -1.0

    def _cisd(self, w: int) -> float:
        votes = []
        for tf in self.cfg.structure_tfs:
            s = self._tf[tf]
            n = s.visible(w)
            if n < 6:
                continue
            price = s.close[n - 1]
            up = _cisd_np(s.open_, s.close, n, "long")
            dn = _cisd_np(s.open_, s.close, n, "short")
            if up is not None and price > up:
                votes.append(1)
            elif dn is not None and price < dn:
                votes.append(-1)
        return 0.0 if not votes else float(np.sign(sum(votes)))

    # ── entry point ───────────────────────────────────────────────────────
    def at(self, when: pd.Timestamp) -> BiasRead:
        """Bias as of `when`, using only information available before it."""
        cfg = self.cfg
        w = ns(when)
        e = int(np.searchsorted(self._idx, w, side="left"))  # bars strictly before
        if e < cfg.min_history_bars:
            return BiasRead(0, 0.0, {"reason": "insufficient_history"})

        d = when.tz_convert(NY).date()
        s = self._start.get(d)
        if s is None or s >= e:
            return BiasRead(0, 0.0, {"reason": "no_session_data"})

        price = float(self._C[e - 1])
        comps = {
            "structure": self._structure(w),
            "pd_array": self._pd_array(when, w, price),
            "daily_olhc": self._daily_olhc(s, e),
            "erl_irl": self._erl_irl(d, s, e),
            "profile": float(self._profile.get(d, 0.0)),
            "cisd": self._cisd(w),
        }
        weights = {
            "structure": cfg.w_structure,
            "pd_array": cfg.w_pd_array,
            "daily_olhc": cfg.w_daily_olhc,
            "erl_irl": cfg.w_erl_irl,
            "profile": cfg.w_profile,
            "cisd": cfg.w_cisd,
        }
        score = sum(comps[k] * weights[k] for k in comps)

        bias = 1 if score >= cfg.min_score else (-1 if score <= -cfg.min_score else 0)
        return BiasRead(bias, float(score), comps)
