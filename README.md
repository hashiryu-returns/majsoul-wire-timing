# majsoul-wire-timing

**What a Mahjong Soul client actually tells the server about how long you
thought — measured from intercepted traffic, not guessed at.**

Mahjong Soul stamps every action with `timeuse`: a whole number of seconds.
That integer is very nearly the entire behavioural trace a client leaves behind.
Mouse paths, hover, cursor jitter, idle movement, right-clicks, the time spent
staring at a settlement screen — none of it is transmitted. A tool that
randomises its mouse movement is decorating something nobody can see; a tool
with a recognisable `timeuse` distribution is legible from a database query.

This repository is the write-up of measuring that distribution across 96
intercepted tables, plus a script that fits a timing model to **your own**
captured opponents rather than shipping constants for everyone to share.

## What was found

- **`timeuse` is integer seconds, always.** Across 7,499 uplink actions, not one
  fractional value. Tuning click delays to odd millisecond values, on the theory
  that round numbers are identifiable, changes nothing the server can see.
- **Fitting a model to observed think times and then adding conditional bonuses
  double-counts.** One shipped implementation runs about 19% slow for exactly
  this reason — the bonuses describe behaviour already present in the
  distribution the base was fitted to.
- **The dealer's opening discard needs its own model.** Treated as an ordinary
  discard it collapses onto the budget cap: 62% of openings arriving in one
  whole-second bucket, against 15% for real dealers. Pooled statistics hide this
  completely, because it is one decision per kyoku.
- **Absent players are not all flagged.** Mahjong Soul auto-plays for an idle
  seat and emits no disconnect event. One such seat pushed an apparent opponent
  sub-second rate from 10.0% to 20.3%.
- **The client's clock and the proxy's differ by 390 ± 290 ms.** Comparing your
  reported `timeuse` against opponents' wall-clock intervals manufactures a
  deficit that does not exist.
- **A uniform random delay is trivially identifiable.** A widely used tool
  builds its delay as "random 1-2 s plus a constant", which yields no discards
  under a second where humans produce about 10%, and almost none in the 4-6 s
  range where humans produce 8-10%. Counting one bucket finds it.

## Fitting your own model

```bash
python3 fit-timing.py /path/to/akagi/data/logs
python3 fit-timing.py /path/to/logs --out my-delay.lua
```

It reads Akagi's `*game-gateway*.log` files, reconstructs how long each opponent
took over each discard, excludes disconnected and auto-played seats, fits a
log-normal per decision type with a long-thought component, and prints the
fitted model beside the measurement:

```
opponent discards, disconnects and auto-played seats excluded:
  all ordinary       n=2356   median= 2.02s  p25= 1.46  p75= 3.17  <1s=  9.5%  >=6s= 6.7%
  tsumogiri          n=870    median= 1.72s  p25= 1.28  p75= 2.47  <1s= 13.6%  >=6s= 3.6%
  tedashi            n=1486   median= 2.27s  p25= 1.58  p75= 3.64  <1s=  7.1%  >=6s= 8.5%
  dealer opening     n=52     median= 5.31s  p25= 4.44  p75= 6.96  <1s=  0.0%  >=6s=42.3%

fit check — model against measurement, whole-second buckets:
  measured     median= 2.02s  <1s=  9.5%  >=6s= 6.7%  >=9s= 1.8%
  model        median= 2.03s  <1s= 11.6%  >=6s= 6.7%  >=9s= 2.0%
  L1 distance 6.2 percentage points (good)
```

With `--out`, those numbers are written into
[`delay-template.lua`](delay-template.lua), which drops in as Akagi's
`configs/delay.lua` and hot-reloads on save.

Requires Python 3.10 or newer. No dependencies. Nothing is uploaded, and the
output contains no account id, device id, game uuid or nickname — only
aggregate statistics.

### The settings that go with it

A think-time model is only half of it. Four client-side values bound what the
model can actually produce, and the fitted profile assumes them:

| Setting | Value | Why |
| --- | --- | --- |
| `min_delay_ms` | 600 | A floor on the *sleep*, with click overhead added on top, so the observed minimum is ~946 ms. Higher and the model's sub-second mass is unreachable; lower and you snap-discard faster than the table |
| `dealer_first_discard_extra_delay_ms` | 3000 | Mechanical, not behavioural. The hand-sort animation swallows presses for ~2.9 s, and a swallowed opening costs the whole turn |
| `bank_use_fraction` | 0.45 | Raises the ceiling on one long thought from 8.67 s to 11.67 s, which the dealer opening needs — human dealers spend 15% of openings at nine seconds or longer |
| `bank_max_single_ms` | 8000 | Same ceiling |

Hover and inter-click delays are *not* on this list. They sit inside the
overhead that gets subtracted before the click, so moving them shifts time
between the sleep and the hover without changing when the click lands. They
cannot affect `timeuse` at all, and tuning them to odd millisecond values —
a popular idea — accomplishes nothing.

### Why fit rather than download

The model's value is that its output is indistinguishable from the players
around it. That property survives being one client among thousands. It does not
survive being a popular preset: a few hundred people emitting the same fitted
shape turns "human" into "users of this repository", a cluster tighter and
easier to filter than the default it replaced. That is precisely why the uniform
model discussed in
[`docs/05-uniform-delay-models.md`](docs/05-uniform-delay-models.md) is so
easy to spot — one hardcoded model, shipped to everybody.

So this repository ships the *procedure* and no fitted constants. The numbers in
the documentation are worked examples from one player's logs, quoted so the
reasoning can be checked. They are not meant to be copied, and
`delay-template.lua` will not run until something fills its placeholders.

## Documents

| | |
| --- | --- |
| [`01-what-the-server-sees.md`](docs/01-what-the-server-sees.md) | Action by action: what reaches the server and what dies in the browser |
| [`02-match-lifecycle.md`](docs/02-match-lifecycle.md) | Login to end of match, frame by frame, with real payloads |
| [`03-fitting-a-delay-model.md`](docs/03-fitting-a-delay-model.md) | **The main one.** Room measurements, the measurement traps, the fit, and how to check it |
| [`04-click-reliability.md`](docs/04-click-reliability.md) | Lost clicks, the hand-sort animation, and the timeouts they cause |
| [`05-uniform-delay-models.md`](docs/05-uniform-delay-models.md) | A read of one widely used tool's timing, and why it stands out |
| [`06-what-gets-noticed.md`](docs/06-what-gets-noticed.md) | Community ban reports read against detection cost — the interpretive chapter |

Start with `03` for the method, or `01` if you want to know what is worth
modelling in the first place. `06` is the one piece here that is inference
rather than measurement, and it argues that timing is the *least* important
thing on its own list — worth reading before deciding how much of this matters.

## Layout

```
.
├── fit-timing.py         Fits a model to opponents in your own logs
├── delay-template.lua    Profile skeleton; placeholders filled by the fit
└── docs/                 The measurements and the reasoning
```

## Scope and caveats

The measurements come from one player's captures across Bronze, Silver and Jade
rooms on the Japanese and English servers, taken over a few days. Gold and
Throne were never played and are not covered. Everything here describes what was
observed on the wire; **what the operator does with that data is not
observable**, and nothing in this repository should be read as a claim about
what is or is not detected in practice. Where inference appears, it is labelled.

The parsing targets [Akagi](https://github.com/shinkuan/Akagi) v3's gateway log
format because that is what produced the captures. Any proxy that records the
`.lq.ActionPrototype` stream with timestamps carries the same information.

This is a measurement writeup, published because the reasoning is more useful
than the constants and because most of what circulates on the subject is
folklore. Automating play violates Mahjong Soul's terms of service and can cost
you the account; that is your call to make, not this repository's to encourage.

## License

[MIT](LICENSE). The log format this parses belongs to Akagi, which is
Apache-2.0; no Akagi code is included here.
