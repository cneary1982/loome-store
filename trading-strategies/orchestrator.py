"""Multi-strategy live trading orchestrator.

Reads a list of Strategy instances from strategies.py, then runs all of them
against a single Tradier connection. Per-symbol lock guarantees only one open
trade per security across all strategies. State is published to state.json
for the Streamlit dashboard; commands.json is read back from the dashboard
(kill switch, per-strategy enable/disable).

Usage:
    export TRADIER_TOKEN='...'
    export TRADIER_ACCOUNT_ID='...'
    python orchestrator.py

    # one-shot (for cron):
    python orchestrator.py --once

The strategies module is imported by NAME (default 'strategies'). To run a
different config file:
    python orchestrator.py --config my_strategies
"""
from __future__ import annotations

import argparse
import importlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from backtest import atr as compute_atr
from backtest import label as compute_label
from position_manager import OpenPosition, PositionManager
from tradier import FUTURE_TO_ETF, TradierClient, TradierError

POLL_SECONDS_DEFAULT = 60
RTH_OPEN_MIN  = 9 * 60 + 30
RTH_CLOSE_MIN = 16 * 60
EOD_FLAT_MIN  = 15 * 60 + 55

log = logging.getLogger("orchestrator")


# ─── Strategy interface ─────────────────────────────────────────────────────
@dataclass
class StrategySignal:
    side:           str       # 'long' / 'short'
    entry_estimate: float     # last close
    atr_at_signal:  float
    tp_distance:    float     # in price units
    sl_distance:    float     # in price units
    bar_ts:         str       # ISO8601 of the bar that triggered the signal


class Strategy(ABC):
    """A registered strategy. Subclass and implement `signal`."""
    name:      str
    symbol:    str
    timeframe: str
    broker:    str = "tradier"

    def __init__(self, name: str, symbol: str, timeframe: str):
        self.name = name
        self.symbol = symbol
        self.timeframe = timeframe

    @abstractmethod
    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp
               ) -> Optional[StrategySignal]:
        """Look at the most recently CLOSED bar in `bars`. Return a signal or None."""


# ─── Regime breakout (the strategy we backtested) ───────────────────────────
class RegimeBreakout(Strategy):
    """Markov-regime breakout from backtest.py, exposed as a live Strategy."""

    def __init__(self, name: str, symbol: str, timeframe: str,
                 lookback: int, threshold: float, atr_mult: float):
        super().__init__(name, symbol, timeframe)
        self.lookback = lookback
        self.threshold = threshold
        self.atr_mult = atr_mult

    def signal(self, bars: pd.DataFrame, now_utc: pd.Timestamp
               ) -> Optional[StrategySignal]:
        if len(bars) < self.lookback + 16:
            return None
        # Skip the most recent bar if it's still in progress (we want closed only)
        lbl = compute_label(bars["Close"], self.lookback, self.threshold)
        atr_s = compute_atr(bars["High"], bars["Low"], bars["Close"])
        if len(lbl) < 2:
            return None
        prev, curr = int(lbl.iloc[-2]), int(lbl.iloc[-1])
        if curr == 1 or prev == curr:
            return None
        last_idx = lbl.index[-1]
        a = float(atr_s.loc[last_idx]) if last_idx in atr_s.index else float("nan")
        if pd.isna(a) or a == 0:
            return None
        side = "long" if curr == 2 else "short"
        entry = float(bars["Close"].iloc[-1])
        dist  = self.atr_mult * a
        return StrategySignal(
            side=side, entry_estimate=entry,
            atr_at_signal=a, tp_distance=dist, sl_distance=dist,
            bar_ts=str(last_idx))


# ─── Sizing ─────────────────────────────────────────────────────────────────
def shares_for_risk(risk_dollars: float, sl_distance: float) -> int:
    """Vol-targeted: each share risks `sl_distance` if stopped out."""
    if sl_distance <= 0:
        return 0
    import math
    return max(1, math.floor(risk_dollars / sl_distance))


# ─── Bar cache ──────────────────────────────────────────────────────────────
class BarCache:
    """One Tradier fetch per (symbol, timeframe) per orchestrator tick."""
    def __init__(self, client: TradierClient):
        self.client = client
        self._cache: dict[tuple[str, str], pd.DataFrame] = {}

    def reset(self) -> None:
        self._cache.clear()

    def get(self, symbol: str, timeframe: str, lookback_bars: int) -> pd.DataFrame:
        k = (symbol, timeframe)
        if k in self._cache:
            return self._cache[k]
        df = self._fetch(symbol, timeframe, lookback_bars)
        self._cache[k] = df
        return df

    def _fetch(self, symbol: str, timeframe: str, lookback_bars: int) -> pd.DataFrame:
        if timeframe == "1d":
            end   = datetime.now(timezone.utc).date()
            start = end - timedelta(days=max(lookback_bars * 3, 90))
            return self.client.daily_bars(symbol, start.isoformat(), end.isoformat())
        intraday_map = {"1m": "1min", "5m": "5min", "15m": "15min"}
        if timeframe not in intraday_map:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        et = pd.Timestamp.now(tz="America/New_York")
        # ~lookback bars of history + buffer
        per_day = {"1m": 390, "5m": 78, "15m": 26}[timeframe]
        days = max(lookback_bars // per_day + 2, 3)
        start = (et - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
        end   = et.strftime("%Y-%m-%d %H:%M")
        return self.client.intraday_bars(symbol, intraday_map[timeframe], start, end)


# ─── Main loop ──────────────────────────────────────────────────────────────
class Orchestrator:
    def __init__(self, strategies: list[Strategy], pm: PositionManager,
                 client: TradierClient, risk_per_trade: float):
        self.strategies = strategies
        self.pm = pm
        self.client = client
        self.risk_per_trade = risk_per_trade
        self.bars = BarCache(client)
        for s in strategies:
            pm.register_strategy(s.name, s.symbol, s.timeframe)
        pm.set_tradier_env(client.env)

    # ─── Exits ──────────────────────────────────────────────────────────────
    def manage_exits(self) -> None:
        et_now = pd.Timestamp.now(tz="America/New_York")
        eod = (et_now.hour * 60 + et_now.minute) >= EOD_FLAT_MIN
        for pos in self.pm.open_positions():
            try:
                bars = self.bars.get(pos.symbol, "5m", lookback_bars=200)
            except TradierError as e:
                log.warning("Exit-monitor bar fetch failed for %s: %s", pos.symbol, e)
                continue
            if bars.empty:
                continue
            since = bars[bars.index > pd.Timestamp(pos.opened_at, tz="UTC")]
            exit_px, reason = None, None
            long = pos.side == "long"
            for _, b in since.iterrows():
                if long:
                    if b.High >= pos.tp: exit_px, reason = pos.tp, "TP"; break
                    if b.Low  <= pos.sl: exit_px, reason = pos.sl, "SL"; break
                else:
                    if b.Low  <= pos.tp: exit_px, reason = pos.tp, "TP"; break
                    if b.High >= pos.sl: exit_px, reason = pos.sl, "SL"; break
            if exit_px is None and eod:
                q = self.client.quote(pos.symbol)
                exit_px = float(q.get("last") or q.get("close") or pos.entry)
                reason = "EOD"
            if exit_px is None:
                continue
            tradier_side = "sell" if long else "buy_to_cover"
            try:
                self.client.place_market(pos.symbol, tradier_side, pos.shares,
                                         tag=f"exit-{reason}")
            except TradierError as e:
                log.error("EXIT order failed for %s: %s", pos.symbol, e)
                continue
            self.pm.close(pos.symbol, exit_px, reason)
            log.info("EXIT %s via %s @ %.2f", pos.symbol, reason, exit_px)

    # ─── Entries ────────────────────────────────────────────────────────────
    def run_signals(self) -> None:
        et_now = pd.Timestamp.now(tz="America/New_York")
        et_min = et_now.hour * 60 + et_now.minute
        rth_open = RTH_OPEN_MIN <= et_min < (EOD_FLAT_MIN - 5)
        if et_now.weekday() >= 5:
            return
        if not rth_open:
            return                              # entries are RTH-only for ETFs
        if self.pm.is_halted():
            return

        open_syms = self.pm.open_symbols()

        for s in self.strategies:
            if not self.pm.is_enabled(s.name):
                continue
            if s.symbol in open_syms:
                continue                        # per-symbol lock
            try:
                bars = self.bars.get(s.symbol, s.timeframe, lookback_bars=300)
            except TradierError as e:
                log.warning("Bar fetch failed for %s/%s: %s",
                            s.symbol, s.timeframe, e)
                continue
            if bars.empty:
                continue
            sig = s.signal(bars, now_utc=pd.Timestamp.now(tz="UTC"))
            if sig is None:
                continue
            if self.pm.already_acted(s.name, sig.bar_ts):
                continue

            shares = shares_for_risk(self.risk_per_trade, sig.sl_distance)
            if shares < 1:
                continue

            tradier_side = "buy" if sig.side == "long" else "sell_short"
            try:
                resp = self.client.place_market(s.symbol, tradier_side, shares,
                                                tag=f"{s.name}")
            except TradierError as e:
                log.error("ENTRY order failed for %s on %s: %s",
                          s.name, s.symbol, e)
                continue
            tp = (sig.entry_estimate + sig.tp_distance) if sig.side == "long" \
                 else (sig.entry_estimate - sig.tp_distance)
            sl = (sig.entry_estimate - sig.sl_distance) if sig.side == "long" \
                 else (sig.entry_estimate + sig.sl_distance)
            pos = OpenPosition(
                symbol=s.symbol, strategy=s.name, side=sig.side,
                shares=shares, entry=sig.entry_estimate, tp=tp, sl=sl,
                atr_at_entry=sig.atr_at_signal,
                opened_at=str(pd.Timestamp.now(tz="UTC")),
                tradier_order_id=str(resp.get("id", "")))
            claimed = self.pm.try_open(pos)
            if claimed:
                self.pm.mark_signal(s.name, sig.bar_ts, sig.side)
                open_syms.add(s.symbol)
                log.info("ENTRY %s: %s %d %s @ ~%.2f (TP=%.2f SL=%.2f)",
                         s.name, tradier_side, shares, s.symbol,
                         sig.entry_estimate, tp, sl)
            else:
                # Two strategies fired same poll on same symbol; we lost the race.
                # Try to cancel the order we just placed.
                oid = resp.get("id")
                if oid:
                    try:
                        self.client.cancel(oid)
                    except TradierError:
                        pass
                log.info("LOST_RACE %s on %s; order cancelled.", s.name, s.symbol)

    # ─── Tick ───────────────────────────────────────────────────────────────
    def tick(self) -> None:
        self.pm.maybe_rollover_day()
        self.pm.apply_commands()
        try:
            bal = self.client.balances()
            self.pm.set_balance(bal)
        except TradierError as e:
            log.warning("balances fetch failed: %s", e)
        self.bars.reset()
        try:
            self.manage_exits()
            self.run_signals()
        finally:
            self.pm.write_state()


def load_strategies(module_name: str) -> list[Strategy]:
    mod = importlib.import_module(module_name)
    strats = getattr(mod, "STRATEGIES", None)
    if not strats:
        raise SystemExit(f"{module_name}.STRATEGIES not found or empty.")
    seen = set()
    for s in strats:
        if not isinstance(s, Strategy):
            raise SystemExit(f"{s!r} is not a Strategy subclass.")
        if s.name in seen:
            raise SystemExit(f"Duplicate strategy name: {s.name}")
        if s.symbol in FUTURE_TO_ETF:
            etf = FUTURE_TO_ETF[s.symbol]
            raise SystemExit(
                f"Strategy '{s.name}' uses futures symbol {s.symbol}, which "
                f"Tradier doesn't trade. Use ETF proxy '{etf}' instead.")
        seen.add(s.name)
    return strats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="strategies",
                    help="Python module name with STRATEGIES list (default 'strategies')")
    ap.add_argument("--once",   action="store_true",
                    help="Single tick then exit (for cron)")
    ap.add_argument("--poll-seconds", type=int, default=POLL_SECONDS_DEFAULT)
    ap.add_argument("--risk-per-trade", type=float, default=25.0,
                    help="Dollars risked per stop-out (default $25)")
    ap.add_argument("--max-daily-loss", type=float, default=-100.0)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    client = TradierClient.from_env()
    strats = load_strategies(args.config)
    pm     = PositionManager(max_daily_loss=args.max_daily_loss)
    orch   = Orchestrator(strats, pm, client, risk_per_trade=args.risk_per_trade)

    log.info("env=%s account=%s strategies=%d risk_per_trade=$%.2f max_daily_loss=$%.2f",
             client.env, client.account_id, len(strats),
             args.risk_per_trade, args.max_daily_loss)
    for s in strats:
        log.info("  registered: %s  symbol=%s  tf=%s", s.name, s.symbol, s.timeframe)

    if args.once:
        orch.tick()
        return

    while True:
        try:
            orch.tick()
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as e:
            log.exception("Tick failed: %s", e)
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
