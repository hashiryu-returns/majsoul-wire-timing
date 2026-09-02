# What reaches the server, and what dies in the browser

Last updated: 2026-09-01

Which autoplay actions cross the gameplay WebSocket, and therefore where making things look human is worth any effort at all.

## Summary

| Action | Gameplay WebSocket | Consequence |
|--------|-------------------|-------------|
| Cursor movement, clicks that hit nothing | **Never sent** | Reproducing cursor paths is pointless |
| Left vs right vs double click | **Never sent** | Implementing input styles is pointless |
| Discards, passes, calls, wins | `inputOperation` / `inputChiPengGang` | **Matters** — content plus `timeuse` |
| Clicks on the settlement screens | Local only | One `confirmNewRound` at the end |

**The only design freedom that survives to the server is `timeuse`.** That is the whole reason this repository confines itself to `delay.lua` and one floor value.

## The RPCs the server sees

Uplink traffic on the gameplay WebSocket, as intercepted by Akagi's MITM proxy:

| RPC | Meaning |
|-----|---------|
| `.lq.FastTest.inputOperation` | Discard, pass, riichi, tsumo, ron |
| `.lq.FastTest.inputChiPengGang` | Chi, pon, kan |
| `.lq.FastTest.confirmNewRound` | Advance past a finished round |
| `.lq.FastTest.checkNetworkDelay` | Heartbeat |

Akagi's own click verification (`src/autoplay/verify.rs`) treats this uplink as the only proof that a click landed.

### Inside `inputOperation`

Present:

- Operation type — `1` discard, `0` pass, `7` riichi, and so on
- **`timeuse`**, the seconds spent deciding
- The tile and its index

Absent:

- Click coordinates
- Which mouse button, and how many times
- Hover duration. It is not merely untransmitted: Akagi counts it in `click_overhead_ms` and subtracts it from the sleep, so raising or lowering it moves the click no earlier or later and `timeuse` is unchanged

### How `timeuse` is treated

Akagi's bridge refuses to count `auto_operation: true`, or an implausibly large `timeuse`, as evidence that a human clicked — that combination is the client timing out and discarding on its own (`is_client_initiated` in `src/bridge/majsoul/mod.rs`). Note that the client does *not* always flag these: a turn lost because every press was swallowed comes back with `auto_operation: false` and a real elapsed time ([`04-click-reliability.md`](04-click-reliability.md)).

Put the other way round, **designing the delays is designing the `timeuse` distribution.** There is no other input to it, and no way to change the distribution by changing how the click is produced.

One qualification, because this is easy to get wrong. `timeuse` is timed from the draw frame through to the click, not across Akagi's sleep alone. Akagi accounts for this by subtracting `click_overhead_ms` from the sleep to hit its target — except at the functional floor, which clamps the sleep and therefore has the overhead added back on top of it. The floor is consequently the one local timing value that shifts what the server records ([`03-fitting-a-delay-model.md`](03-fitting-a-delay-model.md)).

## What stays inside the browser

The `mouseMoved`, `mousePressed` and `mouseReleased` events Akagi sends over the Chrome DevTools Protocol are handled entirely within the page. An uplink RPC appears only once the Mahjong Soul client decides some interface element was actually operated.

```
CDP mouse events
  → Laya hit testing (local)
  → if a control was hit: inputOperation etc. (to the server)
```

The click sequence in `cdp_input.rs` — move, wait for hover, press, hold, release — is local from start to finish.

## Implemented

| Feature | Configuration | Server-visible effect |
|---------|---------------|----------------------|
| Think time | `delay.lua`, `min_delay_ms` | **`timeuse`** |
| Discarding | One left click on the drawn-tile slot, `get_pai_coord(13, …)` | `inputOperation` type 1 |
| Passing on a call | One left click on the Pass button, `MajsoulOpType::None` | `inputOperation` type 0 |

## Deliberately not implemented

| Feature | Reason |
|---------|--------|
| Right-click to pass or discard | Produces a byte-identical uplink to a left click |
| Double-click shortcuts | Same |
| Clicking through settlement screens | Built, proved unreliable, removed in 2026-08 |
| Cursor paths between tiles | Never reaches the WebSocket |
| Re-queueing between matches | **The single most detectable thing available** |

### Right-click and double-click

Passing produces `inputOperation` with `type: 0` whether it came from the Pass button or a right-click shortcut. A tsumogiri is `type: 1` either way. Since the two are indistinguishable to anything watching the WebSocket, and supporting both means depending on coordinates and on client settings, `Step::RightClick` and its configuration were removed from Akagi entirely.

Leave the Mahjong Soul client on **Single-Click**:

| Mahjong Soul setting | Value | Why |
|----------------------|-------|-----|
| Discarding Tiles | **Single-Click** | One left click on the drawn-tile slot |
| Double-Click to Skip & Discard | Off | Unused; identical RPC |
| Right-Click to Skip & Discard | Off | Unused; passing goes through the Pass button |

### Clicking through settlement screens

**Removed as a feature in 2026-08 because it never worked reliably.** Neither `src/autoplay/majsoul/round_advance.rs` nor the `click_settlement_confirm` and `settlement_*` keys under `[autoplay.majsoul]` exist any more.

Removing it changed nothing about the RPCs. The settlement sequence breaks down as:

1. Hand reveal, with a confirm button — local interface only
2. Point transfers, with a confirm button — local interface only
3. Once both have finished, the client sends `confirmNewRound` exactly once

**The final RPC is identical no matter how you got there.** The only thing that varies is elapsed time between `ActionHule` and `confirmNewRound`. Measured, the button cannot be pressed before 13.1 seconds after a win or 6.9 seconds after an exhaustive draw, because the animation is still running; left alone, the client sends it at around 17-18 seconds and 10.2 seconds respectively. The practical consequence is that our confirmation is usually the last one at the table — see [`02-match-lifecycle.md`](02-match-lifecycle.md).

## Telemetry, on a separate path

Beacons to Aliyun SLS and similar endpoints are unrelated to the gameplay WebSocket. Akagi can stop forwarding them with `block_telemetry = true`. Whether they carry cursor paths is a separate question from everything above, and **anyone reasoning only about WebSocket traffic needs to treat telemetry as its own problem.**

A client could in principle inspect input before deciding what to send, but mouse events themselves do not flow over the match WebSocket. The reach-or-not distinction in this document is strictly about gameplay RPCs.

## From the watcher's side

Available from WebSocket logs alone:

- [ ] The `timeuse` distribution for discards, passes and calls
- [ ] Agreement between discards and Mortal's recommendation
- [ ] Time from a win to `confirmNewRound`, and where that falls among the four players
- [ ] `auto_operation` and outlier `timeuse` values from timeouts
- [ ] Login frequency — **by far the cheapest query**

Not available:

- [ ] Cursor paths
- [ ] Right click versus the Pass button
- [ ] How many times the settlement screens were clicked, or where

## Related code

Paths are in [Akagi](https://github.com/shinkuan/Akagi) v3, the client these
captures came from.

| Location | Contents |
|----------|----------|
| `src/autoplay/verify.rs` | Counts uplink RPCs |
| `src/bridge/majsoul/mod.rs` | Parses `inputOperation` |
| `src/autoplay/cdp_input.rs` | The local click sequence |
| `src/autoplay/majsoul/coords.rs` | Coordinate calculation |
| `src/autoplay/manager.rs` | Retry and recovery policy |
| `../delay-template.lua` | The think-time model this repository fits |

## Related

| Document | Contents |
|---|---|
| [`02-match-lifecycle.md`](02-match-lifecycle.md) | The same traffic followed through one session in order |
| [`03-fitting-a-delay-model.md`](03-fitting-a-delay-model.md) | What to do with the one channel that is visible |
| [`06-what-gets-noticed.md`](06-what-gets-noticed.md) | Where each of these sits among the things that get accounts banned |
