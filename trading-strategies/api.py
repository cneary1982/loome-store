"""FastAPI backend for the Loomi.AI Alpine frontend.

Serves JSON over HTTP, reading from state.json (written by orchestrator),
results/*.csv (sweep/backtest outputs), and exposing the strategy registry.
Writes commands.json (read by orchestrator) for kill switch + toggles.

Endpoints:
  GET  /api/state              orchestrator state (positions, P&L, halts)
  GET  /api/strategies         registry of 20 strategies with backtest stats
  POST /api/strategy/toggle    enable/disable a strategy by name
  GET  /api/signals            most recent signals (closeness to firing)
  GET  /api/backtests          summary table of all backtest results
  GET  /api/portfolio          positions + recent trades aggregated
  GET  /api/analytics          equity curve + per-strategy stats
  POST /api/killswitch         flip the global halt
  POST /api/clear_halt
  GET  /api/settings           current entry window + EOD + risk
  POST /api/settings           update settings.json

Static file routes serve the web/ directory at /.

Usage:
    pip install fastapi uvicorn
    uvicorn api:app --reload --port 8000
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from position_manager import COMMANDS_FILE, STATE_FILE, write_command
from trading_window import ENTRY_START_NY, ENTRY_END_NY, EOD_FLAT_NY

ROOT = Path(__file__).parent
WEB = ROOT / "web"
RESULTS = ROOT / "results"
SETTINGS_FILE = ROOT / "settings.json"

app = FastAPI(title="Loomi.AI API", version="0.1")


# ─── helpers ────────────────────────────────────────────────────────────────
def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {
        "entry_window_start_ny": ENTRY_START_NY,
        "entry_window_end_ny": ENTRY_END_NY,
        "eod_flat_ny": EOD_FLAT_NY,
        "risk_per_trade_dollars": 250.0,
        "max_daily_loss_dollars": 1500.0,
        "broker_env": "sandbox",
    }


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    return df.to_dict(orient="records")


# ─── /api/state ─────────────────────────────────────────────────────────────
@app.get("/api/state")
def api_state() -> dict:
    state = _load_state()
    # Augment with quick-glance metrics for the dashboard
    open_positions = state.get("open_positions", []) or []
    recent = state.get("recent_trades", []) or []
    today_r = sum(float(t.get("pnl", 0)) for t in recent)
    return {
        "broker_env": state.get("tradier_env", "sandbox"),
        "cash_available": state.get("balances", {}).get("total_cash"),
        "daily_pnl": state.get("daily_pnl", 0.0),
        "max_daily_loss": state.get("max_daily_loss", 0.0),
        "halted": state.get("halted", False),
        "halt_reason": state.get("halt_reason"),
        "timestamp": state.get("timestamp", ""),
        "open_positions": open_positions,
        "recent_trades": recent[-25:],
        "strategies_total": len(state.get("strategies", []) or []),
        "trades_today": len(recent),
        "today_r": today_r,
    }


# ─── /api/strategies ────────────────────────────────────────────────────────
@app.get("/api/strategies")
def api_strategies() -> dict:
    """Strategy registry + backtest stats joined."""
    # Backtest stats by class name
    summary = {}
    p = RESULTS / "strategies_lib_summary.csv"
    if p.exists():
        for row in _read_csv(p):
            key = f"{row['strategy']}|{row['symbol']}|{row['timeframe']}"
            summary[key] = row
    # Registry (try import; if it fails for any reason, return empty)
    try:
        from strategies import STRATEGIES  # noqa
        state = _load_state()
        live = {s.get("name"): s for s in (state.get("strategies", []) or [])}
        rows = []
        for s in STRATEGIES:
            cls = s.__class__.__name__
            key = f"{cls}|{s.symbol}|{s.timeframe}"
            bt = summary.get(key, {})
            live_s = live.get(s.name, {})
            rows.append({
                "name": s.name,
                "class": cls,
                "symbol": s.symbol,
                "timeframe": s.timeframe,
                "enabled": live_s.get("enabled", True),
                "trades_today": live_s.get("trades_today", 0),
                "pnl_today": live_s.get("pnl_today", 0.0),
                "last_signal_bar": live_s.get("last_signal_bar"),
                "last_signal_side": live_s.get("last_signal_side"),
                "bt_trades": bt.get("trades"),
                "bt_win_rate": bt.get("win_rate"),
                "bt_expectancy": bt.get("expectancy"),
                "bt_total_R": bt.get("total_R"),
            })
        return {"strategies": rows}
    except Exception as e:
        return {"strategies": [], "error": str(e)}


class ToggleBody(BaseModel):
    name: str
    enabled: bool


@app.post("/api/strategy/toggle")
def api_strategy_toggle(body: ToggleBody) -> dict:
    cmds = {}
    if COMMANDS_FILE.exists():
        try:
            cmds = json.loads(COMMANDS_FILE.read_text())
        except Exception:
            pass
    overrides = cmds.get("strategy_enabled", {}) or {}
    overrides[body.name] = body.enabled
    write_command({"strategy_enabled": overrides})
    return {"ok": True}


# ─── /api/signals ───────────────────────────────────────────────────────────
@app.get("/api/signals")
def api_signals() -> dict:
    """Live signal scan — strategies sorted by recency of last signal."""
    state = _load_state()
    rows = []
    for s in state.get("strategies", []) or []:
        bar = s.get("last_signal_bar")
        if not bar:
            continue
        rows.append({
            "name": s.get("name"),
            "symbol": s.get("symbol"),
            "timeframe": s.get("timeframe"),
            "side": s.get("last_signal_side"),
            "bar": bar,
            "trades_today": s.get("trades_today", 0),
        })
    rows.sort(key=lambda r: r["bar"], reverse=True)
    return {"signals": rows[:50]}


# ─── /api/backtests ─────────────────────────────────────────────────────────
@app.get("/api/backtests")
def api_backtests() -> dict:
    return {
        "summary":    _read_csv(RESULTS / "strategies_lib_summary.csv"),
        "sweep_etf":  _read_csv(RESULTS / "best_per_cell_etf_by_total_R.csv"),
        "sweep_all":  _read_csv(RESULTS / "best_per_cell_by_total_R.csv"),
    }


# ─── /api/portfolio ─────────────────────────────────────────────────────────
@app.get("/api/portfolio")
def api_portfolio() -> dict:
    state = _load_state()
    positions = state.get("open_positions", []) or []
    trades = state.get("recent_trades", []) or []
    # Aggregate by symbol
    by_symbol: dict[str, dict] = {}
    for p in positions:
        sym = p["symbol"]
        by_symbol.setdefault(sym, {"symbol": sym, "shares": 0, "exposure": 0.0})
        by_symbol[sym]["shares"] += p.get("shares", 0)
        by_symbol[sym]["exposure"] += float(p.get("shares", 0)) * float(p.get("entry", 0))
    return {
        "positions": positions,
        "by_symbol": list(by_symbol.values()),
        "recent_trades": trades[-100:],
        "cash_available": state.get("balances", {}).get("total_cash"),
        "daily_pnl": state.get("daily_pnl", 0.0),
    }


# ─── /api/analytics ─────────────────────────────────────────────────────────
@app.get("/api/analytics")
def api_analytics() -> dict:
    """Equity curve approximated from recent_trades; per-strategy summary."""
    state = _load_state()
    trades = state.get("recent_trades", []) or []
    curve = []
    cum = 0.0
    for t in trades:
        cum += float(t.get("pnl", 0))
        curve.append({"t": t.get("timestamp"), "equity": cum})
    by_strat: dict[str, dict] = {}
    for t in trades:
        s = t.get("strategy", "unknown")
        d = by_strat.setdefault(s, {"strategy": s, "trades": 0, "wins": 0, "pnl": 0.0})
        d["trades"] += 1
        d["wins"]   += 1 if float(t.get("pnl", 0)) > 0 else 0
        d["pnl"]    += float(t.get("pnl", 0))
    for d in by_strat.values():
        d["win_rate"] = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] else 0
    return {"equity_curve": curve, "by_strategy": list(by_strat.values())}


# ─── kill switch + halt ─────────────────────────────────────────────────────
@app.post("/api/killswitch")
def api_killswitch() -> dict:
    write_command({"kill_switch": True})
    return {"ok": True}


@app.post("/api/clear_halt")
def api_clear_halt() -> dict:
    write_command({"clear_halt": True, "kill_switch": False})
    return {"ok": True}


# ─── /api/settings ──────────────────────────────────────────────────────────
@app.get("/api/settings")
def api_settings_get() -> dict:
    return _load_settings()


class SettingsBody(BaseModel):
    entry_window_start_ny: Optional[float] = None
    entry_window_end_ny:   Optional[float] = None
    eod_flat_ny:           Optional[float] = None
    risk_per_trade_dollars:Optional[float] = None
    max_daily_loss_dollars:Optional[float] = None
    broker_env:            Optional[str]   = None


@app.post("/api/settings")
def api_settings_post(body: SettingsBody) -> dict:
    settings = _load_settings()
    for k, v in body.dict(exclude_none=True).items():
        settings[k] = v
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    return {"ok": True, "settings": settings}


# ─── Static frontend ────────────────────────────────────────────────────────
@app.get("/")
def root() -> FileResponse:
    return FileResponse(WEB / "dashboard.html")


if WEB.exists():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
