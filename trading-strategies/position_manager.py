"""Central state for the multi-strategy orchestrator.

Owns:
  - Open positions (one per symbol; this is the trade lock)
  - Daily PnL and the halt circuit breaker
  - Last-acted-on bar per (strategy, symbol) so a signal isn't re-fired
  - Recent trade log
  - Persistence to state.json (read by dashboard.py)

The lock: try_open(symbol, strategy_name) atomically claims the symbol or
returns None. If two strategies fire on SPY in the same poll cycle, the first
one wins; the second sees the symbol is taken and skips.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STATE_FILE    = Path("state.json")
COMMANDS_FILE = Path("commands.json")
MAX_RECENT_TRADES = 50


@dataclass
class OpenPosition:
    symbol:       str
    strategy:     str
    side:         str          # 'long' / 'short'
    shares:       int
    entry:        float
    tp:           float
    sl:           float
    atr_at_entry: float
    opened_at:    str          # ISO8601 UTC
    tradier_order_id: Optional[str] = None


@dataclass
class ClosedTrade:
    timestamp: str
    symbol:    str
    strategy:  str
    side:      str
    entry:     float
    exit:      float
    shares:    int
    pnl:       float
    reason:    str             # 'TP' / 'SL' / 'EOD' / 'manual'


@dataclass
class StrategyStatus:
    name:             str
    symbol:           str
    timeframe:        str
    enabled:          bool   = True
    trades_today:     int    = 0
    pnl_today:        float  = 0.0
    last_signal_bar:  Optional[str] = None
    last_signal_side: Optional[str] = None


class PositionManager:
    """Thread-safe central state."""

    def __init__(self,
                 max_daily_loss: float = -100.0,
                 state_file:     Path  = STATE_FILE,
                 commands_file:  Path  = COMMANDS_FILE):
        self._lock = threading.RLock()
        self._open: dict[str, OpenPosition] = {}            # keyed by symbol
        self._strategies: dict[str, StrategyStatus] = {}
        self._recent: list[ClosedTrade] = []
        self._daily_pnl: float = 0.0
        self._halted: bool = False
        self._halt_reason: Optional[str] = None
        self._date: str = datetime.now(timezone.utc).date().isoformat()
        self._max_daily_loss = max_daily_loss
        self._state_file = state_file
        self._commands_file = commands_file
        self._tradier_env: str = "sandbox"
        self._last_balance: dict = {}

    # ─── Registration ───────────────────────────────────────────────────────
    def register_strategy(self, name: str, symbol: str, timeframe: str) -> None:
        with self._lock:
            if name not in self._strategies:
                self._strategies[name] = StrategyStatus(
                    name=name, symbol=symbol, timeframe=timeframe)

    def set_tradier_env(self, env: str) -> None:
        with self._lock:
            self._tradier_env = env

    def set_balance(self, balance: dict) -> None:
        with self._lock:
            self._last_balance = balance

    # ─── Daily rollover ─────────────────────────────────────────────────────
    def maybe_rollover_day(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            if today != self._date:
                self._date = today
                self._daily_pnl = 0.0
                self._halted = False
                self._halt_reason = None
                for s in self._strategies.values():
                    s.trades_today = 0
                    s.pnl_today    = 0.0

    # ─── The lock ───────────────────────────────────────────────────────────
    def try_open(self, position: OpenPosition) -> bool:
        """Atomically claim `position.symbol`. Returns False if already taken
        or system is halted."""
        with self._lock:
            if self._halted:
                return False
            if position.symbol in self._open:
                return False
            self._open[position.symbol] = position
            return True

    def close(self, symbol: str, exit_price: float, reason: str,
              shares_filled: Optional[int] = None) -> Optional[ClosedTrade]:
        """Close the open position on `symbol`. Updates daily PnL and may halt."""
        with self._lock:
            pos = self._open.pop(symbol, None)
            if pos is None:
                return None
            shares = shares_filled or pos.shares
            sign = 1 if pos.side == "long" else -1
            pnl  = (exit_price - pos.entry) * shares * sign
            ct = ClosedTrade(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol=symbol, strategy=pos.strategy, side=pos.side,
                entry=pos.entry, exit=exit_price, shares=shares,
                pnl=round(pnl, 2), reason=reason)
            self._recent.insert(0, ct)
            self._recent = self._recent[:MAX_RECENT_TRADES]
            self._daily_pnl = round(self._daily_pnl + pnl, 2)
            ss = self._strategies.get(pos.strategy)
            if ss:
                ss.trades_today += 1
                ss.pnl_today = round(ss.pnl_today + pnl, 2)
            if self._daily_pnl <= self._max_daily_loss and not self._halted:
                self._halted = True
                self._halt_reason = (f"MAX_DAILY_LOSS reached: "
                                     f"{self._daily_pnl:.2f} <= {self._max_daily_loss:.2f}")
            return ct

    # ─── Signal tracking ────────────────────────────────────────────────────
    def mark_signal(self, strategy_name: str, bar_ts: str, side: str) -> None:
        with self._lock:
            s = self._strategies.get(strategy_name)
            if s:
                s.last_signal_bar  = bar_ts
                s.last_signal_side = side

    def already_acted(self, strategy_name: str, bar_ts: str) -> bool:
        with self._lock:
            s = self._strategies.get(strategy_name)
            return bool(s and s.last_signal_bar == bar_ts)

    # ─── Halt + enable/disable ──────────────────────────────────────────────
    def halt(self, reason: str) -> None:
        with self._lock:
            self._halted = True
            self._halt_reason = reason

    def clear_halt(self) -> None:
        with self._lock:
            self._halted = False
            self._halt_reason = None

    def is_halted(self) -> bool:
        with self._lock:
            return self._halted

    def set_strategy_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            s = self._strategies.get(name)
            if s:
                s.enabled = enabled

    def is_enabled(self, name: str) -> bool:
        with self._lock:
            s = self._strategies.get(name)
            return bool(s and s.enabled)

    # ─── Snapshots ──────────────────────────────────────────────────────────
    def open_positions(self) -> list[OpenPosition]:
        with self._lock:
            return list(self._open.values())

    def open_symbols(self) -> set[str]:
        with self._lock:
            return set(self._open)

    def to_snapshot(self) -> dict:
        with self._lock:
            return {
                "timestamp":    datetime.now(timezone.utc).isoformat(),
                "tradier_env":  self._tradier_env,
                "balances":     self._last_balance,
                "daily_pnl":    self._daily_pnl,
                "max_daily_loss": self._max_daily_loss,
                "halted":       self._halted,
                "halt_reason":  self._halt_reason,
                "date":         self._date,
                "strategies":   [asdict(s) for s in self._strategies.values()],
                "open_positions": [asdict(p) for p in self._open.values()],
                "recent_trades":  [asdict(t) for t in self._recent],
            }

    # ─── Persistence ────────────────────────────────────────────────────────
    def write_state(self) -> None:
        snap = self.to_snapshot()
        tmp = self._state_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snap, indent=2, default=str))
        os.replace(tmp, self._state_file)        # atomic swap

    def read_commands(self) -> dict:
        if not self._commands_file.exists():
            return {}
        try:
            return json.loads(self._commands_file.read_text())
        except Exception:
            return {}

    def apply_commands(self) -> None:
        """Read commands.json (written by dashboard) and apply them."""
        cmds = self.read_commands()
        if not cmds:
            return
        if cmds.get("kill_switch"):
            self.halt("kill_switch from dashboard")
        if cmds.get("clear_halt"):
            self.clear_halt()
        for name, enabled in (cmds.get("strategy_enabled") or {}).items():
            self.set_strategy_enabled(name, bool(enabled))


def write_command(payload: dict, path: Path = COMMANDS_FILE) -> None:
    """Helper for the dashboard — merges into commands.json."""
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            pass
    existing.update(payload)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(existing, indent=2))
    os.replace(tmp, path)
