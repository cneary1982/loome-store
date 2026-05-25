# Trading Strategies

A futures-breakout backtest framework for **ES** (E-mini S&P 500), **NQ** (E-mini Nasdaq 100), and **GC** (Gold). Strategy parameters and filters are swept over thousands of configurations to find what actually works.

The current best-of-grid result is **GC 1h with the 3-session window filter: 71.9% win rate, +0.44 R per trade over 64 trades**. See [`results/best_per_cell_by_total_R.csv`](results/best_per_cell_by_total_R.csv) for the full table.

## Quick start

```bash
git clone https://github.com/<you>/trading-strategies.git
cd trading-strategies
pip install -r requirements.txt

# Run the dashboard-default backtest across all (symbol, timeframe) pairs
python backtest.py

# Run the full ~4,200-config sweep (takes about 50 seconds)
python sweep_all.py
```

The sweep writes its results to `results/sweep_all.csv` (full grid) and `results/best_per_cell_by_total_R.csv` (one winner per cell). Both are also committed so you can browse them without running anything.

## What the strategy does

For each `(symbol, timeframe)` it labels every bar into one of three regimes using a log-return lookback:

- **Up regime** if `log(close / close[lookback bars ago]) > +threshold`
- **Down regime** if the same return is `< -threshold`
- **Flat** otherwise

A long is opened whenever the regime flips from non-up to up. A short opens on flips to down. Targets and stops are placed at `entry ± atr_mult × ATR(14)`. Exit on whichever level is hit first.

Three optional filters can be stacked on top of every signal:

1. **`session_window`** — only fire entries during certain clock hours (e.g. gold's 3 main liquidity windows, US market hours).
2. **`trend_filter`** — require the higher timeframes to agree with the signal's direction (20-period EMA + slope check).
3. **`force-flat`** (built into `us_market_hours`) — close any open ES/NQ position at 16:00 ET regardless of TP/SL.

## Project structure

```
trading-strategies/
├── README.md                          ← you are here
├── requirements.txt                   pandas, numpy
├── backtest.py                        regime + ATR backtest engine
├── filters.py                         session windows + HTF trend alignment
├── sweep_all.py                       exhaustive ~4,200-config sweep
├── process_databento.py               raw Databento → continuous front-month CSVs
├── data/                              price bars (UTC, tz-aware)
│   ├── README.md                      data schema + how to refresh
│   ├── ES_{15m,60m,240m,1d}.csv
│   ├── NQ_{15m,60m,240m,1d}.csv
│   └── GC_{15m,60m,240m,1d}.csv
└── results/                           committed backtest outputs
    ├── README.md                      column glossary for the CSVs
    ├── sweep_all.csv                  every config the sweep tested
    └── best_per_cell_by_total_R.csv   winning config per (symbol, timeframe)
```

## Glossary (the short version)

See [`results/README.md`](results/README.md) for the complete column-by-column breakdown.

| Term | What it means |
|---|---|
| **R** | One unit of risk. 1 R = `atr_mult × ATR(14)`. A trade that hits its take-profit returns +1 R; the stop returns -1 R. |
| **expectancy** | Average R per trade. `+0.20` = each trade earned 20% of what it risked, on average. |
| **total_R** | `expectancy × trades`. Best single number for comparing strategies that took different numbers of trades. |
| **session_window** | Clock-hour filter for entries. See table below. |
| **trend_filter** | `off` = take every signal. `on` = require higher-timeframe EMA20 trend + slope agreement. |

### `session_window` values

| Value | Window (US Eastern) |
|---|---|
| `all_hours` | 24h — no filter |
| `us_market_hours` | 09:30-15:30 ET; close any open ES/NQ position at 16:00 |
| `gold_3_sessions` | London 02:00-05:00 + NY morning 08:00-11:00 + Asia 20:00-23:00 |
| `ny_morning_only` | 08:00-11:00 ET (COMEX open + 08:30 data + 10:00 AM Gold Fix) |
| `london_plus_ny` | 02:00-05:00 and 08:00-11:00 ET (no Asia) |
| `ny_morning_wide` | 07:00-12:00 ET |
| `comex_open_window` | 08:20-10:30 ET (COMEX open through AM Gold Fix) |
| `london_through_ny` | 02:00-16:00 ET continuous |

## Current best configurations

From the latest 4,240-run sweep, ranked by total R across each `(symbol, timeframe)` cell:

| Symbol | TF | Lookback | Threshold | ATR mult | Trend filter | Session | Trades | Win % | R/trade | Total R |
|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| GC | 15m | 48 | 0.015 | 2.5 | off | all_hours | 178 | 60.7% | +0.21 | **+37.9** |
| ES | 15m | 32 | 0.010 | 2.5 | off | all_hours | 293 | 55.6% | +0.11 | +33.1 |
| GC | 1h  | 20 | 0.020 | 2.0 | off | **gold_3_sessions** | 64 | **71.9%** | **+0.44** | +28.0 |
| GC | 4h  | 12 | 0.010 | 2.0 | off | all_hours | 212 | 56.1% | +0.12 | +26.1 |
| ES | 4h  | 20 | 0.010 | 2.0 | off | all_hours | 195 | 55.4% | +0.11 | +21.1 |
| ES | 1h  | 48 | 0.010 | 2.5 | off | all_hours | 225 | 54.7% | +0.09 | +20.9 |
| NQ | 4h  | 20 | 0.025 | 3.5 | **on** | all_hours | 73 | 63.0% | +0.26 | +19.0 |
| NQ | 15m | 48 | 0.015 | 2.5 | off | all_hours | 61 | 62.3% | +0.25 | +15.0 |
| ES | 1d  | 20 | 0.030 | 2.0 | -  | all_hours | 56 | 62.5% | +0.25 | +14.0 |
| GC | 1d  | 32 | 0.015 | 3.0 | -  | all_hours | 18 | 88.9% | +0.78 | +14.0 |
| NQ | 1h  | 12 | 0.010 | 2.5 | off | all_hours | 63 | 57.1% | +0.14 | +9.0 |
| NQ | 1d  | 48 | 0.030 | 2.5 | -  | all_hours | 31 | 61.3% | +0.23 | +7.0 |

### Things this sweep already showed

- **ATR 3.0 was too wide.** Every winning config picked ATR 2.0-2.5. Tighter stops + tighter targets win.
- **The 3-session window helps GC 1h specifically** (+0.15 -> +0.44 expectancy). It does not help every gold timeframe — GC 15m wins without any session filter.
- **The HTF trend filter mostly hurts**. Only NQ 4h prefers it on; everywhere else, off wins.
- **The US market-hours filter is a net loss on ES/NQ 15m**. The breakout signal catches genuine overnight macro moves and forcing flat at 16:00 cuts winners short.

## How to make it better

Pull requests welcome. Concrete open ideas:

- **Asymmetric TP/SL.** Right now `atr_mult` controls both target and stop. Splitting into separate `tp_mult` and `sl_mult` lets you test 2:1 / 3:1 / runner-style configurations. Should be a few lines in `backtest()`.
- **Trailing stop.** Replace the fixed stop with a chandelier trail once a trade reaches +1 R: `stop = highest_high_since_entry - trail_mult × ATR`. Lets winners run.
- **Volatility-targeted sizing.** Risk a constant dollar amount per trade by sizing as `1/ATR`. Smooths the equity curve across symbols.
- **New session windows.** Add an entry to `SESSION_PRESETS` in `sweep_all.py` and add it to the symbols you want to test it on in `SESSION_VARIANTS`. It gets tested automatically.
- **Volume confirmation.** Require breakout-bar volume `> N × median(volume, lookback)`. Filters head-fakes on thin tape.
- **Time-of-day filter.** Skip 11:00-14:00 ET ("lunch") for ES/NQ — usually low-quality breakouts. Should be a one-line addition to `filters.py`.
- **Pullback entries.** Instead of entering on the breakout bar, wait for the first close back inside the prior range and enter there. Fewer trades, higher win rate.

If you find something that improves total R across the cells, open a PR with the updated `results/sweep_all.csv` so the headline numbers stay current.

## Data

Price bars come from [Databento](https://databento.com) (CME `GLBX.MDP3` feed) and are stitched into continuous front-month series by `process_databento.py`. The raw multi-contract exports are gitignored; only the clean per-(symbol, timeframe) CSVs are committed. See [`data/README.md`](data/README.md) for the schema and refresh instructions.

## License

TBD. For now, treat as "all rights reserved" until a license file is added.
