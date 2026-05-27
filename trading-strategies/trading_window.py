"""Global trading-window gate.

All strategies are filtered through these checks before their signal is
allowed to fire. This standardizes execution policy across the 15+
registered strategies so each one doesn't have to re-implement it.

Policy (Apr 2025+):
  • Entries allowed 9:30 ET → 13:00 ET on weekdays only
  • All positions force-closed at 16:00 ET (orchestrator does this)
"""
from __future__ import annotations

import pandas as pd

ENTRY_START_NY = 9.5    # 9:30 ET
ENTRY_END_NY   = 13.0   # 13:00 ET
EOD_FLAT_NY    = 16.0   # 16:00 ET — orchestrator force-closes positions


def in_entry_window(ts: pd.Timestamp) -> bool:
    """True if ts (UTC tz-aware) falls inside the global entry window."""
    ny = ts.tz_convert("America/New_York")
    if ny.weekday() >= 5:
        return False
    td = ny.hour + ny.minute / 60.0
    return ENTRY_START_NY <= td < ENTRY_END_NY


def is_eod_flat(ts: pd.Timestamp) -> bool:
    """True if ts is at or after 16:00 ET — force-flat any open positions."""
    ny = ts.tz_convert("America/New_York")
    if ny.weekday() >= 5:
        return True
    td = ny.hour + ny.minute / 60.0
    return td >= EOD_FLAT_NY
