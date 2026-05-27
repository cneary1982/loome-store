"""ETF sweep — same grid as sweep_all.py, but targets SPY/QQQ/GLD.

Reads 5m bars from `data/etf/` and resamples up to 15m, 1h, 4h, 1d.
Session variants are restricted to RTH presets since ETFs are stock-market
instruments — there's no overnight session for them the way there is for
ES/NQ/GC.

Usage:
    python sweep_etf.py
    python sweep_etf.py --min-trades 15
    python sweep_etf.py --rank expectancy
"""
from __future__ import annotations

import argparse
import itertools
import time
from pathlib import Path

import pandas as pd

import filters as F
from backtest import backtest, load_csv, resample
from sweep_all import (
    ATR_MULTS, LOOKBACKS, THRESHOLDS,
    SESSION_PRESETS, _in_windows, print_glossary,
)


# ─── ETF dataset (5m → resampled) ───────────────────────────────────────────
ETF_TARGETS = [
    # (symbol, tf-label, source-file-in-data/etf, resample-rule)
    ("SPY", "15m", "SPY_5m_2yr.csv", "15min"),
    ("SPY", "1h",  "SPY_5m_2yr.csv", "60min"),
    ("SPY", "4h",  "SPY_5m_2yr.csv", "240min"),
    ("SPY", "1d",  "SPY_5m_2yr.csv", "1D"),
    ("QQQ", "15m", "QQQ_5m_2yr.csv", "15min"),
    ("QQQ", "1h",  "QQQ_5m_2yr.csv", "60min"),
    ("QQQ", "4h",  "QQQ_5m_2yr.csv", "240min"),
    ("QQQ", "1d",  "QQQ_5m_2yr.csv", "1D"),
    ("GLD", "15m", "GLD_5m_2yr.csv", "15min"),
    ("GLD", "1h",  "GLD_5m_2yr.csv", "60min"),
    ("GLD", "4h",  "GLD_5m_2yr.csv", "240min"),
    ("GLD", "1d",  "GLD_5m_2yr.csv", "1D"),
]


def load_etf_dataset(folder: Path) -> dict[tuple[str, str], pd.DataFrame]:
    out, cache = {}, {}
    for sym, tf, fname, rule in ETF_TARGETS:
        p = folder / fname
        if not p.exists():
            print(f"  ! missing {p}")
            continue
        if fname not in cache:
            cache[fname] = load_csv(p)
        df = resample(cache[fname], rule) if rule else cache[fname]
        out[(sym, tf)] = df
        print(f"  {sym}/{tf}: {len(df):>5} bars  {df.index[0]} → {df.index[-1]}")
    return out


# ETFs: only RTH-based sessions are meaningful (no overnight session)
ETF_SESSION_VARIANTS: dict = {
    "15m": ["all_hours", "us_market_hours"],
    "1h":  ["all_hours", "us_market_hours"],
    "4h":  ["all_hours"],
    "1d":  ["all_hours"],
}


def _force_flat_etf(sym, variant) -> bool:
    """All ETFs force-flat at 16:00 ET on the us_market_hours variant."""
    return variant == "us_market_hours"


def make_callables(sym, tf, bias_map, use_align, session_variant):
    windows = SESSION_PRESETS.get(session_variant)
    use_session = windows is not None
    entry_ok = force_flat_at = None
    if use_align or use_session:
        def entry_ok(ts, side, sym=sym, tf=tf, windows=windows,
                     use_align=use_align, use_session=use_session):
            if use_session and not _in_windows(ts, windows):
                return False
            if use_align and not F.aligned(sym, tf, side, ts, bias_map):
                return False
            return True
    if use_session and _force_flat_etf(sym, session_variant):
        def force_flat_at(ts):
            return F.esnq_force_flat(ts)
    return entry_ok, force_flat_at


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-trades", type=int, default=10)
    ap.add_argument("--rank", choices=["total_R", "expectancy"], default="total_R")
    ap.add_argument("--no-glossary", action="store_true")
    args = ap.parse_args()

    if not args.no_glossary:
        print_glossary()

    data = load_etf_dataset(Path("data/etf"))
    if not data:
        print("No ETF data found in data/etf/")
        return

    # Build bias map: aligned() needs HTFs for the same symbol. Each ETF has
    # its own HTF series in `data`, so we can reuse build_bias_map directly.
    bias_map = F.build_bias_map(data)

    rows = []
    t0 = time.time()
    for (sym, tf), df in data.items():
        align_choices = (False,) if tf == "1d" else (False, True)
        sess_choices  = ETF_SESSION_VARIANTS.get(tf, ["all_hours"])
        n_combos = (len(LOOKBACKS) * len(THRESHOLDS) * len(ATR_MULTS)
                    * len(align_choices) * len(sess_choices))
        print(f"  {sym}/{tf}: {n_combos} combos")
        for lb, th, am, ua, sv in itertools.product(
                LOOKBACKS, THRESHOLDS, ATR_MULTS, align_choices, sess_choices):
            entry_ok, force_flat_at = make_callables(sym, tf, bias_map, ua, sv)
            r = backtest(df, lb, th, am, entry_ok=entry_ok, force_flat_at=force_flat_at)
            rows.append({
                "symbol":         sym,
                "timeframe":      tf,
                "lookback":       lb,
                "threshold":      th,
                "atr_mult":       am,
                "trend_filter":   "on" if ua else "off",
                "session_window": sv,
                "trades":         r["trades"],
                "win_rate":       r["win_rate"],
                "expectancy":     r["expectancy"],
                "total_R":        round(r["expectancy"] * r["trades"], 2),
            })
    elapsed = time.time() - t0
    print(f"\nRan {len(rows):,} backtests in {elapsed:.1f}s "
          f"({len(rows)/elapsed:.0f} runs/s)")

    df_all = pd.DataFrame(rows)
    results = Path("results"); results.mkdir(exist_ok=True)
    out = results / "sweep_etf.csv"
    df_all.to_csv(out, index=False)
    print(f"Full grid written: {out}")

    df = df_all[df_all["trades"] >= args.min_trades].copy()
    print(f"After min_trades={args.min_trades}: {len(df):,} rows")

    idx = df.groupby(["symbol", "timeframe"])[args.rank].idxmax()
    best = df.loc[idx].sort_values(["symbol", "timeframe"])
    best_out = results / f"best_per_cell_etf_by_{args.rank}.csv"
    best.to_csv(best_out, index=False)
    print(f"Best-per-cell written: {best_out}")
    print(f"\n=== Best per (symbol, timeframe) by {args.rank} ===")
    print(best.to_string(index=False))

    print(f"\n=== Top 15 overall by {args.rank} ===")
    print(df.sort_values(args.rank, ascending=False).head(15).to_string(index=False))


if __name__ == "__main__":
    main()
