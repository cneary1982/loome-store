# Data files

This folder holds the price bars the backtest reads. Every file is a CSV with the same schema:

```
timestamp,open,high,low,close,volume
2024-01-02 14:30:00+00:00,4750.25,4753.50,4748.00,4752.75,12345
...
```

- `timestamp` is **UTC, tz-aware** (the `+00:00` matters — DO NOT strip it).
- Files are **oldest-first**, one bar per row.
- Bars are **outright continuous** front-month: at each timestamp, the contract with the highest volume is selected. Spreads and far-month contracts are filtered out by `process_databento.py`.

## What's here

| File | Symbol | Bar size | Coverage |
|---|---|---|---|
| `ES_15m.csv`  | E-mini S&P 500 | 15 min | ~2 yrs |
| `ES_60m.csv`  | E-mini S&P 500 | 1 hr   | ~2 yrs |
| `ES_240m.csv` | E-mini S&P 500 | 4 hr   | ~3 yrs |
| `ES_1d.csv`   | E-mini S&P 500 | 1 day  | ~4 yrs |
| `NQ_*.csv`    | E-mini Nasdaq 100 | (same as ES) |  |
| `GC_*.csv`    | Gold | (same as ES) |  |

## How to regenerate

The clean CSVs are stitched from raw Databento exports by `process_databento.py`. To refresh:

1. Drop new exports into `data/_raw_daily.csv` and `data/_raw_240m.csv` (Databento ohlcv-1d / ohlcv-4h product, all front-month contracts in one file).
2. Run `python process_databento.py` from the project root.
3. The script writes `{ES,NQ,GC}_{1d,240m}.csv` to this folder.

`_raw_*.csv` is gitignored — keep the source files locally but don't commit them.
