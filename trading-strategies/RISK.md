# Risk disclosures and the go-live checklist

**Read this before you set `TRADIER_ENV=live`.** Once you flip that flag, every signal this code generates will send a real order to a real broker and move real money out of your account.

This is not investment advice. This software is provided as-is under the MIT License, with no warranty. You are 100% responsible for every order it places.

## What this code can and cannot do

**It can:**
- Fetch bars from Tradier
- Compute breakout signals on a single (symbol, timeframe) at a time
- Place market orders to enter
- Place market exits when TP, SL, or end-of-RTH is reached
- Track open positions, daily PnL, and trip a circuit breaker at a configurable max daily loss
- Refuse to enter when at the position cap

**It cannot:**
- Recover from a missed bar (e.g. if your machine crashes mid-trade). The state file is your only record of what's open.
- Detect that the broker rejected an order silently or partially-filled. Always sanity-check positions in the Tradier dashboard.
- Trade futures (Tradier doesn't offer them — ETF proxies SPY/QQQ/GLD are the substitutes).
- Adapt position size to a moving account balance — it sizes by `RISK_PER_TRADE / (atr_mult * ATR)`, which assumes you can afford that risk per trade.
- Hedge, scale in/out, or manage slippage. If liquidity dries up, your fill will be worse than the backtest assumes.

## Material gaps between the backtest and live trading

The backtest is **gross of costs** and assumes **perfect fills at the bar boundary price**. Live trading does not work that way.

| Gap | Impact |
|---|---|
| **Commissions.** Tradier charges $0 for equity trades but $0.35/contract for options. If you're trading ETF shares only, this is mostly free. |
| **Slippage.** Market orders fill at the next available offer/bid, not the bar close. On SPY/QQQ in liquid hours, slippage is 1-2 cents. On low-liquidity ETFs or the open/close auction, it can be 10x worse. |
| **Spread.** Backtest exit-on-stop assumes you got the stop price exactly. In reality the bar's low touching the stop is filled at the bid. For tight ATRs this can flip a winning backtest to losing live. |
| **Halts and reopens.** A volatility halt mid-trade will leave your stop unfilled while price moves through it. |
| **Overnight risk.** ETFs do not trade 24h. Open positions held overnight (this code force-flats at 15:55 ET to avoid this) eat the entire overnight gap on the open. Don't disable the EOD exit unless you understand this. |
| **Data lag.** Tradier's free quote feed is delayed for some accounts. Verify your feed is real-time before going live, or signal latency will compound slippage. |

## Pre-flight checklist — required before going live

Walk through every line. If you can't tick all of them, stay on `TRADIER_ENV=sandbox`.

- [ ] I have run this code in **sandbox mode for at least 20 real signals** without errors.
- [ ] I have **manually verified at least 5 sandbox fills** against the Tradier dashboard to confirm orders, sizes, sides, and TP/SL distances match what the script logged.
- [ ] I have **confirmed my data feed is real-time** (not delayed by 15 minutes). Check this by comparing a SPY tick from `client.quote()` against the real-time price on tradingview.com or your phone.
- [ ] I understand that **`RISK_PER_TRADE` is the dollar amount risked per stop-out**, not the dollar amount per trade. With ATR-based sizing, the position size can be 10-200 shares depending on volatility.
- [ ] I have set **`MAX_DAILY_LOSS`** to a number I can afford to lose **every day for a month** (e.g. if losing $1000 would change my life, set `MAX_DAILY_LOSS=-50`).
- [ ] I have set **`MAX_OPEN_POSITIONS=1`** to start. Do not raise this until you have at least 100 live trades on record and a positive Sharpe.
- [ ] I have **re-backtested on the ETF symbol** (not just the futures contract). The futures backtest doesn't transfer to SPY/QQQ/GLD without re-validation — RTH-only schedules, 1/10 notional, slight tracking differences all matter.
- [ ] I have **alerted myself** when the script halts or errors out (cron + email, or a Discord webhook in the script, or running it under `tmux` and checking on it).
- [ ] I have **a manual kill switch** I know how to use: Ctrl-C the script, then in the Tradier dashboard cancel any open orders and flat any open positions by hand.

## Going live

When and only when every box above is ticked:

```bash
export TRADIER_TOKEN='<your live token from developer.tradier.com>'
export TRADIER_ACCOUNT_ID='<your live account id>'
export TRADIER_ENV=live
export TRADIER_LIVE_CONFIRM='I have read RISK.md'

# Conservative starting environment
export RISK_PER_TRADE=10           # $10 risk per stop-out
export MAX_DAILY_LOSS=-30          # halt after a $30 loss day
export MAX_OPEN_POSITIONS=1

python live_trader.py --symbol SPY --timeframe 15m \
    --lookback 48 --threshold 0.015 --atr-mult 2.5
```

The script will refuse to start if `TRADIER_LIVE_CONFIRM` is missing or wrong.

## When to stop

Halt and re-evaluate the moment any of these are true:

1. **Three consecutive max-loss days.** Something is not behaving like the backtest. Stop and figure out what.
2. **A fill differs from logged price by more than 2 × ATR.** A slippage or feed bug is eating your edge.
3. **The script crashes mid-trade.** Don't restart blind. Reconcile your live positions against the state file before doing anything.
4. **You're tempted to override the cap, the halt, or the EOD exit.** This is the most common way new live-traders blow up — discretionary tweaks that the backtest never validated. Don't.

If any of those happen: stop the script, flatten manually, and post an issue on the repo with what happened.
