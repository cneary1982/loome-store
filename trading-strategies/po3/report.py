"""Performance metrics for a list of PO3 trades.

R-multiples throughout: one unit of risk is the distance from entry to the stop
behind the manipulation wick. That keeps results comparable across instruments
and across the 0.5%/0.25% position sizing the Bible prescribes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .strategy import Skip, Trade


def trades_frame(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(
            columns=[
                "ny_date", "hour", "side", "bias_score", "entry_ts", "entry",
                "stop", "target", "exit_ts", "exit", "r", "outcome", "confs",
                "big_day",
            ]
        )
    rows = []
    for t in trades:
        rows.append(
            {
                "ny_date": t.ny_date,
                "hour": t.hour,
                "side": t.side,
                "bias_score": t.bias_score,
                "entry_ts": t.entry_ts,
                "entry": t.entry,
                "stop": t.stop,
                "target": t.target,
                "exit_ts": t.exit_ts,
                "exit": t.exit,
                "r": t.r,
                "outcome": t.outcome,
                "confs": "+".join(t.confs),
                "big_day": t.big_day,
                "rr": t.detail.get("rr", np.nan),
            }
        )
    return pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)


def skips_frame(skips: list[Skip]) -> pd.DataFrame:
    if not skips:
        return pd.DataFrame(columns=["ny_date", "hour", "reason", "bias_score"])
    return pd.DataFrame(
        [{"ny_date": s.ny_date, "hour": s.hour, "reason": s.reason,
          "bias_score": s.bias_score} for s in skips]
    )


def _max_drawdown_r(r: pd.Series) -> float:
    if r.empty:
        return 0.0
    eq = r.cumsum()
    return float((eq - eq.cummax()).min())


def _max_consec(mask: pd.Series) -> int:
    best = run = 0
    for v in mask:
        run = run + 1 if v else 0
        best = max(best, run)
    return best


def summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"trades": 0}

    r = df["r"]
    wins = r > 0
    gross_win = float(r[r > 0].sum())
    gross_loss = float(-r[r < 0].sum())

    return {
        "trades": int(len(df)),
        "win_rate": round(float(wins.mean()) * 100, 1),
        "total_R": round(float(r.sum()), 2),
        "avg_R": round(float(r.mean()), 3),
        "median_R": round(float(r.median()), 3),
        "best_R": round(float(r.max()), 2),
        "worst_R": round(float(r.min()), 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else np.inf,
        "max_dd_R": round(_max_drawdown_r(r), 2),
        "max_consec_losses": _max_consec(~wins),
        "expectancy_R": round(float(r.mean()), 3),
    }


def by_group(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(col)["r"]
    out = pd.DataFrame(
        {
            "trades": g.size(),
            "win_rate": (df.groupby(col)["r"].apply(lambda s: (s > 0).mean()) * 100).round(1),
            "total_R": g.sum().round(2),
            "avg_R": g.mean().round(3),
        }
    )
    return out.sort_values("total_R", ascending=False)


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Month-by-month table.

    The Bible's yardstick is the month, not the day or the week — so this is the
    table to read first.
    """
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["month"] = pd.to_datetime(d["ny_date"]).dt.to_period("M").astype(str)
    g = d.groupby("month")["r"]
    out = pd.DataFrame(
        {
            "trades": g.size(),
            "win_rate": (d.groupby("month")["r"].apply(lambda s: (s > 0).mean()) * 100).round(1),
            "total_R": g.sum().round(2),
        }
    )
    out["cum_R"] = out["total_R"].cumsum().round(2)
    return out


def format_report(df: pd.DataFrame, skips: pd.DataFrame, title: str) -> str:
    lines = [f"\n{'=' * 68}", f"  {title}", "=" * 68]

    s = summarize(df)
    if s["trades"] == 0:
        lines.append("  no trades")
    else:
        lines.append(
            f"  trades {s['trades']:>4}   win% {s['win_rate']:>5}   "
            f"total R {s['total_R']:>8}   avg R {s['avg_R']:>7}"
        )
        lines.append(
            f"  PF {s['profit_factor']:>7}   maxDD(R) {s['max_dd_R']:>7}   "
            f"max consec losses {s['max_consec_losses']:>3}"
        )
        lines.append(
            f"  best {s['best_R']:>6} R   worst {s['worst_R']:>6} R   "
            f"median {s['median_R']:>6} R"
        )

        for col, label in (("hour", "window (ET hour)"), ("side", "side"),
                           ("outcome", "outcome"), ("confs", "confirmations")):
            t = by_group(df, col)
            if not t.empty:
                lines.append(f"\n  ── by {label} ──")
                lines.append("    " + t.to_string().replace("\n", "\n    "))

        m = monthly(df)
        if not m.empty:
            lines.append("\n  ── by month ──")
            lines.append("    " + m.to_string().replace("\n", "\n    "))

    if not skips.empty:
        lines.append("\n  ── why setups were skipped ──")
        c = skips["reason"].value_counts()
        lines.append("    " + c.to_string().replace("\n", "\n    "))

    return "\n".join(lines)
