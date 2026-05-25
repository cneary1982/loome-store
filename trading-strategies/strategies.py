"""Strategy registry — edit this file to enable / disable / add strategies.

The orchestrator imports `STRATEGIES` from this module on startup. To add a new
strategy: import its class and append an instance. To disable one without
deleting: comment it out, or toggle it from the dashboard at runtime.

Each strategy must have a unique `name`. The per-symbol lock means two
strategies pointing at the same `symbol` can't both be in a trade at once —
first signal wins, the second skips that bar.
"""
from orchestrator import RegimeBreakout

STRATEGIES = [
    # ── ETF live-trading lineup (Tradier-eligible) ────────────────────────
    # Tuned-on-futures parameters used as a starting point. Re-run the sweep
    # on SPY/QQQ/GLD bars before treating these as good — see README.

    RegimeBreakout(
        name="SPY_15m_breakout",
        symbol="SPY",
        timeframe="15m",
        lookback=48, threshold=0.015, atr_mult=2.5,
    ),

    RegimeBreakout(
        name="QQQ_15m_breakout",
        symbol="QQQ",
        timeframe="15m",
        lookback=48, threshold=0.015, atr_mult=2.5,
    ),

    RegimeBreakout(
        name="GLD_5m_breakout",
        symbol="GLD",
        timeframe="5m",
        lookback=48, threshold=0.015, atr_mult=2.5,
    ),

    # ── Add more strategies below ─────────────────────────────────────────
    # Example: an ORB-Fib90-VPA strategy (not implemented yet).
    # ORBFib90VPA(name='SPY_orb', symbol='SPY', timeframe='5m', ...),
]
