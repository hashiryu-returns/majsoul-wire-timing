# Measuring think time, and fitting a model to it

Last updated: 2026-09-01

Mahjong Soul stamps every action with `timeuse`, a whole number of seconds.
That integer, repeated a few thousand times, is very nearly the entire
behavioural trace an autoplaying client leaves on the server. This document
measures what real players put in that field, and derives a model that
reproduces it.

The findings, up front:

1. **A delay model that fits a base to observed think times and then layers
   conditional bonuses on top runs about 19% slow.** The same thinking is
   charged twice. The effect is larger than any difference between rooms.
2. **Bronze opponents are 16% slower than Jade** (Δmu +0.145, 95% CI +0.110 to
   +0.183). Silver is indistinguishable from Jade.
3. **Gold and Throne could not be measured.** Neither appears anywhere in the
   corpus, which covers Bronze, Silver and Jade.
4. Disconnected seats get auto-discarded for by the client, so failing to
   exclude them makes **the lower rooms look faster than they are**.
5. **A zero-second bucket that looks missing may not be.** The client's
   `timeuse` clock leads a proxy's by a fitted 390 ± 290 ms, and an apparent
   deficit can be nothing but that offset. See [two clocks](#two-clocks).
6. **The dealer's opening discard needs its own model.** Pooled figures looked
   healthy while that one decision was arriving in the same whole second 62% of
   the time. See [the dealer's opening discard](#the-dealers-opening-discard).

A pooled histogram can match the population while individual decision types do
not, which is how finding 6 stayed invisible underneath every aggregate above
it.

## Method

Think time for a single discard is the wall-clock gap between
`ActionPrototype: ActionDealTile` for seat N and `ActionDiscardTile` for the
same seat. Restricting to draw turns excludes discards after a call and any
decision about calling. Your own seat is excluded from the opponent figures,
since that is a bot's output rather than a human's.

`timeuse` on the wire is whole seconds only
([`02-match-lifecycle.md`](02-match-lifecycle.md)), but frames are relayed
through the server, so the wall-clock gap tracks it closely for opponents.

The corpus behind the numbers below is 249 intercepted log files pooled across
two checkouts, covering Bronze, Silver and Jade rooms on the Japanese and
English servers.

### What the tool needs to read

[`fit-timing.py`](../fit-timing.py) parses [Akagi](https://github.com/shinkuan/Akagi)
v3's gateway logs because that is what produced these captures, but nothing
about the analysis is specific to that client. Any proxy that records the
decoded frame stream with timestamps carries the same information. The expected
input is JSON Lines, one frame per line:

```json
{"dir":"down","method":".lq.ActionPrototype","payload":{"name":"ActionDiscardTile",
 "data":{"seat":0,"tile":"6z","moqie":false}},"ts":"2026-09-01T15:55:03.412-07:00"}
```

Four fields are load-bearing: `dir`, `method`, `ts`, and `payload`. Within
`payload`, the analysis uses `name` and `data.seat` for every action,
`data.moqie` on a discard, and `data.ju` on `ActionNewRound` to identify the
dealer. Adapting to another capture format means producing those, and nothing
else.

### Validating the pipeline

The measurement checks out against an independent source. Measured Jade
hand-discards under 1.2 seconds come out at 20.8 / 10.0 / 4.3% for honours,
terminals and simples. Akagi's shipped model declares 21 / 10 / 4% for the same
three cells, derived from a different corpus of 30 hanchan and 21,500
decisions. **Two unrelated samples landing on the same numbers is good reason to
trust the measurement.**

### Identifying the room

`game_config.meta.mode_id` from the `authGame` response. East versus South comes
from `game_config.mode.mode` (1 and 2 respectively), which agrees with `chang`
in `ActionNewRound`. Rank comes from the leading three digits of
`players[].level.id`: 101 Novice, 102 Adept, 103 Expert, 104 Master, 105 Saint,
106 Celestial.

The four-player ranked `mode_id` values are 2/3 Bronze, 5/6 Silver, 8/9 Gold,
11/12 Jade and 15/16 Throne, East and South respectively.

| `mode_id` | Room | Games | Opponent discards | Ranks at the table |
|-----------|------|-------|-------------------|--------------------|
| 2 | Bronze East | 59 | 11,038 | Novice 203, Adept 93 |
| 5 | Silver East | 13 | 2,508 | Adept 49, Expert 3 |
| 6 | Silver South | 4 | 1,272 | Adept 14, Expert 2 |
| 12 | Jade South | 4 | 1,492 | Master 17, Saint 3 |

`mode_id` 8 and 9 (Gold) and 15 and 16 (Throne) appear zero times.

Two things fix the mapping independently: the published `mode_id` list, and the
rank gates. Gold admits only Expert and Master, and `mode_id` 5 seated 96
Adepts; Throne admits only Saint and Celestial, and `mode_id` 12 seated 14
Masters. Check both before naming a room — a wrong label inverts which rooms
count as measured without changing a single number.

## Excluding artefacts

Everything hard about this measurement is deciding which intervals to discard.

The lower-room logs are full of dropped connections, and left in they distort
everything. The signal is the `state` field of `NotifyPlayerConnectionState`,
which walks `NULL` → `AUTH` → `SYNCING` → `READY` on a reconnect. Bronze has 68
transitions out of `READY`; Jade has one.

Excluded:

- A seat's discards from the moment it leaves `READY` until it returns, rewound
  60 seconds to catch the timeout discards that precede detection
- Every subsequent discard from a seat that produced `PlayerLeaving`
- Any interval spanning one of your own reconnects (`syncGame`,
  `finishSyncGame`, a repeated `authGame`)
- Any interval where consecutive frames are more than 25 seconds apart,
  indicating a gap in logging rather than a slow player
- Every discard from a seat in Mahjong Soul's AFK auto-play

That last one is the trap. **It is not a disconnection and emits no
`NotifyPlayerConnectionState`**, so none of the filters above catch it. Such a
seat discards almost instantly and nothing else at the table looks unusual. One
AFK seat in a three-game sample pushed the apparent opponent sub-second rate
from 10.0% to 20.3% — enough to make a bot tuned against it look far too fast.
The workable test is behavioural: **a seat putting more than half its discards
under one second is not a person**, and no measured human seat comes close.

| Room | Excluded | Median | Sub-second rate |
|------|----------|--------|-----------------|
| Bronze East | 4.6% | 2.26 → **2.31** s | 12.0 → **9.1** % |
| Silver East | 1.6% | 1.98 → 1.99 s | 11.9 → 11.4 % |
| Silver South | 1.1% | 2.15 → 2.15 s | 8.0 → 7.5 % |
| Jade South | 0.0% | 2.02 → 2.02 s | 10.0 → 10.0 % |

Excluding these makes Bronze **slower**, which is the opposite of the intuition.
A disconnected seat is auto-discarded for instantly, and that mass was inflating
the sub-second bucket. Skip this step and the gap between rooms comes out as
0.121 instead of 0.145 — understated by a fifth.

## Differences between rooms

Median ratios computed per cell across the six combinations of hand-discard or
tsumogiri by three tile classes, then averaged in log space with a
2,000-iteration bootstrap for the interval. Working per cell avoids
contamination from the rooms having different hand-discard rates (Bronze 52%,
Jade 60%).

| Comparison | Δmu | 95% CI | Ratio |
|------------|-----|--------|-------|
| Bronze vs Jade | **+0.145** | +0.110 to +0.183 | ×1.16 |
| Silver vs Jade | +0.014 | −0.026 to +0.057 | ×1.01 |
| Bronze vs Silver | +0.131 | +0.108 to +0.157 | ×1.14 |
| Silver South vs Silver East | +0.030 | −0.015 to +0.078 | ×1.03 |

A log-normal median is e^mu, so a ratio of medians is an additive shift in mu.

- **Only Bronze differs.** All six cells move the same direction, by 8 to 16%.
- **Silver is indistinguishable from Jade.** The interval spans zero and the
  per-cell signs are inconsistent. This is the useful version of the result,
  because Silver and Jade are both rooms in regular use.
- **East versus South does not matter**, so Bronze being an East room is not a
  confound.

**Play does not get slower as rank rises. It gets faster** — the Novice and
Adept tables are the slowest measured. This is worth stating plainly because the
opposite is widely assumed, and acting on the assumption pushes a model in
exactly the wrong direction.

Nothing in a delay script's runtime context identifies the room, so this cannot
be a runtime branch. Refit per room instead: run the tool over logs from the
room you actually play, and the difference is absorbed into the fitted level
without any explicit offset. Only Bronze is far enough from the others to
matter.

## The double-counting failure

This is the most transferable finding here, because the structure that causes it
is a natural way to build such a model.

Akagi's shipped model splits think time into clusters by tile class and by
whether the discard is a tsumogiri, then applies conditional adjustments: a
junme multiplier for how deep the hand is, a multiplier when an opponent has
declared riichi, a survey bonus on the first action of a kyoku, and a bonus when
riichi is declarable. The cluster parameters came from a 21,500-decision fit and
the relative structure between them holds up well.

Porting that model and running it with the covariates **disabled** and then
**enabled**:

| Cell | Declared in the model | Covariates off | Covariates on | Measured Jade |
|------|----------------------|----------------|---------------|---------------|
| Hand discard, honour | 21% | 20.3% | 13.3% | 20.8% |
| Hand discard, terminal | 10% | 9.9% | 5.2% | 10.0% |
| Hand discard, simple | 4% | 6.2% | 3.7% | 4.3% |
| Tsumogiri, honour | 31% | 29.7% | 22.8% | 25.8% |
| Tsumogiri, terminal | 26% | 25.6% | 19.3% | 22.4% |
| Tsumogiri, simple | 20% | 19.7% | 15.2% | 22.4% |

The covariates-off column matches **both** the model's own declared values and
the measurements. Only the covariates-on column misses. The base clusters were
fitted to the **marginal** distribution — which already contains every deep hand
and every live riichi those players were reacting to — and the conditional
bonuses then add that thinking a second time.

| Covariate | Median | Contribution |
|-----------|--------|--------------|
| None | 2.18 s | — |
| First action only | 2.25 s | +0.07 |
| Opponent riichi only | 2.31 s | +0.13 |
| Riichi available only | 2.26 s | +0.08 |
| All | 2.43 s | +0.25 |

**So: fit the marginal and do not decorate it.** The template in this repository
has no junme multiplier, no riichi bonus and no first-action survey, because the
distribution it is fitted to already includes all of them.

### Correcting an existing model

If you have a model with this flaw and want to keep its structure, the relative
structure between cells is worth preserving — it came from a much larger fit —
and only the overall level is wrong. A single mu offset fixes it:

| mu offset | Median | <1s | ≥6s |
|-----------|--------|-----|-----|
| ±0.00 (as shipped) | 2.44 s | 6.4% | 6.6% |
| −0.15 | 2.12 s | 9.5% | 4.5% |
| **−0.22** | **2.07 s** | **10.9%** | 6.7% (with a 7% long-thought rate) |
| −0.25 | 2.03 s | 11.6% | 6.8% |
| Measured Jade | 2.02 s | 10.0% | 7.0% |

A long-thought probability of 2% cannot reach the measured 7.0% at six seconds
and above; 7% can. That figure agrees independently with a comment in the
shipped model itself, which observes that its own corpus dipped into the time
bank on roughly 7% of draws.

L1 distance on the whole-second histogram, which is the resolution the server
records:

| | Jade | Silver | Bronze |
|--|------|--------|--------|
| As shipped | 27.4 pt | — | 12.7 pt |
| **Level corrected** (mu −0.22, 7% long thought) | **6.8 pt** | **5.8 pt** | — |
| Corrected plus a +0.15 room shift | — | — | **5.9 pt** |
| A deliberately fast model | 11.7 pt | — | — |

The fast model scoring better than the shipped one against Jade is not a point
in its favour — it is a measure of how far the shipped model errs slow. Both sit
outside the human distribution, in opposite directions.

**These figures are computed on the delay model's own output, not on what the
server receives.** The two differ at the floor, which
[the floor](#the-floor-and-the-zero-second-bucket) is about.

### Fitting from scratch instead

The correction above assumes you are keeping someone else's structure. Fitting
from nothing is simpler and, for the purpose here, better: two log-normals — one
for tsumogiri, one for hand discards — plus a long-thought component, all
estimated from your own opponents.

One log-normal alone cannot reach the tail. Fitted to the body it lands near 4%
of discards at six seconds or longer where the measurement says closer to 7%,
and "how often does this player think for six seconds" is among the cheapest
questions a server can ask of a discard stream. So a second component is mixed
in at whatever rate reproduces the observed long-thought share. That is still
fitting the marginal, since it is estimated from the tail of the same sample,
rather than a conditional bonus applied on top of it.

The body is fitted from quantiles rather than from the mean of the logs, because
the handful of 30-second thinks that survive the ceiling drag a mean and do not
move a median. Adding tail mass then shifts the median, so the level is
re-centred and the two iterated to a fixed point.

## The dealer's opening discard

Everything above pools all discards together, and the pooled figures were good
while one decision type was badly wrong. **The dealer's opening discard was
arriving in the same whole-second bucket 62% of the time**, against 15% for real
dealers, with a median of 3.63 s against 5.57 s. It is one decision per kyoku,
so it contributes about 3% of the pooled histogram and moved none of the numbers
above.

It only came up because auditing a different tool
([`05-uniform-delay-models.md`](05-uniform-delay-models.md)) found it adding a
flat 4.5 s to the same decision, which prompted checking.

### What the model was doing

Two faults stacked. The script treated the opening as an ordinary first discard
plus a 0.5–1.3 s survey, median about 3.0 s — far below the measured human
figure. And the soft cap sits at
`time_fixed(5000) − safety_margin(1000) − click overhead(330) = 3670` ms, close
enough to that median to flatten what spread remained onto the cap value itself.
The bank, which would have lifted the cap, stayed locked because the script only
unlocks it once think time exceeds the 4-second free window, which 3.0 s does
not.

The output was therefore confined to roughly `[3000, 3670]`, since the animation
pad acts as a floor at 3000. Simulated, 84% in one bucket; measured on the wire,
62%.

The pad did not cause the collapse — the cap did — but it is why the problem went
unnoticed. Sitting directly on top of a model producing 3.0 s, it lifted the
median to something plausible while the distribution underneath had already been
flattened. **A floor near the mode masks a modelling error rather than surfacing
it.**

### Measured human dealers

229 opponent openings, `ActionNewRound` to that dealer's first
`ActionDiscardTile`, disconnect-affected seats excluded by the rules above:

- median 5.57 s, p10 3.61 s, p90 9.64 s, min 2.14 s
- 15% at nine seconds or longer
- whole-second buckets 2 through 9+: 3 / 15 / 19 / 22 / 10 / 10 / 7 / 15%

The median sits above the 5-second free allowance, which means **real dealers
routinely spend bank time on the opening discard.**

### The corrected model

Give the opening its own regime — a log-normal fitted to those measurements
rather than a discard with a bonus attached. Because that clears the free window
on most draws, ordinary budget shaping unlocks the bank by itself and no special
case is needed.

Any bonuses that would otherwise stack on top should be skipped for the opening.
The fitted distribution is a marginal and already contains whatever deliberating
those dealers did; adding more repeats the double-counting mistake above.

Two budget values had to move with it, both raising the ceiling on a single long
thought:

| Key | Was | Now | Effect |
|-----|-----|-----|--------|
| `bank_use_fraction` | 0.25 | 0.45 | Ceiling 8.67 → 11.67 s |
| `bank_max_single_ms` | 5000 | 8000 | Same |

At 8.67 s the opening's upper tail piled up — 17% in the 8-second bucket against
a human 7%, and nothing beyond it.

Verified through the real Lua sandbox with the floors and caps in place, 40,000
samples:

| Distribution | L1 before | L1 after |
|--------------|-----------|----------|
| Dealer's opening discard | 129 pt | **16.6 pt** |
| All other discards | 6.8 pt | **6.8 pt** |

The residual 16.6 points are mostly the nine-second bucket, where humans reach
15% and the model reaches 10.4%.

### What the pad is actually for

The animation pad was lowered from 3000 to 2000 as part of this work, on the
reasoning that it was standing in for think time the model was not producing.
**That was wrong, and it broke something else.**

Masking the shortfall and causing the collapse are different things, and only
the first was the pad's doing. Once the model produces the right distribution
and the bank is unlocked, the pad barely matters statistically: L1 against the
measured openings is 18.6 points at a 2000 floor and 18.9 at 3000 — same median,
same modal bucket, because the fitted draw clears 3000 on 95% of openings.

Meanwhile the pad has a mechanical job. It waits out the client's hand-sort
animation, which swallows presses for about 2.9 s, and at 2000 it stopped doing
it, costing 10% of dealer openings the entire turn. See
[`04-click-reliability.md`](04-click-reliability.md#cause-1-the-dealers-opening-animation).

**A mechanical floor and a behavioural model are separate jobs.** Reading the pad
as think time produced the fingerprint; then removing it to fix the fingerprint
produced lost turns.

## The floor and the zero-second bucket

The `<1s` figures above are the delay model's output. **They are not what the
server sees.**

A well-built autoplayer subtracts the click execution overhead from its sleep so
the click lands on target. For any target above the enforced minimum, that
works. The floor is where it breaks: the minimum clamps the **sleep**, not the
total, and the overhead is then added back on top. So the observed minimum is:

```
  min_delay_ms + hover_delay_ms + hold + latency
      987      +      187       + 100  +   38     = 1312 ms
```

Which matches the first percentile of 5,706 measured discards exactly —
1.312 s. Only 0.09% of them came in under a second. At the shipped defaults of
1000 and 200 the same arithmetic gives about 1.34 s; either way both land in
`timeuse: 1`.

On the wire, against the Jade target, with the unmodified model active:

| `timeuse` | Bot | Measured Jade | Gap |
|-----------|-----|---------------|-----|
| 0 | **1.1%** | **10.0%** | **−8.9** |
| 1 | 35.3% | 39.5% | −4.2 |
| 2 | 35.0% | 23.4% | +11.6 |
| 3 | 14.6% | 11.6% | +3.0 |
| 4 | 6.7% | 4.8% | +1.9 |
| 5 | 3.3% | 3.8% | −0.5 |
| 6 | 1.7% | 2.5% | −0.8 |
| 7 | 0.8% | 1.3% | −0.5 |
| 8+ | 1.5% | 3.2% | −1.7 |

The surplus in buckets 2 and 3 is the model running slow. **The empty zero
bucket is the floor, and no amount of model work fixes it** — every sub-second
decision gets clamped up and arrives as `timeuse: 1`.

### What lowering the floor did

The floor has to satisfy `min_delay_ms + ~340 < 1000`, so anything above 680 is
identical to the default in effect. 600 puts the observed minimum near 938 ms,
inside the bucket with about 60 ms of headroom.

Measured over one session on the new setting — 151 post-draw discards,
timestamped at the proxy from the `ActionDealTile` frame to the `inputOperation`
uplink:

| Prediction | Result |
|------------|--------|
| Observed floor near 938 ms | **946 ms**, the fastest of 151 discards. Confirmed |
| 11.9% of discards under one second | **11.9%**. Confirmed exactly |
| Therefore ~11.9% in bucket 0 | **2.4%**. Wrong |

The first two held and the conclusion drawn from them did not, because **the
client's `timeuse` is not measured from the same instant a proxy is**. Of the 18
discards that took under a second of proxy wall clock, 15 were reported as
`timeuse: 1`.

Nor is the boundary a clean threshold. The three discards that did reach bucket
0 sat at 947, 948 and 986 ms of wall clock — while a 946 ms discard, the fastest
of the whole sample, was reported as 1.

### Two clocks

The offset is never observable directly, but each discard bounds it: given wall
clock `w` and a reported `timeuse`, the offset must lie in
`[timeuse − w, timeuse + 1 − w)`. Fitting a normal to those 150 intervals by
maximum likelihood gives **mean 390 ms, standard deviation 290 ms.** The fit
predicts a 1.8% bucket-0 share against the 2.0% actually observed, which is the
check worth trusting it on.

The mean is the part a lower floor compensates for. The spread is what makes the
floor a shallow lever — the second boundary is crossed probabilistically over a
smear about 600 ms wide, so moving the floor buys roughly one point of bucket 0
per 100 ms:

| `min_delay_ms` | Press lands after the draw frame | Projected bucket 0 |
|---|---|---|
| 600 | 946 ms | 1.9% |
| 500 | 846 ms | 3.1% |
| 400 | 746 ms | 5.2% |
| 300 | 646 ms | 7.7% |
| 250 | 596 ms | 9.1% |

Against a human 10.0% — and **that 10.0% is the flaw in the whole exercise.**

The human bucket-0 figure is not a `timeuse` at all. Opponent frames carry no
timing field: `ActionDiscardTile` reports the tile, the seat and whether it was
tsumogiri, and nothing about how long it took. Opponent think time can therefore
only be measured as a wall-clock gap at the proxy.

So the deficit was computed by putting a *client-reported `timeuse`* next to
opponents' *proxy-measured wall clock* — the two clocks just shown to be 390 ms
apart. The gap was mostly the offset itself.

Measured on one basis, 151 of our discards against 503 opponent discards at the
same tables:

| Bucket, wall clock both sides | Bot at floor 600 | Opponents |
|---|---|---|
| **0** | **11.9%** | **8.9%** |
| 1 | 34.4% | 43.3% |
| 2 | 27.8% | 21.3% |
| 3 | 7.3% | 9.7% |

At 600 the bot was already **slightly ahead** of the humans on sub-second
discards, not eight points behind. And since opponents run the same client,
their reported `timeuse` carries the same offset, which puts the server's view
of them near 2% at bucket 0 as well — where the bot already was.

The real mismatch is in the middle: heavy in bucket 2, light in bucket 1. That
is a shape problem in the model, and no floor value fixes it.

**Compare like with like.** [`fit-timing.py`](../fit-timing.py) measures every
seat, yours included, on the proxy's wall clock for exactly this reason.

### Choosing the floor

The floor was briefly taken to 250 to close the bucket-0 gap above. Once that
gap turned out to be an artefact, the question became what the floor is actually
worth, and measuring it properly needed two corrections to the method.

**Decision mix has to be held constant.** Tsumogiri is much faster than a hand
discard, so a session that happens to draw more of them looks faster with no
change to the model. One session ran 42.9% tsumogiri and another about 32%,
which on its own moved the pooled sub-second rate from 11.9% to 4.5% while the
model was byte-identical. Comparisons have to be per decision type.

**The floor only governs the fast tail**, which is almost entirely tsumogiri.
Hand discards sit far above any floor value and are untouched by it. So the
sub-second rate on tsumogiri is the number that answers the question:

| Floor | Bot tsumogiri under 1 s | Opponents at the same tables | Overshoot |
|---|---|---|---|
| **600** | 17.9% | 13.9% | **+4.0** |
| 250 | 24.6% | 14.5% | +10.1 |

Already a little quick at 600, and 250 doubled it. Medians agree without
settling it alone — tsumogiri ×1.07 of the opponents' at 600 and ×0.92 at 250,
both within noise at 65 to 78 samples per cell, but bracketing 1.0 from the
expected sides.

250 was never mechanically dangerous: 176 discards produced one retry and no
losses, and the fastest press measured 0.60 s. It was simply snap-discarding
faster than the table for no benefit. **Match the sub-second rate, not the
bucket.**

Other click-mechanics values are not worth touching. Hover and inter-click
delays sit inside the overhead that is already subtracted, so moving them
redistributes time between the sleep and the hover without moving the click;
they cannot change `timeuse` at all.

### The cost, and how to watch it

The floor is not only a distribution knob. It exists because a click issued
before the tile has rendered is silently lost, and lowering it moves the press
from 1187 ms after the draw frame to 800 ms. The evidence said render timing was
not what currently fails — lost presses track tile *position*, not tile arrival —
but that had not been tested low.

It has now. At 600, 164 discards produced **two retries and no outright losses**,
against 3.4% and 1.3% on the previous corpus. At 250, one game gave 54 discards
with **zero of either**. Both samples are small, but together they rule out the
feared failure mode: neither floor is eating clicks.

**Keep watching for retries and losses after any change to the floor.**
[`04-click-reliability.md`](04-click-reliability.md) covers the measured loss
rate, what the failures correlate with, and what to grep for.

## The nine-second tail

Jade opponents put 2.2% of their discards at nine seconds or longer. At a hard
budget cap of 8.67 seconds that tail is unreachable, and for 2% of the
distribution it looked not worth chasing.

That call reversed while fixing the dealer's opening, which needs the same
headroom for a much larger share of its distribution — measured human dealers
spend 15% of openings at nine seconds or longer. Raising the ceiling to 11.67 s
recovers the ordinary long-thought tail from 0 to 1.3% as a side effect. Median
and sub-second share are unchanged (1.97 → 1.99 s, 12.0 → 12.1%), so nothing
else in the calibration is affected.

Exceeding the cap hands control to the client's auto-discard, which is the most
conspicuous failure available
([`04-click-reliability.md`](04-click-reliability.md#why-losing-one-is-worse-than-it-sounds)),
so the cap itself should still be honoured unconditionally. A well-behaved
implementation recomputes it from the *remaining* pool on every decision, so two
long thoughts in one kyoku self-limit rather than compounding.

## Fitting from your own logs

```bash
python3 fit-timing.py /path/to/logs
python3 fit-timing.py /path/to/logs --out my-delay.lua
```

The tool scans for `*game-gateway*.log`, reconstructs opponent think times,
applies every exclusion above, fits the parameters, and prints the fitted model
beside the measurement. With `--out` it writes those numbers into
[`delay-template.lua`](../delay-template.lua).

Nothing is uploaded, and nothing but aggregate statistics is written — no
account id, device id, game uuid or nickname — so the output is safe to share
even though the logs it reads are not.

It reports an L1 distance over whole-second buckets:

```
  measured     median= 2.02s  <1s=  9.5%  >=6s= 6.7%  >=9s= 1.8%
  model        median= 2.03s  <1s= 11.6%  >=6s= 6.7%  >=9s= 2.0%
  L1 distance 6.2 percentage points (good)
```

Under about 12 points is good. Above 20 means something is wrong, and the usual
cause is too little data: with fewer than a few hundred discards per class the
quantiles are noisy and the long-thought rate is fitted to a handful of events.

Two things the fit does not cover. Non-discard decisions — calls, riichi
declarations, ron — cannot be measured from logs at all, because an opponent's
call window opening leaves no trace. The template sets those by judgement, as
offsets from your fitted hand-discard level, and says so. And the dealer opening
needs about 20 measured examples before it is fitted rather than extrapolated,
which is roughly 20 kyoku as dealer.

### Why fit rather than copy

Every number in this document is a worked example from one player's logs, quoted
so the reasoning can be checked rather than so it can be pasted. The model's
value is that its output is indistinguishable from the players around it, and
that property survives being one client among thousands but not being a popular
preset: a few hundred people emitting the same fitted shape turns "human" into
"users of this repository". That is precisely why the uniform model in
[`05-uniform-delay-models.md`](05-uniform-delay-models.md) is so easy to spot —
one hardcoded model, shipped to everybody.

## What to check after a change

- The **whole-second histogram** of `inputOperation.timeuse`, against measured
  opponents. Jade is 10.0 / 39.5 / 23.4 / 11.6 / 4.8 / 3.8 / 2.5 / 1.3 / 3.2%
  for buckets 0 through 8+. **A median alone is too coarse to see anything.**
- Hand discards and tsumogiri **separately**, via `moqie`. Their medians differ
  by 0.8 seconds, so a combined figure is not comparable to anything.
- **The dealer's opening on its own**, from `ActionNewRound` to that seat's first
  `ActionDiscardTile`. Invisible in the pooled histogram, and the one that turned
  out to be nearly deterministic.
- **`timeuse` outliers**, meaning anything above about 15. Those are not think
  time, they are turns the client answered after every press was lost. They
  arrive with `auto_operation: false` and will otherwise pollute the histogram.
- Retries and recovery reloads. These are largely independent of the model, so a
  change in them after a model switch means the switch pushed a press into an
  animation.

Cautions:

- **At least 20 rounds per change.** Resolving a single percentage point in one
  bucket takes hundreds of discards; 20 rounds is roughly 400.
- **Millisecond changes are not measurable**, because the wire value is whole
  seconds.
- **Do not pool opponent data uncritically.** Exclude disconnected and
  auto-played seats first, or the lower rooms look faster than they are.
- **Measure on the wire, not on the model.** The two differ by the click
  execution overhead.

| Observation | Meaning |
|-------------|---------|
| Histogram shape moved toward the measured one | The model is working |
| Distribution unchanged across a switch | The setting is not being read, or the change was below one second |
| Zero bucket nearly empty | The floor is too high, but the lever is shallow — expect about one point per 100 ms ([two clocks](#two-clocks)) |
| One bucket holding most of a single decision type | A floor or a cap is sitting near that decision's mode |
| A `timeuse` of 20 or more | A lost turn, not a long think |
| More retries than before | Look at coordinates rather than timing |

## Still unknown

- **Gold and Throne.** Playable, therefore measurable, but absent from this
  corpus. Throne is the one worth measuring, since it is the only room with no
  measured neighbour on both sides.
- **Call decisions and riichi declarations.** An opponent's call window opening
  leaves no trace in the log, so these cannot be timed at all.
- **How often riichi is actually declarable.** Opponent hands are not visible;
  the simulation assumed 8%.
- **The bucket-1 and bucket-2 shape.** Models tend to sit heavy at two seconds
  and light at one against opponents on the same basis. This is the largest
  remaining discrepancy and it belongs to the model, not to any floor or cap.
- **Why the client's `timeuse` clock leads a proxy's.** It is measured and
  reproducible, but the origin it counts from has not been identified, so the
  offset can only be described statistically rather than predicted.

## Related

| Document | Contents |
|----------|----------|
| [`01-what-the-server-sees.md`](01-what-the-server-sees.md) | Which behaviour reaches the server at all |
| [`02-match-lifecycle.md`](02-match-lifecycle.md) | The `timeuse` measurements this calibration is built on |
| [`04-click-reliability.md`](04-click-reliability.md) | The floors here have a mechanical job as well as a statistical one |
| [`05-uniform-delay-models.md`](05-uniform-delay-models.md) | The audit that prompted splitting the dealer's opening out |
| [`06-what-gets-noticed.md`](06-what-gets-noticed.md) | Why this layer is the least important of four, and worth doing anyway |
