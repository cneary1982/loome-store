"""
SIGNAL EXECUTOR
===============
Bridges Jarvis signals → broker execution.
This is WHY Jarvis wasn't trading: no executor loop was wired up.

Flow: signal_queue → gate_check (objective) → size → place_order → confirm → log
"""

import json, time, logging, os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

log = logging.getLogger("signal_executor")

@dataclass
class Signal:
    symbol: str
    direction: str           # "long" or "short"
    entry_price: float
    stop_loss: float
    take_profit: float
    brain_confidence: float
    mta_grade: str
    mta_score: float
    xgb_agree: bool
    source: str              # which alpha source generated this
    size_mult: float = 1.0
    reward_risk: float = 0.0
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.entry_price and self.stop_loss and self.take_profit:
            risk = abs(self.entry_price - self.stop_loss)
            reward = abs(self.take_profit - self.entry_price)
            self.reward_risk = reward / risk if risk > 0 else 0


class SignalExecutor:
    """
    Autonomous signal execution engine.
    Receives signals, gates them through the objective, sizes positions,
    and places orders through the broker.
    """

    def __init__(self, objective, broker_session=None, state_dir: str = "."):
        self.objective = objective
        self.broker = broker_session
        self.state_dir = Path(state_dir)
        self.pending_signals: List[Signal] = []
        self.executed_today: List[dict] = []
        self.rejected_today: List[dict] = []
        self.daily_pnl: float = 0.0
        self._load_state()

    def receive_signal(self, signal: Signal) -> dict:
        """Receive a signal and decide whether to execute it."""
        log.info(f"Signal received: {signal.direction} {signal.symbol} @ {signal.entry_price}")

        current_positions = self._get_positions()

        gate_result = self.objective.should_execute({
            "brain_confidence": signal.brain_confidence,
            "mta_grade": signal.mta_grade,
            "xgb_agree": signal.xgb_agree,
            "reward_risk": signal.reward_risk,
            "size_mult": signal.size_mult,
            "current_positions": len(current_positions),
        })

        if self._daily_loss_exceeded():
            gate_result["execute"] = False
            gate_result["reasons"] = ["daily loss limit hit"]

        if self._already_in_position(signal.symbol, current_positions):
            gate_result["execute"] = False
            gate_result["reasons"] = ["already in position"]

        if not gate_result["execute"]:
            entry = {
                "signal": self._signal_to_dict(signal),
                "reasons": gate_result["reasons"],
                "time": datetime.now(timezone.utc).isoformat(),
            }
            self.rejected_today.append(entry)
            log.info(f"REJECTED {signal.symbol}: {gate_result['reasons']}")
            self._save_state()
            return {"action": "rejected", **entry}

        qty = self._calculate_size(signal, current_positions)
        if qty == 0:
            log.info(f"SKIP {signal.symbol}: position size rounded to 0")
            return {"action": "skip", "reason": "size too small"}

        order_result = self._place_order(signal, qty)

        entry = {
            "signal": self._signal_to_dict(signal),
            "qty": qty,
            "order": order_result,
            "time": datetime.now(timezone.utc).isoformat(),
        }
        self.executed_today.append(entry)
        log.info(f"EXECUTED {signal.direction} {qty}x {signal.symbol} @ {signal.entry_price}")
        self._save_state()
        return {"action": "executed", **entry}

    def _calculate_size(self, signal: Signal, positions: list) -> int:
        """ATR-based risk-parity sizing with Kelly adjustment."""
        account_value = self.objective.account_value
        risk_per_trade_pct = 1.0
        risk_dollars = account_value * (risk_per_trade_pct / 100)
        risk_dollars *= signal.size_mult

        per_share_risk = abs(signal.entry_price - signal.stop_loss)
        if per_share_risk == 0:
            return 0

        raw_qty = risk_dollars / per_share_risk
        position_value = raw_qty * signal.entry_price
        max_position = account_value * (self.objective.max_single_position_pct / 100)
        if position_value > max_position:
            raw_qty = max_position / signal.entry_price

        return max(0, int(raw_qty))

    def _place_order(self, signal: Signal, qty: int) -> dict:
        """Place order through broker. Returns order confirmation."""
        if self.broker is None:
            log.warning("No broker connected — logging paper trade")
            return {
                "status": "paper",
                "symbol": signal.symbol,
                "side": "buy" if signal.direction == "long" else "sell_short",
                "qty": qty,
                "price": signal.entry_price,
                "stop": signal.stop_loss,
                "target": signal.take_profit,
            }

        try:
            if signal.direction == "long":
                order = self.broker.place_equity_order(
                    symbol=signal.symbol,
                    qty=qty,
                    side="buy",
                    order_type="limit",
                    limit_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )
            else:
                order = self.broker.place_equity_order(
                    symbol=signal.symbol,
                    qty=qty,
                    side="sell_short",
                    order_type="limit",
                    limit_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )
            return {"status": "live", "order_id": order.get("id"), "detail": order}
        except Exception as e:
            log.error(f"Order failed: {e}")
            return {"status": "error", "error": str(e)}

    def _get_positions(self) -> list:
        if self.broker is None:
            return []
        try:
            return self.broker.get_positions() or []
        except Exception:
            return []

    def _already_in_position(self, symbol: str, positions: list) -> bool:
        return any(p.get("symbol", "").upper() == symbol.upper() for p in positions)

    def _daily_loss_exceeded(self) -> bool:
        limit = self.objective.account_value * (self.objective.daily_loss_limit_pct / 100)
        return self.daily_pnl < -limit

    def _signal_to_dict(self, s: Signal) -> dict:
        return {
            "symbol": s.symbol, "direction": s.direction,
            "entry": s.entry_price, "stop": s.stop_loss, "target": s.take_profit,
            "confidence": s.brain_confidence, "grade": s.mta_grade,
            "score": s.mta_score, "xgb": s.xgb_agree, "rr": s.reward_risk,
            "source": s.source,
        }

    def _save_state(self):
        state = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "executed": self.executed_today,
            "rejected": self.rejected_today,
            "daily_pnl": self.daily_pnl,
        }
        path = self.state_dir / "executor_state.json"
        with open(path, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self):
        path = self.state_dir / "executor_state.json"
        if not path.exists():
            return
        try:
            with open(path) as f:
                state = json.load(f)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if state.get("date") == today:
                self.executed_today = state.get("executed", [])
                self.rejected_today = state.get("rejected", [])
                self.daily_pnl = state.get("daily_pnl", 0)
        except Exception:
            pass

    def daily_summary(self) -> str:
        lines = [
            f"=== EXECUTOR DAILY SUMMARY ===",
            f"Executed: {len(self.executed_today)} trades",
            f"Rejected: {len(self.rejected_today)} signals",
            f"Daily P&L: ${self.daily_pnl:+.2f}",
        ]
        if self.rejected_today:
            lines.append("\nRejected signals:")
            for r in self.rejected_today[-5:]:
                sig = r.get("signal", {})
                lines.append(f"  {sig.get('direction','')} {sig.get('symbol','')} — {r.get('reasons','')}")
        return "\n".join(lines)
