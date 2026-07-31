# PO3 backtest findings

What the grid actually says about the 10:00 / 14:00 ET 4H-candle model.

- Data: 2024-05-15 → 2026-05-14 (2 years), 4 instruments
- Grid: 216 configs × 4 instruments = 864 runs — [`po3_sweep.csv`](po3_sweep.csv)
- Every config scored on the first 60% **and** the held-out last 40%
- Execution costs charged on both sides ($0.01 ETFs, $0.25 = 1 tick ES)
- Ranked by *cross-instrument* out-of-sample result, not by best single number

Reproduce:

```bash
python po3_sweep.py --jobs 4
python po3_backtest.py --preset robust
```

---

## Headline

**The model has a real but modest edge, and only in its strict form.**

The `robust` preset — bias ≥ 2 confluences, **all three** entry confirmations,
15m FVG tap required, 10:00 window, stop behind the manipulation wick:

| | |
|---|---|
| Trades (4 instruments, 2 yrs) | 107 |
| Win rate | 56.1% |
| Total | **+11.29 R** |
| Average | **+0.105 R / trade** |
| Profit factor | 1.41 |
| Max drawdown | −4.48 R |
| Max consecutive losses | 5 |
| In-sample / out-of-sample | +6.68 R / +4.61 R |
| Positive out-of-sample | **4 of 4 instruments** |
| Positive months | 14 of 24 |

Per instrument: GLD +8.13 R (39 trades) · QQQ +2.91 R (32) · ES +0.92 R (8) ·
SPY −0.67 R (28).

That is roughly **27 trades per instrument over two years** — about one a month.
It is a selective model, exactly as the Bible describes ("if the setup does not
occur, we get off the charts"), and the sample is small enough that the honest
confidence interval around +0.105 R is wide.

---

## 1. The confirmation stack is the edge

Pooled across all 288 configs at each level:

| Confirmations required | Trades | Total R |
|---|---|---|
| 1 of 3 | 23,440 | **−239.6 R** |
| 2 of 3 | 18,167 | +42.6 R |
| 3 of 3 | 6,896 | **+449.8 R** |

This is the clearest signal in the whole grid, and it is monotone. **Every
single config that stayed positive out-of-sample on all four instruments
requires all three confirmations** (IFVG + CISD + reclaim of the 4H open).

The Bible says "try to see at least 2 of these for an A+ setup." The data says
the third one is not optional — two confirmations is roughly break-even and one
is actively negative.

## 2. The 14:00 window is a marginal, positive add

Comparing the 432 config pairs that differ only in whether 14:00 is enabled:

- mean total: **0.00 R** (10:00 only) → **+0.58 R** (10:00 + 14:00)
- 14:00 helped in 44% of pairs
- it contributes ~11 extra trades per config

So it is close to a coin flip that leans slightly positive — which is what
"usually 10 is the best and the 2 is weak unless it's a big day" predicts, and
it is only that good *because* the gate already restricts 14:00 to days that
have expanded past 0.75 × ATR by 14:00 and where 10:00 didn't already fire.
Ungated, it is a losing window.

The `robust` preset ships with 10:00 only because that is where the
all-four-instruments configs cluster. Turn 14:00 back on with `--hours 10,14`.

## 3. The previous-day draw is right in theory, unusable in combination

`target_mode=pdh_pdl` has the better return per trade in aggregate
(+787 R over 11,796 trades vs −535 R over 36,707 for fixed-R). But stack it with
three confirmations and the ≥ 1:2 requirement and it nearly stops trading:

> bias ≥ 2, 3 confirmations, FVG tap, PDH/PDL target → **12 trades in two years
> across four instruments.**

The prior day's high is simply not 2R away often enough at the moment the third
confirmation prints. So the strict entry and the strict target cannot both be
had; the preset keeps the strict entry.

**A structural caveat worth knowing:** in `rr` mode the target is *defined* as
`rr_target × risk`, so the `min_rr` check compares 3.0 against 2.0 and can never
fail. `min_rr` only filters in `pdh_pdl` mode.

## 4. What actually closes the trades

Under the `robust` preset:

| Outcome | Trades | Win rate | Total R |
|---|---|---|---|
| Time exit (4H window close) | 85 | 69.4% | +29.79 |
| Target (3R) | 1 | 100% | +2.81 |
| Stop (behind the wick) | 21 | 0% | −21.31 |

The 3R target almost never fires inside the 4H window. Stated plainly: **this is
a hold-to-the-close model with a manipulation-wick stop**, not a
runner-to-target model. The distribution leg is real but it usually runs less
than 3R before the candle closes.

If you trade it live, the honest expression is "exit at the end of the 4H
candle" with the target as an upside release valve — and a lower target
(1.5–2R) is the obvious thing to test next.

## 5. The 15m FVG tap is a wash on aggregate

| `require_fvg_tap` | Trades | Total R | Mean avg R |
|---|---|---|---|
| False | 30,853 | +178.1 | −0.019 |
| True | 17,650 | +74.7 | −0.053 |

On aggregate it does not pay for the trades it costs. But 4 of the 6 most
cross-instrument-robust configs keep it, so it is doing something for
consistency even where it is not adding raw return. It stays on in the preset;
`--no-fvg-tap` turns it off.

## 6. The loose configs make more, generalize worse

The highest-returning region of the grid is the opposite of the model as
written — one confirmation, no FVG tap, bias ≥ 1, PDH/PDL target:

> **+78.2 R over 499 trades**, but positive on only **3 of 4** instruments, with
> a worst-instrument result of **−6.63 R**.

On SPY alone that config makes +43 R. That is the shape of a fitted result: one
instrument carries it. It is in the CSV, and it is not the recommendation.

---

## Caveats

- **Small sample.** 107 trades is not enough to be confident about +0.105 R. The
  cross-instrument and out-of-sample agreement is what makes it interesting, not
  the point estimate.
- **Preset selection is itself a choice made on this data.** The IS/OOS split
  and the four-instrument requirement constrain it, but they don't eliminate it.
- **ETF proxies aren't futures.** SPY/QQQ/GLD 5m carry no Asia/London session, so
  the profile confluence votes 0 on three of the four datasets. ES 15m has the
  full session but only 16 bars per window. Neither is the 1m MNQ feed the model
  is really written for — see [PO3.md §5](../PO3.md).
- **R hides position sizing.** The Bible's 0.5%/0.25% rules and the 1%
  daily-loss cap live outside this engine.
- **Costs are modelled, queues are not.** Entry is at the confirming bar's close;
  a bar that straddles stop and target is scored as a stop.
