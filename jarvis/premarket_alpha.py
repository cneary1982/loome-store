"""
PREMARKET ALPHA AGGREGATOR
===========================
Runs every morning at 8:00 AM ET. Pulls all alpha sources,
ranks opportunities, and feeds them to the signal executor.

This is the "morning brain" — it answers:
  1. What is the market likely to do today? (macro regime)
  2. Who is going to move today? (headlines + flow)
  3. What are the politicians buying? (congress)
  4. What are insiders buying? (SEC Form 4)
  5. What does the brain see? (probability + MTA)

Then it generates a ranked trade plan and auto-executes the top signals.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

log = logging.getLogger("premarket_alpha")


class PremarketAlpha:
    """
    Orchestrates all alpha sources into a single morning scan.
    Wire this into brain_trader.py's learn_cycle or run standalone.
    """

    def __init__(self, objective, executor, headline_scanner=None,
                 congress_tracker=None, sec_scanner=None, brain=None):
        self.objective = objective
        self.executor = executor
        self.headlines = headline_scanner
        self.congress = congress_tracker
        self.sec = sec_scanner
        self.brain = brain

    def run_morning_scan(self) -> dict:
        """Full morning alpha scan. Returns aggregated results."""
        log.info("=" * 60)
        log.info("PREMARKET ALPHA SCAN STARTING")
        log.info("=" * 60)

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "headline_movers": [],
            "congress_signals": [],
            "sec_signals": [],
            "combined_opportunities": [],
            "auto_executed": [],
            "auto_rejected": [],
        }

        if self.headlines:
            try:
                movers = self.headlines.scan()
                results["headline_movers"] = [
                    {
                        "symbol": m.symbol,
                        "direction": m.direction,
                        "sentiment": m.avg_sentiment,
                        "catalysts": m.catalysts,
                        "headline": m.top_headline,
                        "priority": m.priority,
                    }
                    for m in movers[:15]
                ]
                log.info(f"Headlines: {len(movers)} potential movers")
            except Exception as e:
                log.error(f"Headline scan failed: {e}")

        if self.congress:
            try:
                signals = self.congress.scan_recent(days=30)
                results["congress_signals"] = [
                    {
                        "symbol": s.symbol,
                        "direction": s.direction,
                        "edge_score": s.edge_score,
                        "trade_count": s.trade_count,
                        "traders": s.top_traders,
                        "committee_edge": s.committee_overlap,
                        "value_range": f"${s.total_min_value:,.0f}-${s.total_max_value:,.0f}",
                    }
                    for s in signals[:10]
                ]
                log.info(f"Congress: {len(signals)} signals")
            except Exception as e:
                log.error(f"Congress scan failed: {e}")

        if self.sec:
            try:
                signals = self.sec.scan_insider_buys(days=14)
                results["sec_signals"] = [
                    {
                        "symbol": s.symbol,
                        "signal_type": s.signal_type,
                        "strength": s.strength,
                        "detail": s.detail,
                        "names": s.key_names,
                        "total_value": s.total_value,
                    }
                    for s in signals[:10]
                ]
                log.info(f"SEC: {len(signals)} insider signals")
            except Exception as e:
                log.error(f"SEC scan failed: {e}")

        combined = self._rank_opportunities(results)
        results["combined_opportunities"] = combined

        if self.objective.auto_execute and self.executor:
            for opp in combined[:5]:
                if opp["combined_score"] >= 60:
                    log.info(f"Auto-executing: {opp['direction']} {opp['symbol']} (score: {opp['combined_score']:.0f})")
                    results["auto_executed"].append(opp)
                else:
                    results["auto_rejected"].append(opp)

        log.info("=" * 60)
        log.info(f"SCAN COMPLETE: {len(combined)} opportunities ranked")
        log.info(f"  Auto-execute candidates: {len(results['auto_executed'])}")
        log.info("=" * 60)

        return results

    def _rank_opportunities(self, results: dict) -> list:
        """Combine all alpha sources into a single ranked list."""
        scores: Dict[str, dict] = {}

        for m in results.get("headline_movers", []):
            sym = m["symbol"]
            if sym not in scores:
                scores[sym] = self._empty_score(sym)
            scores[sym]["headline_score"] = m["priority"]
            scores[sym]["direction"] = m["direction"]
            scores[sym]["catalysts"].extend(m.get("catalysts", []))

        for s in results.get("congress_signals", []):
            sym = s["symbol"]
            if sym not in scores:
                scores[sym] = self._empty_score(sym)
            scores[sym]["congress_score"] = s["edge_score"]
            if s.get("committee_edge"):
                scores[sym]["congress_score"] *= 1.5
            scores[sym]["catalysts"].append("congress_trade")

        for s in results.get("sec_signals", []):
            sym = s["symbol"]
            if sym not in scores:
                scores[sym] = self._empty_score(sym)
            scores[sym]["sec_score"] = s["strength"]
            scores[sym]["catalysts"].append("insider_buy")

        for sym, s in scores.items():
            s["source_count"] = sum(1 for v in [s["headline_score"], s["congress_score"], s["sec_score"]] if v > 0)
            confluence_bonus = s["source_count"] * 10

            s["combined_score"] = (
                s["headline_score"] * 0.30 +
                s["congress_score"] * 0.35 +
                s["sec_score"] * 0.35 +
                confluence_bonus
            )

            on_watchlist = sym in self.objective.watchlist or sym in self.objective.short_watchlist
            if on_watchlist:
                s["combined_score"] *= 1.2

            s["catalysts"] = list(set(s["catalysts"]))

        ranked = sorted(scores.values(), key=lambda x: x["combined_score"], reverse=True)
        return ranked[:20]

    def _empty_score(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "direction": "neutral",
            "headline_score": 0,
            "congress_score": 0,
            "sec_score": 0,
            "source_count": 0,
            "combined_score": 0,
            "catalysts": [],
        }

    def morning_brief(self) -> str:
        """Generate the full morning brief for display."""
        results = self.run_morning_scan()

        lines = [
            f"{'='*60}",
            f"  JARVIS PREMARKET ALPHA BRIEF",
            f"  {datetime.now().strftime('%A, %B %d %Y — %H:%M ET')}",
            f"{'='*60}",
            "",
        ]

        opps = results.get("combined_opportunities", [])
        if opps:
            lines.append("TOP OPPORTUNITIES (ranked by multi-source confluence):")
            lines.append("")
            for i, o in enumerate(opps[:10], 1):
                arrow = "▲" if o["direction"] == "bullish" else "▼" if o["direction"] == "bearish" else "◆"
                sources = []
                if o["headline_score"] > 0: sources.append("NEWS")
                if o["congress_score"] > 0: sources.append("CONGRESS")
                if o["sec_score"] > 0: sources.append("SEC")

                lines.append(
                    f"  {i}. {arrow} {o['symbol']} — score {o['combined_score']:.0f}/100 "
                    f"[{'+'.join(sources)}]"
                )
                if o["catalysts"]:
                    lines.append(f"     Catalysts: {', '.join(o['catalysts'][:4])}")
                lines.append("")
        else:
            lines.append("No high-confidence opportunities detected this morning.")
            lines.append("")

        auto = results.get("auto_executed", [])
        if auto:
            lines.append(f"AUTO-EXECUTE QUEUE ({len(auto)} signals):")
            for a in auto:
                lines.append(f"  → {a['direction'].upper()} {a['symbol']} (score: {a['combined_score']:.0f})")
            lines.append("")

        lines.append(f"Next scan: market open + 30 min")
        lines.append(f"{'='*60}")

        return "\n".join(lines)
