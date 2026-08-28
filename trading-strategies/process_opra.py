"""Process Databento OPRA Pillar dumps into a GEX/DEX-ready Parquet layer.

Reads:    gs://qqq-options-data/backtest/YYYY/MM/DD/opra-pillar-YYYYMMDD.{definition,statistics}.csv
Writes:   gs://qqq-options-1yr2025-26/claude_v1/processed/YYYY-MM-DD.parquet
          gs://qqq-options-1yr2025-26/claude_v1/gex_dex/YYYY-MM-DD.parquet

Source is never modified. Output lives in claude_v1/ — delete safely without
affecting anything else.

Stat-type codes (Databento OPRA Pillar schema):
  3  = settlement_price
  9  = open_interest
  11 = close_price

OPRA symbol format ("QQQ   260116P00189780"):
  6 chars : root (left-padded, e.g. "QQQ   ")
  6 chars : expiration YYMMDD
  1 char  : option type (C/P)
  8 chars : strike × 1000, zero-padded
"""
from __future__ import annotations

import argparse
import io
import math
import os
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import storage

SRC_BUCKET = "qqq-options-data"
DST_BUCKET = "qqq-options-1yr2025-26"
DST_PREFIX = "claude_v1"

# ─── OPRA symbol parsing ────────────────────────────────────────────────────
def parse_opra(sym: str):
    """Return (root, expiry_date, opt_type, strike) or None."""
    sym = sym.rstrip()
    if len(sym) < 19:
        return None
    root_part = sym[:-15].strip()           # "QQQ"
    payload = sym[-15:]                     # "260116P00189780"
    yy, mm, dd = payload[:2], payload[2:4], payload[4:6]
    opt_type = payload[6]                   # "C" or "P"
    strike_int = payload[7:]                # "00189780"
    try:
        expiry = date(2000 + int(yy), int(mm), int(dd))
        strike = int(strike_int) / 1000.0
    except ValueError:
        return None
    return root_part, expiry, opt_type, strike


# ─── GCS helpers ────────────────────────────────────────────────────────────
def _client() -> storage.Client:
    return storage.Client()


def read_csv_from_gcs(client, bucket: str, name: str, usecols=None,
                      dtype=None) -> pd.DataFrame:
    blob = client.bucket(bucket).blob(name)
    raw = blob.download_as_bytes()
    return pd.read_csv(io.BytesIO(raw), usecols=usecols, dtype=dtype,
                       low_memory=False)


def write_parquet_to_gcs(client, df: pd.DataFrame, bucket: str, name: str):
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, compression="snappy")
    blob = client.bucket(bucket).blob(name)
    blob.upload_from_string(buf.getvalue(), content_type="application/octet-stream")


def list_available_dates(client) -> list[date]:
    bucket = client.bucket(SRC_BUCKET)
    dates: set[date] = set()
    for blob in client.list_blobs(bucket, prefix="backtest/"):
        # backtest/YYYY/MM/DD/opra-pillar-YYYYMMDD.definition.csv
        parts = blob.name.split("/")
        if len(parts) != 5 or not parts[-1].endswith(".definition.csv"):
            continue
        try:
            dates.add(date(int(parts[1]), int(parts[2]), int(parts[3])))
        except ValueError:
            continue
    return sorted(dates)


# ─── Per-day processing ─────────────────────────────────────────────────────
DEFINITION_COLS = ["instrument_id", "raw_symbol", "expiration", "strike_price"]
STATISTICS_COLS = ["instrument_id", "price", "quantity", "stat_type", "symbol"]

# Databento int64/uint64 null sentinels
INT64_NULL  = 9223372036854775807
UINT64_NULL = 18446744073709551615


def process_day(client: storage.Client, d: date) -> dict | None:
    base = f"backtest/{d.year:04d}/{d.month:02d}/{d.day:02d}/opra-pillar-{d.strftime('%Y%m%d')}"
    def_path = f"{base}.definition.csv"
    stat_path = f"{base}.statistics.csv"

    bucket = client.bucket(SRC_BUCKET)
    if not bucket.blob(def_path).exists():
        return None

    # 1) Definitions: one row per contract
    defs = read_csv_from_gcs(client, SRC_BUCKET, def_path,
                             usecols=DEFINITION_COLS)
    parsed = defs["raw_symbol"].map(parse_opra)
    defs = defs[parsed.notna()].copy()
    defs["root"]    = parsed.dropna().map(lambda t: t[0])
    defs["expiry"]  = parsed.dropna().map(lambda t: t[1])
    defs["opt_type"]= parsed.dropna().map(lambda t: t[2])
    defs["strike"]  = parsed.dropna().map(lambda t: t[3])

    # Keep only QQQ (this dataset is QQQ-only, but be defensive)
    defs = defs[defs["root"] == "QQQ"]
    if defs.empty:
        return None

    # 2) Statistics: collapse duplicate publisher_id rows.
    #    Stat type 3=settle (price field), 9=OI (quantity field), 11=close (price field).
    stats = read_csv_from_gcs(client, SRC_BUCKET, stat_path, usecols=STATISTICS_COLS)
    stats = stats[stats["stat_type"].isin([3, 9, 11])].copy()

    # Mask sentinels → NaN
    stats.loc[stats["price"] == INT64_NULL, "price"] = np.nan
    stats.loc[stats["quantity"] >= INT64_NULL, "quantity"] = np.nan

    # OI lives in quantity; settle/close live in price
    oi_rows     = stats[stats["stat_type"] == 9].dropna(subset=["quantity"])
    settle_rows = stats[stats["stat_type"] == 3].dropna(subset=["price"])
    close_rows  = stats[stats["stat_type"] == 11].dropna(subset=["price"])

    oi     = oi_rows.groupby("instrument_id")["quantity"].max().rename("open_interest")
    settle = settle_rows.groupby("instrument_id")["price"].median().rename("settle_raw")
    close  = close_rows.groupby("instrument_id")["price"].median().rename("close_raw")

    # 3) Merge definitions + stats
    out = (defs.merge(oi,     left_on="instrument_id", right_index=True, how="left")
               .merge(settle, left_on="instrument_id", right_index=True, how="left")
               .merge(close,  left_on="instrument_id", right_index=True, how="left"))

    # Databento price scaling: OPRA prices are int64 fixed-point with 1e9 divisor.
    for col in ("settle_raw", "close_raw"):
        if col in out.columns:
            out[col.replace("_raw", "")] = out[col] / 1e9
            out.drop(columns=[col], inplace=True)

    # Ensure all expected columns exist even if a stat type was absent
    for col in ("settle", "close", "open_interest"):
        if col not in out.columns:
            out[col] = np.nan

    out = out[["instrument_id", "root", "expiry", "opt_type", "strike",
               "settle", "close", "open_interest"]]
    out["date"] = d
    return out


# ─── GEX / DEX computation ──────────────────────────────────────────────────
def bs_d1(S, K, T, sigma, r=0.045, q=0.005):
    return (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))


def call_delta(S, K, T, sigma):
    d1 = bs_d1(S, K, T, sigma)
    return _norm_cdf(d1)


def put_delta(S, K, T, sigma):
    d1 = bs_d1(S, K, T, sigma)
    return _norm_cdf(d1) - 1.0


def gamma(S, K, T, sigma):
    d1 = bs_d1(S, K, T, sigma)
    return _norm_pdf(d1) / (S * sigma * np.sqrt(T))


def _norm_cdf(x):
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


def _norm_pdf(x):
    return np.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def compute_gex_dex(df: pd.DataFrame, spot: float, default_iv: float = 0.20):
    """df is the processed daily Parquet. spot is QQQ close that day."""
    df = df.copy()
    df["T"] = ((pd.to_datetime(df["expiry"]) - pd.to_datetime(df["date"]))
               .dt.days.clip(lower=1) / 365.25)
    iv = default_iv  # placeholder — we don't have ATM IV in raw OPRA
    df["gamma"] = gamma(spot, df["strike"], df["T"], iv)
    df["delta"] = np.where(
        df["opt_type"] == "C",
        call_delta(spot, df["strike"], df["T"], iv),
        put_delta(spot, df["strike"], df["T"], iv),
    )
    # Convention: MM is short calls / long puts (rough), sign by type
    sign = np.where(df["opt_type"] == "C", -1.0, +1.0)
    oi = df["open_interest"].fillna(0)
    df["gex"] = sign * df["gamma"] * oi * 100 * spot * spot * 0.01
    df["dex"] = sign * df["delta"] * oi * 100 * spot
    profile = (df.groupby("strike")[["gex", "dex"]].sum()
                 .reset_index().sort_values("strike"))
    profile["date"] = df["date"].iloc[0]
    profile["spot"] = spot
    profile["iv_assumed"] = iv
    return profile


# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date",     help="YYYY-MM-DD (single day mode)")
    ap.add_argument("--list",     action="store_true", help="List source dates and exit")
    ap.add_argument("--all",      action="store_true", help="Process every available date")
    ap.add_argument("--spot",     type=float, help="QQQ close that day (single-day mode)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="Skip days whose processed parquet already exists")
    ap.add_argument("--local-out", help="Write Parquet to this local dir instead of GCS")
    args = ap.parse_args()

    client = _client()
    local_out = Path(args.local_out) if args.local_out else None
    if local_out:
        (local_out / "processed").mkdir(parents=True, exist_ok=True)
        (local_out / "gex_dex").mkdir(parents=True, exist_ok=True)

    if args.list:
        for d in list_available_dates(client):
            print(d)
        return

    if args.date:
        d = date.fromisoformat(args.date)
        run_one(client, d, args.spot, args.skip_existing, local_out)
        return

    if args.all:
        dates = list_available_dates(client)
        print(f"Found {len(dates)} dates to process")
        for i, d in enumerate(dates, 1):
            try:
                run_one(client, d, None, args.skip_existing, local_out)
                print(f"  [{i}/{len(dates)}] {d} done", flush=True)
            except Exception as e:
                print(f"  [{i}/{len(dates)}] {d}: FAILED {e!r}", file=sys.stderr, flush=True)
        return

    ap.print_help()


def derive_spot_from_parity(df: pd.DataFrame) -> float | None:
    """Estimate spot from put-call parity at the nearest 21–45 day expiry.

    For each strike with both a call and put close: spot ≈ K + (C - P).
    Median across strikes. Ignores the small dividend/rate term — fine for
    30-day-out options on QQQ.
    """
    df = df.dropna(subset=["close"]).copy()
    df["T_days"] = (pd.to_datetime(df["expiry"]) - pd.to_datetime(df["date"])).dt.days
    front = df[(df["T_days"] >= 21) & (df["T_days"] <= 45)]
    if front.empty:
        front = df[df["T_days"] >= 7]
    if front.empty:
        return None
    exp = front["expiry"].value_counts().index[0]
    sub = front[front["expiry"] == exp]
    calls = sub[sub["opt_type"] == "C"].set_index("strike")["close"]
    puts  = sub[sub["opt_type"] == "P"].set_index("strike")["close"]
    common = calls.index.intersection(puts.index)
    if len(common) < 3:
        return None
    spots = common + (calls[common] - puts[common])
    return float(spots.median())


def run_one(client, d: date, spot: float | None, skip_existing: bool,
            local_out: Path | None):
    out_proc_name = f"{DST_PREFIX}/processed/{d.isoformat()}.parquet"
    out_gex_name  = f"{DST_PREFIX}/gex_dex/{d.isoformat()}.parquet"

    if local_out:
        out_proc_path = local_out / "processed" / f"{d.isoformat()}.parquet"
        out_gex_path  = local_out / "gex_dex"   / f"{d.isoformat()}.parquet"
        if skip_existing and out_proc_path.exists():
            # Still try GEX/DEX if processed exists but gex_dex doesn't
            if out_gex_path.exists():
                return
            proc = pd.read_parquet(out_proc_path)
        else:
            proc = process_day(client, d)
            if proc is None:
                return
            proc.to_parquet(out_proc_path, index=False, compression="snappy")
    else:
        if skip_existing and client.bucket(DST_BUCKET).blob(out_proc_name).exists():
            return
        proc = process_day(client, d)
        if proc is None:
            return
        write_parquet_to_gcs(client, proc, DST_BUCKET, out_proc_name)

    if spot is None:
        spot = derive_spot_from_parity(proc)
    if spot is None or math.isnan(spot) or spot <= 0:
        return
    gex = compute_gex_dex(proc, spot=spot)

    if local_out:
        gex.to_parquet(out_gex_path, index=False, compression="snappy")
    else:
        write_parquet_to_gcs(client, gex, DST_BUCKET, out_gex_name)


if __name__ == "__main__":
    main()
