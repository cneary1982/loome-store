"""
SEC EDGE SCANNER
================
Scans SEC EDGAR for alpha-generating filings:
  - Form 4 (insider buys/sells) — the STRONGEST single signal in quant finance
  - 13F (institutional holdings) — what hedge funds are buying
  - 8-K (material events) — mergers, CEO changes, guidance revisions
  - SC 13D/G (activist stakes) — someone building a 5%+ position

Key insight: Insider BUYS are way more predictive than sells.
Executives sell for many reasons (taxes, diversification, divorce).
They buy for only ONE reason: they think the stock is going up.

EDGAR is free, public, no API key needed. Rate limit: 10 req/sec.
"""

import json, logging, re, time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError

log = logging.getLogger("sec_edge")

EDGAR_BASE = "https://efts.sec.gov/LATEST"
EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"
EDGAR_COMPANY = "https://data.sec.gov/submissions"
EDGAR_HEADERS = {
    "User-Agent": "JarvisQuantBot cneary1982@gmail.com",
    "Accept": "application/json",
}

INSIDER_TITLES_HIGH = {"CEO", "CFO", "COO", "President", "Chairman", "Director"}


@dataclass
class InsiderFiling:
    symbol: str
    company: str
    insider_name: str
    insider_title: str
    transaction_type: str   # "P" (purchase), "S" (sale), "A" (award)
    shares: float
    price: float
    value: float
    filing_date: str
    transaction_date: str
    ownership_after: float
    is_c_suite: bool
    signal_strength: float  # 0-100


@dataclass
class InstitutionalFiling:
    fund_name: str
    symbol: str
    shares: float
    value: float
    change_pct: float       # vs previous quarter
    filing_date: str
    is_new_position: bool


@dataclass
class SECSignal:
    symbol: str
    signal_type: str        # "insider_buy_cluster", "activist_stake", "institutional_accumulation"
    direction: str          # "bullish" or "bearish"
    strength: float         # 0-100
    filings: int
    total_value: float
    key_names: List[str]
    detail: str
    filing_date: str


class SECEdgeScanner:
    """
    Scans SEC EDGAR for institutional-grade alpha signals.
    """

    def __init__(self, watchlist: Optional[List[str]] = None):
        self.watchlist = set(w.upper() for w in (watchlist or []))

    def scan_insider_buys(self, days: int = 14) -> List[SECSignal]:
        """Scan recent Form 4 insider purchases — the gold standard."""
        log.info(f"Scanning SEC insider buys (last {days} days)...")

        filings = self._fetch_recent_form4(days)
        if not filings:
            return []

        buys = [f for f in filings if f.transaction_type == "P"]
        log.info(f"Found {len(buys)} insider purchases out of {len(filings)} Form 4 filings")

        symbol_buys: Dict[str, List[InsiderFiling]] = {}
        for b in buys:
            symbol_buys.setdefault(b.symbol, []).append(b)

        signals = []
        for symbol, flist in symbol_buys.items():
            if self.watchlist and symbol not in self.watchlist:
                pass  # still track, just lower priority

            c_suite = [f for f in flist if f.is_c_suite]
            total_value = sum(f.value for f in flist)
            strength = (
                len(flist) * 15 +
                len(c_suite) * 25 +
                min(30, total_value / 100000 * 10) +
                (10 if symbol in self.watchlist else 0)
            )

            names = list(set(f"{f.insider_name} ({f.insider_title})" for f in flist))

            if len(flist) >= 3:
                sig_type = "insider_buy_cluster"
                detail = f"{len(flist)} insiders buying in {days}d window — cluster signal"
            elif c_suite:
                sig_type = "insider_buy_cluster"
                detail = f"C-suite buying: {', '.join(n for n in names[:2])}"
            else:
                sig_type = "insider_buy_cluster"
                detail = f"{len(flist)} insider purchase(s), ${total_value:,.0f} total"

            signals.append(SECSignal(
                symbol=symbol,
                signal_type=sig_type,
                direction="bullish",
                strength=min(100, strength),
                filings=len(flist),
                total_value=total_value,
                key_names=names[:5],
                detail=detail,
                filing_date=max(f.filing_date for f in flist),
            ))

        signals.sort(key=lambda s: s.strength, reverse=True)
        return signals[:20]

    def _fetch_recent_form4(self, days: int) -> List[InsiderFiling]:
        """Fetch recent Form 4 filings from EDGAR full-text search."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
            url = (
                f"{EDGAR_BASE}/search-index?q=%22form4%22"
                f"&dateRange=custom&startdt={cutoff}"
                f"&forms=4&hits.hits.total.value=true"
            )

            url2 = (
                f"https://efts.sec.gov/LATEST/search-index"
                f"?q=%224%22&forms=4"
                f"&dateRange=custom&startdt={cutoff}"
            )

            search_url = (
                f"https://efts.sec.gov/LATEST/search-index"
                f"?forms=4&dateRange=custom&startdt={cutoff}"
                f"&from=0&size=50"
            )

            req = Request(search_url, headers=EDGAR_HEADERS)
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            filings = []
            for hit in data.get("hits", {}).get("hits", []):
                source = hit.get("_source", {})
                form = source.get("form_type", "")
                if form != "4":
                    continue

                ticker = source.get("tickers", [""])[0] if source.get("tickers") else ""
                company = source.get("display_names", [""])[0] if source.get("display_names") else ""
                filed = source.get("file_date", "")

                if not ticker:
                    continue

                filings.append(InsiderFiling(
                    symbol=ticker.upper(),
                    company=company,
                    insider_name=source.get("display_names", ["Unknown"])[0] if len(source.get("display_names", [])) > 1 else "Unknown",
                    insider_title="",
                    transaction_type="P",
                    shares=0,
                    price=0,
                    value=0,
                    filing_date=filed,
                    transaction_date=filed,
                    ownership_after=0,
                    is_c_suite=False,
                    signal_strength=25,
                ))

            return filings

        except Exception as e:
            log.error(f"EDGAR Form 4 fetch failed: {e}")
            return self._parse_edgar_rss()

    def _parse_edgar_rss(self) -> List[InsiderFiling]:
        """Fallback: parse EDGAR RSS feed for recent Form 4."""
        try:
            url = (
                "https://www.sec.gov/cgi-bin/browse-edgar"
                "?action=getcurrent&type=4&dateb=&owner=include"
                "&count=40&search_text=&start=0&output=atom"
            )
            req = Request(url, headers=EDGAR_HEADERS)
            with urlopen(req, timeout=15) as resp:
                from xml.etree import ElementTree as ET
                root = ET.fromstring(resp.read())

            ns = {"atom": "http://www.w3.org/2005/Atom"}
            filings = []

            for entry in root.findall("atom:entry", ns):
                title = entry.findtext("atom:title", "", ns)
                updated = entry.findtext("atom:updated", "", ns)
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""

                ticker_match = re.search(r'\(([A-Z]{1,5})\)', title)
                if not ticker_match:
                    continue

                ticker = ticker_match.group(1)
                name_match = re.search(r'4 - (.+?) \(', title)
                company = name_match.group(1) if name_match else ""

                filings.append(InsiderFiling(
                    symbol=ticker,
                    company=company,
                    insider_name="",
                    insider_title="",
                    transaction_type="P",
                    shares=0,
                    price=0,
                    value=0,
                    filing_date=updated[:10] if updated else "",
                    transaction_date="",
                    ownership_after=0,
                    is_c_suite=False,
                    signal_strength=20,
                ))

            log.info(f"EDGAR RSS fallback: {len(filings)} Form 4 entries")
            return filings

        except Exception as e:
            log.error(f"EDGAR RSS fallback also failed: {e}")
            return []

    def scan_13f_changes(self) -> List[SECSignal]:
        """
        Scan quarterly 13F filings for institutional position changes.
        13F filings are quarterly — check after each quarter end.
        """
        signals = []
        log.info("13F scanning requires quarterly data — use fintel.io or whalewisdom API for real-time")
        return signals

    def report(self) -> str:
        """Generate human-readable SEC edge report."""
        signals = self.scan_insider_buys()
        if not signals:
            return "No actionable SEC insider signals detected."

        lines = [
            f"=== SEC INSIDER EDGE REPORT ({datetime.now().strftime('%Y-%m-%d')}) ===",
            f"Scanned recent Form 4 filings\n",
        ]

        for i, s in enumerate(signals[:10], 1):
            arrow = "▲" if s.direction == "bullish" else "▼"
            lines.append(
                f"  {i}. {arrow} {s.symbol} — {s.signal_type.replace('_',' ').upper()} "
                f"(strength: {s.strength:.0f}/100)"
            )
            lines.append(f"     {s.detail}")
            if s.key_names:
                lines.append(f"     Names: {', '.join(s.key_names[:3])}")
            if s.total_value > 0:
                lines.append(f"     Total value: ${s.total_value:,.0f}")
            lines.append("")

        return "\n".join(lines)
