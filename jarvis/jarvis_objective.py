"""
JARVIS PRIMARY OBJECTIVE
========================
This is the mission file. Every decision Jarvis makes flows from here.
"""

from dataclasses import dataclass, field
from typing import List, Dict
from enum import Enum
import json, os

class RiskTier(Enum):
    CONSERVATIVE = "conservative"
    MODERATE     = "moderate"
    AGGRESSIVE   = "aggressive"
    HEDGE_FUND   = "hedge_fund"

@dataclass
class PortfolioObjective:
    # ── MISSION ──────────────────────────────────────────────────
    name: str = "JARVIS AUTONOMOUS FUND"
    tier: RiskTier = RiskTier.HEDGE_FUND
    description: str = (
        "Build a hedge-fund-grade, tech-heavy, diversified portfolio. "
        "Autonomous execution. No missed signals. Every edge exploited."
    )

    # ── ACCOUNT ──────────────────────────────────────────────────
    broker: str = "tastytrade"
    account_value: float = 11_647.0
    max_drawdown_pct: float = 15.0
    daily_loss_limit_pct: float = 3.0

    # ── ALLOCATION TARGETS ───────────────────────────────────────
    # Sector weights (target %). Tech-heavy by mandate.
    sector_targets: Dict[str, float] = field(default_factory=lambda: {
        "tech":        0.40,   # NVDA, MSFT, AAPL, GOOGL, META, AMZN
        "semis":       0.15,   # AMD, AVGO, MRVL, MU, TSM
        "futures":     0.20,   # ES, NQ, MNQ — the brain's home turf
        "options":     0.10,   # 0DTE, swings, defined risk
        "momentum":    0.10,   # whatever is moving today
        "hedge":       0.05,   # VIX calls, puts on longs, inverse ETFs
    })

    # ── ALPHA SOURCES (ranked by priority) ───────────────────────
    alpha_sources: List[str] = field(default_factory=lambda: [
        "brain_probability",       # conditional-probability brain (core)
        "mta_confluence",          # multi-horizon 3-tier scoring
        "xgboost_covote",          # ensemble co-voter
        "uoa_flow",                # unusual options activity
        "news_headlines",          # morning headline scanner
        "congress_trades",         # politician buy/sell disclosures
        "sec_filings",             # 13F, Form 4 insider buys
        "vix_regime",              # VIX correlation system (Dylan)
        "sector_rotation",         # relative strength across sectors
        "technical_setups",        # ICT FVG, cage breakout, mean reversion
    ])

    # ── EXECUTION RULES ─────────────────────────────────────────
    auto_execute: bool = True          # THE FIX: actually trade signals
    require_confluence_grade: str = "B"  # minimum MTA grade to execute
    require_brain_confidence: float = 0.60
    require_xgb_agree: bool = True
    max_positions: int = 8
    max_single_position_pct: float = 15.0
    max_sector_concentration_pct: float = 45.0
    min_reward_risk: float = 2.0

    # ── SCHEDULE ─────────────────────────────────────────────────
    premarket_scan_time: str = "08:00"   # scan headlines, politician trades, SEC
    market_open_time: str = "09:30"
    trade_hours: int = 23                # run 23h, learn 1h
    learn_hour_start: str = "02:00"      # retrain brains 2-3 AM ET
    eod_review_time: str = "16:15"       # post-market journal

    # ── DATA FEEDS ───────────────────────────────────────────────
    watchlist: List[str] = field(default_factory=lambda: [
        "NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN", "AMD", "AVGO",
        "TSLA", "CRM", "ADBE", "LULU", "MRVL", "MU", "TSM", "NFLX",
    ])
    futures_watchlist: List[str] = field(default_factory=lambda: [
        "ES", "NQ", "MNQ", "VIX",
    ])
    short_watchlist: List[str] = field(default_factory=lambda: [
        "LULU", "CRM", "ADBE",
    ])

    def should_execute(self, signal: dict) -> dict:
        """Gate check: does this signal meet execution criteria?"""
        reasons = []
        go = True

        conf = signal.get("brain_confidence", 0)
        if conf < self.require_brain_confidence:
            reasons.append(f"brain confidence {conf:.2f} < {self.require_brain_confidence}")
            go = False

        grade = signal.get("mta_grade", "F")
        grade_order = {"A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "F": 1}
        if grade_order.get(grade, 0) < grade_order.get(self.require_confluence_grade, 0):
            reasons.append(f"MTA grade {grade} < {self.require_confluence_grade}")
            go = False

        if self.require_xgb_agree and not signal.get("xgb_agree", False):
            reasons.append("XGBoost disagrees")
            go = False

        rr = signal.get("reward_risk", 0)
        if rr < self.min_reward_risk:
            reasons.append(f"R:R {rr:.1f} < {self.min_reward_risk}")
            go = False

        positions = signal.get("current_positions", 0)
        if positions >= self.max_positions:
            reasons.append(f"at max positions ({self.max_positions})")
            go = False

        return {
            "execute": go and self.auto_execute,
            "reasons": reasons if not go else ["all gates passed"],
            "size_mult": signal.get("size_mult", 1.0),
        }

    def portfolio_health(self, positions: list) -> dict:
        """Check portfolio against diversification rules."""
        total_val = sum(p.get("market_value", 0) for p in positions)
        if total_val == 0:
            return {"healthy": True, "warnings": []}

        warnings = []
        sector_totals = {}
        for p in positions:
            sector = p.get("sector", "unknown")
            sector_totals[sector] = sector_totals.get(sector, 0) + p.get("market_value", 0)

        for sector, val in sector_totals.items():
            pct = (val / total_val) * 100
            if pct > self.max_sector_concentration_pct:
                warnings.append(f"{sector} concentration {pct:.0f}% > {self.max_sector_concentration_pct}%")

        for p in positions:
            pct = (p.get("market_value", 0) / total_val) * 100
            if pct > self.max_single_position_pct:
                warnings.append(f"{p.get('symbol','?')} is {pct:.0f}% of portfolio")

        return {"healthy": len(warnings) == 0, "warnings": warnings}

    def save(self, path: str = "jarvis_objective.json"):
        data = {
            "name": self.name,
            "tier": self.tier.value,
            "description": self.description,
            "auto_execute": self.auto_execute,
            "sector_targets": self.sector_targets,
            "alpha_sources": self.alpha_sources,
            "watchlist": self.watchlist,
            "short_watchlist": self.short_watchlist,
            "max_positions": self.max_positions,
            "require_confluence_grade": self.require_confluence_grade,
            "require_brain_confidence": self.require_brain_confidence,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str = "jarvis_objective.json"):
        if not os.path.exists(path):
            return cls()
        with open(path) as f:
            data = json.load(f)
        obj = cls()
        for k, v in data.items():
            if k == "tier":
                obj.tier = RiskTier(v)
            elif hasattr(obj, k):
                setattr(obj, k, v)
        return obj


OBJECTIVE = PortfolioObjective()
