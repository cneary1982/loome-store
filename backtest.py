"""Markov regime backtest on local Barchart CSVs.

Usage:
    python backtest.py                           # uses ./data
    python backtest.py /path/to/csv/folder
    python backtest.py --sweep                   # full param grid
    python backtest.py --atr-mult 2.5

CSV format (Barchart):
    Time,Open,High,Low,Latest,Change,%Change,Volume
    "2026-03-25 23:00",24379.25,24385,24317,24324.75,-55.25,-0.23%,3276
    (newest-first; `Latest` is the close)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ─── Schema loader ──────────────────────────────────────────────────────────
# Two formats:
#   Barchart   : Time,Open,High,Low,Latest,Change,%Change,Volume    (newest-first)
#   yfinance   : timestamp,open,high,low,close,volume               (oldest-first, ISO+TZ)
def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    if "latest" in cols:                                # Barchart
        df = df.rename(columns={cols["latest"]: "Close", cols["time"]: "Time"})
        df["Time"] = pd.to_datetime(df["Time"], errors="coerce")  # footer row → NaT
        df = df[["Time", "Open", "High", "Low", "Close", "Volume"]]
        df = df.dropna(subset=["Time"])
    else:                                               # yfinance-style
        ts_col = cols.get("timestamp") or cols.get("datetime") or cols.get("date")
        df = df.rename(columns={ts_col: "Time", cols["open"]: "Open",
                                cols["high"]: "High", cols["low"]: "Low",
                                cols["close"]: "Close", cols["volume"]: "Volume"})
        df["Time"] = pd.to_datetime(df["Time"], utc=True).dt.tz_convert(None)
        df = df[["Time", "Open", "High", "Low", "Close", "Volume"]]
    df = df.sort_values("Time").set_index("Time")
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna()


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule).agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna()


# ─── Markov + ATR core (from app.py, with _label bug fixed) ─────────────────
def label(close: pd.Series, lookback: int, threshold: float) -> pd.Series:
    lr  = np.log(close / close.shift(lookback)).dropna()
    lbl = pd.Series(1, index=lr.index, dtype=int)
    lbl[lr >  threshold] = 2
    lbl[lr < -threshold] = 0
    return lbl


def transition_matrix(labels: pd.Series) -> np.ndarray:
    counts = np.zeros((3, 3))
    a = labels.to_numpy()
    for i in range(len(a) - 1):
        counts[a[i], a[i + 1]] += 1
    rs = counts.sum(axis=1, keepdims=True)
    rs[rs == 0] = 1.0
    return counts / rs


ATR_LEN = 14


def atr(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    tr   = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(ATR_LEN).mean()


def backtest(df: pd.DataFrame, lookback: int, threshold: float, atr_mult: float) -> dict:
    close  = df["Close"].values.astype(float)
    high   = df["High"].values.astype(float)
    low    = df["Low"].values.astype(float)
    atr_a  = atr(df["High"], df["Low"], df["Close"]).values.astype(float)
    labels = label(df["Close"], lookback, threshold)
    offset = len(close) - len(labels)
    lab    = labels.values.astype(int)

    wins = losses = 0
    rr_sum = 0.0          # sum of realised R-multiples (+1 or -1; here always ±1 since TP/SL = ATR_MULT*ATR)
    skip_until = 0
    for k in range(1, len(lab)):
        pos = k + offset
        if pos < skip_until:
            continue
        prev_r, curr_r = lab[k - 1], lab[k]
        if prev_r == curr_r or curr_r == 1:
            continue
        a = atr_a[pos]
        if np.isnan(a) or a == 0:
            continue
        entry = close[pos]
        long  = curr_r == 2
        tp = entry + atr_mult * a if long else entry - atr_mult * a
        sl = entry - atr_mult * a if long else entry + atr_mult * a
        for j in range(pos + 1, len(close)):
            h, l = high[j], low[j]
            if long:
                if h >= tp: wins   += 1; rr_sum += 1.0; skip_until = j + 1; break
                if l <= sl: losses += 1; rr_sum -= 1.0; skip_until = j + 1; break
            else:
                if l <= tp: wins   += 1; rr_sum += 1.0; skip_until = j + 1; break
                if h >= sl: losses += 1; rr_sum -= 1.0; skip_until = j + 1; break

    total = wins + losses
    return {
        "trades":     total,
        "wins":       wins,
        "losses":     losses,
        "win_rate":   round(wins / max(total, 1) * 100, 1),
        "expectancy": round(rr_sum / max(total, 1), 3),  # in R per trade (TP/SL are equal magnitude → always ±1)
    }


# ─── Dataset assembly ───────────────────────────────────────────────────────
TARGETS = [
    # (symbol, timeframe-label, source-file, resample-rule-or-None)
    ("ES", "15m", "ES_15m.csv",  None),
    ("ES", "1h",  "ES_60m.csv",  None),
    ("ES", "4h",  "ES_240m.csv", None),
    ("ES", "1d",  "ES_1d.csv",   None),
    ("NQ", "15m", "NQ_15m.csv",  None),
    ("NQ", "1h",  "NQ_60m.csv",  None),
    ("NQ", "4h",  "NQ_240m.csv", None),
    ("NQ", "1d",  "NQ_1d.csv",   None),
    ("GC", "15m", "GC_15m.csv",  None),
    ("GC", "1h",  "GC_60m.csv",  None),
    ("GC", "4h",  "GC_240m.csv", None),
    ("GC", "1d",  "GC_1d.csv",   None),
]


def load_dataset(folder: Path) -> dict[tuple[str, str], pd.DataFrame]:
    out = {}
    for sym, tf, fname, rule in TARGETS:
        p = folder / fname
        if not p.exists():
            print(f"  ! missing {p}", file=sys.stderr)
            continue
        df = load_csv(p)
        if rule:
            df = resample(df, rule)
        out[(sym, tf)] = df
        print(f"  {sym}/{tf}: {len(df):>5} bars  "
              f"{df.index[0]} → {df.index[-1]}")
    return out


# ─── Driver ─────────────────────────────────────────────────────────────────
DEFAULT_GRID = {
    "lookback":  [12, 20, 32, 48],
    "threshold": [0.005, 0.010, 0.015, 0.020, 0.030],
}

SINGLE_PARAMS = {
    # mirrors app.py TF_CONFIG
    "15m": {"lookback": 48, "threshold": 0.015},
    "1h":  {"lookback": 48, "threshold": 0.020},
    "4h":  {"lookback": 42, "threshold": 0.025},
    "1d":  {"lookback": 20, "threshold": 0.020},
}


def run_single(data: dict, atr_mult: float):
    rows = []
    for (sym, tf), df in data.items():
        p = SINGLE_PARAMS[tf]
        r = backtest(df, p["lookback"], p["threshold"], atr_mult)
        rows.append({"symbol": sym, "tf": tf, "lookback": p["lookback"],
                     "threshold": p["threshold"], "atr_mult": atr_mult, **r})
    return pd.DataFrame(rows)


def run_sweep(data: dict, atr_mult: float):
    rows = []
    for (sym, tf), df in data.items():
        for lb in DEFAULT_GRID["lookback"]:
            for th in DEFAULT_GRID["threshold"]:
                r = backtest(df, lb, th, atr_mult)
                rows.append({"symbol": sym, "tf": tf, "lookback": lb,
                             "threshold": th, "atr_mult": atr_mult, **r})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default="data",
                    help="Folder containing the Barchart CSVs (default: ./data)")
    ap.add_argument("--sweep", action="store_true",
                    help="Run the full lookback × threshold grid")
    ap.add_argument("--atr-mult", type=float, default=3.0,
                    help="ATR multiplier for TP/SL (default 3.0)")
    ap.add_argument("--min-trades", type=int, default=5,
                    help="Filter out param combos with fewer trades than this (sweep only)")
    args = ap.parse_args()

    folder = Path(args.folder)
    print(f"Loading from: {folder.resolve()}")
    data = load_dataset(folder)
    if not data:
        print("No data loaded — aborting.")
        sys.exit(1)

    print(f"\nATR_MULT = {args.atr_mult}")

    if args.sweep:
        res = run_sweep(data, args.atr_mult)
        res = res[res["trades"] >= args.min_trades].copy()
        print("\n=== Parameter sweep (filtered, sorted by expectancy) ===")
        print(res.sort_values(["symbol", "tf", "expectancy"],
                              ascending=[True, True, False]).to_string(index=False))
        print("\n=== Top 10 by expectancy across all (symbol, tf) ===")
        print(res.sort_values("expectancy", ascending=False).head(10).to_string(index=False))
    else:
        res = run_single(data, args.atr_mult)
        print("\n=== Backtest at dashboard params ===")
        print(res.to_string(index=False))


if __name__ == "__main__":
    main()
