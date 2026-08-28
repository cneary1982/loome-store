"""Query helper for the cleaned options data in gs://qqq-options-1yr2025-26/claude_v1/.

Examples:
    from query_options import contracts_on, gex_on, list_dates

    list_dates()                          # → ['2025-09-02', '2025-09-03', ...]
    contracts_on('2025-09-02')            # → DataFrame of all QQQ contracts that day
    contracts_on('2025-09-02', expiry='2025-12-19')  # → just December expiry
    gex_on('2025-09-02')                  # → GEX/DEX by strike, with spot
    gex_on('2025-09-02', top_strikes=10)  # → top 10 abs-GEX strikes
"""
from __future__ import annotations

import io
from datetime import date, datetime
from functools import lru_cache

import pandas as pd
from google.cloud import storage

BUCKET = "qqq-options-1yr2025-26"
PREFIX = "claude_v1"


@lru_cache(maxsize=1)
def _client() -> storage.Client:
    return storage.Client()


def list_dates() -> list[str]:
    """Return the sorted list of dates we have processed data for."""
    c = _client()
    b = c.bucket(BUCKET)
    out = []
    for blob in c.list_blobs(b, prefix=f"{PREFIX}/processed/"):
        name = blob.name.split("/")[-1]
        if name.endswith(".parquet"):
            out.append(name.replace(".parquet", ""))
    return sorted(out)


def _read_parquet(blob_name: str) -> pd.DataFrame:
    c = _client()
    blob = c.bucket(BUCKET).blob(blob_name)
    return pd.read_parquet(io.BytesIO(blob.download_as_bytes()))


def contracts_on(d, expiry=None, opt_type=None,
                 strike_min=None, strike_max=None) -> pd.DataFrame:
    """Return all contracts trading on date `d`. Optional filters."""
    d = _isodate(d)
    df = _read_parquet(f"{PREFIX}/processed/{d}.parquet")
    if expiry is not None:
        df = df[df["expiry"] == pd.to_datetime(expiry).date()]
    if opt_type is not None:
        df = df[df["opt_type"] == opt_type.upper()]
    if strike_min is not None:
        df = df[df["strike"] >= strike_min]
    if strike_max is not None:
        df = df[df["strike"] <= strike_max]
    return df


def gex_on(d, top_strikes: int | None = None) -> pd.DataFrame:
    """Return GEX/DEX profile for date `d`, optionally just top N strikes."""
    d = _isodate(d)
    df = _read_parquet(f"{PREFIX}/gex_dex/{d}.parquet")
    if top_strikes is not None:
        df = df.iloc[df["gex"].abs().argsort()[::-1][:top_strikes]].sort_values("strike")
    return df


def gex_history(top_strikes_per_day: int = 5) -> pd.DataFrame:
    """Aggregate GEX/DEX across all days. Useful for time-series plots."""
    out = []
    for d in list_dates():
        g = gex_on(d, top_strikes=top_strikes_per_day)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def total_gex_history() -> pd.DataFrame:
    """Per-day total GEX, DEX, spot."""
    out = []
    for d in list_dates():
        g = _read_parquet(f"{PREFIX}/gex_dex/{d}.parquet")
        out.append({
            "date": d,
            "spot": float(g["spot"].iloc[0]) if len(g) else None,
            "total_gex": float(g["gex"].sum()),
            "total_dex": float(g["dex"].sum()),
            "n_strikes": len(g),
        })
    return pd.DataFrame(out)


def _isodate(d) -> str:
    if isinstance(d, str):
        return d
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d")
    raise TypeError(f"can't make ISO date from {d!r}")


if __name__ == "__main__":
    print("Available dates:")
    dates = list_dates()
    print(f"  {len(dates)} dates, {dates[0]} → {dates[-1]}")
    print(f"\nSample — contracts on {dates[0]}:")
    df = contracts_on(dates[0])
    print(df.head().to_string(index=False))
    print(f"\nSample — total GEX history:")
    print(total_gex_history().head().to_string(index=False))
