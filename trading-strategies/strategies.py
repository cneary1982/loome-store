"""Strategy registry — edit this file to enable / disable / add strategies.

The orchestrator imports `STRATEGIES` from this module on startup. On each
tick every enabled strategy is asked for a signal; the per-symbol lock means
two strategies on the same `symbol` can't both be in a trade at once —
first signal wins, the second skips that bar.

Currently registered (9 strategies — growing toward 20):
  • RegimeBreakout  ×3   (SPY/QQQ/GLD)  — Markov regime, ATR exit
  • MACDTrendStack  ×3   (S11 port)
  • BBSqueeze       ×2   (T6 port)
  • FiveBarPullback ×1   (T5 port)
  • BigJohnson      ×2   (S08 port)
  • InverseFVG      ×2   (S09 port)
  • ICTFVGSessionTap×2   (S10 port — 2 different session windows)

To disable one without deleting: comment it out, or toggle from the dashboard
at runtime. To add a new one: import its class and append an instance.
"""
from orchestrator import RegimeBreakout
from strategies_lib import (
    BigJohnson, InverseFVG, ICTFVGSessionTap, MACDTrendStack,
    FiveBarPullback, BBSqueeze,
)

STRATEGIES = [
    # ── Regime breakout (original) ────────────────────────────────────────
    RegimeBreakout(name="SPY_15m_breakout", symbol="SPY", timeframe="15m",
                   lookback=48, threshold=0.015, atr_mult=2.5),
    RegimeBreakout(name="QQQ_15m_breakout", symbol="QQQ", timeframe="15m",
                   lookback=48, threshold=0.015, atr_mult=2.5),
    RegimeBreakout(name="GLD_5m_breakout",  symbol="GLD", timeframe="5m",
                   lookback=48, threshold=0.015, atr_mult=2.5),

    # ── S11 MACD × 200 SMA Rivit ──────────────────────────────────────────
    MACDTrendStack(name="QQQ_1h_macd200",  symbol="QQQ", timeframe="1h"),
    MACDTrendStack(name="GLD_4h_macd200",  symbol="GLD", timeframe="4h"),
    MACDTrendStack(name="SPY_1d_macd200",  symbol="SPY", timeframe="1d"),

    # ── T6 BB Squeeze + EMA50 ─────────────────────────────────────────────
    BBSqueeze(name="QQQ_1h_bbsqueeze",  symbol="QQQ", timeframe="1h"),
    BBSqueeze(name="SPY_1h_bbsqueeze",  symbol="SPY", timeframe="1h"),

    # ── T5 5-Bar Trend Pullback ───────────────────────────────────────────
    FiveBarPullback(name="QQQ_15m_5bar_pb", symbol="QQQ", timeframe="15m"),

    # ── S08 Big Johnson 4.0 ───────────────────────────────────────────────
    BigJohnson(name="GLD_5m_bj4",  symbol="GLD", timeframe="5m", sessions=("ny",)),
    BigJohnson(name="QQQ_5m_bj4",  symbol="QQQ", timeframe="5m", sessions=("ny",)),

    # ── S09 IFVG Inverse FVG ──────────────────────────────────────────────
    InverseFVG(name="GLD_5m_ifvg", symbol="GLD", timeframe="5m"),
    InverseFVG(name="QQQ_5m_ifvg", symbol="QQQ", timeframe="5m"),

    # ── S10 ICT FVG Session Tap ───────────────────────────────────────────
    ICTFVGSessionTap(name="QQQ_5m_ictfvg_ny",
                     symbol="QQQ", timeframe="5m",
                     session_start_h=9.5, session_end_h=11.5, htf="60"),
    ICTFVGSessionTap(name="GLD_5m_ictfvg_london",
                     symbol="GLD", timeframe="5m",
                     session_start_h=2.0, session_end_h=5.0, htf="240"),
]
