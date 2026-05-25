"""Streamlit dashboard for the multi-strategy orchestrator.

Reads state.json (written by orchestrator.py) and writes commands.json
(read by orchestrator.py on every tick). Decoupled from the orchestrator
process so the UI can crash/restart without affecting live trading.

Usage:
    pip install streamlit
    streamlit run dashboard.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from position_manager import COMMANDS_FILE, STATE_FILE, write_command

st.set_page_config(page_title="Trading Strategies", layout="wide",
                   initial_sidebar_state="collapsed")

REFRESH_SECONDS = 5


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def fmt_money(x) -> str:
    try:
        v = float(x)
    except Exception:
        return "—"
    return f"${v:,.2f}"


state = load_state()

# ─── Header ─────────────────────────────────────────────────────────────────
st.title("Trading Strategies")
if not state:
    st.warning("No state.json found. Start the orchestrator: `python orchestrator.py`")
    st.stop()

env       = state.get("tradier_env", "?")
balances  = state.get("balances", {}) or {}
cash      = balances.get("cash", {}).get("cash_available") if isinstance(
                balances.get("cash"), dict) else balances.get("total_cash")
daily_pnl = state.get("daily_pnl", 0.0)
max_dl    = state.get("max_daily_loss", 0.0)
halted    = state.get("halted", False)
halt_rsn  = state.get("halt_reason")
ts        = state.get("timestamp", "")

env_color = "🟢" if env == "sandbox" else "🔴 LIVE"
top1, top2, top3, top4, top5 = st.columns([1.3, 1, 1, 1, 1.2])
top1.metric("Broker mode", f"{env_color} {env}")
top2.metric("Cash available", fmt_money(cash))
top3.metric("Daily PnL", fmt_money(daily_pnl),
            delta=None if not daily_pnl else (f"limit {fmt_money(max_dl)}"))
top4.metric("Halted?", "YES" if halted else "no",
            delta=halt_rsn if halted else None)
top5.metric("Last update", ts.split("T")[1][:8] if "T" in ts else ts)

# ─── Kill switch / clear halt ───────────────────────────────────────────────
k1, k2, _ = st.columns([1, 1, 5])
if k1.button("🛑 Kill switch (halt all)", type="primary", use_container_width=True):
    write_command({"kill_switch": True})
    st.success("Halt command sent.")
if k2.button("Clear halt", use_container_width=True, disabled=not halted):
    write_command({"clear_halt": True, "kill_switch": False})
    st.success("Clear-halt command sent.")

st.divider()

# ─── Strategies ─────────────────────────────────────────────────────────────
st.subheader("Strategies")
strats = state.get("strategies", [])
if not strats:
    st.info("No strategies registered. Add them to strategies.py and restart "
            "the orchestrator.")
else:
    cmds_disk = {}
    if COMMANDS_FILE.exists():
        try:
            cmds_disk = json.loads(COMMANDS_FILE.read_text())
        except Exception:
            cmds_disk = {}
    enabled_overrides = cmds_disk.get("strategy_enabled", {}) or {}

    cols = st.columns([2, 1, 1, 1, 1.3, 1, 1.5])
    cols[0].markdown("**Name**")
    cols[1].markdown("**Symbol**")
    cols[2].markdown("**TF**")
    cols[3].markdown("**Enabled**")
    cols[4].markdown("**Trades today**")
    cols[5].markdown("**PnL today**")
    cols[6].markdown("**Last signal**")

    for s in strats:
        c = st.columns([2, 1, 1, 1, 1.3, 1, 1.5])
        c[0].write(s["name"])
        c[1].write(s["symbol"])
        c[2].write(s["timeframe"])
        toggle_key = f"toggle_{s['name']}"
        new_val = c[3].toggle("", value=bool(s.get("enabled", True)),
                              key=toggle_key, label_visibility="collapsed")
        # Persist only when changed from prior commands-file value (if any)
        prior = enabled_overrides.get(s["name"], s.get("enabled", True))
        if new_val != bool(prior):
            override = {**enabled_overrides, s["name"]: bool(new_val)}
            write_command({"strategy_enabled": override})
        c[4].write(s.get("trades_today", 0))
        c[5].write(fmt_money(s.get("pnl_today", 0.0)))
        bar = s.get("last_signal_bar") or "—"
        side = s.get("last_signal_side") or ""
        c[6].write(f"{bar.split('T')[-1][:8] if 'T' in bar else bar} {side}")

st.divider()

# ─── Open positions ─────────────────────────────────────────────────────────
st.subheader("Open positions (per-symbol lock)")
open_pos = state.get("open_positions", [])
if not open_pos:
    st.write("_no open positions_")
else:
    df_open = pd.DataFrame(open_pos)
    df_open = df_open[["symbol", "strategy", "side", "shares", "entry",
                       "tp", "sl", "atr_at_entry", "opened_at"]]
    st.dataframe(df_open, use_container_width=True, hide_index=True)

st.divider()

# ─── Recent trades ──────────────────────────────────────────────────────────
st.subheader("Recent trades")
trades = state.get("recent_trades", [])
if not trades:
    st.write("_no trades yet_")
else:
    df_t = pd.DataFrame(trades)
    df_t = df_t[["timestamp", "symbol", "strategy", "side",
                 "shares", "entry", "exit", "pnl", "reason"]]
    df_t["pnl"] = df_t["pnl"].astype(float)
    st.dataframe(df_t, use_container_width=True, hide_index=True,
                 column_config={"pnl": st.column_config.NumberColumn(format="$%.2f")})

st.divider()
st.caption(f"Auto-refreshing every {REFRESH_SECONDS}s. "
           f"State file: `{STATE_FILE}`  •  Commands file: `{COMMANDS_FILE}`")

# Auto-refresh
time.sleep(REFRESH_SECONDS)
st.rerun()
