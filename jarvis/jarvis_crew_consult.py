"""
JARVIS CREW CONSULTATION
=========================
Before executing ANY trade, Jarvis consults his crew:
  1. FINANCIAL ANALYST — checks fundamentals (earnings, revenue, margins, debt)
  2. TECHNICAL ANALYST — checks the chart (trend, support/resistance, momentum)
  3. RISK OFFICER — checks portfolio fit (concentration, correlation, drawdown)

Signal flow:
  Alpha source → Signal → Crew vote → Execute or Reject

The morning brief combines all of this into one report for Chris.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

log = logging.getLogger("jarvis_crew")


@dataclass
class CrewVerdict:
    analyst: str
    vote: str            # "approve", "reject", "caution"
    confidence: float    # 0-1
    reasoning: str
    key_metric: str      # the ONE number that matters most


@dataclass
class TradeProposal:
    symbol: str
    direction: str       # "long" or "short"
    entry: float
    stop_loss: float
    take_profit: float
    source: str          # "brain", "headline", "congress", "sec", "strategy"
    brain_confidence: float
    mta_grade: str
    mta_score: float
    xgb_agree: bool


@dataclass
class CrewDecision:
    proposal: TradeProposal
    verdicts: List[CrewVerdict]
    final_vote: str      # "GO", "NO-GO", "WAIT"
    go_count: int
    total_count: int
    summary: str
    execute: bool


class FinancialAnalyst:
    """Checks fundamentals before any trade."""

    def evaluate(self, symbol: str, direction: str, fundamentals: dict = None) -> CrewVerdict:
        if fundamentals is None:
            fundamentals = self._get_fundamentals(symbol)

        if not fundamentals:
            return CrewVerdict(
                analyst="Financial Analyst",
                vote="caution",
                confidence=0.3,
                reasoning=f"No fundamental data available for {symbol} — proceeding on technicals only",
                key_metric="N/A",
            )

        pe = fundamentals.get("pe_ratio", 0)
        rev_growth = fundamentals.get("revenue_growth_pct", 0)
        eps_surprise = fundamentals.get("eps_surprise_pct", 0)
        debt_equity = fundamentals.get("debt_to_equity", 0)
        margin = fundamentals.get("profit_margin_pct", 0)

        score = 0
        reasons = []

        if direction == "long":
            if rev_growth > 15:
                score += 25
                reasons.append(f"revenue growth {rev_growth:.0f}% strong")
            elif rev_growth < 0:
                score -= 20
                reasons.append(f"revenue declining {rev_growth:.0f}%")

            if eps_surprise > 5:
                score += 20
                reasons.append(f"beat earnings by {eps_surprise:.0f}%")
            elif eps_surprise < -5:
                score -= 25
                reasons.append(f"missed earnings by {eps_surprise:.0f}%")

            if margin > 20:
                score += 15
                reasons.append(f"profit margin {margin:.0f}% healthy")

            if debt_equity > 2:
                score -= 15
                reasons.append(f"debt/equity {debt_equity:.1f} high")

            if pe > 0 and pe < 30:
                score += 10
                reasons.append(f"P/E {pe:.0f} reasonable")
            elif pe > 60:
                score -= 10
                reasons.append(f"P/E {pe:.0f} stretched")

        else:  # short
            if rev_growth < 0:
                score += 20
                reasons.append(f"revenue declining {rev_growth:.0f}% — short thesis valid")
            if eps_surprise < -5:
                score += 20
                reasons.append(f"missed earnings — weakness confirmed")
            if pe > 50:
                score += 15
                reasons.append(f"P/E {pe:.0f} overvalued for short")
            if margin < 5:
                score += 10
                reasons.append(f"thin margins {margin:.0f}% — vulnerable")

        if score >= 30:
            vote = "approve"
        elif score <= -10:
            vote = "reject"
        else:
            vote = "caution"

        key = f"RevGrowth:{rev_growth:.0f}% | EPS:{eps_surprise:+.0f}% | PE:{pe:.0f}"

        return CrewVerdict(
            analyst="Financial Analyst",
            vote=vote,
            confidence=min(1.0, max(0.1, (score + 50) / 100)),
            reasoning="; ".join(reasons) if reasons else "neutral fundamentals",
            key_metric=key,
        )

    def _get_fundamentals(self, symbol: str) -> dict:
        """Pull fundamentals. In production, wire to a data provider."""
        return {}


class TechnicalAnalyst:
    """Checks the chart before any trade."""

    def evaluate(self, symbol: str, direction: str, technicals: dict = None) -> CrewVerdict:
        if technicals is None:
            technicals = self._get_technicals(symbol)

        if not technicals:
            return CrewVerdict(
                analyst="Technical Analyst",
                vote="caution",
                confidence=0.3,
                reasoning=f"No technical data for {symbol} — need price data",
                key_metric="N/A",
            )

        rsi = technicals.get("rsi_14", 50)
        above_200sma = technicals.get("above_200sma", True)
        above_50sma = technicals.get("above_50sma", True)
        macd_signal = technicals.get("macd_cross", "neutral")  # "bullish", "bearish", "neutral"
        atr_pct = technicals.get("atr_pct", 2.0)
        volume_ratio = technicals.get("volume_ratio", 1.0)  # today vs 20d avg
        near_support = technicals.get("near_support", False)
        near_resistance = technicals.get("near_resistance", False)

        score = 0
        reasons = []

        if direction == "long":
            if above_200sma:
                score += 15
                reasons.append("above 200 SMA — trend up")
            else:
                score -= 20
                reasons.append("below 200 SMA — trend down, risky long")

            if above_50sma:
                score += 10
                reasons.append("above 50 SMA")

            if 30 < rsi < 70:
                score += 10
                reasons.append(f"RSI {rsi:.0f} healthy range")
            elif rsi > 75:
                score -= 15
                reasons.append(f"RSI {rsi:.0f} overbought — bad entry")
            elif rsi < 30:
                score += 15
                reasons.append(f"RSI {rsi:.0f} oversold — potential bounce")

            if macd_signal == "bullish":
                score += 15
                reasons.append("MACD bullish cross")
            elif macd_signal == "bearish":
                score -= 10
                reasons.append("MACD bearish — momentum fading")

            if near_support:
                score += 10
                reasons.append("near support — good entry zone")

            if volume_ratio > 1.5:
                score += 10
                reasons.append(f"volume {volume_ratio:.1f}x avg — institutional interest")

        else:  # short
            if not above_200sma:
                score += 20
                reasons.append("below 200 SMA — trend confirms short")
            else:
                score -= 15
                reasons.append("above 200 SMA — shorting uptrend is risky")

            if rsi > 75:
                score += 15
                reasons.append(f"RSI {rsi:.0f} overbought — short setup")
            elif rsi < 30:
                score -= 15
                reasons.append(f"RSI {rsi:.0f} already oversold — don't short here")

            if macd_signal == "bearish":
                score += 15
                reasons.append("MACD bearish — momentum supports short")

            if near_resistance:
                score += 10
                reasons.append("at resistance — good short entry")

        if score >= 25:
            vote = "approve"
        elif score <= -10:
            vote = "reject"
        else:
            vote = "caution"

        key = f"RSI:{rsi:.0f} | {'Above' if above_200sma else 'Below'}200SMA | MACD:{macd_signal}"

        return CrewVerdict(
            analyst="Technical Analyst",
            vote=vote,
            confidence=min(1.0, max(0.1, (score + 50) / 100)),
            reasoning="; ".join(reasons) if reasons else "mixed technicals",
            key_metric=key,
        )

    def _get_technicals(self, symbol: str) -> dict:
        """Pull technicals. In production, compute from price data."""
        return {}


class RiskOfficer:
    """Checks portfolio risk before any trade."""

    def evaluate(self, proposal: TradeProposal, current_positions: list,
                 account_value: float, daily_pnl: float) -> CrewVerdict:

        reasons = []
        score = 50  # start neutral

        position_count = len(current_positions)
        if position_count >= 8:
            score -= 30
            reasons.append(f"already {position_count} positions — at capacity")
        elif position_count >= 6:
            score -= 10
            reasons.append(f"{position_count} positions — getting full")

        symbols_held = [p.get("symbol", "").upper() for p in current_positions]
        if proposal.symbol.upper() in symbols_held:
            score -= 40
            reasons.append(f"already holding {proposal.symbol}")

        risk_per_share = abs(proposal.entry - proposal.stop_loss)
        reward_per_share = abs(proposal.take_profit - proposal.entry)
        rr = reward_per_share / risk_per_share if risk_per_share > 0 else 0

        if rr >= 3:
            score += 15
            reasons.append(f"R:R {rr:.1f} excellent")
        elif rr >= 2:
            score += 5
            reasons.append(f"R:R {rr:.1f} acceptable")
        elif rr < 1.5:
            score -= 20
            reasons.append(f"R:R {rr:.1f} too low — need 2:1 minimum")

        risk_dollars = risk_per_share * (account_value * 0.01 / risk_per_share) if risk_per_share > 0 else 0
        risk_pct = (risk_dollars / account_value * 100) if account_value > 0 else 0
        if risk_pct > 2:
            score -= 15
            reasons.append(f"risk {risk_pct:.1f}% of account — too much")

        daily_loss_pct = abs(daily_pnl / account_value * 100) if account_value > 0 and daily_pnl < 0 else 0
        if daily_loss_pct > 2:
            score -= 25
            reasons.append(f"already down {daily_loss_pct:.1f}% today — slow down")

        if score >= 45:
            vote = "approve"
        elif score <= 20:
            vote = "reject"
        else:
            vote = "caution"

        return CrewVerdict(
            analyst="Risk Officer",
            vote=vote,
            confidence=min(1.0, max(0.1, score / 100)),
            reasoning="; ".join(reasons) if reasons else "risk parameters acceptable",
            key_metric=f"R:R {rr:.1f} | Positions: {position_count} | DayPnL: ${daily_pnl:+.0f}",
        )


class JarvisCrew:
    """
    The full crew. Consults all analysts before any trade.
    Majority vote decides. 2 of 3 must approve to execute.
    """

    def __init__(self):
        self.financial = FinancialAnalyst()
        self.technical = TechnicalAnalyst()
        self.risk = RiskOfficer()

    def consult(self, proposal: TradeProposal, positions: list = None,
                account_value: float = 11647, daily_pnl: float = 0,
                fundamentals: dict = None, technicals: dict = None) -> CrewDecision:

        verdicts = [
            self.financial.evaluate(proposal.symbol, proposal.direction, fundamentals),
            self.technical.evaluate(proposal.symbol, proposal.direction, technicals),
            self.risk.evaluate(proposal, positions or [], account_value, daily_pnl),
        ]

        approvals = sum(1 for v in verdicts if v.vote == "approve")
        rejections = sum(1 for v in verdicts if v.vote == "reject")

        if approvals >= 2:
            final = "GO"
            execute = True
        elif rejections >= 2:
            final = "NO-GO"
            execute = False
        else:
            final = "WAIT"
            execute = False

        verdict_lines = []
        for v in verdicts:
            icon = "YES" if v.vote == "approve" else "NO" if v.vote == "reject" else "MEH"
            verdict_lines.append(f"  [{icon}] {v.analyst}: {v.reasoning}")

        summary = (
            f"{proposal.direction.upper()} {proposal.symbol} @ {proposal.entry} "
            f"→ TP {proposal.take_profit} / SL {proposal.stop_loss}\n"
            f"CREW VOTE: {final} ({approvals}/{len(verdicts)} approve)\n"
            + "\n".join(verdict_lines)
        )

        return CrewDecision(
            proposal=proposal,
            verdicts=verdicts,
            final_vote=final,
            go_count=approvals,
            total_count=len(verdicts),
            summary=summary,
            execute=execute,
        )


def build_morning_brief(alpha_results: dict, crew: "JarvisCrew",
                        positions: list = None, account_value: float = 11647) -> str:
    """
    THE MORNING BRIEF — for Chris AND Jarvis.
    Shows what Jarvis likes, what he doesn't, and what the crew thinks.
    """
    now = datetime.now()
    lines = [
        "=" * 60,
        f"  JARVIS DAILY BRIEF — {now.strftime('%A %B %d, %Y')}",
        f"  Account: ${account_value:,.0f} | Positions: {len(positions or [])}",
        "=" * 60,
        "",
    ]

    # WHAT I LIKE TODAY
    likes = []
    dislikes = []
    watch = []

    opps = alpha_results.get("combined_opportunities", [])
    for opp in opps[:15]:
        score = opp.get("combined_score", 0)
        if score >= 60:
            likes.append(opp)
        elif score >= 40:
            watch.append(opp)
        else:
            dislikes.append(opp)

    if likes:
        lines.append("WHAT I LIKE TODAY:")
        lines.append("")
        for o in likes:
            sources = []
            if o.get("headline_score", 0) > 0: sources.append("NEWS")
            if o.get("congress_score", 0) > 0: sources.append("CONGRESS")
            if o.get("sec_score", 0) > 0: sources.append("SEC")
            arrow = "LONG" if o["direction"] == "bullish" else "SHORT" if o["direction"] == "bearish" else "WATCH"
            lines.append(f"  {arrow} {o['symbol']} — score {o['combined_score']:.0f}/100 [{'+'.join(sources)}]")
            if o.get("catalysts"):
                lines.append(f"    Why: {', '.join(o['catalysts'][:3])}")
        lines.append("")

    if dislikes:
        lines.append("WHAT I DON'T LIKE:")
        lines.append("")
        for o in dislikes[:5]:
            lines.append(f"  AVOID {o['symbol']} — score {o['combined_score']:.0f}/100, weak confluence")
        lines.append("")

    if watch:
        lines.append("WATCHING (need more confirmation):")
        lines.append("")
        for o in watch[:5]:
            lines.append(f"  WATCH {o['symbol']} — score {o['combined_score']:.0f}/100")
        lines.append("")

    # HEADLINE MOVERS
    movers = alpha_results.get("headline_movers", [])
    if movers:
        lines.append("HEADLINE MOVERS THIS MORNING:")
        lines.append("")
        for m in movers[:5]:
            arrow = "UP" if m["direction"] == "bullish" else "DN"
            lines.append(f"  [{arrow}] {m['symbol']} — \"{m.get('headline','')[:60]}\"")
        lines.append("")

    # CONGRESS TRADES
    congress = alpha_results.get("congress_signals", [])
    if congress:
        lines.append("POLITICIANS TRADING:")
        lines.append("")
        for c in congress[:5]:
            arrow = "BUYING" if c["direction"] == "bullish" else "SELLING"
            tag = " ** COMMITTEE EDGE **" if c.get("committee_edge") else ""
            lines.append(f"  {', '.join(c.get('traders',['?'])[:2])} {arrow} {c['symbol']}{tag}")
        lines.append("")

    # SEC INSIDER BUYS
    sec = alpha_results.get("sec_signals", [])
    if sec:
        lines.append("INSIDER BUYING:")
        lines.append("")
        for s in sec[:5]:
            lines.append(f"  {s['symbol']} — {s.get('detail','insider activity')}")
        lines.append("")

    # EXECUTION PLAN
    auto = alpha_results.get("auto_executed", [])
    if auto:
        lines.append("TODAY'S TRADE PLAN (auto-execute):")
        lines.append("")
        for a in auto:
            lines.append(f"  -> {a['direction'].upper()} {a['symbol']} (score: {a['combined_score']:.0f})")
        lines.append("")

    lines.append("=" * 60)
    lines.append("  Jarvis is live. Crew on standby. All signals gated.")
    lines.append("=" * 60)

    return "\n".join(lines)
