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
├── RISK.md                            live-trading risks + pre-flight checklist
├── CONTRIBUTING.md                    how to add features and submit PRs
├── LICENSE                            MIT
├── requirements.txt                   pandas, numpy, requests, streamlit
├── .github/workflows/sweep.yml        CI: runs the full sweep on every push/PR
│
│ Backtest path (futures: ES / NQ / GC)
├── backtest.py                        regime + ATR backtest engine
├── filters.py                         session windows + HTF trend alignment
├── sweep_all.py                       exhaustive ~4,200-config sweep
├── strategy.py                        signal logic factored for streaming
├── process_databento.py               raw Databento → continuous front-month CSVs
│
│ Live-trading path (Tradier; ETF proxies SPY / QQQ / GLD)
├── tradier.py                         REST client (sandbox + live)
├── live_trader.py                     single-strategy runner (simple path)
│
│ Multi-strategy orchestrator (recommended live path)
├── orchestrator.py                    daemon: runs all strategies in strategies.py
├── strategies.py                      registry — edit to add/remove strategies
├── position_manager.py                central state + per-symbol lock + circuit breaker
├── dashboard.py                       Streamlit UI (reads state, writes commands)
│
│ Data and results
├── data/                              price bars (UTC, tz-aware)
│   ├── README.md
│   ├── ES_{15m,60m,240m,1d}.csv
│   ├── NQ_{15m,60m,240m,1d}.csv
│   └── GC_{15m,60m,240m,1d}.csv
└── results/                           committed backtest outputs
    ├── README.md
    ├── sweep_all.csv
    └── best_per_cell_by_total_R.csv
```

## Multi-strategy orchestrator (recommended)

For running **multiple strategies simultaneously** with one trade per security at a time, use the orchestrator. It's the unified live system: one Tradier connection, multiple strategy types, central state, kill switch, Streamlit dashboard.

```bash
# Terminal 1: the orchestrator daemon
export TRADIER_TOKEN='...'
export TRADIER_ACCOUNT_ID='...'
# TRADIER_ENV defaults to 'sandbox'
python orchestrator.py --risk-per-trade 25 --max-daily-loss -100

# Terminal 2: the dashboard
streamlit run dashboard.py
```

The dashboard opens at `http://localhost:8501`. It auto-refreshes every 5 seconds and shows:

- **Broker mode** (sandbox / LIVE), cash available, daily PnL, halt status
- **Kill switch** button (halts all strategies immediately)
- **Strategies table** with per-strategy enable/disable toggles, trades today, PnL today
- **Open positions** (per-symbol lock — at most one row per symbol)
- **Recent trades** (last 50)

### Adding a strategy

Edit `strategies.py`:

```python
from orchestrator import RegimeBreakout

STRATEGIES = [
    RegimeBreakout(name="SPY_15m_breakout", symbol="SPY", timeframe="15m",
                   lookback=48, threshold=0.015, atr_mult=2.5),
    RegimeBreakout(name="QQQ_5m_aggressive", symbol="QQQ", timeframe="5m",
                   lookback=32, threshold=0.010, atr_mult=2.0),
    # add more here
]
```

Restart the orchestrator after editing.

### Per-symbol lock

`PositionManager.try_open(symbol, strategy_name)` atomically claims the symbol. If two strategies fire on SPY in the same poll cycle, the first one wins; the second sees the symbol is taken, cancels its order, and logs a `LOST_RACE` event. This guarantees **at most one open position per security across all strategies**.

### Writing a new strategy type

Subclass `Strategy` in `orchestrator.py` (or in your own file imported by `strategies.py`):

```python
from orchestrator import Strategy, StrategySignal

class MyStrategy(Strategy):
    def signal(self, bars, now_utc):
        # bars is a DataFrame with Open/High/Low/Close/Volume, UTC tz-aware index
        # Return StrategySignal(...) or None
        ...
```

See `RegimeBreakout` in `orchestrator.py` as a reference.



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

## Live trading (Tradier, ETF proxies)

> **Read [`RISK.md`](RISK.md) before flipping `TRADIER_ENV` to `live`.** The script will refuse to start otherwise.

Tradier doesn't trade futures, so live trading uses ETF substitutes:

| Backtested futures | ETF proxy on Tradier |
|---|---|
| ES (S&P 500) | **SPY** |
| NQ (Nasdaq 100) | **QQQ** |
| GC (Gold) | **GLD** |

These trade RTH only (09:30-16:00 ET) — none of the futures-overnight signals fire. The strategy's daily and intraday RTH signals translate directly; everything else does not.

### Quick start (sandbox, $0 risk)

1. Get a free sandbox token at https://sandbox.tradier.com
2. Find your sandbox account ID in the dashboard
3. Run:

```bash
export TRADIER_TOKEN='<sandbox token>'
export TRADIER_ACCOUNT_ID='<sandbox account id>'
# TRADIER_ENV defaults to 'sandbox' - safe by default

pip install -r requirements.txt
python live_trader.py --symbol SPY --timeframe 15m \
    --lookback 48 --threshold 0.015 --atr-mult 2.5
```

The script polls every 60 seconds, runs the strategy on Tradier's bars, and places simulated market orders when the regime flips. State (open positions, daily PnL) lives in `live_state.json` next to the script.

### Sizing and safety knobs

| Env var | Default | What it controls |
|---|---|---|
| `RISK_PER_TRADE` | `25` | Dollars risked per stop-out. Shares = `floor(RISK / (atr_mult * ATR))` |
| `MAX_OPEN_POSITIONS` | `1` | Concurrent open positions across all symbols |
| `MAX_DAILY_LOSS` | `-100` | If daily realized PnL goes below this, halt for the day |
| `TRADIER_ENV` | `sandbox` | Set to `live` to use real money (also requires `TRADIER_LIVE_CONFIRM`) |
| `TRADIER_LIVE_CONFIRM` | unset | Must equal `I have read RISK.md` to flip live |

### Going live

When you've worked through [`RISK.md`](RISK.md)'s pre-flight checklist:

```bash
export TRADIER_TOKEN='<live token from developer.tradier.com>'
export TRADIER_ACCOUNT_ID='<live account id>'
export TRADIER_ENV=live
export TRADIER_LIVE_CONFIRM='I have read RISK.md'
export RISK_PER_TRADE=10           # start conservative
export MAX_DAILY_LOSS=-30

python live_trader.py --symbol SPY ...
```

The script will throw `TradierError` and refuse to run if any of the live guards aren't set correctly.

## Data

Price bars come from [Databento](https://databento.com) (CME `GLBX.MDP3` feed) and are stitched into continuous front-month series by `process_databento.py`. The raw multi-contract exports are gitignored; only the clean per-(symbol, timeframe) CSVs are committed. See [`data/README.md`](data/README.md) for the schema and refresh instructions.

Tradier provides its own bar history via `tradier.py` (`daily_bars` / `intraday_bars`), so the live trader doesn't need a separate data subscription.

## License

TBD. For now, treat as "all rights reserved" until a license file is added.
