"""
ASIA SESSION FUTURES SCALPER
==============================
Jarvis's autonomous overnight trading engine.

MISSION: Make $5,000 tonight with $20K capital. $2,500 max loss. Asia session (6PM-2AM ET).
INSTRUMENT: MNQ (Micro Nasdaq futures) — $2/point, ~$1,500 margin per contract.
MAX CONTRACTS: 10 MNQ at a time ($2K risk budget / $200 stop = 10 max)

This is NOT a signal generator. This is a LIVE TRADING LOOP that:
  1. Picks the best 5 strategies from the full library for current conditions
  2. Runs them concurrently on 1-min MNQ data
  3. Executes entries/exits autonomously
  4. Tracks every trade with P&L
  5. Stops when target hit or loss limit reached

STRATEGY SELECTION CRITERIA (Asia session specific):
  - Low volatility = mean reversion works better
  - Thinner order book = breakouts overshoot more
  - No US news = pure technical setups
  - VIX overnight = gamma decay plays
"""

import json, logging, time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

log = logging.getLogger("asia_scalper")


# ── SESSION CONFIG ──────────────────────────────────────────────────

class SessionState(Enum):
    SCANNING = "scanning"
    TRADING = "trading"
    IN_POSITION = "in_position"
    COOLING = "cooling"
    TARGET_HIT = "target_hit"
    STOPPED_OUT = "stopped_out"
    HALTED = "halted"


@dataclass
class ScalperConfig:
    target_pnl: float = 5000.0
    max_loss: float = 2500.0
    capital: float = 20000.0
    instrument: str = "MNQ"
    tick_value: float = 0.50        # MNQ = $0.50 per tick (0.25 point)
    point_value: float = 2.0        # MNQ = $2 per point
    margin_per_contract: float = 1500.0
    max_contracts: int = 10
    session_start: str = "18:00"    # 6 PM ET
    session_end: str = "02:00"      # 2 AM ET
    max_trades_per_hour: int = 8
    cooldown_after_loss_streak: int = 3
    cooldown_minutes: int = 10
    max_hold_minutes: int = 30      # no sitting — scalps only


# ── STRATEGY TEMPLATES ──────────────────────────────────────────────

@dataclass
class ScalpSignal:
    strategy: str
    direction: str       # "long" or "short"
    entry_price: float
    stop_points: float   # stop distance in points
    target_points: float # target distance in points
    confidence: float    # 0-1
    contracts: int
    reason: str
    timestamp: str = ""


@dataclass
class Trade:
    id: int
    strategy: str
    direction: str
    entry_price: float
    entry_time: str
    stop_price: float
    target_price: float
    contracts: int
    exit_price: float = 0.0
    exit_time: str = ""
    pnl: float = 0.0
    status: str = "open"  # "open", "win", "loss", "timeout", "manual"
    hold_seconds: int = 0


class ORBMicroBreakout:
    """
    Opening Range Breakout on Asia session open.
    First 15 min range → trade the break of high/low.
    Best when: range < 20 points (tight = explosive break).
    """
    name = "ORB Micro Breakout"

    def __init__(self):
        self.range_high = None
        self.range_low = None
        self.range_set = False
        self.bars_seen = 0

    def on_bar(self, bar: dict) -> Optional[ScalpSignal]:
        self.bars_seen += 1
        high = bar["high"]
        low = bar["low"]
        close = bar["close"]

        if self.bars_seen <= 15:
            if self.range_high is None:
                self.range_high = high
                self.range_low = low
            else:
                self.range_high = max(self.range_high, high)
                self.range_low = min(self.range_low, low)
            return None

        if not self.range_set:
            self.range_set = True
            range_size = self.range_high - self.range_low
            log.info(f"ORB range set: {self.range_low:.2f} - {self.range_high:.2f} ({range_size:.0f} pts)")
            if range_size > 30:
                log.info("ORB range too wide — skipping")
                return None

        if close > self.range_high + 2:
            stop = max(self.range_high - 3, close - 15)
            target = close + (close - stop) * 2
            return ScalpSignal(
                strategy=self.name, direction="long",
                entry_price=close, stop_points=close - stop,
                target_points=target - close, confidence=0.70,
                contracts=self._size(close - stop),
                reason=f"ORB breakout above {self.range_high:.0f}",
            )

        if close < self.range_low - 2:
            stop = min(self.range_low + 3, close + 15)
            target = close - (stop - close) * 2
            return ScalpSignal(
                strategy=self.name, direction="short",
                entry_price=close, stop_points=stop - close,
                target_points=close - target, confidence=0.70,
                contracts=self._size(stop - close),
                reason=f"ORB breakdown below {self.range_low:.0f}",
            )
        return None

    def _size(self, risk_pts):
        risk_dollars = risk_pts * 2.0
        max_risk = 250
        return max(1, min(10, int(max_risk / risk_dollars)))


class EMA9Bounce:
    """
    Trend continuation — price pulls back to 9 EMA then bounces.
    Best when: clear trend established (ADX > 20).
    """
    name = "EMA9 Bounce"

    def __init__(self):
        self.closes = []
        self.ema9 = None

    def on_bar(self, bar: dict) -> Optional[ScalpSignal]:
        close = bar["close"]
        self.closes.append(close)

        if len(self.closes) < 20:
            return None

        self.ema9 = self._ema(self.closes, 9)
        ema20 = self._ema(self.closes, 20)

        if self.ema9 is None or ema20 is None:
            return None

        trend_up = self.ema9 > ema20
        touching_ema = abs(close - self.ema9) < 3

        prev_close = self.closes[-2] if len(self.closes) > 1 else close

        if trend_up and touching_ema and close > prev_close:
            stop = self.ema9 - 8
            target = close + 12
            return ScalpSignal(
                strategy=self.name, direction="long",
                entry_price=close, stop_points=close - stop,
                target_points=target - close, confidence=0.65,
                contracts=self._size(close - stop),
                reason=f"EMA9 bounce in uptrend, EMA9={self.ema9:.0f}",
            )

        if not trend_up and touching_ema and close < prev_close:
            stop = self.ema9 + 8
            target = close - 12
            return ScalpSignal(
                strategy=self.name, direction="short",
                entry_price=close, stop_points=stop - close,
                target_points=close - target, confidence=0.65,
                contracts=self._size(stop - close),
                reason=f"EMA9 rejection in downtrend, EMA9={self.ema9:.0f}",
            )
        return None

    def _ema(self, data, period):
        if len(data) < period:
            return None
        k = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for val in data[period:]:
            ema = val * k + ema * (1 - k)
        return ema

    def _size(self, risk_pts):
        return max(1, min(8, int(250 / (risk_pts * 2.0))))


class VWAPReversion:
    """
    Mean reversion to VWAP — price overextends, snaps back.
    Best when: Asia session (lower vol, VWAP acts as magnet).
    """
    name = "VWAP Reversion"

    def __init__(self):
        self.cum_vol = 0
        self.cum_pv = 0
        self.vwap = None
        self.bar_count = 0

    def on_bar(self, bar: dict) -> Optional[ScalpSignal]:
        close = bar["close"]
        high = bar["high"]
        low = bar["low"]
        volume = bar.get("volume", 100)
        typical = (high + low + close) / 3

        self.cum_vol += volume
        self.cum_pv += typical * volume
        self.vwap = self.cum_pv / self.cum_vol if self.cum_vol > 0 else close
        self.bar_count += 1

        if self.bar_count < 30:
            return None

        deviation = close - self.vwap

        if deviation > 15:
            stop = close + 8
            target = self.vwap + 3
            return ScalpSignal(
                strategy=self.name, direction="short",
                entry_price=close, stop_points=stop - close,
                target_points=close - target, confidence=0.60,
                contracts=self._size(stop - close),
                reason=f"Extended {deviation:.0f}pts above VWAP={self.vwap:.0f}, reverting",
            )

        if deviation < -15:
            stop = close - 8
            target = self.vwap - 3
            return ScalpSignal(
                strategy=self.name, direction="long",
                entry_price=close, stop_points=close - stop,
                target_points=target - close, confidence=0.60,
                contracts=self._size(close - stop),
                reason=f"Extended {abs(deviation):.0f}pts below VWAP={self.vwap:.0f}, reverting",
            )
        return None

    def _size(self, risk_pts):
        return max(1, min(6, int(200 / (risk_pts * 2.0))))


class RSIExtreme:
    """
    RSI(5) extreme fade — overbought/oversold on fast RSI.
    Best when: range-bound, no strong trend.
    """
    name = "RSI(5) Extreme Fade"

    def __init__(self):
        self.closes = []

    def on_bar(self, bar: dict) -> Optional[ScalpSignal]:
        close = bar["close"]
        self.closes.append(close)

        if len(self.closes) < 10:
            return None

        rsi = self._rsi(self.closes, 5)
        if rsi is None:
            return None

        if rsi > 85:
            stop = close + 10
            target = close - 8
            return ScalpSignal(
                strategy=self.name, direction="short",
                entry_price=close, stop_points=10,
                target_points=8, confidence=0.55,
                contracts=self._size(10),
                reason=f"RSI(5) = {rsi:.0f} extreme overbought — fading",
            )

        if rsi < 15:
            stop = close - 10
            target = close + 8
            return ScalpSignal(
                strategy=self.name, direction="long",
                entry_price=close, stop_points=10,
                target_points=8, confidence=0.55,
                contracts=self._size(10),
                reason=f"RSI(5) = {rsi:.0f} extreme oversold — fading",
            )
        return None

    def _rsi(self, data, period):
        if len(data) < period + 1:
            return None
        changes = [data[i] - data[i-1] for i in range(-period, 0)]
        gains = [c for c in changes if c > 0]
        losses = [-c for c in changes if c < 0]
        avg_gain = sum(gains) / period if gains else 0.001
        avg_loss = sum(losses) / period if losses else 0.001
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _size(self, risk_pts):
        return max(1, min(5, int(150 / (risk_pts * 2.0))))


class MomentumBreak:
    """
    Volume spike + directional candle = momentum entry.
    Best when: news drops during Asia (China data, earnings after-hours).
    """
    name = "Momentum Break"

    def __init__(self):
        self.volumes = []
        self.closes = []

    def on_bar(self, bar: dict) -> Optional[ScalpSignal]:
        close = bar["close"]
        volume = bar.get("volume", 100)
        body = abs(close - bar["open"])

        self.volumes.append(volume)
        self.closes.append(close)

        if len(self.volumes) < 20:
            return None

        avg_vol = sum(self.volumes[-20:]) / 20
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1

        if vol_ratio < 2.5 or body < 5:
            return None

        direction = "long" if close > bar["open"] else "short"

        if direction == "long":
            stop = bar["low"] - 2
            target = close + body * 1.5
            return ScalpSignal(
                strategy=self.name, direction="long",
                entry_price=close, stop_points=close - stop,
                target_points=target - close, confidence=0.60,
                contracts=self._size(close - stop),
                reason=f"Volume spike {vol_ratio:.1f}x + {body:.0f}pt bull candle",
            )
        else:
            stop = bar["high"] + 2
            target = close - body * 1.5
            return ScalpSignal(
                strategy=self.name, direction="short",
                entry_price=close, stop_points=stop - close,
                target_points=close - target, confidence=0.60,
                contracts=self._size(stop - close),
                reason=f"Volume spike {vol_ratio:.1f}x + {body:.0f}pt bear candle",
            )

    def _size(self, risk_pts):
        return max(1, min(8, int(250 / (risk_pts * 2.0))))


# ── THE SCALPING ENGINE ────────────────────────────────────────────

class AsiaSessionScalper:
    """
    The autonomous trading loop. Runs 5 strategies concurrently.
    Manages entries, exits, P&L tracking, and the trade log.
    """

    def __init__(self, config: ScalperConfig = None, broker=None):
        self.config = config or ScalperConfig()
        self.broker = broker
        self.state = SessionState.SCANNING

        self.strategies = [
            ORBMicroBreakout(),
            EMA9Bounce(),
            VWAPReversion(),
            RSIExtreme(),
            MomentumBreak(),
        ]

        self.trades: List[Trade] = []
        self.open_trades: List[Trade] = []
        self.session_pnl = 0.0
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.consecutive_losses = 0
        self.cooldown_until = None
        self.peak_pnl = 0.0
        self.max_drawdown = 0.0

    def on_bar(self, bar: dict):
        """Process one 1-minute bar. Called by data feed."""
        now = bar.get("time", datetime.now(timezone.utc).isoformat())

        if self.state == SessionState.TARGET_HIT:
            return
        if self.state == SessionState.STOPPED_OUT:
            return
        if self.state == SessionState.HALTED:
            return

        if self.cooldown_until and now < self.cooldown_until:
            return

        self._check_exits(bar)

        if self.session_pnl >= self.config.target_pnl:
            self.state = SessionState.TARGET_HIT
            log.info(f"TARGET HIT! P&L: ${self.session_pnl:,.0f}")
            self._close_all(bar, "target_hit")
            return

        if self.session_pnl <= -self.config.max_loss:
            self.state = SessionState.STOPPED_OUT
            log.info(f"LOSS LIMIT HIT! P&L: ${self.session_pnl:,.0f}")
            self._close_all(bar, "loss_limit")
            return

        if len(self.open_trades) >= 2:
            return

        for strat in self.strategies:
            signal = strat.on_bar(bar)
            if signal and self._can_trade(signal):
                self._enter_trade(signal, bar)

    def _can_trade(self, signal: ScalpSignal) -> bool:
        if len(self.open_trades) >= 2:
            return False
        total_contracts = sum(t.contracts for t in self.open_trades)
        if total_contracts + signal.contracts > self.config.max_contracts:
            return False
        if self.consecutive_losses >= self.config.cooldown_after_loss_streak:
            self.cooldown_until = (
                datetime.now(timezone.utc) + timedelta(minutes=self.config.cooldown_minutes)
            ).isoformat()
            self.consecutive_losses = 0
            log.info(f"Cooldown triggered — pausing {self.config.cooldown_minutes} min")
            return False
        potential_loss = signal.stop_points * signal.contracts * self.config.point_value
        if self.session_pnl - potential_loss < -self.config.max_loss:
            return False
        return True

    def _enter_trade(self, signal: ScalpSignal, bar: dict):
        self.trade_count += 1
        entry = signal.entry_price

        if signal.direction == "long":
            stop = entry - signal.stop_points
            target = entry + signal.target_points
        else:
            stop = entry + signal.stop_points
            target = entry - signal.target_points

        trade = Trade(
            id=self.trade_count,
            strategy=signal.strategy,
            direction=signal.direction,
            entry_price=entry,
            entry_time=bar.get("time", datetime.now(timezone.utc).isoformat()),
            stop_price=stop,
            target_price=target,
            contracts=signal.contracts,
        )

        self.open_trades.append(trade)
        self.trades.append(trade)
        self.state = SessionState.IN_POSITION

        log.info(
            f"ENTRY #{trade.id} | {signal.strategy} | {signal.direction.upper()} "
            f"{signal.contracts}x {self.config.instrument} @ {entry:.2f} | "
            f"SL {stop:.2f} TP {target:.2f} | {signal.reason}"
        )

        if self.broker:
            try:
                self.broker.place_order(
                    symbol=self.config.instrument,
                    side="buy" if signal.direction == "long" else "sell",
                    qty=signal.contracts,
                    order_type="market",
                )
            except Exception as e:
                log.error(f"Broker order failed: {e}")

    def _check_exits(self, bar: dict):
        now = bar.get("time", datetime.now(timezone.utc).isoformat())

        for trade in list(self.open_trades):
            high = bar["high"]
            low = bar["low"]

            if trade.direction == "long":
                if low <= trade.stop_price:
                    self._exit_trade(trade, trade.stop_price, "loss", now)
                elif high >= trade.target_price:
                    self._exit_trade(trade, trade.target_price, "win", now)
            else:
                if high >= trade.stop_price:
                    self._exit_trade(trade, trade.stop_price, "loss", now)
                elif low <= trade.target_price:
                    self._exit_trade(trade, trade.target_price, "win", now)

            if trade.status == "open":
                entry_dt = trade.entry_time
                hold_bars = sum(1 for t in self.trades if t.id <= trade.id)
                if hold_bars > self.config.max_hold_minutes:
                    self._exit_trade(trade, bar["close"], "timeout", now)

    def _exit_trade(self, trade: Trade, exit_price: float, status: str, now: str):
        trade.exit_price = exit_price
        trade.exit_time = now
        trade.status = status

        if trade.direction == "long":
            trade.pnl = (exit_price - trade.entry_price) * trade.contracts * self.config.point_value
        else:
            trade.pnl = (trade.entry_price - exit_price) * trade.contracts * self.config.point_value

        self.session_pnl += trade.pnl
        self.peak_pnl = max(self.peak_pnl, self.session_pnl)
        self.max_drawdown = max(self.max_drawdown, self.peak_pnl - self.session_pnl)

        if trade.pnl > 0:
            self.win_count += 1
            self.consecutive_losses = 0
        else:
            self.loss_count += 1
            self.consecutive_losses += 1

        if trade in self.open_trades:
            self.open_trades.remove(trade)

        if not self.open_trades:
            self.state = SessionState.SCANNING

        icon = "W" if trade.pnl > 0 else "L" if trade.pnl < 0 else "T"
        log.info(
            f"EXIT  #{trade.id} [{icon}] | {trade.strategy} | "
            f"${trade.pnl:+,.0f} | Session: ${self.session_pnl:+,.0f} | "
            f"W/L: {self.win_count}/{self.loss_count}"
        )

    def _close_all(self, bar: dict, reason: str):
        for trade in list(self.open_trades):
            self._exit_trade(trade, bar["close"], reason, bar.get("time", ""))

    def get_dashboard(self) -> dict:
        """Returns full state for the front end."""
        wr = (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0
        avg_win = 0
        avg_loss = 0
        wins = [t.pnl for t in self.trades if t.pnl > 0]
        losses = [t.pnl for t in self.trades if t.pnl < 0]
        if wins:
            avg_win = sum(wins) / len(wins)
        if losses:
            avg_loss = sum(losses) / len(losses)

        return {
            "state": self.state.value,
            "session_pnl": self.session_pnl,
            "target": self.config.target_pnl,
            "loss_limit": self.config.max_loss,
            "progress_pct": min(100, max(0, (self.session_pnl / self.config.target_pnl) * 100)),
            "trade_count": self.trade_count,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": wr,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "peak_pnl": self.peak_pnl,
            "max_drawdown": self.max_drawdown,
            "consecutive_losses": self.consecutive_losses,
            "open_positions": [
                {
                    "id": t.id,
                    "strategy": t.strategy,
                    "direction": t.direction,
                    "entry": t.entry_price,
                    "stop": t.stop_price,
                    "target": t.target_price,
                    "contracts": t.contracts,
                    "entry_time": t.entry_time,
                    "unrealized_pnl": 0,
                }
                for t in self.open_trades
            ],
            "recent_trades": [
                {
                    "id": t.id,
                    "strategy": t.strategy,
                    "direction": t.direction,
                    "entry": t.entry_price,
                    "exit": t.exit_price,
                    "pnl": t.pnl,
                    "status": t.status,
                    "contracts": t.contracts,
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                }
                for t in self.trades[-20:]
            ],
            "strategies_active": [s.name for s in self.strategies],
        }

    def session_report(self) -> str:
        d = self.get_dashboard()
        lines = [
            "=" * 60,
            f"  ASIA SESSION SCALPER — FINAL REPORT",
            f"  State: {d['state'].upper()}",
            "=" * 60,
            "",
            f"  Session P&L:    ${d['session_pnl']:+,.0f} / ${d['target']:,.0f} target",
            f"  Progress:       {d['progress_pct']:.0f}%",
            f"  Peak P&L:       ${d['peak_pnl']:+,.0f}",
            f"  Max Drawdown:   ${d['max_drawdown']:,.0f}",
            "",
            f"  Trades:         {d['trade_count']}",
            f"  Win Rate:       {d['win_rate']:.0f}%",
            f"  Avg Win:        ${d['avg_win']:+,.0f}",
            f"  Avg Loss:       ${d['avg_loss']:+,.0f}",
            "",
            "  STRATEGIES USED:",
        ]
        strat_pnl = {}
        strat_count = {}
        for t in self.trades:
            strat_pnl[t.strategy] = strat_pnl.get(t.strategy, 0) + t.pnl
            strat_count[t.strategy] = strat_count.get(t.strategy, 0) + 1

        for name, pnl in sorted(strat_pnl.items(), key=lambda x: x[1], reverse=True):
            count = strat_count[name]
            lines.append(f"    {name}: ${pnl:+,.0f} ({count} trades)")

        lines.append("")
        lines.append("  TRADE LOG:")
        for t in self.trades:
            icon = "W" if t.pnl > 0 else "L"
            lines.append(
                f"    #{t.id} [{icon}] {t.strategy} | {t.direction} {t.contracts}x "
                f"@ {t.entry_price:.0f} -> {t.exit_price:.0f} | ${t.pnl:+,.0f}"
            )

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)
