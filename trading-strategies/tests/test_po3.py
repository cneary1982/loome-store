"""Tests for the PO3 primitives and the causality guarantee.

Run with pytest, or directly:  python tests/test_po3.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from po3.core import (  # noqa: E402
    NY,
    FVGBook,
    cisd_level,
    find_fvgs,
    ns,
    po3_windows,
    resample,
    structure_bias,
    swings,
    unfilled_at,
)
from po3.gate import DayGate, GateConfig  # noqa: E402
from po3.runner import PO3Session  # noqa: E402
from po3.strategy import PO3Config  # noqa: E402
from po3.report import trades_frame  # noqa: E402
from po3 import BiasConfig, RunConfig, load_bars  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"


def frame(rows, start="2025-01-02 14:30", freq="5min"):
    """rows = [(open, high, low, close), ...] → OHLCV frame on a UTC index."""
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "Open": [r[0] for r in rows],
            "High": [r[1] for r in rows],
            "Low": [r[2] for r in rows],
            "Close": [r[3] for r in rows],
            "Volume": [100] * len(rows),
        },
        index=idx,
    )


# ─── FVG ────────────────────────────────────────────────────────────────────
def test_bullish_fvg():
    # bar0 high=10, bar2 low=12 → gap [10, 12]
    df = frame([(9, 10, 8, 10), (10, 13, 10, 13), (13, 14, 12, 13)])
    g = find_fvgs(df)
    assert len(g) == 1, g
    assert g[0].kind == "bull"
    assert (g[0].bottom, g[0].top) == (10, 12)
    assert g[0].ts == df.index[2], "FVG must be stamped on the confirming candle"


def test_bearish_fvg():
    # bar0 low=12, bar2 high=10 → gap [10, 12]
    df = frame([(13, 14, 12, 12), (12, 12, 9, 9), (9, 10, 8, 9)])
    g = find_fvgs(df)
    assert len(g) == 1 and g[0].kind == "bear"
    assert (g[0].bottom, g[0].top) == (10, 12)


def test_no_fvg_when_overlapping():
    df = frame([(9, 11, 8, 10), (10, 12, 9, 11), (11, 13, 10, 12)])
    assert find_fvgs(df) == []


def test_fvg_min_size():
    df = frame([(9, 10, 8, 10), (10, 13, 10, 13), (13, 14, 12, 13)])
    assert len(find_fvgs(df, min_size=1.0)) == 1
    assert find_fvgs(df, min_size=5.0) == []


# ─── CISD ───────────────────────────────────────────────────────────────────
def test_cisd_long_takes_open_of_first_down_candle():
    # two up candles, then a three-candle down run: opens 20, 18, 16
    df = frame([
        (10, 11, 9, 11),
        (11, 13, 11, 13),
        (20, 20, 17, 17),   # first of the down run
        (18, 18, 15, 15),
        (16, 16, 13, 13),
    ])
    assert cisd_level(df, df.index[-1], "long") == 20.0


def test_cisd_short_mirrors():
    df = frame([
        (20, 21, 19, 19),
        (10, 13, 10, 13),   # first of the up run
        (13, 16, 13, 16),
        (16, 18, 16, 18),
    ])
    assert cisd_level(df, df.index[-1], "short") == 10.0


def test_cisd_none_when_no_leg():
    df = frame([(10, 11, 9, 11), (11, 12, 10, 12)])
    assert cisd_level(df, df.index[-1], "long") is None


# ─── swings / structure ─────────────────────────────────────────────────────
def test_swing_confirm_lags_by_right():
    rows = [(10, 10, 9, 10)] * 2 + [(10, 20, 9, 10)] + [(10, 10, 9, 10)] * 2
    df = frame(rows)
    sw = swings(df, 2, 2)
    hi = sw[sw["kind"] == "high"].iloc[0]
    assert hi["ts"] == df.index[2]
    assert hi["confirm_ts"] == df.index[4], "a swing is only knowable `right` bars later"


def test_structure_bias_hh_hl():
    sw = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC"),
        "confirm_ts": pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC"),
        "kind": ["high", "low", "high", "low"],
        "price": [10.0, 5.0, 12.0, 7.0],      # HH + HL
    })
    when = sw["confirm_ts"].iloc[-1]
    assert structure_bias(sw, when) == 1
    # only the first two swings visible → not enough of each kind
    assert structure_bias(sw, sw["confirm_ts"].iloc[1]) == 0


# ─── FVGBook ────────────────────────────────────────────────────────────────
def test_fvgbook_matches_reference():
    rng = np.random.default_rng(7)
    px = 100 + np.cumsum(rng.normal(0, 0.4, 900))
    rows = []
    for i, p in enumerate(px):
        o = p
        c = p + rng.normal(0, 0.3)
        rows.append((o, max(o, c) + abs(rng.normal(0, 0.2)),
                     min(o, c) - abs(rng.normal(0, 0.2)), c))
    df = frame(rows)
    fv, book = find_fvgs(df), FVGBook(df)
    for i in range(50, len(df), 37):
        when = df.index[i]
        for lb in (5, 12, 30):
            a = sorted((g.ts, g.kind) for g in unfilled_at(fv, df, when, lb))
            b = sorted((g.ts, g.kind) for g in book.live(when, lb))
            assert a == b, (when, lb)


def test_fvgbook_born_asof_excludes_unclosed_bar():
    df = frame([(9, 10, 8, 10), (10, 13, 10, 13), (13, 14, 12, 13)])
    book = FVGBook(df)
    ts = df.index[2]
    assert len(book.live(ts, 10)) == 1
    # the gap's own candle has not closed yet at its open stamp
    assert book.live(ts, 10, born_asof=ts - pd.Timedelta("5min")) == []


# ─── PO3 windows ────────────────────────────────────────────────────────────
def _two_day_5m():
    idx = pd.date_range("2025-03-03 09:00", "2025-03-04 20:00", freq="5min", tz=NY)
    idx = idx.tz_convert("UTC")
    n = len(idx)
    return pd.DataFrame(
        {"Open": np.arange(n, dtype=float), "High": np.arange(n) + 1.0,
         "Low": np.arange(n) - 1.0, "Close": np.arange(n, dtype=float),
         "Volume": np.ones(n)},
        index=idx,
    )


def test_windows_anchor_on_ny_clock():
    df = _two_day_5m()
    ws = po3_windows(df)
    assert {w.hour for w in ws} == {10, 14}
    for w in ws:
        ny = w.open_ts.tz_convert(NY)
        assert (ny.hour, ny.minute) == (w.hour, 0)


def test_window_end_respects_flat_minute():
    df = _two_day_5m()
    ws = po3_windows(df, flat_minute={10: 14 * 60, 14: 16 * 60})
    for w in ws:
        end_ny = w.end_ts.tz_convert(NY)
        cap = 14 * 60 if w.hour == 10 else 16 * 60
        assert end_ny.hour * 60 + end_ny.minute <= cap
        assert w.end_ts > w.open_ts


def test_windows_survive_dst_switch():
    # US DST began 2025-03-09; the NY clock anchor must hold either side of it.
    idx = pd.date_range("2025-03-07 08:00", "2025-03-11 18:00", freq="15min", tz=NY)
    idx = idx.tz_convert("UTC")
    n = len(idx)
    df = pd.DataFrame(
        {"Open": np.ones(n), "High": np.ones(n) + 1, "Low": np.ones(n) - 1,
         "Close": np.ones(n), "Volume": np.ones(n)}, index=idx)
    for w in po3_windows(df):
        ny = w.open_ts.tz_convert(NY)
        assert (ny.hour, ny.minute) == (w.hour, 0), ny


# ─── gate ───────────────────────────────────────────────────────────────────
def test_pm_window_needs_a_big_day():
    df = _two_day_5m()
    g = DayGate(df, GateConfig())
    d = sorted(g.stats.index)[-1]
    g.stats.loc[d, "atr"] = 10.0
    g.stats.loc[d, "am_range_atr"] = 0.10          # quiet morning
    assert not g.check(d, 14).allow
    g.stats.loc[d, "am_range_atr"] = 2.00          # expanded morning
    assert g.check(d, 14).allow


def test_pm_blocked_when_am_already_traded():
    df = _two_day_5m()
    g = DayGate(df, GateConfig())
    d = sorted(g.stats.index)[-1]
    g.stats.loc[d, "atr"] = 10.0
    g.stats.loc[d, "am_range_atr"] = 2.00
    assert g.check(d, 14, am_traded=False).allow
    assert not g.check(d, 14, am_traded=True).allow


def test_gate_rebind_keeps_stats():
    df = _two_day_5m()
    g = DayGate(df, GateConfig())
    g2 = g.rebind(GateConfig(pm_big_day_range_atr=99.0))
    assert g2.stats is g.stats
    assert g2.cfg.pm_big_day_range_atr == 99.0


# ─── end-to-end causality ───────────────────────────────────────────────────
def test_no_lookahead_under_truncation():
    path = DATA / "etf" / "SPY_5m_2yr.csv"
    if not path.exists():
        print("  (skipped: SPY data not present)")
        return
    bars = load_bars(path)
    cfg = RunConfig(bias=BiasConfig(min_score=1.0),
                    po3=PO3Config(min_confs=1, require_fvg_tap=False))
    full = trades_frame(PO3Session(bars).run(cfg)[0])

    cut = pd.Timestamp("2025-09-01", tz="UTC")
    part = trades_frame(PO3Session(bars.loc[bars.index < cut]).run(cfg)[0])

    cols = ["entry_ts", "entry", "stop", "target", "exit_ts", "exit", "r"]
    a = full[full["exit_ts"] < cut].reset_index(drop=True)
    b = part[part["exit_ts"] < cut].reset_index(drop=True)
    assert len(a) == len(b), f"trade count changed: {len(a)} vs {len(b)}"
    assert a[cols].equals(b[cols]), "a completed trade changed when future bars were removed"


def test_costs_only_reduce_r():
    path = DATA / "etf" / "SPY_5m_2yr.csv"
    if not path.exists():
        print("  (skipped: SPY data not present)")
        return
    bars = load_bars(path)
    sess = PO3Session(bars)
    base = RunConfig(bias=BiasConfig(min_score=1.0),
                     po3=PO3Config(min_confs=1, require_fvg_tap=False))
    costly = RunConfig(bias=BiasConfig(min_score=1.0),
                       po3=PO3Config(min_confs=1, require_fvg_tap=False,
                                     cost_per_side=0.02))
    a = trades_frame(sess.run(base)[0])
    b = trades_frame(sess.run(costly)[0])
    assert len(a) == len(b), "costs must not change which setups are taken"
    assert (b["r"] <= a["r"] + 1e-9).all()
    assert b["r"].sum() < a["r"].sum()


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
