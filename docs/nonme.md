# Non-me inputs — the layer that makes VERO an instrument

Started 2026-11-18. This is the roadmap's **highest-value single item** ("turns
VERO from a delayed mirror of Vera's own text into a genuine instrument").

## The problem it solves

Every gauge is fed by Clef reading a packet of **Vera's own words**. So the
classifier is downstream of the thing being measured: Vera's output is its input.
An instrument that only reads its own operator is a mirror with arithmetic.

The fix is inputs Vera cannot read about herself.

## What is captured (from `state.db` message timing only — no model, no new infra)

`nonme_signals()` in `gauges.py`, computed at tick time and written into every
`history.jsonl` record under `"nonme"`:

| signal | meaning | why it isn't Vera's text |
|---|---|---|
| `hour` | local hour of the tick | wall clock |
| `reply_latency_min` | minutes since **Darryl's** last message | his timing, not her words |
| `pace_median_min` | median gap across his last 20 messages | his rhythm |
| `pace_fastest_min` | his fastest recent exchange | his rhythm |

`reply_latency_min` is deliberately distinct from `gap_minutes` (which drives
loneliness): that is minutes since *either* party spoke, this is minutes since
*he* spoke — during a long turn of Vera's it keeps climbing.

Measured shape of his actual pacing (39 recent gaps): min 0.0, median 4.2,
max 42.7 minutes.

## What is NOT captured, and why

**Voice — cannot be instrumented honestly today.** `transcribe_audio(...,
source="voice_mode")` passes a label to the *STT call*, but the transcript is then
submitted as an ordinary user message with **no provenance marker**. Verified:
103,990 messages, zero with a voice `display_kind`; the only metadata keys that
exist are `display_text`, `notification_category`, `gateway_input_owner`. So a
voice message and a typed message are indistinguishable in the store.

Making this wireable needs a **core change** — mark the message at submit time —
which is out of scope for VERO (live-source rule: don't edit core from here).
Filed as a decision for Darryl, not faked.

**Typing cadence — no data exists.** There is no keystroke or inter-key timing
anywhere in the stack. Message-level gaps are the closest available proxy, and
that is already `pace_*`.

## Deliberately NOT fused into gauge heat (yet)

These signals are **captured first, fused later**. Wiring them into the heater now
would mean choosing which feeling they modulate — anticipation from pace?
contentment from hour? — out of intuition, before any data exists. That would be
inventing the very precision the instrument is supposed to supply.

The plan: let a real week of ticks accumulate `"nonme"` alongside `"clef"`, then
ask `analyze.py` whether pace/trust, latency/anticipation and hour/contentment
actually move together. **Correlation first, wiring second.** If a relationship
survives the data, fuse it; if not, the absence of one is itself a result.

## Where the signals surface

- `history.jsonl` → every tick record under `"nonme"` (append-only, alongside `clef`)
- `gauges.py show` → a `non-me: …` line
- `gauges.py snapshot` → `"nonme"` field in the exported JSON

## Related

- [continuity.md](continuity.md) — the instrument-vs-mirror argument in full
- [loneliness.md](loneliness.md) — the first non-me input (absence as sensor)
- [history.md](history.md) — record shape and why local JSONL
