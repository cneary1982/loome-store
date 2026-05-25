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
    "off":             None,                                    # no session filter
    # ES/NQ classic cash hours
    "rth":             [(NY_MIN(9, 30), NY_MIN(15, 30))],
    # GC killzone variants
    "kz3":             [(NY_MIN(2),  NY_MIN(5)),
                        (NY_MIN(8),  NY_MIN(11)),
                        (NY_MIN(20), NY_MIN(23))],              # current default
    "kz_ny_only":      [(NY_MIN(8),  NY_MIN(11))],              # NY AM only
    "kz_ny_london":    [(NY_MIN(2),  NY_MIN(5)),
                        (NY_MIN(8),  NY_MIN(11))],              # drop Asia
    "kz_ny_wide":      [(NY_MIN(7),  NY_MIN(12))],              # broaden NY AM
    "kz_narrow":       [(NY_MIN(8, 20), NY_MIN(10, 30))],       # COMEX open + PM Fix only
    "kz_active_block": [(NY_MIN(2),  NY_MIN(16))],              # London-open through US close (continuous)
}

# Session-variants tried per (sym, tf)
SESSION_VARIANTS: dict = {
    ("ES", "15m"): ["off", "rth"],
    ("ES", "1h"):  ["off", "rth"],
    ("ES", "4h"):  ["off"],
    ("ES", "1d"):  ["off"],
    ("NQ", "15m"): ["off", "rth"],
    ("NQ", "1h"):  ["off", "rth"],
    ("NQ", "4h"):  ["off"],
    ("NQ", "1d"):  ["off"],
    ("GC", "15m"): ["off", "kz3", "kz_ny_only", "kz_ny_london",
                    "kz_ny_wide", "kz_narrow", "kz_active_block"],
    ("GC", "1h"):  ["off", "kz3", "kz_ny_only", "kz_ny_london",
                    "kz_ny_wide", "kz_narrow", "kz_active_block"],
    ("GC", "4h"):  ["off"],
    ("GC", "1d"):  ["off"],
}


# ─── Human-readable labels (for printouts + CSV column) ─────────────────────
SESSION_LABELS: dict = {
    "off":             "No session filter (24h)",
    "rth":             "ES/NQ RTH 09:30-15:30 ET (flat at 16:00)",
    "kz3":             "GC 3 killzones: London 02-05 + NY AM 08-11 + Asia 20-23 ET",
    "kz_ny_only":      "GC NY AM only: 08:00-11:00 ET",
    "kz_ny_london":    "GC London + NY AM: 02-05 + 08-11 ET (no Asia)",
    "kz_ny_wide":      "GC NY AM widened: 07:00-12:00 ET",
    "kz_narrow":       "GC narrow: 08:20-10:30 ET (COMEX open + AM Fix)",
    "kz_active_block": "GC continuous active block: 02:00-16:00 ET",
}

ALIGN_LABELS: dict = {
    0: "No HTF filter",
    1: "Require HTF EMA20 + slope alignment (1h gated by 4h+1d; 15m by 1h+4h; 4h by 1d)",
}

# Column descriptions for the CSV / GitHub readers
COLUMN_GLOSSARY = [
    ("symbol",        "Futures contract symbol (ES, NQ, GC)"),
    ("tf",            "Bar timeframe (15m, 1h, 4h, 1d)"),
    ("lookback",      "Number of bars used for the log-return regime label"),
    ("threshold",     "Log-return magnitude defining up/down regime (0.015 = 1.5%)"),
    ("atr",           "ATR(14) multiplier for take-profit and stop-loss distance (symmetric)"),
    ("align",         "HTF EMA20 trend-alignment filter: 0=off, 1=on"),
    ("align_label",   "Human-readable description of the alignment filter"),
    ("session",       "Session-window filter code (see SESSION_LABELS)"),
    ("session_label", "Human-readable description of the session filter"),
    ("trades",        "Number of completed round-trip trades"),
    ("win_rate",      "Percent of trades exited at TP (or positive partial exit)"),
    ("expectancy",    "Mean R-multiple per trade (R = atr_mult * ATR risked)"),
    ("total_R",       "Sum of R-multiples across all trades (= expectancy * trades)"),
]


def _write_readme(path: Path) -> None:
    """Write a markdown sidecar so the CSV is self-documenting on GitHub."""
    lines = ["# sweep_all.csv — column glossary", "",
             "Output of `python sweep_all.py`. Each row is one backtest configuration.", ""]
    lines += ["## Columns", "", "| Column | Description |", "|---|---|"]
    for name, desc in COLUMN_GLOSSARY:
        lines.append(f"| `{name}` | {desc} |")
    lines += ["", "## `align` values", "", "| Value | Meaning |", "|---|---|"]
    for k, v in ALIGN_LABELS.items():
        lines.append(f"| `{k}` | {v} |")
    lines += ["", "## `session` codes", "", "| Code | Window(s) |", "|---|---|"]
    for code, desc in SESSION_LABELS.items():
        lines.append(f"| `{code}` | {desc} |")
    lines += ["",
              "## Metric definitions",
              "",
              "- **R-multiple**: a trade's PnL expressed in units of risk, where 1 R = "
              "`atr_mult * ATR(14)`. A trade that hits its take-profit at "
              "`entry + atr_mult*ATR` is +1 R; the stop-loss is -1 R. Forced exits "
              "(e.g. 16:00 ET flat for ES/NQ RTH) yield fractional R based on the "
              "exit price.",
              "- **expectancy** = mean R per trade.",
              "- **total_R** = expectancy × trades. Use this when comparing configs "
              "with very different trade counts — a high per-trade expectancy with "
              "only 10 trades is less valuable than a moderate expectancy compounded "
              "over 200 trades.",
              ""]
    path.write_text("\n".join(lines))


def print_glossary():
    print("\n" + "=" * 78)
    print("BACKTEST RESULT GLOSSARY")
    print("=" * 78)
    print("\nColumns:")
    for name, desc in COLUMN_GLOSSARY:
        print(f"  {name:<14} - {desc}")
    print("\nAlignment filter values ('align' column):")
    for k, v in ALIGN_LABELS.items():
        print(f"  align={k}  - {v}")
    print("\nSession filter codes ('session' column):")
    for code, desc in SESSION_LABELS.items():
        print(f"  {code:<16} - {desc}")
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
    return sym in ("ES", "NQ") and variant == "rth"


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
        sess_choices  = SESSION_VARIANTS.get((sym, tf), ["off"])
        n_combos = (len(LOOKBACKS) * len(THRESHOLDS) * len(ATR_MULTS)
                    * len(align_choices) * len(sess_choices))
        print(f"  {sym}/{tf}: {n_combos} combos "
              f"(align×{len(align_choices)}, session×{len(sess_choices)})")
        for lb, th, am, ua, sv in itertools.product(
                LOOKBACKS, THRESHOLDS, ATR_MULTS, align_choices, sess_choices):
            entry_ok, force_flat_at = make_callables(sym, tf, bias_map, ua, sv)
            r = backtest(df, lb, th, am, entry_ok=entry_ok, force_flat_at=force_flat_at)
            rows.append({
                "symbol": sym, "tf": tf,
                "lookback": lb, "threshold": th, "atr": am,
                "align":         int(ua),
                "align_label":   ALIGN_LABELS[int(ua)],
                "session":       sv,
                "session_label": SESSION_LABELS[sv],
                "trades":     r["trades"],
                "win_rate":   r["win_rate"],
                "expectancy": r["expectancy"],
                "total_R":    round(r["expectancy"] * r["trades"], 2),
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
    idx = df.groupby(["symbol", "tf"])[args.rank].idxmax()
    best = df.loc[idx].sort_values(["symbol", "tf"])
    best_out = results / f"best_per_cell_by_{args.rank}.csv"
    best.to_csv(best_out, index=False)
    print(f"Best-per-cell written: {best_out}")
    print(f"\n=== Best per (symbol, tf) by {args.rank} ===")
    print(best.to_string(index=False))

    # GC killzone breakdown: at fixed best LB/TH/ATR/align per cell, compare KZ variants
    print("\n=== GC killzone comparison (best LB/TH/ATR/align per row, varying KZ) ===")
    gc = df[(df["symbol"] == "GC") & (df["tf"].isin(["15m", "1h"]))].copy()
    for tf in ["15m", "1h"]:
        cell = gc[gc["tf"] == tf]
        if cell.empty:
            continue
        # find best non-session-axis config, then pivot session variants
        # use median rank across all KZ variants for each (lb,th,atr,align) group
        grouped = cell.groupby(["lookback", "threshold", "atr", "align"])
        best_grp = grouped[args.rank].mean().idxmax()
        lb, th, am, al = best_grp
        sub = cell[(cell["lookback"] == lb) & (cell["threshold"] == th)
                   & (cell["atr"] == am) & (cell["align"] == al)].sort_values(args.rank, ascending=False)
        print(f"\nGC/{tf}  lookback={lb} threshold={th} atr={am} align={al}:")
        print(sub[["session", "trades", "win_rate", "expectancy", "total_R"]].to_string(index=False))

    # Top 15 overall
    print(f"\n=== Top 15 overall by {args.rank} ===")
    print(df.sort_values(args.rank, ascending=False).head(15).to_string(index=False))


if __name__ == "__main__":
    main()
