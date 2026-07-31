"""Wires bias + gate + entry model together over a whole price series."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import pandas as pd

from .bias import BiasConfig, BiasEngine
from .core import po3_windows
from .gate import DayGate, GateConfig
from .strategy import PO3Config, PO3Model, Skip, Trade


@dataclass
class RunConfig:
    bias: BiasConfig = field(default_factory=BiasConfig)
    gate: GateConfig = field(default_factory=GateConfig)
    po3: PO3Config = field(default_factory=PO3Config)
    # 14:00 windows are cut at 16:00 ET so nothing is held through the equity
    # close; set to 18*60 for a 24h futures run.
    flat_minute: dict[int, int] = field(
        default_factory=lambda: {10: 14 * 60, 14: 16 * 60}
    )


class PO3Session:
    """Precomputed state for one instrument, reusable across many configs.

    The expensive parts — HTF resamples, swing tables, FVG books, per-day gate
    statistics and the raw bias score at every window open — depend only on the
    *structural* settings (timeframes, ATR length, swing widths). Thresholds like
    `min_score`, `min_confs` or the big-day cutoff are applied per run, so a
    sweep builds this once and then evaluates hundreds of configs against it.
    """

    def __init__(
        self,
        bars: pd.DataFrame,
        bias_cfg: BiasConfig | None = None,
        gate_cfg: GateConfig | None = None,
        po3_cfg: PO3Config | None = None,
        flat_minute: dict[int, int] | None = None,
    ):
        self.bars = bars
        self.bias_cfg = bias_cfg or BiasConfig()
        self.gate_cfg = gate_cfg or GateConfig()
        self.po3_cfg = po3_cfg or PO3Config()
        self.flat_minute = flat_minute or {10: 14 * 60, 14: 16 * 60}

        # Build every hour we might ever want; the gate filters per run.
        self.windows = po3_windows(bars, (10, 14), self.flat_minute)
        self.gate = DayGate(bars, self.gate_cfg)
        self.bias = BiasEngine(bars, self.bias_cfg)
        self.model = PO3Model(bars, self.po3_cfg)

        reads = {w.open_ts: self.bias.at(w.open_ts) for w in self.windows}
        self.scores = {ts: r.score for ts, r in reads.items()}
        self.components = {ts: r.components for ts, r in reads.items()}

    def run(self, cfg: RunConfig):
        """Evaluate one config. Returns (trades, skips)."""
        gate = self.gate.rebind(cfg.gate)
        model = self.model.rebind(cfg.po3)
        min_score = cfg.bias.min_score

        trades: list[Trade] = []
        skips: list[Skip] = []
        day_trades: dict[object, int] = {}

        for w in self.windows:
            if w.hour not in cfg.gate.trade_hours:
                continue

            n_today = day_trades.get(w.ny_date, 0)
            if n_today >= cfg.gate.max_trades_per_day:
                skips.append(Skip(w.ny_date, w.hour, "daily_trade_cap"))
                continue

            g = gate.check(w.ny_date, w.hour, am_traded=n_today > 0)
            if not g.allow:
                skips.append(Skip(w.ny_date, w.hour, g.reason))
                continue

            score = self.scores.get(w.open_ts, 0.0)
            bias = 1 if score >= min_score else (-1 if score <= -min_score else 0)

            res = model.run_window(w, bias, score, g.big_day)
            if isinstance(res, Trade):
                trades.append(res)
                day_trades[w.ny_date] = n_today + 1
            else:
                skips.append(res)

        return trades, skips


def run_backtest(bars: pd.DataFrame, cfg: RunConfig | None = None):
    """Walk every 10:00 / 14:00 window in `bars`. Returns (trades, skips).

    The two windows on a day are processed in clock order so the 14:00 gate can
    see whether 10:00 already fired.
    """
    cfg = cfg or RunConfig()
    session = PO3Session(bars, cfg.bias, cfg.gate, cfg.po3, cfg.flat_minute)
    return session.run(cfg)
