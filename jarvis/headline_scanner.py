"""
HEADLINE SCANNER
================
Scans morning news headlines to identify daily movers BEFORE market open.
Headlines determine who pops today — this is the edge the morning brief needs.

Sources:
  - RSS feeds (free, no API key): Yahoo Finance, MarketWatch, Bloomberg (summaries)
  - Finviz news scraper (free)
  - SEC EDGAR RSS (free)
  - Reddit wallstreetbets (free API)

Output: ranked list of tickers likely to move today + sentiment + catalyst.
"""

import re, json, logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError
from xml.etree import ElementTree as ET

log = logging.getLogger("headline_scanner")

RSS_FEEDS = {
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "marketwatch_top": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "marketwatch_markets": "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "cnbc_earnings": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    "sec_filings": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&dateb=&owner=include&count=40&search_text=&start=0&output=atom",
}

TICKER_PATTERN = re.compile(
    r'\b(?:NVDA|MSFT|AAPL|GOOGL|GOOG|META|AMZN|AMD|AVGO|TSLA|CRM|ADBE|'
    r'LULU|MRVL|MU|TSM|NFLX|INTC|QCOM|SMCI|ARM|PLTR|SNOW|UBER|COIN|'
    r'JPM|GS|BAC|WFC|V|MA|UNH|JNJ|PFE|XOM|CVX|WMT|HD|NKE|DIS|'
    r'SPY|QQQ|IWM|DIA|VIX)\b'
)

SENTIMENT_WORDS = {
    "positive": [
        "beat", "beats", "exceeded", "surpass", "upgrade", "upgraded", "raises",
        "raised", "record", "surge", "surges", "soar", "soars", "rally", "rallies",
        "bullish", "breakout", "all-time high", "outperform", "buy", "growth",
        "profit", "revenue beat", "strong earnings", "guidance raised", "momentum",
        "deal", "acquisition", "partnership", "contract", "approved", "launch",
        "innovation", "ai", "artificial intelligence",
    ],
    "negative": [
        "miss", "misses", "missed", "fell", "fall", "falls", "drop", "drops",
        "decline", "declines", "downgrade", "downgraded", "cut", "cuts", "warns",
        "warning", "layoff", "layoffs", "loss", "losses", "recall", "lawsuit",
        "bearish", "crash", "plunge", "plunges", "selloff", "sell-off", "weak",
        "disappointing", "guidance lowered", "underperform", "sell", "investigation",
        "subpoena", "bankruptcy", "default", "fraud",
    ],
}


@dataclass
class Headline:
    title: str
    source: str
    url: str
    published: str
    tickers: List[str]
    sentiment: str       # "positive", "negative", "neutral"
    sentiment_score: float  # -1.0 to 1.0
    catalyst_type: str   # "earnings", "upgrade", "deal", "macro", "insider", "unknown"


@dataclass
class MoverCandidate:
    symbol: str
    headline_count: int
    avg_sentiment: float
    catalysts: List[str]
    top_headline: str
    direction: str       # "bullish", "bearish", "mixed"
    priority: float      # 0-100 ranking score


class HeadlineScanner:
    def __init__(self, watchlist: Optional[List[str]] = None):
        self.watchlist = set(w.upper() for w in (watchlist or []))

    def scan(self) -> List[MoverCandidate]:
        """Run full morning scan. Call this at premarket (8:00 AM ET)."""
        log.info("Starting headline scan...")
        headlines = []

        for name, url in RSS_FEEDS.items():
            try:
                fetched = self._fetch_rss(url, name)
                headlines.extend(fetched)
                log.info(f"  {name}: {len(fetched)} headlines")
            except Exception as e:
                log.warning(f"  {name} failed: {e}")

        if not headlines:
            log.warning("No headlines fetched from any source")
            return []

        ticker_map: Dict[str, List[Headline]] = {}
        for h in headlines:
            for ticker in h.tickers:
                ticker_map.setdefault(ticker, []).append(h)

        candidates = []
        for symbol, hlines in ticker_map.items():
            if self.watchlist and symbol not in self.watchlist:
                continue

            sentiments = [h.sentiment_score for h in hlines]
            avg_sent = sum(sentiments) / len(sentiments)
            catalysts = list(set(h.catalyst_type for h in hlines if h.catalyst_type != "unknown"))
            top = max(hlines, key=lambda h: abs(h.sentiment_score))

            if avg_sent > 0.2:
                direction = "bullish"
            elif avg_sent < -0.2:
                direction = "bearish"
            else:
                direction = "mixed"

            priority = (
                len(hlines) * 15 +
                abs(avg_sent) * 40 +
                len(catalysts) * 10 +
                (20 if symbol in self.watchlist else 0)
            )

            candidates.append(MoverCandidate(
                symbol=symbol,
                headline_count=len(hlines),
                avg_sentiment=avg_sent,
                catalysts=catalysts or ["news"],
                top_headline=top.title,
                direction=direction,
                priority=min(100, priority),
            ))

        candidates.sort(key=lambda c: c.priority, reverse=True)
        log.info(f"Scan complete: {len(candidates)} potential movers identified")
        return candidates[:20]

    def _fetch_rss(self, url: str, source: str) -> List[Headline]:
        req = Request(url, headers={"User-Agent": "JarvisBot/1.0"})
        with urlopen(req, timeout=10) as resp:
            data = resp.read()

        root = ET.fromstring(data)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        headlines = []

        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            if title:
                headlines.append(self._parse_headline(title, source, link, pub))

        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            link = link_el.get("href", "") if link_el is not None else ""
            pub = (entry.findtext("{http://www.w3.org/2005/Atom}updated") or "").strip()
            if title:
                headlines.append(self._parse_headline(title, source, link, pub))

        return headlines

    def _parse_headline(self, title: str, source: str, url: str, published: str) -> Headline:
        tickers = list(set(TICKER_PATTERN.findall(title.upper())))
        sentiment, score = self._analyze_sentiment(title)
        catalyst = self._detect_catalyst(title)

        return Headline(
            title=title,
            source=source,
            url=url,
            published=published,
            tickers=tickers,
            sentiment=sentiment,
            sentiment_score=score,
            catalyst_type=catalyst,
        )

    def _analyze_sentiment(self, text: str) -> Tuple[str, float]:
        lower = text.lower()
        pos = sum(1 for w in SENTIMENT_WORDS["positive"] if w in lower)
        neg = sum(1 for w in SENTIMENT_WORDS["negative"] if w in lower)
        total = pos + neg
        if total == 0:
            return "neutral", 0.0
        score = (pos - neg) / total
        if score > 0.2:
            return "positive", min(1.0, score)
        elif score < -0.2:
            return "negative", max(-1.0, score)
        return "neutral", score

    def _detect_catalyst(self, text: str) -> str:
        lower = text.lower()
        if any(w in lower for w in ["earnings", "revenue", "eps", "guidance", "quarterly"]):
            return "earnings"
        if any(w in lower for w in ["upgrade", "downgrade", "price target", "analyst"]):
            return "analyst"
        if any(w in lower for w in ["deal", "acquisition", "merger", "buyout", "partnership"]):
            return "deal"
        if any(w in lower for w in ["fed", "rate", "inflation", "gdp", "jobs", "cpi", "fomc"]):
            return "macro"
        if any(w in lower for w in ["insider", "filing", "form 4", "13f", "sec"]):
            return "insider"
        if any(w in lower for w in ["ai", "artificial intelligence", "chip", "gpu", "data center"]):
            return "tech_catalyst"
        return "unknown"

    def morning_brief(self) -> str:
        """Generate human-readable morning brief."""
        movers = self.scan()
        if not movers:
            return "No significant headline movers detected this morning."

        lines = [
            f"=== JARVIS MORNING HEADLINE BRIEF ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===",
            f"Top {min(10, len(movers))} potential movers:\n",
        ]
        for i, m in enumerate(movers[:10], 1):
            arrow = "▲" if m.direction == "bullish" else "▼" if m.direction == "bearish" else "◆"
            lines.append(
                f"  {i}. {arrow} {m.symbol} — {m.direction.upper()} "
                f"(sentiment: {m.avg_sentiment:+.2f}, {m.headline_count} headlines)"
            )
            lines.append(f"     Catalysts: {', '.join(m.catalysts)}")
            lines.append(f"     \"{m.top_headline[:80]}\"")
            lines.append("")

        return "\n".join(lines)
