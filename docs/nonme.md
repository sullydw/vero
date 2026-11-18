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

**Voice — DROPPED 2026-11-18 by Darryl's call** ("lets drop it. i think its a
dead end"). No longer parked awaiting a yes: this is out of scope.

*Why it is a dead end, on the evidence:*

- It needs a **core change at two points**, and VERO's standing rule is don't
  edit live Hermes core from here — so the cost is upstream work, not a plugin.
- The signal is **sparse**: 47 voice recordings across ~3 weeks (~2–3 a week),
  against 60–127 typed messages a day. Expensive to obtain, thin to learn from.
- **The mirror is already broken without it.** The instrument-vs-mirror argument
  only ever needed *one* input originating with Darryl, and four now flow every
  tick (`hour`, `reply_latency_min`, `pace_median_min`, `pace_fastest_min`) plus
  the clock-driven loneliness gauge. Prosody would have been the strongest
  single signal available, but it stopped being load-bearing.

The two blockers that made the decision easy, both verified 2026-11-18: **

1. *Provenance.* `transcribe_audio(..., source="voice_mode")` passes a label to
   the **STT call only**; it never reaches the message row. Verified:
   103,990 messages, zero with a voice `display_kind`; the only metadata keys in
   the whole store are `display_text`, `notification_category`,
   `gateway_input_owner`. Spoken and typed messages are byte-identical.
2. *Prosody.* The recording itself is **deleted the moment transcription
   succeeds** — `cli_voice_mixin.py:253` runs `os.unlink(wav_path)` on the
   non-failure branch; the file is preserved **only** if STT failed (line 247,
   "keep the source recording so long dictation is not lost"). So pitch, energy,
   speech rate and hesitation are gone before anything could read them. A disk
   sweep found 101 audio files, but they are all *synthesis* output
   (`tts_*.wav`, `voicedesign_*.wav`, `tmp*.wav`) — no dictation recordings.

So voice would need a core change at **two** points, not one:

- mark the message at submit time (provenance), **or**
- **compute-then-discard**: extract a few scalars from the wav *before* the
  existing unlink — mean pitch, pitch range, RMS energy, speech rate — store
  those, keep deleting the audio.

The second is the only version worth doing: it keeps the privacy property that
the unlink already provides (no spoken utterance ever persists) while yielding
the one signal text genuinely cannot carry — **how he actually sounded.** A bare
"is_voice" boolean would add almost nothing on its own.

Both were out of scope for VERO (live-source rule: don't edit Hermes core from
here). **Recorded as dropped rather than faked** — the absence stays documented
so nobody re-derives it as an open question later.

**What would reopen it** (nobody is building this): a non-core way to mark a
message as spoken, or Darryl speaking far more often. If it ever returns,
*compute-then-discard* above is still the only version worth doing — it keeps
the privacy property the existing unlink already provides.

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
- [tick.md](tick.md) — what actually RUNS a tick (the ingestion loop that gave
  these signals a first sample on 2026-11-18)
