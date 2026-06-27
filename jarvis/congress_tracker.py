"""
CONGRESS TRACKER
================
Scans congressional stock trading disclosures (STOCK Act filings).
Politicians trade on information the public doesn't have yet.
This is free, public data — and it's one of the strongest alpha signals available.

Data sources:
  - House clerk EFDS: https://efdsearch.senate.gov/search/
  - Capitol Trades API (free tier): capitoltrades.com
  - QuiverQuant API (free tier): quiverquant.com
  - Senate periodic transaction reports (XML/PDF)

Key insight: Congressional trades filed within 45 days of transaction.
Delay means we're 1-45 days behind — but the DIRECTION is still alpha
because these trades tend to be informed by committee knowledge.
"""

import json, logging, re
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError

log = logging.getLogger("congress_tracker")

NOTABLE_TRADERS = {
    "Nancy Pelosi": "high",
    "Dan Crenshaw": "medium",
    "Tommy Tuberville": "high",
    "Marjorie Taylor Greene": "medium",
    "Michael McCaul": "high",
    "Josh Gottheimer": "medium",
    "Mark Green": "medium",
    "Ro Khanna": "medium",
}

COMMITTEE_EDGE = {
    "Armed Services": ["LMT", "RTX", "NOC", "GD", "BA", "HII", "LHX"],
    "Intelligence": ["PLTR", "GOOG", "MSFT", "AMZN", "PANW", "CRWD"],
    "Finance": ["JPM", "GS", "BAC", "WFC", "MS", "V", "MA"],
    "Commerce": ["AMZN", "GOOGL", "META", "NFLX", "DIS", "CMCSA"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "NEE", "ENPH"],
    "Health": ["UNH", "JNJ", "PFE", "MRNA", "LLY", "ABBV"],
    "Technology": ["NVDA", "AAPL", "MSFT", "GOOGL", "AMD", "AVGO", "CRM"],
}


@dataclass
class CongressTrade:
    politician: str
    party: str           # "R" or "D"
    chamber: str         # "House" or "Senate"
    symbol: str
    transaction: str     # "Purchase", "Sale", "Sale (Full)", "Sale (Partial)"
    amount_range: str    # "$1,001 - $15,000", "$15,001 - $50,000", etc.
    amount_min: float
    amount_max: float
    transaction_date: str
    disclosure_date: str
    committees: List[str]
    is_notable: bool
    edge_score: float    # 0-100, how likely this is informed trading


@dataclass
class CongressSignal:
    symbol: str
    direction: str       # "bullish" (buys outweigh sells) or "bearish"
    trade_count: int
    notable_count: int
    total_min_value: float
    total_max_value: float
    top_traders: List[str]
    committee_overlap: bool
    edge_score: float
    latest_trade_date: str


class CongressTracker:
    """
    Tracks congressional trading activity for alpha signals.
    """

    def __init__(self, cache_dir: str = ".", api_key: Optional[str] = None):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.trades: List[CongressTrade] = []

    def scan_recent(self, days: int = 30) -> List[CongressSignal]:
        """Scan recent congressional trades and rank by edge potential."""
        self.trades = self._fetch_trades(days)
        if not self.trades:
            log.warning("No congressional trades fetched")
            return []

        symbol_trades: Dict[str, List[CongressTrade]] = {}
        for t in self.trades:
            symbol_trades.setdefault(t.symbol, []).append(t)

        signals = []
        for symbol, trades in symbol_trades.items():
            buys = [t for t in trades if "Purchase" in t.transaction]
            sells = [t for t in trades if "Sale" in t.transaction]

            if len(buys) > len(sells):
                direction = "bullish"
                key_trades = buys
            elif len(sells) > len(buys):
                direction = "bearish"
                key_trades = sells
            else:
                direction = "bullish" if sum(t.amount_min for t in buys) > sum(t.amount_min for t in sells) else "bearish"
                key_trades = buys if direction == "bullish" else sells

            notable = [t for t in key_trades if t.is_notable]
            committee_match = any(
                symbol in stocks
                for t in key_trades
                for comm in t.committees
                for comm_name, stocks in COMMITTEE_EDGE.items()
                if comm_name.lower() in comm.lower()
            )

            edge = (
                len(key_trades) * 10 +
                len(notable) * 25 +
                (30 if committee_match else 0) +
                min(20, sum(t.amount_min for t in key_trades) / 50000 * 10)
            )

            traders = list(set(t.politician for t in key_trades))
            latest = max(t.transaction_date for t in key_trades) if key_trades else ""

            signals.append(CongressSignal(
                symbol=symbol,
                direction=direction,
                trade_count=len(key_trades),
                notable_count=len(notable),
                total_min_value=sum(t.amount_min for t in key_trades),
                total_max_value=sum(t.amount_max for t in key_trades),
                top_traders=traders[:5],
                committee_overlap=committee_match,
                edge_score=min(100, edge),
                latest_trade_date=latest,
            ))

        signals.sort(key=lambda s: s.edge_score, reverse=True)
        return signals[:20]

    def _fetch_trades(self, days: int) -> List[CongressTrade]:
        """Fetch from Capitol Trades (free JSON endpoint) or cache."""
        try:
            url = "https://bff.capitoltrades.com/trades?pageSize=96&page=1"
            req = Request(url, headers={
                "User-Agent": "JarvisBot/1.0",
                "Accept": "application/json",
            })
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            trades = []
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            for item in data.get("data", []):
                tx_date = item.get("txDate", "")
                if not tx_date:
                    continue

                politician = f"{item.get('firstName','')} {item.get('lastName','')}".strip()
                symbol = (item.get("asset", {}).get("assetTicker") or "").upper()
                if not symbol or len(symbol) > 6:
                    continue

                tx_type = item.get("txType", "")
                amount = item.get("value", 0)

                amount_ranges = {
                    (0, 15000): "$1,001 - $15,000",
                    (15001, 50000): "$15,001 - $50,000",
                    (50001, 100000): "$50,001 - $100,000",
                    (100001, 250000): "$100,001 - $250,000",
                    (250001, 500000): "$250,001 - $500,000",
                    (500001, 1000000): "$500,001 - $1,000,000",
                    (1000001, 5000000): "$1,000,001 - $5,000,000",
                    (5000001, 50000000): "$5,000,001+",
                }

                amount_label = "$1,001 - $15,000"
                a_min, a_max = 1001, 15000
                for (lo, hi), label in amount_ranges.items():
                    if lo <= (amount or 0) <= hi:
                        amount_label = label
                        a_min, a_max = lo, hi
                        break

                chamber = item.get("chamber", "")
                party = item.get("party", "")
                committees = item.get("committees", [])
                if isinstance(committees, list):
                    committees = [c.get("name", "") if isinstance(c, dict) else str(c) for c in committees]

                is_notable = politician in NOTABLE_TRADERS
                edge = 50 if is_notable else 25

                trades.append(CongressTrade(
                    politician=politician,
                    party=party,
                    chamber=chamber,
                    symbol=symbol,
                    transaction="Purchase" if "buy" in tx_type.lower() else "Sale",
                    amount_range=amount_label,
                    amount_min=a_min,
                    amount_max=a_max,
                    transaction_date=tx_date,
                    disclosure_date=item.get("filingDate", ""),
                    committees=committees,
                    is_notable=is_notable,
                    edge_score=edge,
                ))

            log.info(f"Fetched {len(trades)} congressional trades")
            return trades

        except Exception as e:
            log.error(f"Capitol Trades fetch failed: {e}")
            return self._load_cache()

    def _load_cache(self) -> List[CongressTrade]:
        try:
            with open(f"{self.cache_dir}/congress_cache.json") as f:
                data = json.load(f)
            return [CongressTrade(**t) for t in data]
        except Exception:
            return []

    def report(self) -> str:
        """Generate human-readable congress trading report."""
        signals = self.scan_recent()
        if not signals:
            return "No congressional trading signals available."

        lines = [
            f"=== CONGRESS TRADING REPORT ({datetime.now().strftime('%Y-%m-%d')}) ===",
            f"Tracking {len(self.trades)} recent trades\n",
        ]

        for i, s in enumerate(signals[:10], 1):
            arrow = "▲" if s.direction == "bullish" else "▼"
            committee_tag = " [COMMITTEE EDGE]" if s.committee_overlap else ""
            lines.append(
                f"  {i}. {arrow} {s.symbol} — {s.direction.upper()} "
                f"(edge: {s.edge_score:.0f}/100){committee_tag}"
            )
            lines.append(f"     {s.trade_count} trades, ${s.total_min_value:,.0f}-${s.total_max_value:,.0f}")
            lines.append(f"     Traders: {', '.join(s.top_traders[:3])}")
            lines.append(f"     Latest: {s.latest_trade_date}")
            lines.append("")

        return "\n".join(lines)
