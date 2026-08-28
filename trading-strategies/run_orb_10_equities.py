"""Pull 5m bars for 10 equities from yfinance and run 15/30-min ORB.

yfinance caps 5m data at 60 days. That gives ~60 trading days × 78 bars
= ~4,700 bars per symbol, ~50-60 ORB trades. Smaller sample than the
2-year ETF data we already had, but enough for a directional read.

Tickers: 10 liquid mega-caps + index ETFs.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

from backtest_generic import backtest_strategy
from strategies_lib import OpeningRangeBreakout

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
           "META", "TSLA", "AMD",  "NFLX", "COIN"]

DATA_DIR = Path("data/equities")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _to_our_format(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # yfinance returns MultiIndex columns when single ticker; flatten
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df.index.name = "Time"
    df = df.reset_index().rename(columns={"Datetime": "Time"})
    if "Datetime" in df.columns:
        df = df.rename(columns={"Datetime": "Time"})
    if "Time" not in df.columns and "Date" in df.columns:
        df = df.rename(columns={"Date": "Time"})
    # Keep only the cols we need, renamed to lowercase as our loader expects
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume"
    })
    df["Time"] = pd.to_datetime(df["Time"], utc=True)
    out = df[["Time", "open", "high", "low", "close", "volume"]].copy()
    out.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    return out


def fetch_or_load(ticker: str) -> pd.DataFrame:
    p = DATA_DIR / f"{ticker}_5m_60d.csv"
    if p.exists():
        print(f"  cached: {p.name}")
        return None  # Already cached, will be loaded by load_csv later
    print(f"  downloading 5m × 60d for {ticker}…")
    df = yf.download(ticker, period="60d", interval="5m",
                     auto_adjust=False, progress=False, prepost=False)
    if df.empty:
        print(f"    ! empty data for {ticker}")
        return None
    out = _to_our_format(df)
    out.to_csv(p, index=False)
    print(f"    saved {len(out):,} bars → {p}")
    return out


def main():
    from backtest import load_csv

    rows = []
    for t in TICKERS:
        fetch_or_load(t)
    print("\nRunning 15 & 30-min ORB on each…\n")
    print(f"{'sym':<6} {'range':>5}  {'N':>4}  {'WR':>5}  {'Exp':>7}  {'Total R':>8}")
    print("─" * 50)
    for t in TICKERS:
        p = DATA_DIR / f"{t}_5m_60d.csv"
        if not p.exists():
            print(f"{t:<6} no data")
            continue
        df = load_csv(p)
        if len(df) < 200:
            print(f"{t:<6} too few bars ({len(df)})")
            continue
        for rm in (15, 30):
            s = OpeningRangeBreakout(name=f"{t}_orb{rm}",
                                     symbol=t, timeframe="5m",
                                     range_minutes=rm)
            r = backtest_strategy(s, df, warmup=100)
            print(f"{t:<6} {rm:>3}min  {r['trades']:>4}  "
                  f"{r['win_rate']:>5.1f}  {r['expectancy']:>+7.3f}  "
                  f"{r['total_R']:>+8.2f}")
            rows.append({
                "symbol": t, "range_minutes": rm,
                "trades": r["trades"], "win_rate": r["win_rate"],
                "expectancy": r["expectancy"], "total_R": r["total_R"],
            })
    out = Path("results/orb_10_equities.csv")
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
