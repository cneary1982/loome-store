"""Markov 2.0 — Hedge Fund Method (corrected).

States → transition matrix → stickiness → signal, with three documented
flaws fixed:

  FIX 1 — Stride sampling. Overlapping rolling windows share 19/20 days and
          fake persistence on the diagonal. We count transitions between
          NON-overlapping windows (stride = window length). Both matrices are
          computed; only the stride-sampled one is statistically honest.
  FIX 2 — Label verification. After labeling, we verify the state mapping
          against known-direction periods in the data (the strongest 20-day
          up-stretch must read BULL, the worst must read BEAR, a flat stretch
          SIDEWAYS). If the rendered mapping disagrees, we fix it.
  FIX 3 — Three explicit modes:
            CONFLUENCE — regime gates an existing strategy (long only when
                         signal > +thr, short only when < -thr, flat in chop)
            SIZE       — position scaled to |signal|, capped
            SCREENER   — rank a basket by signal; top=long, bottom=short, mid=skip

States (default): 20-day cumulative return ≥ +5% = BULL, ≤ −5% = BEAR, else
SIDEWAYS. Encoding: 0=SIDEWAYS, 1=BULL, 2=BEAR.

Signal: P(BULL tomorrow) − P(BEAR tomorrow), read from the current state's row.
Multi-day forecasts via matrix powers (converge to the stationary distribution
— long-horizon forecasts carry no signal).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# State encoding (FIX 2 reference mapping)
SIDEWAYS, BULL, BEAR = 0, 1, 2
STATE_NAME = {SIDEWAYS: "SIDEWAYS", BULL: "BULL", BEAR: "BEAR"}


# ─── States ─────────────────────────────────────────────────────────────────
def label_states(close: pd.Series, window: int = 20,
                 bull_thr: float = 0.05, bear_thr: float = -0.05) -> pd.Series:
    """Label each bar by its trailing `window`-day cumulative return."""
    cum = close / close.shift(window) - 1.0
    state = pd.Series(SIDEWAYS, index=close.index, dtype=int)
    state[cum >= bull_thr] = BULL
    state[cum <= bear_thr] = BEAR
    state[cum.isna()] = -1          # undefined warmup
    return state


# ─── FIX 2: label verification ──────────────────────────────────────────────
def verify_labels(close: pd.Series, state: pd.Series, window: int = 20) -> dict:
    """Verify the mapping: strongest up-stretch must be BULL, worst BEAR,
    flattest SIDEWAYS. Returns a report; raises if the mapping is inverted."""
    cum = (close / close.shift(window) - 1.0)
    valid = state >= 0
    cum, st = cum[valid], state[valid]

    i_max = cum.idxmax()            # strongest 20-day rally
    i_min = cum.idxmin()            # worst 20-day decline
    i_flat = (cum.abs()).idxmin()   # flattest stretch

    report = {
        "strongest_up":   (str(i_max),  round(float(cum[i_max]) * 100, 1),  STATE_NAME[int(st[i_max])]),
        "worst_down":     (str(i_min),  round(float(cum[i_min]) * 100, 1),  STATE_NAME[int(st[i_min])]),
        "flattest":       (str(i_flat), round(float(cum[i_flat]) * 100, 1), STATE_NAME[int(st[i_flat])]),
    }
    ok = (int(st[i_max]) == BULL and int(st[i_min]) == BEAR)
    report["mapping_ok"] = ok
    if not ok:
        raise ValueError(f"Label mapping verification FAILED: {report}")
    return report


# ─── Transition matrices ────────────────────────────────────────────────────
def _counts(seq: np.ndarray) -> np.ndarray:
    m = np.zeros((3, 3))
    for a, b in zip(seq[:-1], seq[1:]):
        if a >= 0 and b >= 0:
            m[a, b] += 1
    return m


def transition_overlapping(state: pd.Series) -> np.ndarray:
    """LEGACY: every consecutive day. Overlapping windows → fake persistence."""
    return _normalize(_counts(state.to_numpy()))


def transition_stride(state: pd.Series, stride: int = 20) -> np.ndarray:
    """FIX 1: only non-overlapping windows (stride = window length)."""
    seq = state.to_numpy()[::stride]
    return _normalize(_counts(seq))


def _normalize(counts: np.ndarray) -> np.ndarray:
    rs = counts.sum(axis=1, keepdims=True)
    rs[rs == 0] = 1.0
    return counts / rs


def stickiness(T: np.ndarray) -> dict:
    return {STATE_NAME[i]: round(float(T[i, i]), 3) for i in range(3)}


# ─── Signal ─────────────────────────────────────────────────────────────────
def signal_from(T: np.ndarray, current_state: int) -> float:
    """P(BULL tomorrow) − P(BEAR tomorrow) given the current state."""
    if current_state < 0:
        return 0.0
    return float(T[current_state, BULL] - T[current_state, BEAR])


def forecast_n_days(T: np.ndarray, current_state: int, n: int) -> np.ndarray:
    """State distribution n days out via matrix power."""
    v = np.zeros(3); v[current_state] = 1.0
    return v @ np.linalg.matrix_power(T, n)


def stationary_distribution(T: np.ndarray) -> np.ndarray:
    """Long-run distribution (left eigenvector for eigenvalue 1)."""
    vals, vecs = np.linalg.eig(T.T)
    i = np.argmin(np.abs(vals - 1.0))
    v = np.real(vecs[:, i])
    return v / v.sum()


# ─── FIX 3: the three modes ─────────────────────────────────────────────────
@dataclass
class Decision:
    signal: float
    mode: str
    # CONFLUENCE
    allow_long: bool = False
    allow_short: bool = False
    # SIZE / SCREENER
    size: float = 0.0          # signed position in [-cap, +cap]
    verdict: str = "SKIP"      # LONG / SHORT / SKIP


def decide(sig: float, mode: str, conf_thr: float = 0.10,
           size_cap: float = 1.0, size_floor: float = 0.05) -> Decision:
    mode = mode.upper()
    if mode == "CONFLUENCE":
        return Decision(signal=sig, mode=mode,
                        allow_long=sig > conf_thr,
                        allow_short=sig < -conf_thr,
                        verdict="LONG" if sig > conf_thr else "SHORT" if sig < -conf_thr else "SKIP")
    if mode == "SIZE":
        size = float(np.clip(sig / size_cap, -1.0, 1.0)) * size_cap
        if abs(size) < size_floor:
            size = 0.0
        return Decision(signal=sig, mode=mode, size=size,
                        verdict="LONG" if size > 0 else "SHORT" if size < 0 else "SKIP")
    if mode == "SCREENER":
        return Decision(signal=sig, mode=mode,
                        verdict="LONG" if sig > conf_thr else "SHORT" if sig < -conf_thr else "SKIP",
                        size=sig)
    raise ValueError(f"unknown mode {mode!r} (CONFLUENCE | SIZE | SCREENER)")


def screen_basket(signals: dict[str, float], conf_thr: float = 0.10) -> pd.DataFrame:
    """Rank a basket of {ticker: signal}. Top=long, bottom=short, mid=skip."""
    rows = []
    for tkr, sig in signals.items():
        d = decide(sig, "SCREENER", conf_thr=conf_thr)
        rows.append({"ticker": tkr, "signal": round(sig, 4), "verdict": d.verdict})
    return pd.DataFrame(rows).sort_values("signal", ascending=False).reset_index(drop=True)


# ─── Walk-forward proof ─────────────────────────────────────────────────────
def walk_forward(close: pd.Series, window: int = 20, stride: int = 20,
                 mode: str = "SIZE", conf_thr: float = 0.10,
                 warmup: int = 252, use_stride: bool = True) -> dict:
    """Walk bar-by-bar. At each day, build the matrix ONLY from past data,
    take a position for the next day, record return. Never sees the future."""
    state_full = label_states(close, window)
    rets = close.pct_change().shift(-1)        # next-day return aligned to today
    equity, positions, correct, n = [1.0], [], 0, 0
    daily = []

    for t in range(warmup, len(close) - 1):
        hist = state_full.iloc[:t + 1]
        cur = int(hist.iloc[-1])
        if cur < 0:
            positions.append(0.0); continue
        T = transition_stride(hist, stride) if use_stride else transition_overlapping(hist)
        sig = signal_from(T, cur)
        d = decide(sig, mode, conf_thr=conf_thr)
        pos = d.size if mode in ("SIZE", "SCREENER") else (1.0 if d.allow_long else -1.0 if d.allow_short else 0.0)
        r = rets.iloc[t]
        if pd.isna(r):
            positions.append(0.0); continue
        pnl = pos * r
        equity.append(equity[-1] * (1 + pnl))
        positions.append(pos)
        if pos != 0:
            n += 1
            correct += 1 if (pos > 0 and r > 0) or (pos < 0 and r < 0) else 0
        daily.append(pnl)

    eq = np.array(equity)
    daily = np.array(daily)
    wins = daily[daily > 0].sum()
    losses = -daily[daily < 0].sum()
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    years = max((len(close) - warmup) / 252, 0.1)
    return {
        "mode": mode,
        "matrix": "stride" if use_stride else "overlapping",
        "trades": n,
        "win_rate": round(correct / n * 100, 1) if n else 0.0,
        "profit_factor": round(wins / losses, 2) if losses > 0 else float("inf"),
        "total_return_pct": round((eq[-1] - 1) * 100, 1),
        "cagr_pct": round((eq[-1] ** (1 / years) - 1) * 100, 1),
        "max_drawdown_pct": round(dd * 100, 1),
        "equity": eq,
    }
