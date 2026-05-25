"""Live trading runner — polls Tradier, runs the strategy, places orders.

Defaults are SAFE:
  - TRADIER_ENV=sandbox unless explicitly flipped (see tradier.py)
  - RISK_PER_TRADE=$25 (vol-targeted; shares = floor(RISK / (atr_mult * ATR)))
  - MAX_OPEN_POSITIONS=1
  - MAX_DAILY_LOSS=-$100 (circuit breaker; trips a halt for the day)
  - One trade per signal: no doubling down, no averaging in
  - All state lives in live_state.json next to this script

Usage:
    export TRADIER_TOKEN='...'
    export TRADIER_ACCOUNT_ID='...'
    python live_trader.py --symbol SPY --timeframe 15m \\
        --lookback 48 --threshold 0.015 --atr-mult 2.5

This is the WORKING-OUT-OF-THE-BOX path. Read RISK.md before going live.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from backtest import atr, label
from strategy import _in_any_window
from tradier import FUTURE_TO_ETF, TradierClient, TradierError

STATE_FILE = Path("live_state.json")

# Same RTH window as the backtest's us_market_hours preset
NY_MIN = lambda h, m=0: h * 60 + m
RTH_WINDOWS = [(NY_MIN(9, 30), NY_MIN(15, 30))]


# ─── State ──────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"open_positions": {}, "daily_pnl": 0.0,
                "halted": False, "last_signal_bar": None,
                "date": datetime.now(timezone.utc).date().isoformat()}
    s = json.loads(STATE_FILE.read_text())
    # Reset daily PnL at session rollover (UTC date change is fine for RTH)
    today = datetime.now(timezone.utc).date().isoformat()
    if s.get("date") != today:
        s["daily_pnl"] = 0.0
        s["halted"]    = False
        s["date"]      = today
    return s


def save_state(s: dict) -> None:
    STATE_FILE.write_text(json.dumps(s, indent=2, default=str))


# ─── Sizing ─────────────────────────────────────────────────────────────────
def shares_to_risk(risk_dollars: float, atr_mult: float, atr_value: float) -> int:
    """Volatility-targeted size. Each share risks atr_mult*ATR if stopped out."""
    one_r_per_share = atr_mult * atr_value
    if one_r_per_share <= 0:
        return 0
    return max(1, math.floor(risk_dollars / one_r_per_share))


# ─── Signal extraction (per-bar, with no lookahead) ─────────────────────────
def latest_signal(df: pd.DataFrame, lookback: int, threshold: float
                  ) -> tuple[str | None, float, pd.Timestamp]:
    """Return ('long'|'short'|None, atr_at_bar, bar_timestamp) for the most
    recently CLOSED bar. None means no regime flip on this bar."""
    if len(df) < lookback + 16:
        return None, 0.0, df.index[-1]
    lbl = label(df["Close"], lookback, threshold)
    a   = atr(df["High"], df["Low"], df["Close"])
    last_idx = lbl.index[-1]
    if last_idx not in a.index or pd.isna(a.loc[last_idx]):
        return None, 0.0, last_idx
    if len(lbl) < 2:
        return None, 0.0, last_idx
    prev, curr = int(lbl.iloc[-2]), int(lbl.iloc[-1])
    if curr == 1 or prev == curr:
        return None, float(a.loc[last_idx]), last_idx
    side = "long" if curr == 2 else "short"
    return side, float(a.loc[last_idx]), last_idx


# ─── Main loop ──────────────────────────────────────────────────────────────
TF_TO_TRADIER = {"1m": "1min", "5m": "5min", "15m": "15min"}


def fetch_recent_bars(client: TradierClient, symbol: str, timeframe: str,
                      lookback: int) -> pd.DataFrame:
    if timeframe == "1d":
        end   = datetime.now(timezone.utc).date()
        start = end - timedelta(days=max(lookback * 3, 90))
        return client.daily_bars(symbol, start.isoformat(), end.isoformat())
    if timeframe not in TF_TO_TRADIER:
        raise SystemExit(f"Unsupported timeframe for live trading: {timeframe}. "
                         f"Tradier intraday: {list(TF_TO_TRADIER)} or 1d.")
    et   = pd.Timestamp.now(tz="America/New_York")
    start = (et - timedelta(days=max(lookback // 10 + 3, 7))).strftime("%Y-%m-%d %H:%M")
    end   = et.strftime("%Y-%m-%d %H:%M")
    return client.intraday_bars(symbol, TF_TO_TRADIER[timeframe], start, end)


def run_once(args, client: TradierClient) -> None:
    state = load_state()
    if state.get("halted"):
        print(f"[{datetime.now()}] HALTED for the day "
              f"(daily_pnl={state['daily_pnl']:.2f}). Skipping.")
        return

    df = fetch_recent_bars(client, args.symbol, args.timeframe, args.lookback)
    if df.empty:
        print(f"[{datetime.now()}] No bars returned.")
        return

    # RTH-only entry filter for ETFs. Last bar's NY clock time:
    last_ts = df.index[-1]
    if not _in_any_window(last_ts, RTH_WINDOWS):
        print(f"[{datetime.now()}] {args.symbol} last bar {last_ts} is outside RTH — skip.")
        return

    side, atr_val, bar_ts = latest_signal(df, args.lookback, args.threshold)
    last_signal_bar = state.get("last_signal_bar")
    if side is None:
        print(f"[{datetime.now()}] {args.symbol} {args.timeframe} "
              f"bar={bar_ts}  no signal.")
        return
    if str(bar_ts) == last_signal_bar:
        print(f"[{datetime.now()}] Already acted on bar {bar_ts}. Skip.")
        return

    # Sizing
    risk_dollars = float(os.environ.get("RISK_PER_TRADE", "25"))
    shares = shares_to_risk(risk_dollars, args.atr_mult, atr_val)
    print(f"[{datetime.now()}] SIGNAL {args.symbol} {side} "
          f"bar={bar_ts}  atr={atr_val:.4f}  "
          f"risk=${risk_dollars:.0f}  shares={shares}")

    # Position cap
    open_pos = state.get("open_positions", {})
    if args.symbol in open_pos:
        print(f"  -> already in a {args.symbol} position, skip new entry.")
        return
    if len(open_pos) >= int(os.environ.get("MAX_OPEN_POSITIONS", "1")):
        print(f"  -> at MAX_OPEN_POSITIONS, skip.")
        return

    # Place order
    tradier_side = "buy" if side == "long" else "sell_short"
    try:
        resp = client.place_market(args.symbol, tradier_side, shares,
                                   tag=f"breakout-{args.timeframe}-{side}")
    except TradierError as e:
        print(f"  !! ORDER FAILED: {e}")
        return

    quote = client.quote(args.symbol)
    fill_estimate = float(quote.get("last") or quote.get("close") or 0.0)
    tp_dist = args.atr_mult * atr_val
    state["open_positions"][args.symbol] = {
        "side":          side,
        "shares":        shares,
        "entry_estimate": fill_estimate,
        "atr_at_entry":  atr_val,
        "tp_dist":       tp_dist,
        "tradier_order": resp,
        "opened_at":     str(bar_ts),
    }
    state["last_signal_bar"] = str(bar_ts)
    save_state(state)
    print(f"  -> ENTRY placed: {tradier_side} {shares} {args.symbol}  "
          f"order_id={resp.get('id')}  estimated fill={fill_estimate:.2f}")


def manage_exits(args, client: TradierClient) -> None:
    """Close any open position whose TP or SL was touched, or whose RTH is closing."""
    state = load_state()
    open_pos = state.get("open_positions", {})
    if not open_pos:
        return
    df = fetch_recent_bars(client, args.symbol, args.timeframe, args.lookback)
    if df.empty:
        return
    pos = open_pos.get(args.symbol)
    if pos is None:
        return
    entry = pos["entry_estimate"]
    tp_dist = pos["tp_dist"]
    long = pos["side"] == "long"
    tp = entry + tp_dist if long else entry - tp_dist
    sl = entry - tp_dist if long else entry + tp_dist

    bars_since = df[df.index > pd.Timestamp(pos["opened_at"], tz="UTC")]
    exit_reason = None
    exit_px     = None
    for _, b in bars_since.iterrows():
        if long:
            if b.High >= tp:
                exit_reason, exit_px = "TP", tp; break
            if b.Low <= sl:
                exit_reason, exit_px = "SL", sl; break
        else:
            if b.Low <= tp:
                exit_reason, exit_px = "TP", tp; break
            if b.High >= sl:
                exit_reason, exit_px = "SL", sl; break

    # End-of-RTH force flat (ETFs don't trade overnight; force exit at 15:55 ET)
    et_now = pd.Timestamp.now(tz="America/New_York")
    if et_now.hour == 15 and et_now.minute >= 55:
        if exit_reason is None:
            exit_reason = "EOD"
            exit_px = float(client.quote(args.symbol).get("last", entry))

    if exit_reason is None:
        return

    exit_side = "sell" if long else "buy_to_cover"
    try:
        client.place_market(args.symbol, exit_side, pos["shares"],
                            tag=f"exit-{exit_reason}")
    except TradierError as e:
        print(f"  !! EXIT FAILED: {e}")
        return

    realized = (exit_px - entry) * pos["shares"] * (1 if long else -1)
    state["daily_pnl"] = float(state.get("daily_pnl", 0.0)) + realized
    state["open_positions"].pop(args.symbol, None)
    max_loss = float(os.environ.get("MAX_DAILY_LOSS", "-100"))
    if state["daily_pnl"] <= max_loss:
        state["halted"] = True
        print(f"  !! CIRCUIT BREAKER tripped at daily_pnl={state['daily_pnl']:.2f}")
    save_state(state)
    print(f"[{datetime.now()}] EXIT {args.symbol} via {exit_reason} @ {exit_px:.2f}  "
          f"realized=${realized:+.2f}  daily=${state['daily_pnl']:+.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol",    required=True, help="ETF symbol, e.g. SPY, QQQ, GLD")
    ap.add_argument("--timeframe", default="15m", choices=["1m", "5m", "15m", "1d"])
    ap.add_argument("--lookback",  type=int,   default=48)
    ap.add_argument("--threshold", type=float, default=0.015)
    ap.add_argument("--atr-mult",  type=float, default=2.5)
    ap.add_argument("--poll-seconds", type=int, default=60,
                    help="Interval between bar fetches (default 60s)")
    ap.add_argument("--once", action="store_true",
                    help="Run a single iteration and exit (useful for cron)")
    args = ap.parse_args()

    if args.symbol in FUTURE_TO_ETF:
        suggested = FUTURE_TO_ETF[args.symbol]
        print(f"NOTE: {args.symbol} is a futures contract; Tradier doesn't trade it. "
              f"Use {suggested} instead.")
        sys.exit(2)

    client = TradierClient.from_env()
    print(f"[startup] env={client.env}  account={client.account_id}  "
          f"symbol={args.symbol}  tf={args.timeframe}  "
          f"params(lb={args.lookback}, th={args.threshold}, atr={args.atr_mult})")
    bal = client.balances()
    print(f"[startup] cash={bal.get('cash', {}).get('cash_available', '?')}  "
          f"buying_power={bal.get('margin', {}).get('stock_buying_power', '?')}")

    if args.once:
        manage_exits(args, client)
        run_once(args, client)
        return

    while True:
        try:
            manage_exits(args, client)
            run_once(args, client)
        except KeyboardInterrupt:
            print("Stopped.")
            break
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}")
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
