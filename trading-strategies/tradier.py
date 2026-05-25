"""Tradier REST API client.

Defaults to the SANDBOX endpoint. To trade real money you must explicitly:
  1. Set TRADIER_ENV=live
  2. Set TRADIER_LIVE_CONFIRM='I have read RISK.md'
  3. Have read RISK.md and worked through the go-live checklist

Auth: set TRADIER_TOKEN env var (sandbox tokens at https://sandbox.tradier.com,
production tokens at https://developer.tradier.com).

Endpoints used:
  GET  /v1/markets/quotes                  - latest quote for symbol(s)
  GET  /v1/markets/history                 - daily bars
  GET  /v1/markets/timesales                - intraday bars
  GET  /v1/accounts/{id}/balances          - cash + buying power
  GET  /v1/accounts/{id}/positions         - open positions
  GET  /v1/accounts/{id}/orders            - working orders
  POST /v1/accounts/{id}/orders            - place order
  DELETE /v1/accounts/{id}/orders/{oid}    - cancel order
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import pandas as pd
import requests

SANDBOX_BASE = "https://sandbox.tradier.com"
LIVE_BASE    = "https://api.tradier.com"

# ETF proxies for the futures-validated strategies. These trade US RTH only
# (09:30-16:00 ET) — none of the futures-overnight signals apply.
FUTURE_TO_ETF: dict[str, str] = {
    "ES": "SPY",   # E-mini S&P 500  -> SPDR S&P 500 ETF
    "NQ": "QQQ",   # E-mini Nasdaq 100 -> Invesco QQQ
    "GC": "GLD",   # Gold              -> SPDR Gold Shares
}


class TradierError(RuntimeError):
    pass


@dataclass
class TradierClient:
    token:      str
    account_id: str
    env:        Literal["sandbox", "live"] = "sandbox"

    @classmethod
    def from_env(cls) -> "TradierClient":
        env = os.environ.get("TRADIER_ENV", "sandbox").lower()
        token   = os.environ.get("TRADIER_TOKEN")
        account = os.environ.get("TRADIER_ACCOUNT_ID")
        if not token or not account:
            raise TradierError(
                "Missing TRADIER_TOKEN or TRADIER_ACCOUNT_ID. Set both env vars.\n"
                "Sandbox tokens: https://sandbox.tradier.com\n"
                "Live tokens:    https://developer.tradier.com"
            )
        if env == "live":
            confirm = os.environ.get("TRADIER_LIVE_CONFIRM")
            if confirm != "I have read RISK.md":
                raise TradierError(
                    "Refusing to use LIVE endpoint without explicit confirmation.\n"
                    "Read RISK.md, then set TRADIER_LIVE_CONFIRM='I have read RISK.md'."
                )
        elif env != "sandbox":
            raise TradierError(f"TRADIER_ENV must be 'sandbox' or 'live', got {env!r}")
        return cls(token=token, account_id=account, env=env)

    @property
    def base_url(self) -> str:
        return LIVE_BASE if self.env == "live" else SANDBOX_BASE

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def _request(self, method: str, path: str, **kw) -> dict:
        url = f"{self.base_url}{path}"
        r = requests.request(method, url, headers=self._headers, timeout=10, **kw)
        if not r.ok:
            raise TradierError(f"{method} {path} -> {r.status_code}: {r.text}")
        return r.json()

    # ─── Market data ────────────────────────────────────────────────────────
    def quote(self, symbol: str) -> dict:
        j = self._request("GET", "/v1/markets/quotes",
                          params={"symbols": symbol, "greeks": "false"})
        return j.get("quotes", {}).get("quote", {})

    def daily_bars(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Daily OHLCV bars. start/end are ISO dates 'YYYY-MM-DD'."""
        j = self._request("GET", "/v1/markets/history",
                          params={"symbol": symbol, "interval": "daily",
                                  "start": start, "end": end})
        days = j.get("history", {}).get("day") or []
        if isinstance(days, dict):
            days = [days]
        if not days:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        df = pd.DataFrame(days)
        df["timestamp"] = pd.to_datetime(df["date"], utc=True)
        df = df.set_index("timestamp").rename(
            columns={"open": "Open", "high": "High", "low": "Low",
                     "close": "Close", "volume": "Volume"})
        return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)

    def intraday_bars(self, symbol: str, interval: str, start: str, end: str) -> pd.DataFrame:
        """Intraday bars. interval: '1min' | '5min' | '15min'.
        start/end are ISO datetimes 'YYYY-MM-DD HH:MM' in US/Eastern."""
        j = self._request("GET", "/v1/markets/timesales",
                          params={"symbol": symbol, "interval": interval,
                                  "start": start, "end": end,
                                  "session_filter": "all"})
        rows = j.get("series", {}).get("data") or []
        if isinstance(rows, dict):
            rows = [rows]
        if not rows:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["time"]).dt.tz_localize(
            "America/New_York").dt.tz_convert("UTC")
        df = df.set_index("timestamp").rename(
            columns={"open": "Open", "high": "High", "low": "Low",
                     "close": "Close", "volume": "Volume"})
        return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)

    # ─── Account ────────────────────────────────────────────────────────────
    def balances(self) -> dict:
        return self._request("GET", f"/v1/accounts/{self.account_id}/balances"
                             ).get("balances", {})

    def positions(self) -> list[dict]:
        j = self._request("GET", f"/v1/accounts/{self.account_id}/positions")
        pos = j.get("positions")
        if not pos or pos == "null":
            return []
        items = pos.get("position", [])
        return items if isinstance(items, list) else [items]

    def working_orders(self) -> list[dict]:
        j = self._request("GET", f"/v1/accounts/{self.account_id}/orders",
                          params={"includeTags": "true"})
        orders = j.get("orders")
        if not orders or orders == "null":
            return []
        items = orders.get("order", [])
        return items if isinstance(items, list) else [items]

    # ─── Orders ─────────────────────────────────────────────────────────────
    def place_market(self, symbol: str, side: str, quantity: int,
                     tag: str | None = None) -> dict:
        """Market order. side: 'buy' | 'sell' | 'sell_short' | 'buy_to_cover'."""
        if quantity < 1:
            raise TradierError(f"quantity must be >= 1, got {quantity}")
        params = {"class": "equity", "symbol": symbol,
                  "side": side, "quantity": str(quantity),
                  "type": "market", "duration": "day"}
        if tag:
            params["tag"] = tag[:255]
        return self._request("POST", f"/v1/accounts/{self.account_id}/orders",
                             data=params).get("order", {})

    def cancel(self, order_id: str | int) -> dict:
        return self._request("DELETE",
                             f"/v1/accounts/{self.account_id}/orders/{order_id}")
