# Did the click land?

Last updated: 2026-09-01

Every other document here asks whether our traffic looks human. This one asks a
prior question: **did the click do anything at all?**

It gets its own document because the two concerns pull against each other. An
earlier press looks more human and is likelier to be swallowed, and a swallowed
press does not produce a missing discard — it produces the loudest single signal
we can emit. Tuning timing without watching this is how the calibration
work briefly made things worse.

## How a lost click is detected

A synthetic click reports success whether or not the client did anything with
it: the page dispatched the events, and nothing downstream disagrees. The
client's own uplink is the only proof. Accepting a discard, a call or a win makes
it send `inputOperation` or `inputChiPengGang`, so a press followed by one of
those landed, and a press followed by silence did not (`src/autoplay/verify.rs`).

Akagi takes a counter snapshot before pressing and checks afterwards whether the
count moved. If it did not, it presses again, up to `click_retries` times, each
time confirming that the decision window is still the one the plan was made for.
After `reload_after_failures` consecutive dead decisions it reloads the page and
reconnects into the hand.

## What the logs show

Across every session in both checkouts, against 5,928 of our own discards:

| | Count |
|---|---|
| Decisions needing at least one retry | 204 |
| Needing a second retry | 107 |
| Recovered by a retry | 118 (57.8%) |
| **Lost after every attempt** | **80** — 73 discards, 7 passes |
| Reloads to recover a dead client | 15 |

So roughly 3% of decisions need a retry and **1.3% are lost outright.** The
retry mechanism is doing real work; without it the loss rate would be about 3%.

## Why losing one is worse than it sounds

A lost discard does not mean the turn is skipped. It means nobody answers, the
turn timer runs down, and the client discards for us — a tile of its own
choosing, after draining the entire time bank. On the wire:

```
inputOperation {"moqie":true,"tile":"4z","timeuse":28,"type":1,"auto_operation":false}
```

That single frame carries a maximum-value `timeuse`, a tsumogiri nobody chose,
and an 8-second allowance plus a 20-second bank spent on one decision. It is the
most conspicuous frame these notes turned up, and it is the *client's* doing,
not something a profile can shape. Note also that `auto_operation` is `false` —
the client does not flag these, so they sit in our own `timeuse` distribution
looking like deliberate 28-second thinks.

**Reliability is therefore part of the fingerprint, not a separate concern.**

## Cause 1: the dealer's opening animation

Mahjong Soul plays a hand-sort animation when the dealer receives fourteen tiles
at once, and presses during it are dropped. `dealer_first_discard_extra_delay_ms`
exists to wait it out.

Measured over 127 of our own dealer openings, grouped by when the first press
landed after `ActionNewRound`:

| First press landed | Openings | Lost outright |
| --- | --- | --- |
| 2.5 s bucket | 10 | **10 (100%)** |
| 3.0 s bucket | 39 | 2 |
| 3.5 s bucket | 21 | 1 |
| 4.0 s and later | 44 | **0** |

The animation clears at about 2.9 seconds — the earliest uplink among the
successes is 2.89 s. 45% of the openings that did succeed needed at least one
retry, and their uplinks cluster at 3.0–3.1 s: the first press was eaten and the
second landed.

At a pad of 2000 the first press lands at roughly 2.3 s, inside the animation,
and **10% of dealer openings were lost entirely.** The pad is 3000, which puts
the first press near 3.3 s.

This value was briefly lowered to 2000 during the calibration work, on the theory
that it was standing in for think time the model was not producing. That
diagnosis was wrong — the collapse it was blamed for came from the budget cap,
and is discussed in [03-fitting-a-delay-model.md](03-fitting-a-delay-model.md#the-dealers-opening-discard).
The cost of putting it back is negligible: against measured human openings, the
L1 distance is 18.6 points at a 2000 floor and 18.9 at 3000, with the same median
and the same modal bucket, because the model's own draw clears 3000 on 95% of
openings. **Do not lower it again.**

## Cause 2: the retry cadence

The retries themselves were the second half of that failure. `verify_input_ms` is
a flat 300 ms, so all three presses of a decision landed within about 1.3 seconds
of each other. That asks the same question three times. It is the right shape when
a button declined a press for its own reasons, and useless when the client is not
accepting presses *yet* — which is exactly the animation case, where an early
first press guarantees three early presses.

The wait now doubles per attempt — 300, 600, 1200 ms — spreading the presses
across about 2.1 seconds. This is free on the happy path: the wait polls at 20 ms
and returns the moment the uplink appears, so a longer ceiling costs nothing when
the press worked. The escalation of the press *shape* was already there: the
second press holds longer, the third also nudges the cursor mid-press.

## Cause 3: coordinates, for the rest

The remaining failures are not timing. Comparing the tiles involved in retried
discards against the distribution of all our discards:

| | Share of retries | Share of all discards | Enrichment |
| --- | --- | --- | --- |
| Hand discard (tedashi) | 76.4% | 63.2% | ×1.21 |
| Tsumogiri | 23.6% | 36.8% | **×0.64** |
| Terminal | 33.9% | 25.3% | ×1.34 |
| Honor | 36.2% | 33.1% | ×1.10 |
| Simple | 29.9% | 41.6% | ×0.72 |

Tsumogiri is the one discard that always clicks the same place — the fixed
drawn-tile slot — and it is the one that fails least. Hand discards, which need a
slot computed from the hand, fail more, and within them the tile classes Mahjong
Soul sorts to the ends of the hand fail most. **That points at coordinate
calculation rather than at render timing**, since waiting on a render would not
care which tile it is.

This is unresolved. `src/autoplay/majsoul/coords.rs` is where it would be fixed.
Two riichi declarations were lost outright in the corpus, which is the worst
version of this failure: if the declaration press is lost but the tile press
lands, the hand throws its intended riichi tile with no riichi behind it. Akagi
verifies riichi separately for that reason (`InputKind::Reach`).

## The render margin, and the floor

The floor exists for the same mechanical reason as the pad: a click issued before
the tile has rendered is silently lost. `min_delay_ms` has come down twice while
chasing the zero-second `timeuse` bucket
([03-fitting-a-delay-model.md](03-fitting-a-delay-model.md#two-clocks)),
and each step spends margin:

| `min_delay_ms` | Press lands after the draw frame | Evidence |
|---|---|---|
| 1000 (Akagi default) | 1187 ms | 3.4% retried, 1.3% lost outright |
| 600 | 946 ms measured | 164 discards, 2 retries, 0 lost |
| 250 (tried, reverted) | 596 ms measured | 176 discards, 1 retry, 0 lost |
| **600 (current)** | **946 ms measured** | **164 discards, 2 retries, 0 lost** |

The evidence above says render timing is not what currently fails — the failures
track tile position, not tile arrival — and both lowered floors bore that out.
Even 250, less than half the default's margin, lost nothing across 176 discards.

The floor came back to 600 for a distribution reason rather than a reliability
one ([03-fitting-a-delay-model.md](03-fitting-a-delay-model.md#choosing-the-floor)): 250 made our
tsumogiri snap-discards visibly quicker than the table. The useful conclusion
for this document is that the render margin is not the binding constraint
anywhere in the 250 to 1000 range, so **the floor should be chosen on
distribution grounds and simply watched here.** A lost turn stamps `timeuse: 28`
on the record and outweighs any distribution refinement, so keep checking.

## Watching it

All of these leave lines in `all.log`:

```bash
cd <repo root>
LOG=data/logs/<session>/all.log

grep -c 'pressing .* again (attempt 1)'      "$LOG"   # decisions needing a retry
grep -c 'never produced an input command'    "$LOG"   # decisions lost outright
grep -c 'stopped accepting presses'          "$LOG"   # recovery reloads
grep    'never produced an input command'    "$LOG"   # ...with coordinates
```

The give-up line includes the coordinates aimed at and the hover and hold
timings, which is what distinguishes "the press is landing in the wrong place"
from "a default never reached this config".

| Observation | Meaning |
|---|---|
| Retry rate around 3%, most recovered | Normal for this corpus |
| Retries on dealer openings | The pad is too short for this machine; raise it |
| Retries favouring particular tiles | Coordinates, not timing |
| Retries climbing right after a floor change | Render margin; raise `min_delay_ms` |
| `never produced an input command` on discards | Check for `timeuse` outliers in the same rounds |
| Recovery reloads at all | The client stopped accepting input; look for a modal or a resized window |

**Reliability figures are largely independent of the delay model.** Swapping one
model for a faster or slower one should not move them; if it does, the model is
pushing presses into an animation somewhere.

## Related

| Document | Contents |
|---|---|
| [`03-fitting-a-delay-model.md`](03-fitting-a-delay-model.md) | The floor, the pad's effect on the histogram, and the dealer-opening model |
| [`05-uniform-delay-models.md`](05-uniform-delay-models.md) | The audit that turned up the dealer-opening problem |
| [`06-what-gets-noticed.md`](06-what-gets-noticed.md) | Where a timeout tsumogiri sits among the things that get accounts noticed |
