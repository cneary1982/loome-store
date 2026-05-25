# sweep_all.csv — column glossary

Output of `python sweep_all.py`. Each row is one backtest configuration.

## Columns

| Column | Description |
|---|---|
| `symbol` | Futures contract: ES (S&P 500), NQ (Nasdaq 100), GC (Gold) |
| `timeframe` | Bar size of the entry signal: 15m, 1h, 4h, or 1d |
| `lookback` | Number of past bars used to measure the trend (log-return window) |
| `threshold` | Log-return size that flips the regime to up/down (0.015 = 1.5%) |
| `atr_mult` | Multiple of ATR(14) used for the take-profit AND stop-loss distance (symmetric) |
| `trend_filter` | Higher-timeframe trend filter: 'off' or 'on' (see TREND_FILTER_LABELS) |
| `session_window` | Which clock hours entries are allowed in (see SESSION_LABELS) |
| `trades` | Number of round-trip trades the strategy took in the backtest period |
| `win_rate` | Percent of trades that closed with a positive R |
| `expectancy` | Average R per trade. +0.20 = each trade earned 0.20 of its risked R on average |
| `total_R` | Total R across all trades (= expectancy x trades). Best single number to compare strategies |

## `trend_filter` values

| Value | Meaning |
|---|---|
| `off` | No higher-timeframe filter - take every signal that fires on the entry timeframe |
| `on` | Require higher-timeframe trend agreement: signal direction must match a 20-period EMA (plus slope) on the next-higher timeframes. 15m signals must agree with 1h and 4h. 1h signals must agree with 4h and 1d. 4h signals must agree with 1d. |

## `session_window` values

| Value | Window(s) |
|---|---|
| `all_hours` | No session filter - trade 24 hours a day |
| `us_market_hours` | US stock market hours: 09:30-15:30 ET entries; close any open trade at 16:00 ET |
| `gold_3_sessions` | Three gold liquidity windows: London open 02:00-05:00, NY morning 08:00-11:00, Asia 20:00-23:00 ET |
| `ny_morning_only` | NY morning only: 08:00-11:00 ET (COMEX open + 08:30 US data + 10:00 AM Gold Fix) |
| `london_plus_ny` | London open + NY morning: 02:00-05:00 and 08:00-11:00 ET (no Asia) |
| `ny_morning_wide` | Broader NY morning: 07:00-12:00 ET |
| `comex_open_window` | Narrow gold window: 08:20-10:30 ET (COMEX pit open through AM Gold Fix) |
| `london_through_ny` | London open through US close, continuous: 02:00-16:00 ET |

## How to read the results

- **R** is the unit of risk: 1 R = `atr_mult * ATR(14)`. A trade that hits its take-profit at `entry + atr_mult*ATR` returns +1 R; one that hits the stop-loss returns -1 R. Forced exits (e.g. 16:00 ET close on `us_market_hours`) return a fractional R based on the exit price.
- **expectancy** is the average R per trade. +0.20 means on average each trade earned one-fifth of what was risked on it.
- **total_R** = expectancy x trades. This is the best single number to compare two strategies that took different numbers of trades. A strategy with +0.40 R/trade over only 10 trades (= +4 R) is worse than one with +0.10 R/trade over 200 trades (= +20 R).

## How to make this better

Open ideas to try (PRs welcome):
- **Asymmetric TP/SL**: separate `tp_mult` and `sl_mult` instead of one ATR.
- **Trailing stop**: replace the fixed stop with a chandelier trail once price has moved +1 R in favor (highest high - k*ATR).
- **Volatility-targeted sizing**: risk constant $ per trade by sizing 1/ATR.
- **New session windows**: add a preset to `SESSION_PRESETS` in `sweep_all.py` and it will be tested automatically for the symbols it's listed under in `SESSION_VARIANTS`.
- **Volume confirmation**: only fire entries when the breakout bar's volume is N x median(volume).
