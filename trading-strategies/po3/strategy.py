"""The PO3 entry model itself: accumulation → manipulation → distribution.

One 4H window (10:00 or 14:00 ET) is walked bar by bar in the entry timeframe:

  1. **Accumulation** — the first `accum_minutes` after the 4H open define the
     range price is coiling in. On a red/orange-folder news day the Bible says
     the manipulation is immediate, so those days read their accumulation from
     *before* the open instead.
  2. **Manipulation** — price runs the accumulation extreme *against* the daily
     bias, ideally into a recent 15m fair value gap. That low (long) or high
     (short) is the 4H candle's wick, and it becomes the stop.
  3. **Distribution** — the leg we actually take. Entry needs at least
     `min_confs` of the Bible's three confirmations, all on the entry timeframe:
       a. IFVG   — a gap from the manipulation leg closed back through
       b. CISD   — the last opposing candle body closed through
       c. a close back above/below the 4H candle's open price
  4. **Target** — previous day's high/low, the main draw on liquidity. If that
     draw is closer than `min_rr`, the setup is skipped rather than shrunk.

Fills are conservative: entry at the confirming bar's close, and when a bar
straddles both stop and target the stop is assumed first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .core import (
    NY,
    FVGBook,
    Window,
    atr,
    cisd_level,
    daily_from_intraday,
    find_fvgs,
    resample,
)


@dataclass
class PO3Config:
    # ── phase 1: accumulation ──────────────────────────────────────────────
    accum_minutes: int = 30
    news_dates: frozenset[date] = frozenset()
    news_pre_open_minutes: int = 30   # news days accumulate before the 4H open
    news_accum_minutes: int = 5

    # ── phase 2: manipulation ──────────────────────────────────────────────
    require_fvg_tap: bool = True
    fvg_tf: str = "15min"
    fvg_lookback: int = 12            # how many 15m bars back stays "recent"
    max_manip_bars: int = 24          # bars after accumulation to find the sweep

    # ── phase 3: entry ─────────────────────────────────────────────────────
    min_confs: int = 2                # of {ifvg, cisd, reclaim_4h_open}
    max_confirm_bars: int = 24        # bars after the sweep to confirm

    # ── risk ───────────────────────────────────────────────────────────────
    atr_len: int = 14
    stop_buf_atr: float = 0.10        # padding beyond the manipulation extreme
    min_rr: float = 2.0
    target_mode: str = "pdh_pdl"      # 'pdh_pdl' (ERL draw) | 'rr'
    rr_target: float = 3.0

    # Execution reality. R-multiples flatter tight stops badly: a sweep that
    # only ran a few ticks produces a huge R on any ordinary drift, and that is
    # exactly where spread and slippage hurt most. `cost_per_side` is charged in
    # price units on entry and exit; `min_stop_atr` refuses setups whose stop is
    # too tight to be worth trading.
    cost_per_side: float = 0.0
    min_stop_atr: float = 0.0

    # Bible money management: trim 80% at 2R, rest runs, stop to breakeven.
    trim_frac: float = 0.0
    trim_r: float = 2.0
    be_after_trim: bool = True


@dataclass
class Trade:
    ny_date: object
    hour: int
    side: str
    bias_score: float
    entry_ts: pd.Timestamp
    entry: float
    stop: float
    target: float
    exit_ts: pd.Timestamp
    exit: float
    r: float
    outcome: str                      # target | stop | time | trim_time
    confs: tuple[str, ...] = ()
    big_day: float = 0.0
    detail: dict = field(default_factory=dict)


@dataclass
class Skip:
    ny_date: object
    hour: int
    reason: str
    bias_score: float = 0.0


def _slice(df: pd.DataFrame, lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame:
    """Bars in [lo, hi]."""
    return df.loc[(df.index >= lo) & (df.index <= hi)]


class PO3Model:
    """Runs the entry model over one instrument's bars."""

    def __init__(self, bars: pd.DataFrame, cfg: PO3Config | None = None):
        self.bars = bars
        self.cfg = cfg or PO3Config()
        self.atr = atr(bars, self.cfg.atr_len).shift(1)

        self.htf = resample(bars, self.cfg.fvg_tf)
        self.htf_book = FVGBook(self.htf)

        daily = daily_from_intraday(bars)
        self.pdh = daily["High"].shift(1)
        self.pdl = daily["Low"].shift(1)

    def rebind(self, cfg: PO3Config) -> "PO3Model":
        """Same precomputed ATR / FVG book / daily levels, different tactics.

        Only `atr_len` and `fvg_tf` feed the precomputation; changing either
        forces a rebuild, everything else is read per window.
        """
        if cfg.atr_len != self.cfg.atr_len or cfg.fvg_tf != self.cfg.fvg_tf:
            return PO3Model(self.bars, cfg)
        clone = object.__new__(PO3Model)
        clone.__dict__.update(self.__dict__)
        clone.cfg = cfg
        return clone

    # ── helpers ───────────────────────────────────────────────────────────
    def _accum_range(self, w: Window) -> tuple[pd.DataFrame, pd.Timestamp]:
        """Accumulation bars and the timestamp the manipulation may start from."""
        cfg = self.cfg
        if w.ny_date in cfg.news_dates:
            lo = w.open_ts - pd.Timedelta(minutes=cfg.news_pre_open_minutes)
            hi = w.open_ts + pd.Timedelta(minutes=cfg.news_accum_minutes)
        else:
            lo = w.open_ts
            hi = w.open_ts + pd.Timedelta(minutes=cfg.accum_minutes)
        return _slice(self.bars, lo, hi), hi

    def _draw(self, w: Window, side: str) -> float | None:
        """The ERL draw on liquidity: previous day's high (long) or low (short)."""
        key = pd.Timestamp(w.ny_date)
        v = self.pdh.get(key) if side == "long" else self.pdl.get(key)
        return None if v is None or not np.isfinite(v) else float(v)

    # ── the model ─────────────────────────────────────────────────────────
    def run_window(
        self, w: Window, bias: int, bias_score: float, big_day: float = 0.0
    ) -> Trade | Skip:
        cfg = self.cfg
        if bias == 0:
            return Skip(w.ny_date, w.hour, "no_bias", bias_score)

        side = "long" if bias == 1 else "short"
        acc, manip_start = self._accum_range(w)
        if len(acc) < 2:
            return Skip(w.ny_date, w.hour, "no_accumulation", bias_score)

        acc_hi = float(acc["High"].max())
        acc_lo = float(acc["Low"].min())

        rest = _slice(self.bars, manip_start, w.end_ts)
        if len(rest) < 3:
            return Skip(w.ny_date, w.hour, "window_too_short", bias_score)

        a = self.atr.get(w.open_ts, np.nan)
        if not np.isfinite(a) or a <= 0:
            return Skip(w.ny_date, w.hour, "no_atr", bias_score)

        # Live 15m arrays once accumulation is done — the pools the wick should
        # reach into. The Bible's gap forms *during* accumulation, so these are
        # read at the end of that phase, counting only fully-closed 15m bars.
        want_kind = "bull" if side == "long" else "bear"
        step = pd.Timedelta(cfg.fvg_tf)
        pools = (
            self.htf_book.live(
                manip_start, cfg.fvg_lookback,
                kind=want_kind, born_asof=manip_start - step,
            )
            if cfg.require_fvg_tap
            else []
        )
        if cfg.require_fvg_tap and not pools:
            return Skip(w.ny_date, w.hour, "no_15m_fvg", bias_score)

        # ── phases 2 & 3: manipulation, then distribution ─────────────────
        # One sequential pass. The manipulation extreme keeps extending until an
        # entry actually confirms, so the stop sits behind the wick's real low
        # rather than behind whichever bar first poked through the range.
        manip_ext: float | None = None
        manip_ts: pd.Timestamp | None = None
        tapped = False
        swept = False
        entry_ts = entry_px = None
        confs: tuple[str, ...] = ()

        # Recomputed whenever the leg extends to a new extreme.
        cisd: float | None = None
        leg_fvgs: list = []
        cached_ext_ts: pd.Timestamp | None = None

        limit = cfg.max_manip_bars + cfg.max_confirm_bars
        for i, ts in enumerate(rest.index):
            if i >= limit:
                break
            lo = float(rest["Low"].iloc[i])
            hi = float(rest["High"].iloc[i])
            c = float(rest["Close"].iloc[i])

            if side == "long":
                if lo < acc_lo:
                    swept = True
                    if manip_ext is None or lo < manip_ext:
                        manip_ext, manip_ts = lo, ts
                if pools and any(lo <= g.top for g in pools):
                    tapped = True
            else:
                if hi > acc_hi:
                    swept = True
                    if manip_ext is None or hi > manip_ext:
                        manip_ext, manip_ts = hi, ts
                if pools and any(hi >= g.bottom for g in pools):
                    tapped = True

            # Give the sweep `max_manip_bars` to appear before abandoning the day.
            if not swept:
                if i >= cfg.max_manip_bars:
                    break
                continue
            if cfg.require_fvg_tap and not tapped:
                continue
            if ts <= manip_ts:
                continue  # the extreme bar itself can't also be the entry

            if cached_ext_ts != manip_ts:
                leg = _slice(self.bars, acc.index[0], manip_ts)
                leg_fvgs = [g for g in find_fvgs(leg) if g.kind != want_kind]
                cisd = cisd_level(
                    self.bars.loc[self.bars.index <= manip_ts], manip_ts, side
                )
                cached_ext_ts = manip_ts

            hit: list[str] = []
            # a. IFVG — an opposing gap from the leg closed back through
            for g in leg_fvgs:
                if g.ts >= ts:
                    continue
                if (side == "long" and c > g.top) or (side == "short" and c < g.bottom):
                    hit.append("ifvg")
                    break
            # b. CISD — the last opposing candle body closed through
            if cisd is not None and (
                (side == "long" and c > cisd) or (side == "short" and c < cisd)
            ):
                hit.append("cisd")
            # c. reclaim of the 4H candle's opening price
            if (side == "long" and c > w.open_price) or (
                side == "short" and c < w.open_price
            ):
                hit.append("open_reclaim")

            if len(hit) >= cfg.min_confs:
                entry_ts, entry_px, confs = ts, c, tuple(hit)
                break

        if manip_ext is None:
            return Skip(w.ny_date, w.hour, "no_manipulation", bias_score)
        if cfg.require_fvg_tap and not tapped:
            return Skip(w.ny_date, w.hour, "no_fvg_tap", bias_score)
        if entry_ts is None:
            return Skip(w.ny_date, w.hour, "no_confirmation", bias_score)

        # ── risk / target ─────────────────────────────────────────────────
        buf = cfg.stop_buf_atr * float(a)
        stop = manip_ext - buf if side == "long" else manip_ext + buf
        risk = abs(entry_px - stop)
        if risk <= 0:
            return Skip(w.ny_date, w.hour, "bad_risk", bias_score)
        if cfg.min_stop_atr > 0 and risk < cfg.min_stop_atr * float(a):
            return Skip(w.ny_date, w.hour, "stop_too_tight", bias_score)

        # Round-trip execution cost, expressed in units of this trade's risk.
        cost_r = (2.0 * cfg.cost_per_side / risk) if cfg.cost_per_side else 0.0

        if cfg.target_mode == "pdh_pdl":
            draw = self._draw(w, side)
            if draw is None:
                return Skip(w.ny_date, w.hour, "no_draw", bias_score)
            target = draw
        else:
            target = (
                entry_px + cfg.rr_target * risk
                if side == "long"
                else entry_px - cfg.rr_target * risk
            )

        rr = (target - entry_px) / risk if side == "long" else (entry_px - target) / risk
        if rr < cfg.min_rr:
            return Skip(w.ny_date, w.hour, "rr_too_low", bias_score)

        # ── manage ────────────────────────────────────────────────────────
        trade_bars = _slice(self.bars, entry_ts, w.end_ts).iloc[1:]
        trimmed = False
        realized = 0.0
        remaining = 1.0
        cur_stop = stop
        trim_px = (
            entry_px + cfg.trim_r * risk if side == "long" else entry_px - cfg.trim_r * risk
        )

        for ts, bar in trade_bars.iterrows():
            hi, lo = float(bar["High"]), float(bar["Low"])

            # Stop first — conservative when a bar straddles both levels.
            stop_hit = lo <= cur_stop if side == "long" else hi >= cur_stop
            if stop_hit:
                r_leg = (
                    (cur_stop - entry_px) / risk
                    if side == "long"
                    else (entry_px - cur_stop) / risk
                )
                realized += remaining * r_leg
                return Trade(
                    w.ny_date, w.hour, side, bias_score, entry_ts, entry_px, stop,
                    target, ts, cur_stop, realized - cost_r,
                    "stop" if not trimmed else "trim_stop", confs, big_day,
                    {"rr": rr, "risk": risk, "cost_r": cost_r, "confs": list(confs)},
                )

            if cfg.trim_frac > 0 and not trimmed:
                trim_hit = hi >= trim_px if side == "long" else lo <= trim_px
                if trim_hit:
                    trimmed = True
                    realized += cfg.trim_frac * cfg.trim_r
                    remaining = 1.0 - cfg.trim_frac
                    if cfg.be_after_trim:
                        cur_stop = entry_px

            tgt_hit = hi >= target if side == "long" else lo <= target
            if tgt_hit:
                realized += remaining * rr
                return Trade(
                    w.ny_date, w.hour, side, bias_score, entry_ts, entry_px, stop,
                    target, ts, target, realized - cost_r, "target", confs, big_day,
                    {"rr": rr, "risk": risk, "cost_r": cost_r, "confs": list(confs)},
                )

        # Time exit at the 4H close / forced flat.
        if trade_bars.empty:
            return Skip(w.ny_date, w.hour, "no_bars_after_entry", bias_score)
        last_ts = trade_bars.index[-1]
        last_px = float(trade_bars["Close"].iloc[-1])
        r_leg = (
            (last_px - entry_px) / risk if side == "long" else (entry_px - last_px) / risk
        )
        realized += remaining * r_leg
        return Trade(
            w.ny_date, w.hour, side, bias_score, entry_ts, entry_px, stop, target,
            last_ts, last_px, realized - cost_r, "trim_time" if trimmed else "time",
            confs, big_day, {"rr": rr, "risk": risk, "cost_r": cost_r, "confs": list(confs)},
        )
