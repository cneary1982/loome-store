# PO3 — trading the 10:00 and 14:00 ET 4H candle opens

An implementation and backtest of the PO3 (Power of Three) entry model from
*The PO3 Bible*: **Accumulation → Manipulation → Distribution** on the 4-hour
candle that opens at 10:00 AM ET, with 14:00 ET as the conditional second
window.

- Engine: [`po3/`](po3/) — bias, gate, entry model, reporting
- Backtest CLI: [`po3_backtest.py`](po3_backtest.py)
- Parameter sweep: [`po3_sweep.py`](po3_sweep.py)
- TradingView strategy: [`pine/PO3_10_2.pine`](pine/PO3_10_2.pine)
- Pine validator: [`tools/pinecheck.py`](tools/pinecheck.py)
- Tests: [`tests/test_po3.py`](tests/test_po3.py)

```bash
pip install -r requirements.txt

python po3_backtest.py                       # all datasets, defaults
python po3_sweep.py --jobs 4                 # parameter grid, IS/OOS split
python tests/test_po3.py                     # 19 tests incl. a lookahead check
python tools/pinecheck.py pine/PO3_10_2.pine # lint the Pine strategy
```

---

## 1. What the model is

`OLHC` / `OHLC` describes how a candle actually delivers. A bullish 4H candle
usually prints its **low first** (the wick), then expands up to put in the rest
of the candle. That low is not noise — it is the manipulation leg, and it is
where the trade is set up.

The three phases, all read on the **1–5 minute** chart while the 4H candle is
forming:

| Phase | What it is | What it becomes on the 4H candle |
|---|---|---|
| 1. Accumulation | price coils after the 4H opens | the open |
| 2. Manipulation | a sweep *against* the daily bias, into a recent 15m FVG | the wick |
| 3. Distribution | the expansion you actually trade | the body |

The 15-minute chart is the timeframe that genuinely aligns with the 4H candle,
which is why the manipulation target is a recent **15m fair value gap** rather
than an arbitrary level.

**Why 10:00 and 14:00.** On CME's 18:00 ET session start, the 4H boundaries fall
at 18 / 22 / 02 / 06 / **10** / **14** ET. Those last two are the only 4H opens
inside the NY session, which is the whole reason the model is built around them.

---

## 2. Step by step, and where each step lives in the code

### Step 0 — Bias, before anything else

Bias is not one signal. It is a **stack of higher-timeframe confluences**, each
voting −1 / 0 / +1. If the stack doesn't reach the threshold, the day is a
**no-trade day**.

| Confluence (from the Bible) | Implementation | Code |
|---|---|---|
| Daily & weekly profiles (NY reversal vs NY continuation) | Asia range vs London: London distributing through one side only = continuation | `_precompute_profiles` |
| HTF PD arrays | nearest still-unmitigated 1h/4h FVG, and which side price sits on | `_pd_array` |
| HTF MMXM / structure — **HH & LL** | swing highs/lows on 1h + 4h: HH+HL = bullish, LH+LL = bearish | `_structure` |
| Daily OLHC | is today printing its low first (bullish) or its high first (bearish)? | `_daily_olhc` |
| ERL ⇄ IRL | premium/discount of the prior day's range, plus which liquidity pool is still unswept | `_erl_irl` |
| HTF CISD | has the last opposing leg been reclaimed on 1h/4h? | `_cisd` |

`bias_score = Σ weight × vote`. Long if `score ≥ min_score`, short if
`score ≤ −min_score`, otherwise **stand down**. Every weight and the threshold
are configurable — see [`po3/bias.py`](po3/bias.py).

### Step 1 — The 4H candle opens

At 10:00 ET (or 14:00) a new 4H candle opens. Its **opening price** is recorded;
it is one of the three entry confirmations later. Price accumulates on the 1m.
→ `po3_windows()` in [`po3/core.py`](po3/core.py), `Window.open_price`.

**News days.** If there is a red/orange folder release directly at 10:00, the
manipulation is immediate and the accumulation is visible *before* the candle
opens. Pass those dates as `PO3Config.news_dates` and the accumulation range is
read from `news_pre_open_minutes` before the open instead.

### Step 2 — A 15m FVG forms

After accumulating, a new 15-minute fair value gap prints. That gap is the pool
price should reach into. Only gaps that are **still unmitigated** and formed
within `fvg_lookback` bars count.
→ `FVGBook.live()`; gaps are admitted only once their third candle has closed.

### Step 3 — Manipulation into the gap

Price runs the accumulation extreme *against* the bias and taps the gap. That
extreme is the 4H wick, and it becomes the stop.

The extreme keeps extending until an entry actually confirms — so the stop sits
behind the wick's real low, not behind whichever bar first poked through.

### Step 4 — Entry: at least 2 of 3 confirmations

Read on the 1–5 minute chart (`min_confs`, default 2):

1. **IFVG** — a gap from the manipulation leg gets closed back through
2. **CISD** — the last opposing candle body gets closed through
3. **Open reclaim** — a close back above/below the 4H candle's opening price

Entry is at the **close of the confirming bar**.

### Step 5 — Target and stop

- **Target**: the previous day's high (long) or low (short) — the main draw on
  liquidity, the ERL the whole day is reaching for.
- **Stop**: just past the manipulation extreme (`stop_buf_atr × ATR`).
- If the draw is closer than `min_rr`, **the setup is skipped**, not shrunk.
  The Bible's rule is ≥ 1:2, so that is the default.

### Step 6 — Management

Optional, matching the Bible's money management: trim `trim_frac` (0.8) at
`trim_r` (2R), move the remainder to breakeven, let it run to target. Anything
still open at the end of the 4H window is closed.

---

## 3. Gating 10:00 vs 14:00

> "Usually 10 is the best and the 2 is weak unless it's a big day."

Both windows go through [`po3/gate.py`](po3/gate.py), which is the PO3 analogue
of the ORB day gate — same shape, retuned thresholds.

**10:00 (primary)** — light gate. Trades unless:
- a calendar block fires (Mondays if enabled; CPI/FOMC dates and the day before,
  via `--blackout`)
- the overnight session already ran more than `am_max_on_range_atr` × ATR
- the gap from the prior close exceeds `am_max_gap_atr` × ATR

**14:00 (conditional)** — stays locked unless:
- the 09:30→14:00 range has already expanded past `pm_big_day_range_atr` × ATR
  — the "big day" test, and it is only knowable at 14:00, never earlier; **and**
- the 10:00 window did not already produce a trade (`pm_only_if_am_flat`)

That gives both behaviours asked for: 14:00 is a genuine fallback when 10:00
produced nothing, and it only unlocks on days with enough range to be worth it.
`max_trades_per_day` (default 1) enforces the Bible's one-trade-a-day rule.

> **Note on the ORB gate.** The ORB 7.7/7.8 gating script is not in this repo,
> so this is a reimplementation of that gate's *shape* rather than a port of its
> exact thresholds. `GateConfig` is the single place to retune it. If you drop
> the real ORB gate in, the swap point is `DayGate.check()`.

---

## 4. Correctness

Backtests of an intrabar model are easy to get wrong, so the guarantees are
tested rather than asserted:

- **No lookahead.** `test_no_lookahead_under_truncation` re-runs the backtest on
  data truncated mid-history and requires every already-completed trade to come
  back bit-identical. It does.
- **Closed bars only.** HTF series are resampled once for speed, so a bar counts
  as visible only when `bar_open + timeframe ≤ now`. Swings inherit this through
  their confirming bar. FVGs are admitted only after their third candle closes.
- **Conservative fills.** Entry at the confirming bar's close. When a bar
  straddles both stop and target, the **stop** is taken.
- **Costs are charged.** `cost_per_side` is deducted on entry and exit. This
  matters: R-multiples flatter tight stops, and that is exactly where spread and
  slippage hurt most.

---

## 5. Data, and an honest limitation

| Dataset | Bars per 10:00 window | Asia/London coverage |
|---|---|---|
| `data/etf/{SPY,QQQ,GLD}_5m_2yr.csv` | 48 | **no** — 07:00–19:00 ET only |
| `data/ES_15m.csv` | 16 | yes — full 24h |

There is a genuine trade-off in what is on disk:

- The **5m ETF proxies** have the resolution the model needs (accumulation, a
  sweep, and three confirmations all inside one 4H window) but no overnight
  data — so the Asia/London **profile confluence always votes 0** on them, and
  the overnight-range gate sees only pre-market.
- **ES 15m** has full session coverage so every confluence works, but 16 bars per
  window is coarse for an entry model built on the 1–5 minute chart.

`NQ_15m.csv` and `GC_15m.csv` are raw Barchart exports (newest-first, footer
row, Central time); `load_bars` handles that schema, but they carry only a few
months of history, so they are not in the default set.

**The fix is data, not code**: 1m futures bars for MNQ/NQ would let the model run
at its intended resolution with every confluence live. The engine already reads
any bar size — point `--data` at it.

---

## 6. Backtest results

Command that produces the table below:

```bash
python po3_sweep.py --jobs 4 --out results/po3_sweep.csv
```

Every config is scored on the first 60% of the span **and** on the held-out last
40%, and the sweep's headline ranking is *cross-instrument robustness* — how
many instruments a config is positive on out-of-sample — not the single best
number, which is almost always fitted.

**The model has a real but modest edge, and only in its strict form.**

```bash
python po3_backtest.py --preset robust
```

bias ≥ 2 confluences · **all three** confirmations · 15m FVG tap required ·
10:00 window · stop behind the manipulation wick:

| | |
|---|---|
| Trades (4 instruments, 2 yrs) | 107 |
| Win rate | 56.1% |
| Total / average | **+11.29 R** / **+0.105 R** per trade |
| Profit factor | 1.41 |
| Max drawdown | −4.48 R |
| In-sample / out-of-sample | +6.68 R / +4.61 R |
| Positive out-of-sample | **4 of 4 instruments** |

The three results that matter most:

1. **Confirmations are the edge.** Pooled across the grid: 1-of-3 → −239.6 R,
   2-of-3 → +42.6 R, 3-of-3 → **+449.8 R**. Every config that held up
   out-of-sample on all four instruments requires all three. The Bible says
   "at least 2"; the data says the third is not optional.
2. **The 14:00 window is a marginal positive** (+0.58 R vs 0.00 R mean, helps in
   44% of paired configs) — and only because the gate already restricts it to
   expanded days where 10:00 didn't fire. Ungated it loses.
3. **It is a hold-to-the-close model.** 85 of 107 trades exit at the 4H close
   (+29.8 R); the 3R target fires once. The wick stop is what defines the risk.

Full read-out, including what *didn't* work and the caveats:
**[`results/po3_findings.md`](results/po3_findings.md)**. Full grid:
[`results/po3_sweep.csv`](results/po3_sweep.csv).

`--preset bible` (the default) runs the model exactly as written — at least 2
confirmations, previous day's high/low as the draw. That version trades far less
and is not profitable on this data; §3 of the findings explains why the strict
entry and the strict target can't both be satisfied.

---

## 7. Risk rules from the Bible

Encoded where the engine can enforce them, documented where it can't:

| Rule | Status |
|---|---|
| One trade per day | `max_trades_per_day = 1` |
| ≥ 1:2 risk/reward | `min_rr = 2.0`; setups below it are skipped |
| Trim 80% at 2R, rest to breakeven | `trim_frac = 0.8`, `trim_r = 2.0` |
| Never trim before 1R | enforced by `trim_r ≥ 1` |
| Don't trade Mondays | `--skip-dows 0` |
| Don't trade the day before CPI/FOMC | `--blackout news_dates.txt` (blocks the listed date *and* the session before) |
| No setup → no trade | that is what the `no_bias` / `no_confirmation` skips are |
| 0.5% risk per trade above starting balance, 0.25% below | position sizing, outside this engine — see [`RISK.md`](RISK.md) |

---

## 8. The Pine strategy

[`pine/PO3_10_2.pine`](pine/PO3_10_2.pine) is the TradingView version: same
bias stack, same gate, same three confirmations, with a live bias-readout table.

Run the linter before pasting it in:

```bash
python tools/pinecheck.py pine/PO3_10_2.pine
```

`pinecheck` is not a published package — it is implemented here
([`tools/pinecheck.py`](tools/pinecheck.py)) and checks v6 syntax (version
pragma, bracket/string balance, v5 builtins used without their namespace, and
Pine's continuation-line indent rule) plus the automation-stack rules: bracket
exits, a `strategy.opentrades == 0` guard, commission/slippage set, alert
payloads carrying `action`/`sentiment`/`quantity`, and a forced flat.

**Before going live:**
- Strategy settings → *Recalculate on bar close* **ON**, *on every tick* **OFF**
- TradersPost → *Allow Add to Position* **OFF**
- Chart timeframe 1m–5m; the model needs intrabar resolution
- The Pine `profile` confluence needs a 24h feed (futures). On an RTH-only
  symbol it votes 0, exactly as the Python engine does.
