"""Day-quality gate — decides *whether* a 10:00 or 14:00 window may be traded.

This is the PO3 equivalent of the ORB day gate: same shape (volatility regime +
overnight behaviour + calendar blocks), retuned for the two 4H opens.

The asymmetry between the two windows is deliberate and matches how the model is
actually traded:

  * **10:00 is the primary window.** It gets the light gate — it only has to
    clear the calendar blocks and not be a day that already exhausted its range
    overnight.
  * **14:00 is the weak window.** It stays locked unless the session has proved
    itself a big day by 14:00 (range already expanded vs ATR), and by default
    only when the 10:00 window did not already produce a trade. That is the
    "usually 10 is best, 2 is weak unless it's a big day" rule, and the "sometimes
    10 is no good so 2 works" fallback.

Nothing here uses information from after the moment being judged: the AM gate
sees the overnight session and the prior daily ATR, the PM gate additionally
sees 09:30-14:00 of the same day.

NOTE: the ORB 7.7/7.8 gate script is not in this repo, so this is a
reimplementation of that gate's *shape* rather than a port of its exact
thresholds. `GateConfig` is the single place to retune it, and
`po3_sweep.py` sweeps the thresholds that matter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .core import atr, daily_from_intraday, ny_frame


@dataclass
class GateConfig:
    trade_hours: tuple[int, ...] = (10, 14)

    # Calendar blocks. The Bible's rule set skips Mondays and the day before
    # CPI/FOMC; `blackout_dates` is where those event dates get injected.
    skip_dows: tuple[int, ...] = ()               # 0=Mon … 4=Fri
    blackout_dates: frozenset[date] = frozenset()

    atr_len: int = 14

    # ── 10:00 (AM) gate ────────────────────────────────────────────────────
    am_enabled: bool = True
    am_max_on_range_atr: float = 1.50   # overnight already ran this far → stand down
    am_max_gap_atr: float = 1.25        # runaway gap → stand down
    am_min_atr_pct: float = 0.0         # dead-vol floor, ATR as % of price

    # ── 14:00 (PM) gate ────────────────────────────────────────────────────
    pm_enabled: bool = True
    pm_require_big_day: bool = True
    pm_big_day_range_atr: float = 0.75  # 09:30→14:00 range vs daily ATR
    pm_only_if_am_flat: bool = True     # skip PM when the AM window already traded

    max_trades_per_day: int = 1         # Bible: one trade a day


@dataclass
class GateDecision:
    allow: bool
    reason: str
    big_day: float = 0.0                # 09:30→14:00 range / daily ATR
    detail: dict = field(default_factory=dict)


class DayGate:
    """Precomputes the per-day statistics, then answers per-window questions."""

    def __init__(self, bars: pd.DataFrame, cfg: GateConfig | None = None):
        self.cfg = cfg or GateConfig()
        self.bars = bars
        self.stats = self._build(bars, self.cfg.atr_len)

    # ── per-day statistics ────────────────────────────────────────────────
    @staticmethod
    def _build(bars: pd.DataFrame, atr_len: int) -> pd.DataFrame:
        daily = daily_from_intraday(bars)
        # Shift by one day: at today's open only yesterday's ATR is known.
        d_atr = atr(daily, atr_len).shift(1)
        prev_close = daily["Close"].shift(1)

        f = ny_frame(bars)
        rows = []
        dates = sorted(set(f["ny_date"]))
        by_date = {d: g for d, g in f.groupby("ny_date")}

        for i, d in enumerate(dates):
            day = by_date[d]
            key = pd.Timestamp(d)
            a = d_atr.get(key, np.nan)
            pc = prev_close.get(key, np.nan)

            # Overnight = 18:00 ET the previous evening → 09:30 ET today.
            prev_eve = by_date[dates[i - 1]] if i else None
            on_parts = [day[day["ny_min"] < 9 * 60 + 30]]
            if prev_eve is not None:
                on_parts.append(prev_eve[prev_eve["ny_min"] >= 18 * 60])
            on = pd.concat(on_parts)
            on_range = (
                float(on["High"].max() - on["Low"].min()) if len(on) else np.nan
            )

            rth = day[day["ny_min"] >= 9 * 60 + 30]
            first_px = float(rth["Open"].iloc[0]) if len(rth) else np.nan
            gap = abs(first_px - pc) if not np.isnan(pc) and not np.isnan(first_px) else np.nan

            # Range built between the RTH open and the 14:00 candle open.
            am = day[(day["ny_min"] >= 9 * 60 + 30) & (day["ny_min"] < 14 * 60)]
            am_range = float(am["High"].max() - am["Low"].min()) if len(am) else np.nan

            rows.append(
                {
                    "ny_date": d,
                    "dow": int(day["ny_dow"].iloc[0]),
                    "atr": a,
                    "px": first_px,
                    "on_range": on_range,
                    "gap": gap,
                    "am_range": am_range,
                }
            )

        out = pd.DataFrame(rows).set_index("ny_date")
        out["on_range_atr"] = out["on_range"] / out["atr"]
        out["gap_atr"] = out["gap"] / out["atr"]
        out["am_range_atr"] = out["am_range"] / out["atr"]
        out["atr_pct"] = out["atr"] / out["px"] * 100.0
        return out

    def rebind(self, cfg: GateConfig) -> "DayGate":
        """Same per-day statistics, different thresholds.

        The stats table depends only on `atr_len`; everything else in GateConfig
        is a threshold applied in `check`. A changed `atr_len` forces a rebuild.
        """
        if cfg.atr_len != self.cfg.atr_len:
            return DayGate(self.bars, cfg)
        clone = object.__new__(DayGate)
        clone.cfg = cfg
        clone.bars = self.bars
        clone.stats = self.stats
        return clone

    # ── decisions ─────────────────────────────────────────────────────────
    def _calendar_block(self, d) -> str | None:
        cfg = self.cfg
        if d not in self.stats.index:
            return "no_stats"
        row = self.stats.loc[d]
        if int(row["dow"]) in cfg.skip_dows:
            return "blocked_dow"
        if d in cfg.blackout_dates:
            return "blackout_date"
        if not np.isfinite(row["atr"]):
            return "no_atr"
        return None

    def check(self, d, hour: int, am_traded: bool = False) -> GateDecision:
        """May the `hour` window on NY date `d` be traded?

        `am_traded` reports whether the 10:00 window already produced a trade —
        that is what makes 14:00 a genuine fallback rather than a second bite.
        """
        cfg = self.cfg
        if hour not in cfg.trade_hours:
            return GateDecision(False, "hour_not_traded")

        blocked = self._calendar_block(d)
        if blocked:
            return GateDecision(False, blocked)

        row = self.stats.loc[d]
        big = float(row["am_range_atr"]) if np.isfinite(row["am_range_atr"]) else 0.0
        detail = {
            "on_range_atr": float(row["on_range_atr"]) if np.isfinite(row["on_range_atr"]) else None,
            "gap_atr": float(row["gap_atr"]) if np.isfinite(row["gap_atr"]) else None,
            "am_range_atr": big,
            "atr_pct": float(row["atr_pct"]) if np.isfinite(row["atr_pct"]) else None,
        }

        if hour == 10:
            if not cfg.am_enabled:
                return GateDecision(False, "am_disabled", big, detail)
            if np.isfinite(row["atr_pct"]) and row["atr_pct"] < cfg.am_min_atr_pct:
                return GateDecision(False, "vol_too_low", big, detail)
            if np.isfinite(row["on_range_atr"]) and row["on_range_atr"] > cfg.am_max_on_range_atr:
                return GateDecision(False, "overnight_exhausted", big, detail)
            if np.isfinite(row["gap_atr"]) and row["gap_atr"] > cfg.am_max_gap_atr:
                return GateDecision(False, "gap_too_large", big, detail)
            return GateDecision(True, "am_ok", big, detail)

        # hour == 14
        if not cfg.pm_enabled:
            return GateDecision(False, "pm_disabled", big, detail)
        if cfg.pm_only_if_am_flat and am_traded:
            return GateDecision(False, "am_already_traded", big, detail)
        if cfg.pm_require_big_day and big < cfg.pm_big_day_range_atr:
            return GateDecision(False, "pm_not_big_day", big, detail)
        return GateDecision(True, "pm_ok", big, detail)


def load_blackout_dates(path: str | None) -> frozenset[date]:
    """Read a newline-delimited YYYY-MM-DD file of CPI/FOMC-style blackout dates.

    Blank lines and `#` comments are ignored. Each listed date is blocked along
    with the session before it, per the Bible's "do not trade the day before CPI
    or FOMC" rule.
    """
    if not path:
        return frozenset()
    out: set[date] = set()
    with open(path) as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            d = pd.Timestamp(line).date()
            out.add(d)
            out.add((pd.Timestamp(d) - pd.Timedelta(days=1)).date())
    return frozenset(out)
