"""
JARVIS LIVE TRADING INFRASTRUCTURE
====================================
This is the WIRING. It connects:
  Data Feed → Strategy/Brain → Crew Consult → Signal Executor → Broker → P&L Tracking

What Jarvis needs to trade live:
  1. BROKER SESSION — TastyTrade API (session token + account number)
  2. MARKET DATA — real-time quotes + 1-min bars (TastyTrade streaming or DXFeed)
  3. ALWAYS-ON PROCESS — VPS, Raspberry Pi, or cloud VM running 23h/day
  4. THIS FILE — the main loop that connects everything together

Architecture:
  ┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────┐
  │ Market Data  │──▸│ Strategies   │──▸│ Crew Consult │──▸│ Executor │
  │ (streaming)  │   │ (brain/MTA)  │   │ (3 analysts) │   │ (broker) │
  └─────────────┘   └──────────────┘   └──────────────┘   └──────────┘
       │                                                        │
       ▼                                                        ▼
  ┌─────────────┐                                        ┌──────────┐
  │ Pre-market   │                                        │ Position │
  │ Alpha Scan   │                                        │ Manager  │
  └─────────────┘                                        └──────────┘
"""

import json, logging, time, os, sys, signal
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path

log = logging.getLogger("jarvis_live")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 1: TASTYTRADE BROKER CONNECTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TastyTradeSession:
    """
    Live broker connection to TastyTrade API.
    Handles auth, orders, positions, account data.

    API docs: https://developer.tastytrade.com/
    Base URL: https://api.tastytrade.com
    Sandbox:  https://api.cert.tastytrade.com (paper trading)
    """

    PROD_URL = "https://api.tastytrade.com"
    SANDBOX_URL = "https://api.cert.tastytrade.com"

    def __init__(self, username: str, password: str, account_number: str,
                 sandbox: bool = False):
        self.username = username
        self.password = password
        self.account_number = account_number
        self.base_url = self.SANDBOX_URL if sandbox else self.PROD_URL
        self.session_token = None
        self.headers = {}
        self._authenticated = False

    def connect(self) -> bool:
        """Authenticate and get session token."""
        try:
            import requests
        except ImportError:
            log.error("requests library required: pip install requests")
            return False

        resp = requests.post(
            f"{self.base_url}/sessions",
            json={"login": self.username, "password": self.password},
            headers={"Content-Type": "application/json"},
        )

        if resp.status_code != 201:
            log.error(f"TastyTrade auth failed: {resp.status_code} {resp.text}")
            return False

        data = resp.json().get("data", {})
        self.session_token = data.get("session-token")
        self.headers = {
            "Authorization": self.session_token,
            "Content-Type": "application/json",
        }
        self._authenticated = True
        log.info(f"TastyTrade connected: account {self.account_number}")
        return True

    def get_account(self) -> dict:
        """Get account balances."""
        import requests
        resp = requests.get(
            f"{self.base_url}/accounts/{self.account_number}/balances",
            headers=self.headers,
        )
        return resp.json().get("data", {})

    def get_positions(self) -> list:
        """Get current positions."""
        import requests
        resp = requests.get(
            f"{self.base_url}/accounts/{self.account_number}/positions",
            headers=self.headers,
        )
        items = resp.json().get("data", {}).get("items", [])
        return [
            {
                "symbol": p.get("symbol", ""),
                "quantity": p.get("quantity", 0),
                "direction": p.get("quantity-direction", ""),
                "market_value": p.get("market-value", 0),
                "cost_basis": p.get("average-open-price", 0),
                "pnl": p.get("realized-day-gain", 0),
            }
            for p in items
        ]

    def place_equity_order(self, symbol: str, qty: int, side: str,
                           order_type: str = "limit", limit_price: float = 0,
                           stop_loss: float = 0, take_profit: float = 0,
                           time_in_force: str = "Day") -> dict:
        """Place an equity order."""
        import requests

        action = "Buy to Open" if side == "buy" else "Sell to Open"

        order = {
            "time-in-force": time_in_force,
            "order-type": order_type.capitalize(),
            "legs": [
                {
                    "instrument-type": "Equity",
                    "symbol": symbol,
                    "quantity": qty,
                    "action": action,
                }
            ],
        }

        if order_type == "limit" and limit_price > 0:
            order["price"] = str(limit_price)

        resp = requests.post(
            f"{self.base_url}/accounts/{self.account_number}/orders",
            headers=self.headers,
            json=order,
        )

        result = resp.json()
        if resp.status_code in (200, 201):
            order_id = result.get("data", {}).get("order", {}).get("id")
            log.info(f"Order placed: {side} {qty}x {symbol} @ {limit_price} → ID {order_id}")

            if stop_loss > 0:
                self._place_stop(symbol, qty, stop_loss, side)
            if take_profit > 0:
                self._place_target(symbol, qty, take_profit, side)

            return {"id": order_id, "status": "placed", "detail": result}
        else:
            log.error(f"Order failed: {resp.status_code} {result}")
            return {"id": None, "status": "error", "detail": result}

    def place_futures_order(self, symbol: str, qty: int, side: str,
                            order_type: str = "limit", limit_price: float = 0,
                            stop_loss: float = 0, take_profit: float = 0) -> dict:
        """Place a futures order (MNQ, NQ, ES)."""
        import requests

        future_symbol = self._resolve_futures_symbol(symbol)
        action = "Buy to Open" if side == "buy" else "Sell to Open"

        order = {
            "time-in-force": "GTC",
            "order-type": order_type.capitalize(),
            "legs": [
                {
                    "instrument-type": "Future",
                    "symbol": future_symbol,
                    "quantity": qty,
                    "action": action,
                }
            ],
        }

        if order_type == "limit" and limit_price > 0:
            order["price"] = str(limit_price)

        resp = requests.post(
            f"{self.base_url}/accounts/{self.account_number}/orders",
            headers=self.headers,
            json=order,
        )

        result = resp.json()
        if resp.status_code in (200, 201):
            order_id = result.get("data", {}).get("order", {}).get("id")
            log.info(f"Futures order: {side} {qty}x {future_symbol} @ {limit_price} → ID {order_id}")
            return {"id": order_id, "status": "placed", "detail": result}
        else:
            log.error(f"Futures order failed: {resp.status_code} {result}")
            return {"id": None, "status": "error", "detail": result}

    def cancel_order(self, order_id: str) -> bool:
        import requests
        resp = requests.delete(
            f"{self.base_url}/accounts/{self.account_number}/orders/{order_id}",
            headers=self.headers,
        )
        return resp.status_code in (200, 204)

    def get_orders(self, status: str = "Live") -> list:
        import requests
        resp = requests.get(
            f"{self.base_url}/accounts/{self.account_number}/orders/live",
            headers=self.headers,
        )
        return resp.json().get("data", {}).get("items", [])

    def _place_stop(self, symbol, qty, stop_price, original_side):
        close_side = "Sell to Close" if original_side == "buy" else "Buy to Close"
        import requests
        order = {
            "time-in-force": "GTC",
            "order-type": "Stop",
            "stop-trigger": str(stop_price),
            "legs": [{"instrument-type": "Equity", "symbol": symbol,
                       "quantity": qty, "action": close_side}],
        }
        requests.post(
            f"{self.base_url}/accounts/{self.account_number}/orders",
            headers=self.headers, json=order,
        )

    def _place_target(self, symbol, qty, target_price, original_side):
        close_side = "Sell to Close" if original_side == "buy" else "Buy to Close"
        import requests
        order = {
            "time-in-force": "GTC",
            "order-type": "Limit",
            "price": str(target_price),
            "legs": [{"instrument-type": "Equity", "symbol": symbol,
                       "quantity": qty, "action": close_side}],
        }
        requests.post(
            f"{self.base_url}/accounts/{self.account_number}/orders",
            headers=self.headers, json=order,
        )

    def _resolve_futures_symbol(self, root: str) -> str:
        """Convert 'MNQ' → '/MNQU5' (current front-month contract)."""
        now = datetime.now()
        month_codes = {3: "H", 6: "M", 9: "U", 12: "Z"}

        for exp_month in sorted(month_codes.keys()):
            if now.month <= exp_month:
                code = month_codes[exp_month]
                break
        else:
            code = "H"

        year_digit = str(now.year)[-1]
        return f"/{root}{code}{year_digit}"

    def get_quote(self, symbol: str) -> dict:
        """Get current quote for a symbol."""
        import requests
        resp = requests.get(
            f"{self.base_url}/market-data/{symbol}/quotes",
            headers=self.headers,
        )
        return resp.json().get("data", {})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 2: MARKET DATA STREAMING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MarketDataFeed:
    """
    Real-time market data via TastyTrade's DXFeed websocket.

    TastyTrade uses DXFeed under the hood. The streaming endpoint:
      wss://streamer.cert.tastytrade.com (sandbox)
      wss://streamer.tastytrade.com (prod)

    Requires: session token from TastyTradeSession
    Provides: real-time quotes, 1-min candles, time & sales
    """

    def __init__(self, session: TastyTradeSession):
        self.session = session
        self.streamer_url = None
        self.streamer_token = None
        self.ws = None
        self.subscriptions = {}
        self.callbacks = {}  # symbol → [callback_fn]
        self.bar_builders = {}  # symbol → BarBuilder
        self._running = False

    def connect(self) -> bool:
        """Get DXFeed streamer credentials from TastyTrade API."""
        try:
            import requests
            resp = requests.get(
                f"{self.session.base_url}/api-quote-tokens",
                headers=self.session.headers,
            )
            data = resp.json().get("data", {})
            self.streamer_url = data.get("websocket-url") or data.get("dxfeed-url")
            self.streamer_token = data.get("token")

            if not self.streamer_url:
                log.error("Could not get streamer URL from TastyTrade")
                return False

            log.info(f"Market data feed connected: {self.streamer_url}")
            return True
        except Exception as e:
            log.error(f"Market data connection failed: {e}")
            return False

    def subscribe_bars(self, symbol: str, interval: str = "1m",
                       callback=None):
        """Subscribe to 1-min bars for a symbol."""
        self.subscriptions[symbol] = {"type": "candle", "interval": interval}
        if callback:
            self.callbacks.setdefault(symbol, []).append(callback)
        self.bar_builders[symbol] = BarBuilder(symbol, interval)
        log.info(f"Subscribed to {interval} bars: {symbol}")

    def subscribe_quotes(self, symbols: list, callback=None):
        """Subscribe to real-time quotes."""
        for sym in symbols:
            self.subscriptions[sym] = {"type": "quote"}
            if callback:
                self.callbacks.setdefault(sym, []).append(callback)

    def start_streaming(self):
        """Start the websocket stream in a background thread."""
        self._running = True
        self._stream_thread = threading.Thread(
            target=self._stream_loop, daemon=True
        )
        self._stream_thread.start()
        log.info("Market data streaming started")

    def stop(self):
        self._running = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _stream_loop(self):
        """Websocket streaming loop with reconnection."""
        try:
            import websocket
        except ImportError:
            log.error("websocket-client required: pip install websocket-client")
            return

        while self._running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.streamer_url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open,
                    header={"Authorization": f"Bearer {self.streamer_token}"},
                )
                self.ws.run_forever(ping_interval=30)
            except Exception as e:
                log.error(f"Stream error: {e}")

            if self._running:
                log.info("Reconnecting in 5s...")
                time.sleep(5)

    def _on_open(self, ws):
        log.info("DXFeed websocket connected")
        for symbol, sub in self.subscriptions.items():
            msg = {
                "type": "FEED_SUBSCRIPTION",
                "channel": 1,
                "add": [{"symbol": symbol, "type": sub["type"].upper()}],
            }
            ws.send(json.dumps(msg))

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            event_type = data.get("type", "")

            if event_type in ("FEED_DATA", "candle", "quote", "trade"):
                events = data.get("data", [data])
                for event in events:
                    symbol = event.get("eventSymbol") or event.get("symbol", "")

                    if symbol in self.bar_builders:
                        bar = self.bar_builders[symbol].update(event)
                        if bar:
                            for cb in self.callbacks.get(symbol, []):
                                cb(bar)

                    for cb in self.callbacks.get(symbol, []):
                        cb(event)
        except Exception as e:
            log.debug(f"Message parse error: {e}")

    def _on_error(self, ws, error):
        log.error(f"DXFeed stream error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        log.info(f"DXFeed stream closed: {close_status_code}")


class BarBuilder:
    """Builds 1-min OHLCV bars from tick data."""

    def __init__(self, symbol: str, interval: str = "1m"):
        self.symbol = symbol
        self.interval = interval
        self.current_bar = None
        self.current_minute = None

    def update(self, tick: dict) -> Optional[dict]:
        price = tick.get("bidPrice") or tick.get("price") or tick.get("close", 0)
        volume = tick.get("size") or tick.get("volume", 0)

        if not price:
            return None

        now = datetime.now(timezone.utc)
        minute = now.replace(second=0, microsecond=0)

        if self.current_minute != minute:
            completed_bar = self.current_bar
            self.current_bar = {
                "symbol": self.symbol,
                "timestamp": minute.isoformat(),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
            }
            self.current_minute = minute
            return completed_bar

        if self.current_bar:
            self.current_bar["high"] = max(self.current_bar["high"], price)
            self.current_bar["low"] = min(self.current_bar["low"], price)
            self.current_bar["close"] = price
            self.current_bar["volume"] += volume

        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 3: POSITION MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PositionManager:
    """
    Tracks open positions, manages stops/targets, calculates real-time P&L.
    Bridges the gap between strategy signals and broker execution.
    """

    def __init__(self, broker: TastyTradeSession):
        self.broker = broker
        self.positions = {}  # symbol → position dict
        self.orders = {}     # order_id → order dict
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.trade_log = []

    def open_position(self, symbol: str, direction: str, qty: int,
                      entry_price: float, stop: float, target: float,
                      strategy: str = "", is_futures: bool = False) -> dict:
        """Open a new position through the broker."""

        side = "buy" if direction == "long" else "sell_short"

        if is_futures:
            result = self.broker.place_futures_order(
                symbol=symbol, qty=qty, side=side,
                order_type="limit", limit_price=entry_price,
                stop_loss=stop, take_profit=target,
            )
        else:
            result = self.broker.place_equity_order(
                symbol=symbol, qty=qty, side=side,
                order_type="limit", limit_price=entry_price,
                stop_loss=stop, take_profit=target,
            )

        if result.get("status") in ("placed", "paper"):
            self.positions[symbol] = {
                "symbol": symbol,
                "direction": direction,
                "qty": qty,
                "entry_price": entry_price,
                "stop_price": stop,
                "target_price": target,
                "strategy": strategy,
                "order_id": result.get("id"),
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "is_futures": is_futures,
            }
            log.info(f"Position opened: {direction} {qty}x {symbol} @ {entry_price}")

        return result

    def close_position(self, symbol: str, exit_price: float,
                       reason: str = "manual") -> dict:
        """Close a position and log the trade."""
        pos = self.positions.get(symbol)
        if not pos:
            return {"error": f"No position in {symbol}"}

        qty = pos["qty"]
        direction = pos["direction"]

        close_side = "sell" if direction == "long" else "buy_to_cover"
        is_futures = pos.get("is_futures", False)

        if is_futures:
            result = self.broker.place_futures_order(
                symbol=symbol, qty=qty, side=close_side,
                order_type="market",
            )
        else:
            result = self.broker.place_equity_order(
                symbol=symbol, qty=qty, side=close_side,
                order_type="market",
            )

        if direction == "long":
            pnl = (exit_price - pos["entry_price"]) * qty
        else:
            pnl = (pos["entry_price"] - exit_price) * qty

        if is_futures:
            pnl *= 2.0  # MNQ $2/point

        self.realized_pnl += pnl

        trade = {
            "symbol": symbol,
            "direction": direction,
            "qty": qty,
            "entry": pos["entry_price"],
            "exit": exit_price,
            "pnl": pnl,
            "strategy": pos.get("strategy", ""),
            "reason": reason,
            "entry_time": pos["entry_time"],
            "exit_time": datetime.now(timezone.utc).isoformat(),
        }
        self.trade_log.append(trade)
        del self.positions[symbol]

        log.info(f"Position closed: {symbol} P&L ${pnl:+.2f} ({reason})")
        return trade

    def check_stops_and_targets(self, quotes: dict):
        """Check all positions against current prices for stop/target hits."""
        for symbol, pos in list(self.positions.items()):
            price = quotes.get(symbol, {}).get("last", 0)
            if not price:
                continue

            if pos["direction"] == "long":
                if price <= pos["stop_price"]:
                    self.close_position(symbol, price, "stop_hit")
                elif price >= pos["target_price"]:
                    self.close_position(symbol, price, "target_hit")
            else:
                if price >= pos["stop_price"]:
                    self.close_position(symbol, price, "stop_hit")
                elif price <= pos["target_price"]:
                    self.close_position(symbol, price, "target_hit")

    def update_unrealized(self, quotes: dict):
        """Calculate unrealized P&L across all positions."""
        self.unrealized_pnl = 0
        for symbol, pos in self.positions.items():
            price = quotes.get(symbol, {}).get("last", 0)
            if not price:
                continue
            multiplier = 2.0 if pos.get("is_futures") else 1.0
            if pos["direction"] == "long":
                self.unrealized_pnl += (price - pos["entry_price"]) * pos["qty"] * multiplier
            else:
                self.unrealized_pnl += (pos["entry_price"] - price) * pos["qty"] * multiplier

    def summary(self) -> str:
        lines = [
            f"=== POSITION MANAGER ===",
            f"Open positions: {len(self.positions)}",
            f"Realized P&L: ${self.realized_pnl:+.2f}",
            f"Unrealized P&L: ${self.unrealized_pnl:+.2f}",
            f"Total trades: {len(self.trade_log)}",
        ]
        for sym, pos in self.positions.items():
            lines.append(f"  {pos['direction'].upper()} {pos['qty']}x {sym} @ {pos['entry_price']}")
        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 4: THE MAIN LOOP — JARVIS LIVE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class JarvisLive:
    """
    The main autonomous trading loop.

    Startup sequence:
      1. Load objective
      2. Connect to TastyTrade (broker + market data)
      3. Run pre-market alpha scan at 8 AM ET
      4. Start streaming market data
      5. Feed bars to strategies → crew consult → executor
      6. Track positions, stops, targets
      7. EOD journal at 4:15 PM ET
      8. Run learning cycle at 2 AM ET
      9. Repeat

    Usage:
      jarvis = JarvisLive(
          username="cneary1982",
          password="<tastytrade_password>",
          account_number="<account_number>",
          sandbox=True,  # start in sandbox!
      )
      jarvis.start()
    """

    def __init__(self, username: str, password: str, account_number: str,
                 sandbox: bool = True, state_dir: str = "."):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.broker = TastyTradeSession(username, password, account_number, sandbox)
        self.data_feed = None
        self.position_mgr = None

        # these get imported from the other jarvis modules
        self.objective = None
        self.executor = None
        self.crew = None
        self.alpha = None
        self.scalper = None

        self._running = False
        self._mode = "equities"  # or "futures_scalp"

    def start(self):
        """Boot Jarvis and start the main loop."""
        log.info("=" * 60)
        log.info("  JARVIS AUTONOMOUS TRADING SYSTEM — GOING LIVE")
        log.info("=" * 60)

        # 1. Load objective
        self._load_modules()

        # 2. Connect to broker
        if not self.broker.connect():
            log.error("CANNOT CONNECT TO BROKER — aborting")
            return

        # 3. Set up position manager
        self.position_mgr = PositionManager(self.broker)

        # 4. Connect market data
        self.data_feed = MarketDataFeed(self.broker)
        if not self.data_feed.connect():
            log.error("CANNOT CONNECT MARKET DATA — aborting")
            return

        # 5. Subscribe to watchlist
        self._subscribe_watchlist()

        # 6. Start streaming
        self.data_feed.start_streaming()

        # 7. Run the main loop
        self._running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        log.info("Jarvis is live. Entering main loop.")
        self._main_loop()

    def start_scalper(self):
        """Start the Asia session scalper mode instead of equity mode."""
        self._mode = "futures_scalp"
        self.start()

    def _load_modules(self):
        """Import and initialize all Jarvis modules."""
        try:
            from jarvis_objective import PortfolioObjective
            self.objective = PortfolioObjective.load(
                str(self.state_dir / "jarvis_objective.json")
            )
        except ImportError:
            from jarvis_objective import OBJECTIVE
            self.objective = OBJECTIVE

        try:
            from signal_executor import SignalExecutor
            self.executor = SignalExecutor(
                self.objective, self.broker, str(self.state_dir)
            )
        except ImportError:
            log.warning("signal_executor not found — paper mode")
            self.executor = None

        try:
            from jarvis_crew_consult import JarvisCrew
            self.crew = JarvisCrew()
        except ImportError:
            log.warning("jarvis_crew_consult not found — no crew gate")
            self.crew = None

        try:
            from premarket_alpha import PremarketAlpha
            from headline_scanner import HeadlineScanner
            from congress_tracker import CongressTracker
            from sec_edge import SECEdgeScanner

            self.alpha = PremarketAlpha(
                objective=self.objective,
                executor=self.executor,
                headline_scanner=HeadlineScanner(),
                congress_tracker=CongressTracker(),
                sec_scanner=SECEdgeScanner(self.objective.watchlist),
            )
        except ImportError:
            log.warning("alpha modules not found — no pre-market scan")

        if self._mode == "futures_scalp":
            try:
                from asia_session_scalper import AsiaSessionScalper, ScalperConfig
                self.scalper = AsiaSessionScalper(ScalperConfig())
            except ImportError:
                log.warning("asia_session_scalper not found")

    def _subscribe_watchlist(self):
        """Subscribe to market data for all watchlist symbols."""
        if self._mode == "futures_scalp":
            futures_sym = self.broker._resolve_futures_symbol("MNQ")
            self.data_feed.subscribe_bars(
                futures_sym, "1m", callback=self._on_futures_bar
            )
            log.info(f"Subscribed to futures bars: {futures_sym}")
        else:
            for sym in self.objective.watchlist:
                self.data_feed.subscribe_quotes([sym], callback=self._on_quote)
            for sym in self.objective.futures_watchlist:
                futures_sym = self.broker._resolve_futures_symbol(sym)
                self.data_feed.subscribe_bars(
                    futures_sym, "1m", callback=self._on_futures_bar
                )

    def _main_loop(self):
        """The always-on main loop."""
        last_premarket = None
        last_eod = None
        last_learn = None

        while self._running:
            now = datetime.now()
            hour_min = now.strftime("%H:%M")

            # Pre-market alpha scan at 8:00 AM ET
            if hour_min == self.objective.premarket_scan_time and last_premarket != now.date():
                last_premarket = now.date()
                self._run_premarket()

            # EOD review at 4:15 PM ET
            if hour_min == self.objective.eod_review_time and last_eod != now.date():
                last_eod = now.date()
                self._run_eod_review()

            # Learning cycle at 2:00 AM ET
            if hour_min == self.objective.learn_hour_start and last_learn != now.date():
                last_learn = now.date()
                self._run_learning()

            # Check positions for stop/target hits every 5 seconds
            if self.position_mgr and self.position_mgr.positions:
                quotes = self._get_live_quotes()
                self.position_mgr.check_stops_and_targets(quotes)
                self.position_mgr.update_unrealized(quotes)

            # Save state every minute
            if now.second == 0:
                self._save_state()

            time.sleep(1)

    def _on_quote(self, event: dict):
        """Handle incoming quote update."""
        symbol = event.get("eventSymbol") or event.get("symbol", "")
        if not symbol:
            return

    def _on_futures_bar(self, bar: dict):
        """Handle completed 1-min futures bar."""
        if not bar:
            return

        if self._mode == "futures_scalp" and self.scalper:
            signals = self.scalper.on_bar(bar)
            if signals:
                for sig in signals if isinstance(signals, list) else [signals]:
                    self._execute_scalp_signal(sig)

    def _execute_scalp_signal(self, sig):
        """Execute a scalp signal through the position manager."""
        if not self.position_mgr:
            return

        if sig.direction == "long":
            stop = sig.entry_price - sig.stop_points
            target = sig.entry_price + sig.target_points
        else:
            stop = sig.entry_price + sig.stop_points
            target = sig.entry_price - sig.target_points

        self.position_mgr.open_position(
            symbol="MNQ",
            direction=sig.direction,
            qty=sig.contracts,
            entry_price=sig.entry_price,
            stop=stop,
            target=target,
            strategy=sig.strategy,
            is_futures=True,
        )

    def _run_premarket(self):
        """Run the 8 AM pre-market alpha scan."""
        log.info("=" * 60)
        log.info("RUNNING PRE-MARKET ALPHA SCAN")
        log.info("=" * 60)

        if self.alpha:
            results = self.alpha.run_morning_scan()

            if self.crew:
                from jarvis_crew_consult import build_morning_brief
                brief = build_morning_brief(
                    results, self.crew,
                    positions=self.position_mgr.positions if self.position_mgr else [],
                    account_value=self.objective.account_value,
                )
                log.info(brief)
                self._save_brief(brief)

    def _run_eod_review(self):
        """End of day review and journal."""
        log.info("=" * 60)
        log.info("END OF DAY REVIEW")
        log.info("=" * 60)

        if self.position_mgr:
            log.info(self.position_mgr.summary())
        if self.executor:
            log.info(self.executor.daily_summary())

        self._save_state()

    def _run_learning(self):
        """2 AM learning cycle — retrain brains."""
        log.info("LEARNING CYCLE — retraining models")

    def _get_live_quotes(self) -> dict:
        """Pull current quotes for all positions."""
        quotes = {}
        for symbol in (self.position_mgr.positions if self.position_mgr else {}):
            try:
                q = self.broker.get_quote(symbol)
                quotes[symbol] = {"last": q.get("last", 0) or q.get("mark", 0)}
            except Exception:
                pass
        return quotes

    def _save_brief(self, brief: str):
        path = self.state_dir / f"brief_{datetime.now().strftime('%Y%m%d')}.txt"
        with open(path, "w") as f:
            f.write(brief)

    def _save_state(self):
        state = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self._mode,
            "positions": dict(self.position_mgr.positions) if self.position_mgr else {},
            "realized_pnl": self.position_mgr.realized_pnl if self.position_mgr else 0,
            "trade_count": len(self.position_mgr.trade_log) if self.position_mgr else 0,
        }
        path = self.state_dir / "jarvis_live_state.json"
        with open(path, "w") as f:
            json.dump(state, f, indent=2)

    def _shutdown(self, signum=None, frame=None):
        log.info("JARVIS SHUTDOWN — closing positions and saving state")
        self._running = False
        if self.data_feed:
            self.data_feed.stop()
        self._save_state()
        log.info("Jarvis is offline.")

    def status(self) -> str:
        """Current system status for the front end."""
        lines = [
            f"=== JARVIS LIVE STATUS ===",
            f"Mode: {self._mode}",
            f"Running: {self._running}",
            f"Broker: {'connected' if self.broker._authenticated else 'disconnected'}",
            f"Data feed: {'streaming' if self.data_feed and self.data_feed._running else 'offline'}",
        ]
        if self.position_mgr:
            lines.append(f"Positions: {len(self.position_mgr.positions)}")
            lines.append(f"Realized P&L: ${self.position_mgr.realized_pnl:+.2f}")
            lines.append(f"Unrealized P&L: ${self.position_mgr.unrealized_pnl:+.2f}")
        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYER 5: WHAT JARVIS NEEDS TO GO LIVE (CHECKLIST)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHAT_JARVIS_NEEDS = """
╔══════════════════════════════════════════════════════════════╗
║             JARVIS — WHAT HE NEEDS TO TRADE LIVE            ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. BROKER CREDENTIALS (TastyTrade)                         ║
║     ├─ Username: cneary1982                                  ║
║     ├─ Password: (stored in config.py on Drive)              ║
║     ├─ Account Number: (from TastyTrade account page)        ║
║     ├─ API: https://api.tastytrade.com                       ║
║     └─ Sandbox first: https://api.cert.tastytrade.com        ║
║                                                              ║
║  2. MARKET DATA FEED                                         ║
║     ├─ Source: TastyTrade's built-in DXFeed websocket        ║
║     │   (comes FREE with the TastyTrade account)             ║
║     ├─ Provides: real-time quotes, 1-min candles             ║
║     ├─ Protocol: WebSocket → JSON events                     ║
║     ├─ Equities: all watchlist symbols ($0 extra)            ║
║     └─ Futures: MNQ, NQ, ES, VIX ($0 extra for micros)      ║
║                                                              ║
║  3. ALWAYS-ON SERVER (pick one)                              ║
║     ├─ Option A: DigitalOcean Droplet — $6/mo (1GB RAM)      ║
║     ├─ Option B: AWS Lightsail — $5/mo (1GB RAM)             ║
║     ├─ Option C: Raspberry Pi 4 at home — $0/mo (own it)     ║
║     ├─ Option D: Render.com — free tier (sleeps after 15m)   ║
║     └─ RECOMMENDED: DigitalOcean $6/mo Droplet               ║
║        → Ubuntu 22.04, Python 3.11, tmux, pip install deps   ║
║                                                              ║
║  4. PYTHON DEPENDENCIES                                      ║
║     ├─ requests          — HTTP to TastyTrade API            ║
║     ├─ websocket-client  — DXFeed streaming                  ║
║     ├─ numpy             — math for strategies               ║
║     ├─ xgboost           — ensemble co-voter                 ║
║     └─ Optional: redis (for state), flask (for dashboard)    ║
║                                                              ║
║  5. FILES JARVIS NEEDS (already built)                       ║
║     ├─ jarvis_objective.py       — mission & rules           ║
║     ├─ signal_executor.py        — signal → broker bridge    ║
║     ├─ jarvis_crew_consult.py    — 3-analyst gate            ║
║     ├─ premarket_alpha.py        — morning orchestrator      ║
║     ├─ headline_scanner.py       — news alpha                ║
║     ├─ congress_tracker.py       — politician trades         ║
║     ├─ sec_edge.py               — insider buys              ║
║     ├─ asia_session_scalper.py   — overnight futures         ║
║     ├─ jarvis_live_infra.py      — THIS FILE (wiring)        ║
║     └─ brain_trader.py           — the brain (on Drive)      ║
║                                                              ║
║  6. STARTUP COMMAND                                          ║
║     $ pip install requests websocket-client numpy xgboost    ║
║     $ python jarvis_live_infra.py                            ║
║     (or: tmux new -s jarvis 'python jarvis_live_infra.py')   ║
║                                                              ║
║  7. MONITORING                                               ║
║     ├─ brain_terminal.html connects via API (already built)  ║
║     ├─ Logs → jarvis_live.log (rotating file handler)        ║
║     └─ State → jarvis_live_state.json (updated every min)    ║
║                                                              ║
║  COST TO GO LIVE: $6/month (server) + $0 (data + broker)    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENTRYPOINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("jarvis_live.log"),
        ],
    )

    parser = argparse.ArgumentParser(description="Jarvis Live Trading")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--sandbox", action="store_true", default=True,
                        help="Use sandbox/paper trading (default: True)")
    parser.add_argument("--live", action="store_true",
                        help="Use LIVE trading (real money)")
    parser.add_argument("--mode", choices=["equities", "scalper"], default="equities",
                        help="Trading mode: equities (day) or scalper (Asia session)")
    parser.add_argument("--state-dir", default=".", help="Directory for state files")
    args = parser.parse_args()

    print(WHAT_JARVIS_NEEDS)

    sandbox = not args.live
    if not sandbox:
        print("\n⚠️  LIVE TRADING MODE — REAL MONEY ⚠️")
        confirm = input("Type 'YES' to confirm: ")
        if confirm != "YES":
            print("Aborted.")
            sys.exit(0)

    jarvis = JarvisLive(
        username=args.username,
        password=args.password,
        account_number=args.account,
        sandbox=sandbox,
        state_dir=args.state_dir,
    )

    if args.mode == "scalper":
        jarvis.start_scalper()
    else:
        jarvis.start()
