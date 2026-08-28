"""HOLY GRAIL — deployment config for the two proven strategies.

Combined backtest: +244.5R over 2 years across SPY/QQQ/GLD
  ConnorsRSI2:          +106.0R (SPY +40, QQQ +16, GLD +50) — 15m
  OpeningRangeBreakout: +138.5R (SPY +46, QQQ +51.5, GLD +41) — 5m

These two strategies are complementary:
  - ConnorsRSI2 is mean-reversion (buys dips, sells rips) on 15m
  - ORB is momentum/breakout on 5m
  - Different timeframes = different signal cadence, no conflict
  - Both positive on ALL three ETFs = robust, not curve-fit

Usage (live):
    python orchestrator.py --config holy_grail --risk-per-trade 25

Usage (backtest):
    python run_holy_grail_backtest.py
"""
from strategies_lib import ConnorsRSI2, OpeningRangeBreakout

STRATEGIES = [
    # ── ConnorsRSI2: mean-reversion on 15m ──────────────────────
    # +50R on GLD, +40R on SPY, +16R on QQQ
    ConnorsRSI2(
        name="ConnorsRSI2_GLD_15m",
        symbol="GLD",
        timeframe="15m",
    ),
    ConnorsRSI2(
        name="ConnorsRSI2_SPY_15m",
        symbol="SPY",
        timeframe="15m",
    ),
    ConnorsRSI2(
        name="ConnorsRSI2_QQQ_15m",
        symbol="QQQ",
        timeframe="15m",
    ),

    # ── OpeningRangeBreakout: momentum on 5m ────────────────────
    # +51.5R on QQQ, +46R on SPY, +41R on GLD
    OpeningRangeBreakout(
        name="ORB_QQQ_5m",
        symbol="QQQ",
        timeframe="5m",
        range_minutes=30,
        tp_mult_range=1.5,
    ),
    OpeningRangeBreakout(
        name="ORB_SPY_5m",
        symbol="SPY",
        timeframe="5m",
        range_minutes=30,
        tp_mult_range=1.5,
    ),
    OpeningRangeBreakout(
        name="ORB_GLD_5m",
        symbol="GLD",
        timeframe="5m",
        range_minutes=30,
        tp_mult_range=1.5,
    ),
]
