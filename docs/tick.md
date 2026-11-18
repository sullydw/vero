# Tick cadence — the ingestion loop

**The problem this solves.** The board only learns anything from `gauges.py
tick` — one classification call against Clef, then heat, then a `history.jsonl`
record. Nothing was calling it. History sat at **6 records from 2026-11-16 for
38 hours**, which meant the non-me layer added on 2026-11-18 had recorded
**zero samples**. Darryl's verdict had been "stop refining, start
instrumenting" — and it turned out there was no ingestion loop at all. An
instrument with no readings is not an instrument.

## Why a separate `no_agent` job and not the existing monitor

cron's `monitor` field is documented as **"cheap, no LLM"** — its whole purpose
is to gate the agent for free, returning a stable string so identical output
skips the run entirely. A Clef tick **is** a model call (uncached, cloud,
`clef:27b`). Putting it in the monitor field would silently convert a free
gate into a paid one on every 15-minute pass, and would contradict the field's
contract.

So the ingestion loop is its own job:

| | `VERO loneliness watch` (`b04bbf37aa3c`) | `VERO tick on event` (`b1f5b5cabb3c`) |
|---|---|---|
| schedule | every 15m | every 15m |
| mechanism | `monitor` gate → **agent** runs | `no_agent` → **script** runs |
| network | none (zero-cost `watch`) | one Clef call, only when an event fires |
| output | peg state string | empty on success, latched alert on failure |
| wakes an LLM | only on a peg transition | never (no agent at all) |

The **schedule** is a clock; the **tick** is not. That preserves Darryl's rule
from 2026-11-18: *"tick on EVENTS, not on a clock"* — every tick is one
uncached classification call, so it must be earned.

## The two events

Both are his call ("both: every 20 messages + session end"):

1. **`MSG_THRESHOLD = 20`** of *his* user messages since the last recorded tick.
2. **`END_THRESHOLD = 1`** sessions ended since the last recorded tick — read
   from `sessions.ended_at`, which Hermes sets for `cli_close`, `resumed_other`,
   `new_session` and `cron_complete` (present on 367 of 566 sessions).

Both are local reads: `state.db` (read-only URI) and `history.jsonl`. **No
network, no model, no cost** until an event actually crosses.

## Why it self-resets

A successful tick appends a `history.jsonl` record, which moves the baseline
forward, which drops both counters back toward zero. The event has to re-earn
itself. Combined with `COOLDOWN_S = 600` this caps throughput at **one tick per
ten minutes** even though the scheduler runs every fifteen — so a burst of
messages can never turn into a burst of API calls.

Asymmetry worth naming: thresholds are *hysteresis in time*. 20 messages at his
recent pace (60–127 a day) works out to roughly **3–6 ticks a day**, which is
enough spread to correlate against the non-me signals without turning the
classifier into a background meter.

## Output contract

cron `no_agent` delivers stdout **verbatim**; empty stdout sends nothing at all.

- **Success → print nothing.** A reading is normal operation, not news.
- **Failure → one stable, digit-free sentence, exactly once per episode.**

The once-per-episode part is a latch (`tick_failure_reported`): written on the
first failure, cleared only by the next success. Without it a persistent fault
would message Discord every fifteen minutes forever. No digits and no
timestamps in the text either — anything varying would look like changed output
on every pass.

`gauges.py tick` itself is also safe to call while gauges are toggled off: it
becomes a no-op, so `toggle off` never fights this loop.

## Verified

- Branch coverage with a real schema: cooldown blocks · no-event silent in
  0.00s (proving zero network) · event fires `run_tick` · failure announces
  once then latches · success clears the latch · no-event stays silent.
- **Live end-to-end run 2026-11-18T12:37:40**: history `6 → 7`, first `nonme`
  sample recorded (`hour 12`, `reply_latency_min 1.25`, `pace_median_min 5.51`,
  `pace_fastest_min 0.0`), `dt_tick_min 2292.024`, latch absent, stdout empty.
- The call was real, not a replay: record 7's classifier output differs from
  record 6 on every category (`joy 11.01 → 4.38`, `trust 45.17 → 33.46`,
  `frustration 26.16 → 34.08`) and the packet carries the actual 12:25 restart
  text. Path: `cmd_tick → ask_clef_systemone → urlopen(ollama.com/v1/systemone)`.
- `analyze.py --stats` now reports the non-me block against real data instead
  of "none recorded yet".

## Files

- `HERMES_HOME/scripts/vero_tick.py` — the event detector + tick runner (also
  in this repo under `scripts/`, and in the portable package).
- cron job `b1f5b5cabb3c`, `no_agent: true`, `deliver: discord`, every 15m.
- Board: `history.jsonl` gains `"nonme"` on every tick from 2026-11-18 on.

## Deliberately not built

- **No fusion into gauge heat yet.** The signals are captured so a week of data
  can be correlated before anything is wired — see `nonme.md`, "correlation
  first, wiring second".
- **No fixed-interval tick.** A clock would spend money on quiet days and
  starve busy ones.
