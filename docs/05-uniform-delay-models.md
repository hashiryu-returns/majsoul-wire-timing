# Reading a competitor: MahjongCopilot's timing

Last updated: 2026-09-01

`latorc/MahjongCopilot` is the other widely used Mahjong Soul bot built on Mortal.
It is a useful subject because it is open source, popular enough that its output
is presumably well represented in whatever samples Yostar has, and its
automation is simple enough to reason about exactly. This note records what its
delay model looks like from the server's side, and the bug in our own model that
auditing it exposed.

Method: its delay logic (`game/automation.py`, `common/settings.py`) was
re-implemented and replayed over 6,085 real discard decisions taken from our own
gateway logs, so tile classes, riichi states and dealer turns are the ones a
Mortal-driven seat actually produces rather than a synthetic mix. Human figures
are the Jade-room opponents from
[03-fitting-a-delay-model.md](03-fitting-a-delay-model.md).

## Conclusions

1. **Its distribution has holes at the default settings.** Nothing arrives under
   1.4 seconds and essentially nothing between 4 and 6, where humans sit 8.6% of
   the time. One range predicate over roughly 100 discards separates it from a
   human at p < 1e-4. The holes are closable through config; the flatness
   underneath them is not — see [how much a user can
   configure](#how-much-of-this-a-user-can-configure).
2. **Every long think it produces is the same event.** All of its discards at
   six seconds or longer are the dealer's opening discard. The relationship holds
   in both directions.
3. **Its think time is a step function of the tile thrown**, with hard edges the
   server can recover by grouping on a column it already stores.
4. **The same fault class appears in fitted models**, not just uniform ones: a
   dealer's opening discard arriving in a single whole-second bucket 62% of the
   time. Diagnosed in
   [03-fitting-a-delay-model.md](03-fitting-a-delay-model.md#the-dealers-opening-discard);
   summarised [below](#the-same-fault-in-a-fitted-model).

## What its model does

The delay before a click is `uniform(delay_random_lower, delay_random_upper)`,
defaulting to 1 to 2 seconds, plus an additive lookup:

| Condition | Extra |
| --- | --- |
| Tsumogiri, or a terminal/honor hand discard | +0.00 s |
| Hand discard of a 2 or an 8 | +0.50 s |
| Hand discard of a 3 through 7 | +0.75 to +1.00 s |
| Per opponent in riichi | +0.20 to +0.30 s |
| Dealer's first discard of a kyoku | +4.50 s |
| Riichi declaration | +1.00 s |
| Any call or pass | +0.50 s |

Then the model's own computation time is subtracted, floored at zero. Click
mechanics add another 0.4 to 0.9 seconds on top, uncompensated.

In a real hand, 74% of a Mortal seat's discards draw `+0.00`: 36.8% tsumogiri
plus 37.3% terminal-or-honor hand discards. The `min(extra, 3.0)` cap in the
source is dead code in four-player — the terms cannot reach 3.

## What the server receives

Whole-second `timeuse`, which is the full resolution of the channel. The two bot
columns are their models' output, not wire captures, so the two are compared on
equal terms:

| Bucket | Measured humans | MahjongCopilot | A fitted model |
| --- | --- | --- | --- |
| 0 s | 10.0% | 0.0% | 12.1% |
| 1 s | 39.5% | 23.6% | 39.5% |
| 2 s | 23.4% | 63.2% | 22.5% |
| 3 s | 11.6% | 10.9% | 10.3% |
| 4 s | 4.8% | **0.0%** | 5.8% |
| 5 s | 3.8% | **0.0%** | 3.7% |
| 6 s | 2.5% | 2.0% | 2.4% |
| 7 s | 1.3% | 0.3% | 1.5% |
| 8+ s | 3.2% | 0.0% | 2.2% |
| **L1** | — | **80 pt** | **6.8 pt** |

One caveat on the `0 s` row. Akagi's modelled 12.1% does not survive the trip to
the server: the client's clock leads our measurement by about 390 ms, so most
sub-second decisions are reported as `timeuse: 1` and the observed share is
nearer 2%
([`03-fitting-a-delay-model.md`](03-fitting-a-delay-model.md#two-clocks)).
Copilot's 0.0% is structural and would survive any clock — it cannot produce a
sub-second value at all.

### How much of this a user can configure

This deserves precision, because it is the obvious objection. Of everything in
the table above, **exactly two numbers are settings**: `delay_random_lower` and
`delay_random_upper`, the bounds of the base uniform. Every other term —
the +4.5 dealer constant, the tile lookup, the per-riichi increment, the riichi
and call additions, the `min(extra, 3.0)` cap and the latency subtraction — is a
literal inside `Automation.get_delay()`. The single most distinctive one, the
dealer constant, cannot be changed without editing the source.

Sweeping the two that can be, over the same 5,961 real decisions:

| `lower`–`upper` | L1 | Zero bucket | Buckets the server never sees |
| --- | --- | --- | --- |
| **1–2 (default)** | **74.9** | 0.0% | 0, 4, 5, 8 |
| 0–2 | **37.0** | 12.8% | 4, 8 |
| 0–3 | 43.7 | 8.4% | 8 |
| 1–3 | 90.5 | 0.0% | 0, 5, 8 |
| 0–5 | 68.2 | 5.2% | none |
| 0–6 | 79.4 | 4.1% | none |
| 1–6 | 106.3 | 0.0% | 0 |

So the empty buckets **are** reachable by configuration: drop the lower bound to
zero and widen the upper past five and the holes close. That much of the finding
is a criticism of the default rather than of the design, and a user who does it
is meaningfully harder to pick out by the range predicate above.

What no setting fixes is the shape. The best L1 available anywhere in the range
is 37 points, against 6.8 for a fitted log-normal, and widening past 0–2 makes it
worse rather than better. At 0–6 the delivered distribution is essentially flat —
15 to 17% in every bucket from one second to six — where humans put 39.5% in the
one-second bucket and decay from there:

| Bucket | Copilot at 0–6 | Measured humans |
| --- | --- | --- |
| 0 s | 3.9% | 10.0% |
| 1 s | **14.7%** | **39.5%** |
| 2 s | 15.9% | 23.4% |
| 3 s | 16.3% | 11.6% |
| 4 s | 16.6% | 4.8% |
| 5 s | 17.0% | 3.8% |
| 6 s | 12.3% | 2.5% |

**Two bounds cannot turn a rectangle into a decaying curve.** Closing the holes
and matching the distribution are separate problems, and only the first one is
exposed as a setting.

Detection cost, testing only "did this seat ever discard in the 4-6 second band":

| Own discards observed | P(a human shows none) |
| --- | --- |
| 50 | 1.1e-02 |
| 100 | 1.2e-04 |
| 150 | 1.4e-06 |
| 300 | 1.9e-12 |

Roughly 150 own-discards is one hanchan.

### Think time reveals the tile

Support of the delivered delay per discard class, 20,000 draws each at defaults:

| Discard class | Min | Max | Reachable `timeuse` |
| --- | --- | --- | --- |
| Tsumogiri, any tile | 1.44 s | 2.88 s | 1, 2 |
| Hand discard, terminal or honor | 1.45 s | 2.86 s | 1, 2 |
| Hand discard, 2 or 8 | 1.95 s | 3.34 s | 1, 2, 3 |
| Hand discard, 3 through 7 | 2.22 s | 3.84 s | 2, 3 |
| Dealer's first discard | 5.95 s | 7.35 s | 5, 6, 7 |

The server knows which tile was discarded. Real players' distributions overlap
heavily across these classes — the class shifts the median by a few hundred
milliseconds and changes nothing about the range.

Widening the base window does blur this, since the additive term stays the same
size while the noise around it grows: at 0–6 the medians are 3.5 s for
terminals and honors against 4.5 s for the rest, a separation that is still there
but no longer separates the *supports*. It is the one fingerprint here that
configuration genuinely mitigates, and mitigating it costs overall fit.

### The remote-model failure mode

Subtracting model latency and flooring at zero means a slow model does not delay
the click, it removes the delay:

| Model latency | Discards under 1 s | Median |
| --- | --- | --- |
| 0.3 s (local Mortal) | 0.0% | 2.35 s |
| 1.5 s | 23.8% | 1.34 s |
| 2.5 s (hosted model) | 86.4% | 0.68 s |
| 3.5 s | 97.7% | 0.65 s |

Anyone on the hosted model emits a bimodal distribution with a spike at zero and
a gap in between. Our equivalent path is bounded below by `min_delay_ms`, which
is part of why that floor exists.

### Where its effort goes

Randomized mouse paths, idle cursor jiggle, and drag-versus-click are all
invisible to the server: Mahjong Soul transmits the resulting operation, not the
cursor. Two of the three are off by default anyway. Meanwhile the AI-choice
randomization, at its default strength of 1, raises the probabilities to the
power of 5 and leaves the top Mortal choice selected 97% of the time — so move
agreement is essentially undiluted.

The two channels that do reach the server, timing and session shape, are the two
modelled least carefully. Auto-join requeues immediately and indefinitely; a
stop-timer was added as a feature, which implies long unattended runs. Emoji
replies are uniform over all nine, fire only in response to someone else's, and
never spontaneously.

## The same fault in a fitted model

Copilot adds a constant 4.5 seconds to the dealer's opening discard. A fitted
model reaches a worse version of the same result through
`dealer_first_discard_extra_delay_ms`: openings arriving in a single whole
second 62% of the time against a human 15%, from two faults stacking — a model
producing a 3.0 s median where humans take 5.57, and a budget cap close enough
to that median to flatten it.

The diagnosis and the corrected model are in
[03-fitting-a-delay-model.md](03-fitting-a-delay-model.md#the-dealers-opening-discard);
the pad's separate mechanical job, waiting out the hand-sort animation, is in
[04-click-reliability.md](04-click-reliability.md#cause-1-the-dealers-opening-animation).
The opening's L1 distance against measured human dealers went from 129 points to
16.6, with the rest of the distribution unchanged at 6.8.

One residue belongs here, since this document is about fingerprints. Akagi's
built-in model — `mode = "legacy"`, and the silent fallback when `delay.lua`
fails to compile — does not sample the first action of a kyoku at all. It returns
`pre_click_delay_max_ms` as a fixed value, so legacy's openings are a constant:
exactly the pattern this audit went looking for in someone else's code. It is
left alone because reproducing old Akagi is what legacy is for, but a syntax
error saved into `delay.lua` mid-session drops to it with only a warning in
`all.log`.

## What to take from this

- **Never let a constant be the dominant term.** Both bots' worst signature came
  from one.
- **Never let a cap sit near the mode.** A cap in the tail trims; a cap near the
  mode flattens the distribution onto itself.
- **A floor near the mode hides modelling errors.** The 3000 ms pad sat right on
  top of a model producing 3.0 s, so the median looked plausible while the
  distribution underneath had been destroyed.
- **Audit each decision type separately.** Every failure above is invisible in a
  pooled histogram and obvious once the dealer's opening is split out. This is
  the single most useful habit to come out of the exercise.
- **Audit for empty buckets, not for medians.** All of it is invisible to a median.
- **Heavy tails have no edges to find.** This is the reason the profiles here use
  log-normal clusters rather than bounded noise, and it is not a detail — it is
  the difference between a model that can be tuned and one that cannot be fixed.
- **A mechanical floor and a behavioural model are different jobs.** Conflating
  them is what produced both the fingerprint and, when the floor was then lowered
  to fix the fingerprint, the lost turns in
  [04-click-reliability.md](04-click-reliability.md).

## Related

| Document | Contents |
| --- | --- |
| [`03-fitting-a-delay-model.md`](03-fitting-a-delay-model.md) | The fitted alternative, and the dealer-opening fix this prompted |
| [`04-click-reliability.md`](04-click-reliability.md) | The pad's mechanical role, separate from its effect on the histogram |
| [`06-what-gets-noticed.md`](06-what-gets-noticed.md) | Why session shape matters more than timing |
