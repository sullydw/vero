# Overall affect dial (VA 38 CFR §4.25, split by valence)

One signed summary number for the whole board, shown in `show`, `--stats`, the
dashboard header, and written to `history.jsonl` on every tick.

    overall affect -- pos 69.5  neg 10.0  net +59.5

## The rule

§4.25 remaining-capacity combination — each claim takes only what is left:

    v = v + s·(1 − v)          iterated over the pool
    (equivalent closed form: v = 1 − Π(1 − s))

It reproduces the CFR worked examples exactly, which is the acceptance test for
`combine_remaining()`:

| inputs | expected | got |
|---|---|---|
| 60 + 30 | 72 | 72 |
| 40 + 20 | 52 | 52 |
| 60 + 40 + 20 | 80.8 | 80.8 |
| 10 + 10 | 19 | 19 |

The second arrow in Darryl's recorded examples (72→70, 52→50, 80.8→80) is the
VA round-to-nearest-10 display step. **VERO does not round** — a dial wants
resolution, so `net` is reported to one decimal.

## Why the split (the important part)

The original spec was one §4.25 combine over all 14 gauges. That was rejected
after measuring it, for two reasons.

**1. It saturates.** Over 14 terms the rule is `1 − (1−s)¹⁴`, which climbs a
cliff:

    every gauge at  5  ->  51.2
    every gauge at 10  ->  77.1
    every gauge at 20  ->  95.6
    every gauge at 30  ->  99.3

Measured on the live board at the time: **all-14 combined = 85.8** while the
plain mean of those same 14 gauges was **12.3**. A board whose average feeling
is 12 reading 86 has no headroom left to distinguish calm from intense — the
dial would sit pegged near 100 during any real conversation. That is the same
saturation class root-caused in the heater, reintroduced one layer up.
§4.25 assumes a *handful* of terms; it was written for two or three
impairments, not fourteen gauges.

**2. Negatives counted as affect.** Fear, anger and frustration *raised* the
dial, so a board full of dread read as high affect — useless for a number
meant to replace the valence dial.

## The shape that shipped

Same §4.25 rule, applied once per valence pool, then differenced:

    pos = §4.25(7 positives)          # joy trust anticipation affection
                                       # contentment pride nostalgia
    neg = §4.25(6 negatives)          # fear sadness disgust anger
                                       # frustration guilt
    net = pos − neg                   # −100 … +100

Live board at build time: **pos 79.0 / neg 29.0 / net +49.9**.

Range is usable where the board actually lives (7 gauges at level L):

    L= 0 ->  0.0     L=10 -> 52.2     L=30 -> 91.8
    L= 5 -> 30.2     L=20 -> 79.0     L=50 -> 99.2

**`surprise` is in neither pool.** It is valence-neutral — a spike says nothing
about good vs bad — so including it would corrupt `net`. Coverage is therefore
7 + 6 = 13 of the 14 catalog feelings, deliberately.

Bounds are exact: all-zero → net 0; all-100 → net 0 (both pools pegged);
negatives-only → net −100; empty input → 0.

## Where it appears

| surface | how |
|---|---|
| `gauges.py show` | header line after the ON/OFF line |
| `analyze.py --stats` | `affect :` line above the table |
| `gauges.py dashboard` | "Overall affect" card: big signed net, pos/neg, net sparkline, signed centre-zero track |
| `history.jsonl` | `"affect": {"pos", "neg", "net"}` appended per tick |

History records written before this change lack the `affect` key. Every reader
uses `.get()` and treats it as optional, so old and new records coexist — the
net sparkline stays `n/a` until ≥2 records carry it (by design).

## Storage decision

`affect` is **derived and stored**, not recomputed on read. Reason: it must be
a time series to be chartable, and recomputing from `T` on read would give a
value that silently changes as the board decays — a sparkline whose past points
move. Storing it at tick time pins each sample to the moment it was true.

It is still purely a function of `T` at that tick — no extra API call, no extra
state, no new failure mode. Failure to compute would block the append, so the
value is built before `append_history` is called with everything else.

## Verification performed

- All four CFR worked examples reproduce exactly through `combine_remaining()`.
- Pool coverage checked: 13/14 in exactly one pool, no overlap, `surprise`
  alone in neither.
- Bounds: all-zero, all-100, empty, negatives-only.
- `show`, `--stats` and dashboard all report the *same* pos/neg/net.
- `state.json` sha256 identical before/after `show`, `dashboard`, `--stats`.
- Kill switch regression re-run: `toggle off` → `tick` skipped → `toggle on`,
  state hash identical, history line count unchanged.
- Tick writes `affect` into history; dashboard div balance 35 open / 35 close.

Backups: `gauges.py.bak-pre-affect`.
