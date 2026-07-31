"""PO3 primitives: bar loading, 4H PO3 windows, FVG / IFVG / CISD, swing structure.

Everything here is *causal* — no function may look at a bar later than the one it
is asked about. The backtest depends on that; see `PO3.md` for the audit notes.

Timestamps are tz-aware UTC on the index; all clock logic converts to
America/New_York through zoneinfo so DST is handled correctly.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")

# The 4H candle opens we trade. On CME's 18:00 ET session start the 4H boundaries
# land on 18/22/02/06/10/14 ET — which is exactly why the 10:00 and 14:00 candles
# are the two NY-session opens the PO3 Bible builds the model around.
PO3_OPEN_HOURS = (10, 14)
CME_4H_ANCHORS = (18, 22, 2, 6, 10, 14)


# ─── Loading ────────────────────────────────────────────────────────────────
def load_bars(path: str | Path) -> pd.DataFrame:
    """Read a CSV into an OHLCV frame indexed by tz-aware UTC timestamps.

    Handles both schemas that live in `data/`:
      Databento/yfinance : timestamp,open,high,low,close,volume   (oldest-first, ISO+TZ)
      Barchart           : Time,Open,High,Low,Latest,...,Volume   (newest-first, no TZ)

    Barchart exports carry a trailing "Downloaded from Barchart.com..." line and
    quote their timestamps; both are dropped here. Barchart stamps are naive
    US/Central, so they are localised to Chicago before converting to UTC.
    """
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}

    if "latest" in cols:  # Barchart
        df = df.rename(columns={cols["latest"]: "Close", cols["time"]: "Time"})
        df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
        df = df.dropna(subset=["Time"])
        df["Time"] = (
            df["Time"].dt.tz_localize(
                "America/Chicago", ambiguous=True, nonexistent="shift_forward"
            ).dt.tz_convert("UTC")
        )
    else:  # Databento / yfinance
        ts_col = cols.get("timestamp") or cols.get("datetime") or cols.get("date")
        df = df.rename(
            columns={
                ts_col: "Time",
                cols["open"]: "Open",
                cols["high"]: "High",
                cols["low"]: "Low",
                cols["close"]: "Close",
                cols["volume"]: "Volume",
            }
        )
        df["Time"] = pd.to_datetime(df["Time"], utc=True, errors="coerce")
        df = df.dropna(subset=["Time"])

    df = df[["Time", "Open", "High", "Low", "Close", "Volume"]]
    for c in ("Open", "High", "Low", "Close", "Volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna().sort_values("Time").set_index("Time")
    return df[~df.index.duplicated(keep="first")]


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample OHLCV. Bars are label=left/closed=left, so a bar stamped 10:00
    covers [10:00, 10:00+rule) — the convention the rest of the code assumes."""
    out = df.resample(rule, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    )
    return out.dropna(subset=["Open", "High", "Low", "Close"])


def to_ny(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return idx.tz_convert(NY)


def ny_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Attach NY-local date/hour/minute columns used by the session logic."""
    ny = to_ny(df.index)
    out = df.copy()
    out["ny_date"] = ny.date
    out["ny_dow"] = ny.dayofweek          # Mon=0
    out["ny_min"] = ny.hour * 60 + ny.minute
    return out


def daily_from_intraday(df: pd.DataFrame) -> pd.DataFrame:
    """Daily OHLC keyed by NY calendar date.

    NY calendar day (not the 18:00 ET futures session day) is used deliberately:
    it matches the "previous day's high" a trader reads off a daily chart, which
    is what the Bible calls the main draw on liquidity.
    """
    f = ny_frame(df)
    g = f.groupby("ny_date")
    out = pd.DataFrame(
        {
            "Open": g["Open"].first(),
            "High": g["High"].max(),
            "Low": g["Low"].min(),
            "Close": g["Close"].last(),
            "Volume": g["Volume"].sum(),
        }
    )
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


# ─── ATR ────────────────────────────────────────────────────────────────────
def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Wilder ATR. Shifted by one bar by the callers that need it."""
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


# ─── Fair Value Gaps ────────────────────────────────────────────────────────
@dataclass
class FVG:
    ts: pd.Timestamp      # timestamp of the 3rd (confirming) candle
    kind: str             # 'bull' | 'bear'
    top: float
    bottom: float

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def size(self) -> float:
        return self.top - self.bottom

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top


def find_fvgs(df: pd.DataFrame, min_size: float = 0.0) -> list[FVG]:
    """Three-candle imbalances.

    bullish : low[i] > high[i-2]  → unfilled buy-side gap [high[i-2], low[i]]
    bearish : high[i] < low[i-2]  → unfilled sell-side gap [high[i], low[i-2]]

    The FVG is only *known* once candle i closes, so `ts` is candle i's stamp and
    callers must not consult a gap before that stamp.
    """
    if len(df) < 3:
        return []
    h = df["High"].to_numpy()
    l = df["Low"].to_numpy()
    ts = df.index

    out: list[FVG] = []
    for i in range(2, len(df)):
        if l[i] > h[i - 2] and (l[i] - h[i - 2]) >= min_size:
            out.append(FVG(ts[i], "bull", top=l[i], bottom=h[i - 2]))
        elif h[i] < l[i - 2] and (l[i - 2] - h[i]) >= min_size:
            out.append(FVG(ts[i], "bear", top=l[i - 2], bottom=h[i]))
    return out


def unfilled_at(
    fvgs: list[FVG], df: pd.DataFrame, when: pd.Timestamp, lookback_bars: int = 12
) -> list[FVG]:
    """FVGs formed in the last `lookback_bars` bars before `when` that price has
    not yet traded fully through.

    "Filled" means price closed the gap completely: for a bullish gap, trade at or
    below its bottom; for a bearish gap, trade at or above its top. A partial tap
    leaves the array live, which is the behaviour the manipulation leg relies on.

    Straightforward but O(n) per gap — `FVGBook` is the version to use in a loop.
    """
    if not fvgs:
        return []
    window = df.loc[:when]
    if window.empty:
        return []
    cutoff = window.index[max(0, len(window) - lookback_bars)]

    live: list[FVG] = []
    for g in fvgs:
        if g.ts > when or g.ts < cutoff:
            continue
        after = df.loc[df.index > g.ts]
        after = after.loc[after.index <= when]
        if after.empty:
            live.append(g)
            continue
        if g.kind == "bull" and after["Low"].min() <= g.bottom:
            continue
        if g.kind == "bear" and after["High"].max() >= g.top:
            continue
        live.append(g)
    return live


def ns(ts) -> int:
    """Timestamp → int64 nanoseconds since epoch, UTC.

    pandas 3 hands back datetime64[us] from `resample`, so `DatetimeIndex.asi8`
    and `Timestamp.value` can disagree by a factor of 1000. Everything that
    compares timestamps as integers goes through here or `ns_array`.
    """
    return pd.Timestamp(ts).as_unit("ns").value


def ns_array(idx: pd.DatetimeIndex) -> np.ndarray:
    """DatetimeIndex → int64 nanoseconds since epoch, UTC."""
    return idx.tz_convert("UTC").tz_localize(None).to_numpy("datetime64[ns]").astype("int64")


class FVGBook:
    """All FVGs on a series, each tagged with the bar that finally filled it.

    Fill timestamps are resolved once up front, so asking "which arrays are still
    live at 10:00 today?" is a couple of binary searches instead of a rescan. The
    answer is identical to `unfilled_at` — a gap counts as live at `when` when it
    printed at or before `when` and had not been traded through by then.

    A gap still open after `max_scan` bars is treated as never filled; any
    realistic `lookback_bars` has long since expired it.
    """

    def __init__(self, bars: pd.DataFrame, min_size: float = 0.0, max_scan: int = 800):
        self.bars = bars
        self.fvgs = find_fvgs(bars, min_size)

        idx = bars.index
        high = bars["High"].to_numpy()
        low = bars["Low"].to_numpy()
        pos = {t: i for i, t in enumerate(idx)}

        fill: list[int] = []          # int64 ns, or NaT sentinel
        born: list[int] = []
        for g in self.fvgs:
            i = pos[g.ts]
            stop = min(len(idx), i + 1 + max_scan)
            if g.kind == "bull":
                hits = np.nonzero(low[i + 1 : stop] <= g.bottom)[0]
            else:
                hits = np.nonzero(high[i + 1 : stop] >= g.top)[0]
            fill.append(ns(idx[i + 1 + hits[0]]) if len(hits) else np.iinfo(np.int64).max)
            born.append(ns(g.ts))

        self._born = np.asarray(born, dtype="int64")
        self._fill = np.asarray(fill, dtype="int64")
        self._idx_ns = ns_array(idx)

    def live(
        self,
        when: pd.Timestamp,
        lookback_bars: int,
        kind: str | None = None,
        born_asof: pd.Timestamp | None = None,
    ) -> list[FVG]:
        """Arrays still unmitigated at `when`.

        `born_asof` caps which gaps are allowed to *exist* yet, separately from
        the fill check. Pass `when - timeframe` to admit only gaps whose third
        candle has actually closed — otherwise a gap stamped exactly at `when`
        would be used before it printed.
        """
        if not self.fvgs:
            return []
        w = ns(when)
        b = w if born_asof is None else ns(born_asof)
        # Bar containing `when`, then step back `lookback_bars` for the cutoff.
        i = int(np.searchsorted(self._idx_ns, w, side="right")) - 1
        if i < 0:
            return []
        cutoff = self._idx_ns[max(0, i - lookback_bars + 1)]

        ok = (self._born <= b) & (self._born >= cutoff) & (self._fill > w)
        out = [self.fvgs[j] for j in np.nonzero(ok)[0]]
        return [g for g in out if kind is None or g.kind == kind]


# ─── CISD (Change In State of Delivery) ─────────────────────────────────────
def cisd_level(df: pd.DataFrame, upto: pd.Timestamp, direction: str) -> float | None:
    """Level that flips delivery, measured off the leg that ends at `upto`.

    Bullish (direction='long'): walk back from `upto` over the run of down-close
    candles that produced the manipulation low; the level is the OPEN of the
    earliest candle in that run. A close above it is the Bible's "last move down
    candle body getting closed above".

    Bearish is the mirror: open of the earliest up-close candle in the run.
    """
    w = df.loc[:upto]
    if w.empty:
        return None
    o = w["Open"].to_numpy()
    c = w["Close"].to_numpy()

    i = len(w) - 1
    down = direction == "long"
    # Step back to the last candle that belongs to the manipulation leg.
    while i >= 0 and ((c[i] >= o[i]) if down else (c[i] <= o[i])):
        i -= 1
    if i < 0:
        return None
    j = i
    while j - 1 >= 0 and ((c[j - 1] < o[j - 1]) if down else (c[j - 1] > o[j - 1])):
        j -= 1
    return float(o[j])


# ─── Swing structure → HH / HL / LH / LL ────────────────────────────────────
def swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    """Fractal swing highs/lows.

    A swing at bar i is only confirmed once `right` further bars have printed, so
    the returned frame carries `confirm_ts` — the stamp at which the swing became
    knowable. Bias code keys off `confirm_ts`, never off `ts`, to stay causal.
    """
    n = len(df)
    if n < left + right + 1:
        return pd.DataFrame(columns=["ts", "confirm_ts", "kind", "price"])

    h = df["High"].to_numpy()
    l = df["Low"].to_numpy()
    ts = df.index

    rows = []
    for i in range(left, n - right):
        seg_h = h[i - left : i + right + 1]
        seg_l = l[i - left : i + right + 1]
        if h[i] == seg_h.max() and (seg_h == h[i]).sum() == 1:
            rows.append((ts[i], ts[i + right], "high", float(h[i])))
        elif l[i] == seg_l.min() and (seg_l == l[i]).sum() == 1:
            rows.append((ts[i], ts[i + right], "low", float(l[i])))

    return pd.DataFrame(rows, columns=["ts", "confirm_ts", "kind", "price"])


def structure_bias(sw: pd.DataFrame, when: pd.Timestamp) -> int:
    """+1 for HH+HL, -1 for LH+LL, 0 when the two disagree.

    Uses only swings confirmed at or before `when`.
    """
    if sw.empty:
        return 0
    vis = sw[sw["confirm_ts"] <= when]
    highs = vis[vis["kind"] == "high"]["price"].to_numpy()
    lows = vis[vis["kind"] == "low"]["price"].to_numpy()
    if len(highs) < 2 or len(lows) < 2:
        return 0

    hh = highs[-1] > highs[-2]
    hl = lows[-1] > lows[-2]
    if hh and hl:
        return 1
    if not hh and not hl:
        return -1
    return 0


# ─── PO3 windows ────────────────────────────────────────────────────────────
@dataclass
class Window:
    """One 4H PO3 candle: the 10:00 or the 14:00 ET open."""
    ny_date: object
    hour: int                 # 10 or 14
    open_ts: pd.Timestamp     # first bar at/after the 4H open
    end_ts: pd.Timestamp      # hard flat time (4H close or forced session flat)
    open_price: float


def po3_windows(
    df: pd.DataFrame,
    hours: tuple[int, ...] = PO3_OPEN_HOURS,
    flat_minute: dict[int, int] | None = None,
) -> list[Window]:
    """Build the tradeable 4H windows.

    The 10:00 candle runs to 14:00 ET. The 14:00 candle nominally runs to 18:00,
    but is cut at 16:00 ET by default so nothing is carried through the equity
    close — override via `flat_minute` for a 24h futures run.
    """
    flat_minute = flat_minute or {10: 14 * 60, 14: 16 * 60}
    f = ny_frame(df)
    out: list[Window] = []

    for (d, hr), grp in f.groupby(["ny_date", (f["ny_min"] // 60)], sort=True):
        if hr not in hours:
            continue
        start_min = hr * 60
        seg = grp[grp["ny_min"] >= start_min]
        if seg.empty:
            continue
        open_ts = seg.index[0]

        day = f[f["ny_date"] == d]
        end_min = flat_minute.get(hr, start_min + 240)
        tail = day[day["ny_min"] <= end_min]
        end_ts = tail.index[-1] if not tail.empty else day.index[-1]
        if end_ts <= open_ts:
            continue

        out.append(
            Window(
                ny_date=d,
                hour=hr,
                open_ts=open_ts,
                end_ts=end_ts,
                open_price=float(seg["Open"].iloc[0]),
            )
        )

    out.sort(key=lambda w: w.open_ts)
    return out
