# What actually gets accounts banned

Last updated: 2026-09-01

This is the interpretive chapter. Everything else in this repository reports
what was measured on the wire; this one reads community ban reports alongside
how expensive each behaviour would be to find from the operator's side, and
that reasoning is inference rather than observation.

It is here mainly to keep the rest of the repository honest, because it leads
to an uncomfortable conclusion: **timing is the least important item on the
list, and it is the only one this repository addresses.**

## The ordering

| # | Behaviour | Cost to detect | Where the fix lives |
|---|-----------|----------------|---------------------|
| 1 | Full automation: auto-rematch, auto-queue, auto-login | **Trivial** | Do not use it |
| 2 | Volume and session length | Cheap | Your habits, not a setting |
| 3 | High rating combined with high agreement to an AI | Moderate; needs replay analysis | Model and candidate choice |
| 4 | Discard timing | Moderate to high | **What this repository does** |

An enforcement pipeline naturally runs cheapest-first: narrow the field with a
query, then confirm the survivors by analysing their replays. The first two
items fall out of a single query over login and match timestamps. Timing only
becomes visible after building a per-account distribution and comparing it
against a population baseline. So perfecting item 4 is wasted effort if you are
doing item 1.

The table ranks behaviours. It deliberately leaves out
[account identity](#account-identity-which-is-not-a-behaviour), which is not one
and which can be cheaper to check than anything on it.

### Selection and conviction are different problems

The distinction that matters is which stage of that pipeline a behaviour belongs
to.

**Selection is cheap and metadata-only.** Logins per match, matches per day,
session span, account age, rank trajectory, accumulated reports — all of it is a
query over data the operator already stores, runnable across the whole
population nightly.

**Conviction is expensive.** Establishing that an account is bot-driven means
replaying its hands through a model and scoring agreement. That is real compute
per account, so it only runs against a shortlist.

Two consequences follow, and they set the priorities.

**Selection is where you actually get caught**, because it is the only stage
applied to everyone. And, less comfortably, **if you reach the conviction stage,
timing work does not help you.** Replay analysis does not examine `timeuse`
distributions; it asks whether the moves match the model — and a bot's moves are
the model's moves. Fitting a timing model lowers the chance of being *selected*
by a timing query, and does nothing at all once you have been selected by any
other route.

One premise here is contested. Conviction is only scarce while the operator is
the one paying for it, and above Gold it is not
([below](#conviction-is-not-only-the-operators-to-pay-for)). A second premise
fails outright against an account whose device is already on a list, since both
stages were paid for on a previous account
([also below](#after-a-ban-the-profile-is-the-liability)).

### How much to trust any of this

The ban reports are self-selected anecdotes from a Discord, with no denominators
and no control group. The clearest case — over ten accounts lost — combined
eight-hour days, a dozen-plus hanchan, rating above 95, and automated rematch.
Four variables, one outcome, no way to attribute it to any of them.

Read against that, one data point deserves more weight than it usually gets:
**an account running stock, unmodified autoplay timing for roughly 400 games was
not actioned.** Whatever protection timing customisation offers, it is not
visible in this evidence. Timing is ranked fourth here for a reason.

The population also skews. Most reported bans come from Chinese accounts, where
this tooling is used far more heavily, and enforcement effort is presumably
sized to that population. That makes the base rate elsewhere lower today. It
does not make it a guarantee, because attention can move.

## 1. Full automation

Most auto-rematch implementations take the same shape: the moment a match ends,
log out, log back in, re-queue. It is the simplest thing to build, and it leaves
behind an account that logs in exactly once per match. Nothing else on this list
is that easy to query for.

Reported outcomes:

- 10-12 games a day across two or three sessions, fully automated — **detected
  within two to three days**, login refused the following morning
- Eight hours a day, a dozen-plus hanchan, rating above 95 — **banned within
  three days to a week**, across more than ten accounts
- A different tool, one week at six east-only games a day — **temporary
  suspension**

Tools that synthesise mouse input rather than injecting packets have produced
bans too. **The pattern being recognised is the repetition of the session, not
how the clicks are generated.** Making the input more convincing does not help
when the login history is the giveaway.

The sequence after a match — `Confirm`, `Confirm`, `One More Match`, `Confirm` —
is tedious, and every implementation that automated it went down early. **Click
it yourself.**

## 2. Volume and session length

This is outlier detection on play volume, and the continuity of sessions matters
as much as the count.

| Pace | Outcome |
|------|---------|
| Eight hours a day, a dozen-plus hanchan, back to back | Banned in three days to a week |
| Four hours a day, six to eight hanchan | Around a month |
| One to five hanchan a day, averaging three, never above fifteen | 600 games, no action |
| Mostly login bonuses with occasional longer sessions | No action |

**The same total spread differently is a different signal.** Six hundred games
accumulated over a year at one or two a day reads as an ordinary player. The same
six hundred inside two months at ten hanchan a day does not.

## 3. Rating and agreement with an AI

This is what confirms a candidate once replay analysis begins. Reports place
**rating 95 and above in dangerous territory**; dropping into the 88-92 range
extended survival from about a week to about a month on the same tooling and a
similar schedule. That is the closest thing in the evidence to a controlled
comparison, and even it is confounded — the reporter changed volume and
agreement together.

Always taking the top suggestion leaves a signature in the replays that no
amount of timing variation can hide. Timing work does not reach this layer.

### The knob usually exists, and is usually off

Mortal, which most of these tools are built on, can be made to play
stochastically: `MortalEngine` accepts `boltzmann_epsilon`, `boltzmann_temp` and
`top_p`. With epsilon above zero, that fraction of decisions is sampled from the
softmax over Q-values instead of taken as the argmax.

Most integrations pass none of them, leaving the defaults of `0`, `1` and `1` —
**pure argmax on every decision**, which is the maximum-agreement configuration
available. The Chinese tooling exposes the same mechanism under a name that
translates roughly as "reduce duplication", and the reporter above credits it
for the difference between a week and a month.

The trade is direct and unavoidable: agreement *is* playing strength, and
lowering one lowers the other. Which is rather the point. An account that never
deviates from the model is making a claim about itself that no human can
support.

Nothing here recommends a value. Epsilon is the one that matters; temperature
and nucleus only shape the deviations it produces, and keeping nucleus below 1
is what stops a deviation from being an obviously terrible move rather than a
defensible second choice. **Any setting above zero costs points**, and how many
you should spend depends on how much rank you are willing to give up — which is
not a question measurement can answer.

What can be said is that this is **the only lever on this list that acts at the
stage where accounts are actually convicted**, and that leaving it at zero is
itself a choice.

## 4. Discard timing

The mildest item. Several reports describe 400-600 hands on stock settings
without consequence. It is still not free, for two reasons.

### The shape of the distribution

Shipped defaults mean every user of a given tool shares the same floor. But the
server receives `timeuse` as a whole number of seconds, so **nudging a floor by
a few milliseconds changes nothing** ([`02-match-lifecycle.md`](02-match-lifecycle.md)).
What matters is which second a value lands in, and the overall shape of the
histogram the model produces.

That cuts both ways. Moving a floor *across* a second boundary matters a great
deal: at a 1000 ms floor the observed minimum is about 1.34 s, because the floor
clamps the sleep and click overhead is then added on top, so the zero-second
bucket sits near 1% against a human 9-11%
([`03-fitting-a-delay-model.md`](03-fitting-a-delay-model.md#choosing-the-floor)).

Measurement turned up a concrete problem here. **A model that fits its base to
observed think times and then adds conditional bonuses double-counts, running
about 19% slow.** Refitting closes most of that gap
([`03-fitting-a-delay-model.md`](03-fitting-a-delay-model.md)). This is where the
available improvement in this layer actually is — not in the millisecond values.

Measurement also reversed an assumption worth stating, because the opposite is
widely believed: **opponents in the lower rooms are meaningfully slower**, with
Bronze running about 14% longer than Jade. Playing slowly does not become more
conspicuous as you climb.

And one decision was far worse than the aggregate suggested. **The dealer's
opening discard arrived in the same whole second 62% of the time**, against 15%
for real dealers, and the pooled figures hid it completely because it is one
decision per kyoku. A per-account histogram exposes a near-constant value on a
recurring decision immediately. The general lesson — **audit each decision type
separately, because a healthy overall histogram can contain a nearly
deterministic one** — is the most useful thing to come out of that work
([`03-fitting-a-delay-model.md`](03-fitting-a-delay-model.md#the-dealers-opening-discard)).

### Lost turns, which are worse than any of it

A press the client swallows is not a missing discard. The turn runs to timeout
and the client discards on its own: a tsumogiri of its own choosing, `timeuse`
stamped at the maximum, the entire time bank spent on one decision, and
`auto_operation` left `false` so it does not even read as an idle player. **One
of those frames is more conspicuous than any distribution mismatch discussed
here**, and they were occurring on 10% of dealer openings until the cause was
found.

Timing and reliability pull against each other — an earlier press looks more
human and is likelier to be swallowed — so a change to any floor has to be
checked against the retry rate rather than only against the histogram.
[`04-click-reliability.md`](04-click-reliability.md) covers the measurement.

### Being noticed at the table

Players in the higher rooms report recognising suspected bot accounts at a rate
of roughly one per four games, from things like unusually slow North
declarations, long pauses before passing on a call, and late riichi. That
perception is what starts a report. Above Gold it can then be followed up with
the replays themselves, and what happens to it after that is not encouraging
reading in either direction
([who pays for conviction](#conviction-is-not-only-the-operators-to-pay-for)).

## Account identity, which is not a behaviour

The four items above are things you do, and each can be stopped by doing
something else. What follows cannot. Identity is a property of the account and
the machine, it is attached before play begins, and no amount of careful play
detaches it.

That also puts it outside the cost ordering rather than somewhere within it. A
lookup against a known device is cheaper than the cheapest behavioural query on
the list, because it needs no aggregation and no time window — which is what
makes the post-ban case below the sharpest item in this chapter.

### The device ID links accounts to each other

Every login carries an explicit hardware block, so account linkage is not
something an operator has to infer — the client volunteers a join key:

```json
"device": { "device_id": "<profile uuid>", "os": "mac", "software": "Chrome", ... },
"random_key": "<profile uuid>"
```

`device_id` is a stable UUID kept in the browser profile's local storage and
resent on every login. Two rules follow from where it is stored:

- **Same profile, same region → same `device_id`.** Every account played through
  one profile reports one UUID, so they group with a single query.
- **Different region → different `device_id`.** Local storage is scoped per
  origin, so the JP and EN clients each mint and keep their own UUID even inside
  the same profile. Playing both does not link them.

Any tool that reuses one browser profile directory so logins survive restarts —
which is nearly all of them — therefore links every account played through it in
a given region. The reports agree that **a confirmed tool user loses every
linked account**, which makes linked accounts one unit rather than independent
trials.

To keep accounts separate, give each its own persistent profile directory, or
play one account per region. Two caveats: a shared egress IP links them
regardless, and randomising the ID per session is *worse* than sharing it,
because a stable account whose hardware appears to change daily is a louder
signal than the grouping it would have replaced.

### After a ban, the profile is the liability

The linkage above is simultaneous: accounts played through one profile group
together, and a confirmation on one takes the rest. The same key also works
forwards in time, and that case is worse.

A `device_id` attached to a confirmed ban is no longer a heuristic. It is a
labelled positive, and checking it costs one indexed comparison at login. Every
other item in this chapter needs accumulated behaviour before it says anything —
volume needs days, a timing histogram needs hundreds of discards, agreement
needs replays. A blacklisted device matches **before the first hand is played**.

That inverts the pipeline the ordering is built around. Selection and conviction
both already happened, on the previous account; what is left is a lookup. A new
account created after a ban and played through the surviving profile therefore
starts flagged, and patient, low-volume growth — which helps against everything
else here — buys nothing, because the flag precedes the behaviour it would
otherwise have to earn.

Whether an operator acts on such a match automatically is a separate question,
and inference. `device_id` is client-supplied local storage: clearable,
forgeable, and shared by everyone on one machine, so treating it as proof would
misfire on shared and family machines. Lowering a threshold for the accounts it
groups, or holding the group and sweeping it when one member is confirmed, costs
nothing and survives those objections.

The remedy is cheap and easy to miss. **After a ban, discard the browser
profile, not only the account.** A new profile directory mints a new UUID on
first login; creating a fresh account inside the old one is the single move that
guarantees the link.

### Account age

Not something the reports quantify, but it costs nothing to reason about. A
freshly created account that immediately produces daily heavy volume and a fast
rank climb is the cheapest possible query — age, games and rank delta are three
columns in the same table. An account with years of ordinary history behind it
has to be pulled out by something else first.

Judge age from the oldest badge timestamp in the login response rather than from
the account ID: IDs are not issued in creation order, and a numerically high one
can be years old.

## Conviction is not only the operator's to pay for

The ordering in this chapter rests on replay analysis being expensive, and
therefore rare enough that selection is the stage worth optimising against.
Third-party replay hosting weakens that assumption, and it is the one part of
the cost argument with a live counterexample.

Replays from Gold upward are uploaded to a public archive that publishes volume
rankings alongside its other statistics. Players who suspect an account report
batch-analysing its replays — think time, rating, agreement with a model — and
submitting the result to the operator as a written case.

Three consequences follow, none of them measured here:

- **Volume is publicly visible**, not merely inferable from data the operator
  holds. Appearing repeatedly in a heavy-play ranking is a selection event that
  occurs outside the operator entirely, and outside any schedule.
- **The expensive stage gets donated.** Volunteers absorb the compute that the
  cost argument assumed would keep conviction scarce, and they have no
  obligation to size their effort to a population.
- **A report can arrive pre-substantiated.** An operator handed a written case
  with agreement figures attached is not being asked to run the pipeline, only
  to check someone else's.

This is reported to be common in the Chinese community. What remains unclear is
the conversion rate, since well-documented collusion reports have also produced
nothing. Treat it as a route that exists rather than one with a known yield.

The practical reading is that the rooms above Gold cost more than their rank
suggests. The same behaviour becomes legible to a second set of eyes, working
without a budget and with considerably more patience than any nightly job.

## Tells that have nothing to do with timing

Behaviours visible to the table or the client that bots typically do not
reproduce. **Most never reach the gameplay WebSocket**
([`01-what-the-server-sees.md`](01-what-the-server-sees.md)), so they rank low,
but they can still prompt a report.

Invisible to the server:

- Cursor movement between tiles is uniform, with no path — the pointer teleports
- No dragging, ever
- Tsumogiri shortcuts go unused, though the resulting RPC is identical anyway

Visible to the server, and therefore more relevant:

- Whether a discard came from the hand or straight from the draw, transmitted as
  `inputOperation.moqie` (36.8% tsumogiri in these measurements)
- Auto-win and auto-North features never being used
- Round confirmations arriving last at the table, every time

## An open problem: the confirmation is always last

When nothing clicks through the settlement screens, the client's own timeout
sends the confirmation instead. Across 402 rounds it arrived last of the four
**77.9% of the time**, where an average player is last one round in four
([`02-match-lifecycle.md`](02-match-lifecycle.md#2-our-confirmation-is-always-last-at-the-table)).

Being consistently slowest at the table is cheap to query for, but on its own it
only identifies someone who is not touching the settlement screen — which
describes plenty of humans who step away between rounds. It corroborates; it
proves nothing.

Clicking sooner is not the fix either. Pressing the instant the animation clears,
every round, is as artificial a spike as the timeout, just in the other
direction. The fix is spread, and it remains unimplemented.

## Related

| Document | Contents |
|----------|----------|
| [`01-what-the-server-sees.md`](01-what-the-server-sees.md) | Which of the tells above can actually be seen from the server |
| [`02-match-lifecycle.md`](02-match-lifecycle.md) | The measurements behind the automation and confirmation figures |
| [`03-fitting-a-delay-model.md`](03-fitting-a-delay-model.md) | What can be done about item 4 |
| [`04-click-reliability.md`](04-click-reliability.md) | Lost turns, the loudest signal on the list |
