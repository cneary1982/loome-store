"""Exhaustive policy sweep across every meaningful axis.

Axes per (symbol, tf) cell:
  * lookback         {12, 20, 32, 48}
  * threshold        {0.010, 0.015, 0.020, 0.025, 0.030}
  * atr_mult         {2.0, 2.5, 3.0, 3.5}
  * align            {off, on}                  (off only for 1d — no HTF above)
  * session variant  depends on (symbol, tf):
        - HTFs (4h, 1d):      ['off']
        - ES/NQ intraday:     ['off', 'rth']                       (09:30-15:30 ET + 16:00 force-flat)
        - GC intraday:        ['off', 6 killzone presets]          (see SESSION_VARIANTS)

Reports the best config per cell by total R (= expectancy × trades) and by
expectancy. Writes the full grid to data/sweep_all.csv.

Usage:
    python sweep_all.py                       # ~3-4k runs
    python sweep_all.py --min-trades 15
    python sweep_all.py --rank expectancy
"""
from __future__ import annotations

import argparse
import itertools
import time
from pathlib import Path

import pandas as pd

import filters as F
from backtest import backtest, load_dataset


# ─── Grid definitions ───────────────────────────────────────────────────────
LOOKBACKS    = [12, 20, 32, 48]
THRESHOLDS   = [0.010, 0.015, 0.020, 0.025, 0.030]
ATR_MULTS    = [2.0, 2.5, 3.0, 3.5]

# Session-window presets. Each value is a list of (start_min, end_min) NY-minute
# windows where ENTRIES are allowed.
NY_MIN = lambda h, m=0: h * 60 + m
SESSION_PRESETS: dict = {
    "all_hours":          None,                                          # no session filter (trade 24h)
    "us_market_hours":    [(NY_MIN(9, 30), NY_MIN(15, 30))],             # ES/NQ cash equity hours
    "gold_3_sessions":    [(NY_MIN(2),  NY_MIN(5)),
                           (NY_MIN(8),  NY_MIN(11)),
                           (NY_MIN(20), NY_MIN(23))],                    # London + NY AM + Asia
    "ny_morning_only":    [(NY_MIN(8),  NY_MIN(11))],
    "london_plus_ny":     [(NY_MIN(2),  NY_MIN(5)),
                           (NY_MIN(8),  NY_MIN(11))],                    # London + NY AM (no Asia)
    "ny_morning_wide":    [(NY_MIN(7),  NY_MIN(12))],                    # broadened NY AM
    "comex_open_window":  [(NY_MIN(8, 20), NY_MIN(10, 30))],             # COMEX open + AM Gold Fix
    "london_through_ny":  [(NY_MIN(2),  NY_MIN(16))],                    # London open through US close
}

# Session-variants tried per (sym, tf)
SESSION_VARIANTS: dict = {
    ("ES", "15m"): ["all_hours", "us_market_hours"],
    ("ES", "1h"):  ["all_hours", "us_market_hours"],
    ("ES", "4h"):  ["all_hours"],
    ("ES", "1d"):  ["all_hours"],
    ("NQ", "15m"): ["all_hours", "us_market_hours"],
    ("NQ", "1h"):  ["all_hours", "us_market_hours"],
    ("NQ", "4h"):  ["all_hours"],
    ("NQ", "1d"):  ["all_hours"],
    ("GC", "15m"): ["all_hours", "gold_3_sessions", "ny_morning_only", "london_plus_ny",
                    "ny_morning_wide", "comex_open_window", "london_through_ny"],
    ("GC", "1h"):  ["all_hours", "gold_3_sessions", "ny_morning_only", "london_plus_ny",
                    "ny_morning_wide", "comex_open_window", "london_through_ny"],
    ("GC", "4h"):  ["all_hours"],
    ("GC", "1d"):  ["all_hours"],
}


# ─── Human-readable labels (for printouts + CSV column) ─────────────────────
SESSION_LABELS: dict = {
    "all_hours":         "No session filter - trade 24 hours a day",
    "us_market_hours":   "US stock market hours: 09:30-15:30 ET entries; close any open trade at 16:00 ET",
    "gold_3_sessions":   "Three gold liquidity windows: London open 02:00-05:00, NY morning 08:00-11:00, Asia 20:00-23:00 ET",
    "ny_morning_only":   "NY morning only: 08:00-11:00 ET (COMEX open + 08:30 US data + 10:00 AM Gold Fix)",
    "london_plus_ny":    "London open + NY morning: 02:00-05:00 and 08:00-11:00 ET (no Asia)",
    "ny_morning_wide":   "Broader NY morning: 07:00-12:00 ET",
    "comex_open_window": "Narrow gold window: 08:20-10:30 ET (COMEX pit open through AM Gold Fix)",
    "london_through_ny": "London open through US close, continuous: 02:00-16:00 ET",
}

TREND_FILTER_LABELS: dict = {
    "off": "No higher-timeframe filter - take every signal that fires on the entry timeframe",
    "on":  ("Require higher-timeframe trend agreement: signal direction must match a 20-period EMA "
            "(plus slope) on the next-higher timeframes. 15m signals must agree with 1h and 4h. "
            "1h signals must agree with 4h and 1d. 4h signals must agree with 1d."),
}

# Column descriptions for the CSV / README readers
COLUMN_GLOSSARY = [
    ("symbol",         "Futures contract: ES (S&P 500), NQ (Nasdaq 100), GC (Gold)"),
    ("timeframe",      "Bar size of the entry signal: 15m, 1h, 4h, or 1d"),
    ("lookback",       "Number of past bars used to measure the trend (log-return window)"),
    ("threshold",      "Log-return size that flips the regime to up/down (0.015 = 1.5%)"),
    ("atr_mult",       "Multiple of ATR(14) used for the take-profit AND stop-loss distance (symmetric)"),
    ("trend_filter",   "Higher-timeframe trend filter: 'off' or 'on' (see TREND_FILTER_LABELS)"),
    ("session_window", "Which clock hours entries are allowed in (see SESSION_LABELS)"),
    ("trades",         "Number of round-trip trades the strategy took in the backtest period"),
    ("win_rate",       "Percent of trades that closed with a positive R"),
    ("expectancy",     "Average R per trade. +0.20 = each trade earned 0.20 of its risked R on average"),
    ("total_R",        "Total R across all trades (= expectancy x trades). Best single number to compare strategies"),
]


def _write_readme(path: Path) -> None:
    """Write a markdown sidecar so the CSV is self-documenting on GitHub."""
    lines = ["# sweep_all.csv — column glossary", "",
             "Output of `python sweep_all.py`. Each row is one backtest configuration.", ""]
    lines += ["## Columns", "", "| Column | Description |", "|---|---|"]
    for name, desc in COLUMN_GLOSSARY:
        lines.append(f"| `{name}` | {desc} |")
    lines += ["", "## `trend_filter` values", "", "| Value | Meaning |", "|---|---|"]
    for k, v in TREND_FILTER_LABELS.items():
        lines.append(f"| `{k}` | {v} |")
    lines += ["", "## `session_window` values", "", "| Value | Window(s) |", "|---|---|"]
    for code, desc in SESSION_LABELS.items():
        lines.append(f"| `{code}` | {desc} |")
    lines += ["",
              "## How to read the results",
              "",
              "- **R** is the unit of risk: 1 R = `atr_mult * ATR(14)`. A trade that "
              "hits its take-profit at `entry + atr_mult*ATR` returns +1 R; one that "
              "hits the stop-loss returns -1 R. Forced exits (e.g. 16:00 ET close on "
              "`us_market_hours`) return a fractional R based on the exit price.",
              "- **expectancy** is the average R per trade. +0.20 means on average each "
              "trade earned one-fifth of what was risked on it.",
              "- **total_R** = expectancy x trades. This is the best single number to "
              "compare two strategies that took different numbers of trades. A strategy "
              "with +0.40 R/trade over only 10 trades (= +4 R) is worse than one with "
              "+0.10 R/trade over 200 trades (= +20 R).",
              "",
              "## How to make this better",
              "",
              "Open ideas to try (PRs welcome):",
              "- **Asymmetric TP/SL**: separate `tp_mult` and `sl_mult` instead of one ATR.",
              "- **Trailing stop**: replace the fixed stop with a chandelier trail once "
              "price has moved +1 R in favor (highest high - k*ATR).",
              "- **Volatility-targeted sizing**: risk constant $ per trade by sizing 1/ATR.",
              "- **New session windows**: add a preset to `SESSION_PRESETS` in "
              "`sweep_all.py` and it will be tested automatically for the symbols it's "
              "listed under in `SESSION_VARIANTS`.",
              "- **Volume confirmation**: only fire entries when the breakout bar's "
              "volume is N x median(volume).",
              ""]
    path.write_text("\n".join(lines))


def print_glossary():
    print("\n" + "=" * 78)
    print("BACKTEST RESULT GLOSSARY")
    print("=" * 78)
    print("\nColumns:")
    for name, desc in COLUMN_GLOSSARY:
        print(f"  {name:<16} - {desc}")
    print("\nTrend filter ('trend_filter' column):")
    for k, v in TREND_FILTER_LABELS.items():
        print(f"  {k:<18} - {v}")
    print("\nSession windows ('session_window' column):")
    for code, desc in SESSION_LABELS.items():
        print(f"  {code:<18} - {desc}")
    print("=" * 78 + "\n")


# ─── Filter callable factory ────────────────────────────────────────────────
def _in_windows(ts, windows) -> bool:
    """ts: tz-aware. windows: list of (start_min, end_min) NY-tz minute ranges."""
    ny  = ts.tz_convert(F.NY)
    wd  = ny.weekday()
    m   = ny.hour * 60 + ny.minute
    # weekend gate matches filters.py conventions
    if wd == 5:                          # Saturday
        return False
    if wd == 6 and m < NY_MIN(18):       # Sunday before 18:00 ET reopen
        return False
    return any(start <= m < end for start, end in windows)


def _force_flat_for_variant(sym, variant) -> bool:
    """ES/NQ RTH variant forces flat at 16:00; killzone variants do NOT."""
    return sym in ("ES", "NQ") and variant == "us_market_hours"


def make_callables(sym, tf, bias_map, use_align, session_variant):
    windows = SESSION_PRESETS.get(session_variant)
    use_session = windows is not None
    entry_ok = None
    force_flat_at = None
    if use_align or use_session:
        def entry_ok(ts, side, sym=sym, tf=tf, windows=windows,
                     use_align=use_align, use_session=use_session):
            if use_session and not _in_windows(ts, windows):
                return False
            if use_align and not F.aligned(sym, tf, side, ts, bias_map):
                return False
            return True
    if use_session and _force_flat_for_variant(sym, session_variant):
        def force_flat_at(ts):
            return F.esnq_force_flat(ts)
    return entry_ok, force_flat_at


# ─── Driver ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-trades", type=int, default=10)
    ap.add_argument("--rank", choices=["total_R", "expectancy"], default="total_R")
    ap.add_argument("--no-glossary", action="store_true",
                    help="Skip the glossary header")
    args = ap.parse_args()

    if not args.no_glossary:
        print_glossary()

    data = load_dataset(Path("data"))
    bias_map = F.build_bias_map(data)

    rows = []
    t0 = time.time()
    for (sym, tf), df in data.items():
        align_choices = (False,) if tf == "1d" else (False, True)
        sess_choices  = SESSION_VARIANTS.get((sym, tf), ["all_hours"])
        n_combos = (len(LOOKBACKS) * len(THRESHOLDS) * len(ATR_MULTS)
                    * len(align_choices) * len(sess_choices))
        print(f"  {sym}/{tf}: {n_combos} combos "
              f"(trend_filter x{len(align_choices)}, session_window x{len(sess_choices)})")
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
    out = results / "sweep_all.csv"
    df_all.to_csv(out, index=False)
    _write_readme(results / "README.md")
    print(f"Full grid written: {out}")
    print(f"Glossary written:  {results / 'README.md'}")

    df = df_all[df_all["trades"] >= args.min_trades].copy()
    print(f"After min_trades={args.min_trades}: {len(df):,} rows")

    # Best per (sym, tf) by chosen rank metric
    idx = df.groupby(["symbol", "timeframe"])[args.rank].idxmax()
    best = df.loc[idx].sort_values(["symbol", "timeframe"])
    best_out = results / f"best_per_cell_by_{args.rank}.csv"
    best.to_csv(best_out, index=False)
    print(f"Best-per-cell written: {best_out}")
    print(f"\n=== Best per (symbol, timeframe) by {args.rank} ===")
    print(best.to_string(index=False))

    # GC session-window breakdown: at the best non-session config per cell,
    # show how each session_window compares.
    print("\n=== GC session-window comparison "
          "(best lookback/threshold/atr_mult/trend_filter per row, varying session_window) ===")
    gc = df[(df["symbol"] == "GC") & (df["timeframe"].isin(["15m", "1h"]))].copy()
    for tf in ["15m", "1h"]:
        cell = gc[gc["timeframe"] == tf]
        if cell.empty:
            continue
        grouped = cell.groupby(["lookback", "threshold", "atr_mult", "trend_filter"])
        best_grp = grouped[args.rank].mean().idxmax()
        lb, th, am, tfilt = best_grp
        sub = cell[(cell["lookback"] == lb) & (cell["threshold"] == th)
                   & (cell["atr_mult"] == am) & (cell["trend_filter"] == tfilt)].sort_values(args.rank, ascending=False)
        print(f"\nGC/{tf}  lookback={lb} threshold={th} atr_mult={am} trend_filter={tfilt}:")
        print(sub[["session_window", "trades", "win_rate", "expectancy", "total_R"]].to_string(index=False))

    # Top 15 overall
    print(f"\n=== Top 15 overall by {args.rank} ===")
    print(df.sort_values(args.rank, ascending=False).head(15).to_string(index=False))


if __name__ == "__main__":
    main()
