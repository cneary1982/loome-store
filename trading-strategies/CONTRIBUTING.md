# Contributing

This project lives or dies by whether new ideas actually move the **total R** numbers in [`results/best_per_cell_by_total_R.csv`](results/best_per_cell_by_total_R.csv). If your change improves any of those numbers without regressing the others, send a PR.

## How CI works

Every push and pull request triggers `.github/workflows/sweep.yml`, which:

1. Runs `python backtest.py` as a smoke test.
2. Runs the full sweep: `python sweep_all.py --no-glossary` (about 50 seconds).
3. Uploads the refreshed `results/sweep_all.csv` and `results/best_per_cell_by_total_R.csv` as a downloadable artifact.
4. Posts the winners table in the job summary.

You don't need to commit refreshed CSVs in your PR — CI will produce them. But it's helpful to commit the refresh on a PR that adds a new feature so the diff shows the impact in `git`.

## Local workflow

```bash
git clone https://github.com/<your-fork>/trading-strategies.git
cd trading-strategies
pip install -r requirements.txt

# Make your change, then:
python backtest.py            # quick sanity check
python sweep_all.py           # full sweep, refreshes results/*.csv

git add -A
git commit -m "Add <thing> and refresh sweep"
git push
```

## Three concrete recipes

### A. Add a new session window

Open `sweep_all.py` and find `SESSION_PRESETS`. Add an entry:

```python
SESSION_PRESETS: dict = {
    # ... existing entries ...
    "fomc_only": [(NY_MIN(13, 30), NY_MIN(15, 30))],   # 13:30-15:30 ET (FOMC release window)
}
```

Add a friendly label so the CSV is self-documenting:

```python
SESSION_LABELS: dict = {
    # ... existing entries ...
    "fomc_only": "FOMC release window only: 13:30-15:30 ET",
}
```

Wire it into the symbols you want to test it on by adding the name to `SESSION_VARIANTS`:

```python
("GC", "1h"):  ["all_hours", "gold_3_sessions", ..., "fomc_only"],
```

Run `python sweep_all.py` and inspect `results/best_per_cell_by_total_R.csv` — if `fomc_only` wins any cell, you're done.

### B. Add a new filter axis (e.g. volume confirmation)

1. Add the gate function to `filters.py`:

   ```python
   def volume_ok(bar_volume: float, median_recent_volume: float, mult: float = 1.5) -> bool:
       """Require the breakout bar's volume to exceed `mult` × the recent median."""
       return bar_volume >= mult * median_recent_volume
   ```

2. Plumb it into `backtest()` in `backtest.py` — accept an extra `volume_ok` callable, call it before the entry check.

3. In `sweep_all.py`, add the new axis to the `itertools.product` call and pass the multiplier into `make_callables`.

4. Update `COLUMN_GLOSSARY`, the row dict in `main()`, and `SESSION_LABELS`-style labels if needed.

Run `python sweep_all.py`. If it improves a cell's total R, ship it.

### C. Tune existing parameters

You don't even need new code for this. Edit the grid lists at the top of `sweep_all.py`:

```python
LOOKBACKS  = [12, 20, 32, 48]                              # try wider: [8, 12, 20, 32, 48, 72]
THRESHOLDS = [0.010, 0.015, 0.020, 0.025, 0.030]           # try finer: every 0.0025
ATR_MULTS  = [2.0, 2.5, 3.0, 3.5]                          # try smaller: [1.0, 1.5, 2.0, 2.5]
```

The sweep finishes in under a minute for most grid sizes — feel free to throw 10,000 configs at it.

## What I'm looking for in PRs

- **Better total R** in `results/best_per_cell_by_total_R.csv`, ideally across multiple cells.
- A short note in the PR description explaining the idea and what changed.
- Refreshed CSVs committed (optional but appreciated).
- No regressions on cells your change doesn't target — if you optimize for GC, make sure ES/NQ didn't get worse.

## What I'm not looking for

- Look-ahead bias. If your filter peeks at future data, it's not a real edge. Higher-timeframe series in `filters.py` are explicitly shifted by 1 bar for this reason — any new HTF feature must do the same.
- Curve-fitting to a single cell. If a config only wins one cell by a tiny margin and adds 10 parameters, it probably won't generalize.
- Strategies that only work without commissions/slippage. The current backtest is gross-of-cost; if your edge is +0.05 R, it might disappear after fees.

If you're not sure whether an idea is worth building, open an issue first and we'll discuss.
