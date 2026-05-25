# sweep_all.csv — column glossary

Output of `python sweep_all.py`. Each row is one backtest configuration.

## Columns

| Column | Description |
|---|---|
| `symbol` | Futures contract symbol (ES, NQ, GC) |
| `tf` | Bar timeframe (15m, 1h, 4h, 1d) |
| `lookback` | Number of bars used for the log-return regime label |
| `threshold` | Log-return magnitude defining up/down regime (0.015 = 1.5%) |
| `atr` | ATR(14) multiplier for take-profit and stop-loss distance (symmetric) |
| `align` | HTF EMA20 trend-alignment filter: 0=off, 1=on |
| `align_label` | Human-readable description of the alignment filter |
| `session` | Session-window filter code (see SESSION_LABELS) |
| `session_label` | Human-readable description of the session filter |
| `trades` | Number of completed round-trip trades |
| `win_rate` | Percent of trades exited at TP (or positive partial exit) |
| `expectancy` | Mean R-multiple per trade (R = atr_mult * ATR risked) |
| `total_R` | Sum of R-multiples across all trades (= expectancy * trades) |

## `align` values

| Value | Meaning |
|---|---|
| `0` | No HTF filter |
| `1` | Require HTF EMA20 + slope alignment (1h gated by 4h+1d; 15m by 1h+4h; 4h by 1d) |

## `session` codes

| Code | Window(s) |
|---|---|
| `off` | No session filter (24h) |
| `rth` | ES/NQ RTH 09:30-15:30 ET (flat at 16:00) |
| `kz3` | GC 3 killzones: London 02-05 + NY AM 08-11 + Asia 20-23 ET |
| `kz_ny_only` | GC NY AM only: 08:00-11:00 ET |
| `kz_ny_london` | GC London + NY AM: 02-05 + 08-11 ET (no Asia) |
| `kz_ny_wide` | GC NY AM widened: 07:00-12:00 ET |
| `kz_narrow` | GC narrow: 08:20-10:30 ET (COMEX open + AM Fix) |
| `kz_active_block` | GC continuous active block: 02:00-16:00 ET |

## Metric definitions

- **R-multiple**: a trade's PnL expressed in units of risk, where 1 R = `atr_mult * ATR(14)`. A trade that hits its take-profit at `entry + atr_mult*ATR` is +1 R; the stop-loss is -1 R. Forced exits (e.g. 16:00 ET flat for ES/NQ RTH) yield fractional R based on the exit price.
- **expectancy** = mean R per trade.
- **total_R** = expectancy × trades. Use this when comparing configs with very different trade counts — a high per-trade expectancy with only 10 trades is less valuable than a moderate expectancy compounded over 200 trades.
