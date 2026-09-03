#!/usr/bin/env python3
"""Fit a discard-timing model to the opponents in your own Mahjong Soul logs.

Reads Akagi game-gateway logs (JSONL), measures how long the *other three
players* took over each discard, and writes those numbers into a delay
profile.

The point is that the constants come from your tables, not from someone
else's. A model everyone downloads with identical numbers is a shape a
server can look for; a model each person fits to their own opponents is
not. See docs/03-fitting-a-delay-model.md.

    python3 fit-timing.py <log-dir> [<log-dir> ...]
    python3 fit-timing.py ~/akagi/data/logs --out my-delay.lua

Nothing is uploaded and nothing but aggregate statistics is written: the
tool never emits an account id, device id, game uuid or nickname.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# A discard faster than this is not a decision; it is the client
# auto-playing for an absent seat, or a misparse.
FLOOR_S = 0.05
# Longer than this and the seat has stopped playing, or the log has a gap.
CEIL_S = 60.0
# A seat that snaps this often is being auto-played by the client. Real
# players tsumogiri quickly but not relentlessly, and Mahjong Soul does
# not announce AFK auto-play the way it announces a disconnect.
AFK_SUBSECOND_RATE = 0.50
AFK_MIN_DISCARDS = 12
# Fewer samples than this and a fitted cell is noise.
MIN_SAMPLES = 60

TURN_GRANTS = ("ActionDealTile", "ActionChiPengGang")


def parse_ts(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


class Table:
    """One connection's worth of frames: up to a few games at one table."""

    def __init__(self, path: Path):
        self.path = path
        self.mode_id: int | None = None
        self.our_seat: int | None = None
        # seat -> list of (think_seconds, tsumogiri, is_dealer_opening)
        self.discards: dict[int, list[tuple[float, bool, bool]]] = defaultdict(list)
        self.disconnected: set[int] = set()


def read_table(path: Path) -> Table | None:
    t = Table(path)
    turn_at: dict[int, float] = {}
    # A seat's first discard of a kyoku is only an "opening" for the dealer,
    # who receives fourteen tiles at once and plays a hand-sort animation.
    dealer_seat: int | None = None
    opening_pending = False
    last_uplink_ts: float | None = None
    uplink_followers: defaultdict[int, int] = defaultdict(int)
    seat_discard_count: defaultdict[int, int] = defaultdict(int)

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None

    for line in lines:
        try:
            o = json.loads(line)
        except (ValueError, TypeError):
            continue
        method = o.get("method", "")
        payload = o.get("payload") or {}
        try:
            ts = parse_ts(o["ts"])
        except (KeyError, ValueError):
            continue

        # Our own actions leave the machine as inputOperation; the seat whose
        # discards keep following one is us. Nothing else in the frame says
        # which seat we are.
        if o.get("dir") == "up" and method.endswith("inputOperation"):
            last_uplink_ts = ts
            continue

        if t.mode_id is None:
            mode = payload.get("mode")
            if isinstance(mode, dict) and isinstance(mode.get("mode"), int):
                t.mode_id = mode["mode"]

        if method.endswith("NotifyPlayerConnectionState"):
            seat = payload.get("seat")
            if isinstance(seat, int):
                t.disconnected.add(seat)
            continue

        if method != ".lq.ActionPrototype":
            continue
        name = payload.get("name")
        data = payload.get("data") or {}
        seat = data.get("seat")

        if name == "ActionNewRound":
            turn_at.clear()
            # ju counts the dealership round-robin; the dealer is that seat.
            ju = data.get("ju")
            dealer_seat = ju if isinstance(ju, int) else None
            if dealer_seat is not None:
                turn_at[dealer_seat] = ts
            opening_pending = True
            continue

        if name in TURN_GRANTS and isinstance(seat, int):
            turn_at[seat] = ts
            continue

        if name != "ActionDiscardTile" or not isinstance(seat, int):
            continue

        seat_discard_count[seat] += 1
        if last_uplink_ts is not None and 0 <= ts - last_uplink_ts <= 1.0:
            uplink_followers[seat] += 1
            last_uplink_ts = None

        start = turn_at.pop(seat, None)
        is_opening = opening_pending and seat == dealer_seat
        if is_opening:
            opening_pending = False
        if start is None:
            continue
        dt = ts - start
        if not (FLOOR_S <= dt <= CEIL_S):
            continue
        t.discards[seat].append((dt, bool(data.get("moqie")), is_opening))

    if uplink_followers:
        best = max(uplink_followers, key=lambda s: uplink_followers[s])
        # Only trust it if that seat really is dominated by our uplinks.
        if uplink_followers[best] >= 0.5 * max(seat_discard_count[best], 1):
            t.our_seat = best
    return t


def opponent_samples(tables: list[Table]) -> tuple[list[tuple[float, bool, bool]], dict]:
    """Every opponent discard that survives the exclusions."""
    kept: list[tuple[float, bool, bool]] = []
    stats = {
        "tables": len(tables),
        "seats_seen": 0,
        "seats_dropped_disconnect": 0,
        "seats_dropped_afk": 0,
        "our_seat_unknown": 0,
    }
    for t in tables:
        if t.our_seat is None:
            stats["our_seat_unknown"] += 1
        for seat, rows in t.discards.items():
            if seat == t.our_seat:
                continue
            stats["seats_seen"] += 1
            if seat in t.disconnected:
                stats["seats_dropped_disconnect"] += 1
                continue
            if len(rows) >= AFK_MIN_DISCARDS:
                sub = sum(1 for dt, _, _ in rows if dt < 1.0) / len(rows)
                if sub > AFK_SUBSECOND_RATE:
                    stats["seats_dropped_afk"] += 1
                    continue
            kept.extend(rows)
    return kept, stats


def robust_lognormal(xs: list[float]) -> tuple[float, float]:
    """mu and sigma from the median and the interquartile range.

    The mean of the logs is dragged around by the handful of 30-second
    thinks that survive the ceiling; quantiles are not.
    """
    xs = sorted(xs)
    med = statistics.median(xs)
    q1, q3 = quantile(xs, 0.25), quantile(xs, 0.75)
    mu = math.log(med)
    sigma = (math.log(q3) - math.log(q1)) / 1.349 if q3 > q1 > 0 else 0.5
    return mu, max(sigma, 0.05)


# Shape of the occasional genuine tank — recounting discards, weighing a
# fold. Only its frequency is fitted; the shape is held fixed so that one
# number, not three, is being estimated from the tail of your sample.
LONG_MU, LONG_SIGMA = 1.50, 0.50
LONG_CAP = 0.30
SIM_N = 60_000


def fit_class(xs: list[float], seed: int = 12345) -> tuple[float, float, float]:
    """Fit mu, sigma and a long-thought rate to one class of discard.

    A single log-normal fitted to the body cannot reach the tail real
    players produce: it lands around 4% of discards at six seconds or
    longer where the measurement says closer to 7%. That gap is worth
    closing, because "how often does this player think for six seconds"
    is about the cheapest question a server can ask of a discard stream.

    So the body is fitted from quantiles, which the tail cannot drag, and
    then a second component is mixed in at whatever rate reproduces the
    observed share of long thoughts. Adding mass moves the median, so the
    level is re-centred and the pair iterated to a fixed point.
    """
    if not xs:
        return 0.7, 0.6, 0.0
    mu, sigma = robust_lognormal(xs)
    target_long = share(sorted(xs), lo=6.0) / 100.0
    target_med = statistics.median(xs)
    p = 0.0

    for _ in range(6):
        rnd = random.Random(seed)
        base = [math.exp(rnd.gauss(mu, sigma)) for _ in range(SIM_N)]
        rnd = random.Random(seed + 1)
        extra = [math.exp(rnd.gauss(LONG_MU, LONG_SIGMA)) for _ in range(SIM_N)]

        lo, hi = 0.0, LONG_CAP
        for _ in range(24):
            p = (lo + hi) / 2
            rnd = random.Random(seed + 2)
            sim = [b + (e if rnd.random() < p else 0.0) for b, e in zip(base, extra)]
            if sum(1 for s in sim if s >= 6.0) / len(sim) < target_long:
                lo = p
            else:
                hi = p
        p = (lo + hi) / 2

        rnd = random.Random(seed + 2)
        sim = [b + (e if rnd.random() < p else 0.0) for b, e in zip(base, extra)]
        drift = math.log(target_med) - math.log(statistics.median(sim))
        if abs(drift) < 0.002:
            break
        mu += drift

    return mu, sigma, p


def quantile(sorted_xs: list[float], q: float) -> float:
    if not sorted_xs:
        return float("nan")
    i = q * (len(sorted_xs) - 1)
    lo, hi = math.floor(i), math.ceil(i)
    if lo == hi:
        return sorted_xs[int(i)]
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (i - lo)


def share(xs: list[float], lo: float | None = None, hi: float | None = None) -> float:
    if not xs:
        return float("nan")
    n = sum(1 for x in xs if (lo is None or x >= lo) and (hi is None or x < hi))
    return 100.0 * n / len(xs)


def describe(label: str, xs: list[float]) -> str:
    if not xs:
        return f"  {label:<18} (no samples)"
    s = sorted(xs)
    return (
        f"  {label:<18} n={len(s):<6d} median={statistics.median(s):5.2f}s  "
        f"p25={quantile(s, 0.25):5.2f}  p75={quantile(s, 0.75):5.2f}  "
        f"<1s={share(s, hi=1.0):5.1f}%  >=6s={share(s, lo=6.0):4.1f}%  "
        f">=9s={share(s, lo=9.0):4.1f}%"
    )


def sample_class(mu: float, sigma: float, p_long: float, n: int, seed: int) -> list[float]:
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        x = math.exp(rnd.gauss(mu, sigma))
        if rnd.random() < p_long:
            x += math.exp(rnd.gauss(LONG_MU, LONG_SIGMA))
        out.append(x)
    return out


def verify(mu_t, sg_t, p_t, mu_h, sg_h, p_h, obs_t, obs_h) -> str:
    """Show what the fitted model produces next to what was measured.

    Compared in whole-second buckets because that is the resolution the
    server records: `timeuse` is an integer.
    """
    obs = sorted(obs_t + obs_h)
    if not obs:
        return "  (nothing to verify)"
    n_t = max(1, int(round(SIM_N * len(obs_t) / len(obs))))
    sim = sorted(
        sample_class(mu_t, sg_t, p_t, n_t, 991)
        + sample_class(mu_h, sg_h, p_h, SIM_N - n_t, 992)
    )

    def hist(xs):
        h = [0] * 13
        for x in xs:
            h[min(int(x), 12)] += 1
        return [100.0 * c / len(xs) for c in h]

    l1 = sum(abs(a - b) for a, b in zip(hist(obs), hist(sim)))
    fmt = lambda lbl, xs: (
        f"  {lbl:<12} median={statistics.median(xs):5.2f}s  <1s={share(xs, hi=1.0):5.1f}%  "
        f">=6s={share(xs, lo=6.0):4.1f}%  >=9s={share(xs, lo=9.0):4.1f}%"
    )
    verdict = "good" if l1 < 12 else "loose — collect more games" if l1 < 20 else "poor"
    return (
        f"{fmt('measured', obs)}\n{fmt('model', sim)}\n"
        f"  L1 distance {l1:.1f} percentage points ({verdict})"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fit a discard-timing model to opponents in your own logs."
    )
    ap.add_argument("logdirs", nargs="+", type=Path, help="directories to scan")
    ap.add_argument("--out", type=Path, help="write the profile here")
    ap.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).with_name("delay-template.lua"),
        help="Lua profile to fill in (default: delay-template.lua beside this script)",
    )
    args = ap.parse_args()

    files: list[Path] = []
    for d in args.logdirs:
        if d.is_file():
            files.append(d)
        else:
            files.extend(sorted(d.rglob("*game-gateway*.log")))
    if not files:
        print("no *game-gateway*.log files found", file=sys.stderr)
        return 1

    tables = [t for t in (read_table(f) for f in files) if t is not None]
    rows, stats = opponent_samples(tables)
    if not rows:
        print("no usable opponent discards", file=sys.stderr)
        return 1

    ordinary = [(dt, mo) for dt, mo, op in rows if not op]
    tsumogiri = [dt for dt, mo in ordinary if mo]
    tedashi = [dt for dt, mo in ordinary if not mo]
    openings = [dt for dt, _, op in rows if op]

    modes = sorted({t.mode_id for t in tables if t.mode_id is not None})

    print(f"\nlog files            {len(files)}")
    print(f"tables parsed        {stats['tables']}")
    print(f"opponent seats kept  {stats['seats_seen'] - stats['seats_dropped_disconnect'] - stats['seats_dropped_afk']}"
          f"  (dropped {stats['seats_dropped_disconnect']} disconnected,"
          f" {stats['seats_dropped_afk']} auto-played)")
    if stats["our_seat_unknown"]:
        print(f"  note: our own seat was unidentifiable in {stats['our_seat_unknown']} table(s);")
        print("        those tables contribute our discards to the baseline too.")
    if modes:
        print(f"mode_id seen         {', '.join(str(m) for m in modes)}")

    print("\nopponent discards, disconnects and auto-played seats excluded:")
    print(describe("all ordinary", [dt for dt, _ in ordinary]))
    print(describe("tsumogiri", tsumogiri))
    print(describe("tedashi", tedashi))
    print(describe("dealer opening", openings))

    thin = [n for n, xs in (("tsumogiri", tsumogiri), ("tedashi", tedashi)) if len(xs) < MIN_SAMPLES]
    if thin:
        print(f"\nWARNING: fewer than {MIN_SAMPLES} samples for {', '.join(thin)}.")
        print("         Play more games before trusting the fit.")

    mu_t, sg_t, p_t = fit_class(tsumogiri)
    mu_h, sg_h, p_h = fit_class(tedashi)
    if len(openings) >= 20:
        mu_o, sg_o = robust_lognormal(openings)
        opening_note = f"{len(openings)} measured openings"
    else:
        # Not enough dealer openings yet. Fall back to the hand-discard fit
        # shifted up, rather than inventing a number: an opening is a
        # fourteen-tile survey and is reliably slower than a mid-hand discard.
        mu_o, sg_o = mu_h + 0.9, max(sg_h, 0.38)
        opening_note = f"only {len(openings)} openings; extrapolated from tedashi"

    print("\nfitted parameters (log-normal in ln-seconds, plus long-thought rate):")
    print(f"  tsumogiri       mu={mu_t:+.3f}  sigma={sg_t:.3f}  long={p_t * 100:4.1f}%   median {math.exp(mu_t):.2f}s")
    print(f"  tedashi         mu={mu_h:+.3f}  sigma={sg_h:.3f}  long={p_h * 100:4.1f}%   median {math.exp(mu_h):.2f}s")
    print(f"  dealer opening  mu={mu_o:+.3f}  sigma={sg_o:.3f}              median {math.exp(mu_o):.2f}s  ({opening_note})")

    print("\nfit check — model against measurement, whole-second buckets:")
    print(verify(mu_t, sg_t, p_t, mu_h, sg_h, p_h, tsumogiri, tedashi))

    sub = share(sorted([dt for dt, _ in ordinary]), hi=1.0)
    print(f"\nOpponents put {sub:.1f}% of discards under one second. A minimum-delay "
          "setting\nfloors the sleep before click overhead is added, so anything much above\n"
          "700 ms puts that share out of reach. 600 is the measured compromise; see\n"
          "docs/03-fitting-a-delay-model.md#choosing-the-floor.")

    if args.out:
        if not args.template.exists():
            print(f"\ntemplate not found: {args.template}", file=sys.stderr)
            return 1
        text = args.template.read_text(encoding="utf-8")
        subs = {
            "__MU_TSUMOGIRI__": f"{mu_t:.3f}",
            "__SIGMA_TSUMOGIRI__": f"{sg_t:.3f}",
            "__P_LONG_TSUMOGIRI__": f"{p_t:.3f}",
            "__MU_TEDASHI__": f"{mu_h:.3f}",
            "__SIGMA_TEDASHI__": f"{sg_h:.3f}",
            "__P_LONG_TEDASHI__": f"{p_h:.3f}",
            "__MU_OPENING__": f"{mu_o:.3f}",
            "__SIGMA_OPENING__": f"{sg_o:.3f}",
            "__FIT_SUMMARY__": (
                f"{len(ordinary)} opponent discards "
                f"({len(tsumogiri)} tsumogiri, {len(tedashi)} tedashi, "
                f"{len(openings)} dealer openings) across {stats['tables']} tables"
            ),
        }
        missing = [k for k in subs if k not in text]
        if missing:
            print(f"\ntemplate is missing placeholders: {', '.join(missing)}", file=sys.stderr)
            return 1
        for k, v in subs.items():
            text = text.replace(k, v)
        args.out.write_text(text, encoding="utf-8")
        print(f"\nwrote {args.out}")
        print("Copy it over your Akagi configs/delay.lua; it hot-reloads on save.")
    else:
        print("\nRe-run with --out my-delay.lua to write a profile.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
