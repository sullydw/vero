# Clef `/v1/systemone` API — Reverse-Engineered Contract

Status: **validated end-to-end** (2026-11-16, session with Vera + Darryl).
Source: live probing of `https://ollama.com/v1/systemone`, documented as we went.

Clef is a *decision model*: it does not serve `/v1/chat/completions`. Any attempt
returns HTTP 400:

```json
{"error":"clef:27b is a decision model and only supports /v1/systemone"}
```

## Authentication

Same path every Hermes agent uses — nothing special:

- Endpoint: `https://ollama.com/v1/systemone`
- Header: `Authorization: Bearer $OLLAMA_API_KEY`
- The key lives in `.env`; never print or commit it.
- `GET /v1/models` with the same auth lists 24 cloud models, including `clef:27b`.

## Request schema

Fields are validated in order; each missing/invalid field produces a 400 whose
message names the next requirement (that's how the schema was mapped).

```json
{
  "model": "clef:27b",
  "state": "<string | object | array>  // the context packet / situation being judged",
  "questions": {
    "<question-id>": {
      "instructions": "<non-empty string — what to judge>",
      "type": "score | choice | noul",
      "criteria": ["<string>", "..."]        // required for type=score: 3-level legend worked
    }
  }
}
```

- `questions` must map **ids to objects** (ids are free-form strings: `joy`, `1`, `q1` all fine).
- `questions` accepts **1–64 entries** — the whole 14-feeling VERO catalog fits in one call.
- `state` is where the context packet goes: a plain string worked fine.

### Question types (all three validated 2026-11-16)

**`score`** — graded legend scoring.
- `criteria`: **array of strings** (numbers rejected) — becomes the `legend`.
- Response: `score` in range **0 … len(criteria)-1** (normalize: `score/(n-1)`),
  plus `confidence` and `probabilities` per legend entry.

**`choice`** — categorical pick.
- `criteria`: **object** mapping `option-id → option description`, 2–255 options
  (a single `"label"` key fails the count check).
- Response: `{"type":"choice","choice":"<option-id>","confidence":…,"probabilities":{…}}`.
- Verified: state "I just won the lottery" → `choice: "positive"`, conf 0.976.

**`noul`** — bare scalar, no criteria needed (and criteria as an array is rejected;
  must be an object if present at all).
- Response: `{"type":"noul","noul": <float 0..1>}` — no confidence, no probabilities.
- **Semantics: it answers the proposition as phrased in `instructions`**, not an
  objective underlying state. Verified 2026-11-16:
  | state | instructions | noul |
  |---|---|---|
  | "I just won the lottery" | "Overall mood?" | 0.9635 |
  | "My dog died…crying" | "Overall mood?" | 0.6975 |
  | "My dog died…crying" | "How positive is the overall mood?" | 0.0057 |
  | "I passed my exam!" | "Is this good news?" | 0.9929 |
- **Pitfall:** vague question → vague number. `noul` instructions must state the
  proposition sharply or the value is meaningless. The name's expansion is not
  documented — do not guess at it in code comments.
- Natural VERO use: one `noul` per tick as a cheap overall-valence readout
  (e.g. "How positive is the overall mood right now?"), alongside the 14 `score` gauges.

## Response shape (HTTP 200)

```json
{
  "model": "...",
  "answers": {
    "<question-id>": {
      "type": "score",
      "score": 1.9114,
      "confidence": 0.809,
      "legend": {"0": "...", "1": "...", "2": "..."},
      "probabilities": {"0": 0.97, "1": 0.02, "2": 0.01}
    }
  },
  "usage": {"input_tokens": 1513, "output_tokens": 0}
}
```

### Score calibration (important)

- Score range is **0 … len(criteria)-1**, NOT 0–1.
  With a 3-level legend the observed range was 0…~2.
  **Normalize: `t = score / (len(criteria) - 1)`.**
- Each answer carries `confidence` + per-legend `probabilities` —
  a free confidence readout per gauge.
- Single-question call example: `score=0.0315, confidence=0.9257`.

## Validation run (14 feelings, one call)

Synthetic packet (Monday 8:05pm, finished a render after 3 failed attempts,
forgot dinner, proud of the surface, "wish you'd been here"):

| feeling | score | conf |
|---|---|---|
| pride | 1.9114 | 0.809 |
| joy | 1.6424 | 0.310 |
| contentment | 1.4045 | 0.125 |
| frustration | 0.8599 | 0.198 |
| affection | 0.6723 | 0.140 |
| sadness | 0.4016 | 0.273 |
| trust | 0.2680 | 0.453 |
| anticipation | 0.2210 | 0.522 |
| nostalgia | 0.1408 | 0.673 |
| guilt | 0.1264 | 0.703 |
| surprise | 0.0824 | 0.811 |
| anger | 0.0457 | 0.885 |
| disgust | 0.0183 | 0.958 |
| fear | 0.0171 | 0.960 |

Verdict: ranking matches the packet's content (pride/joy/contentment on top,
threat emotions flat at zero). **14/14 answered in one request**, ~1,513 input
tokens, ~3 s wall clock.

## Known gaps / next investigations

- [x] `choice` question type — criteria object = option-id → description, 2–255 options (validated).
- [x] `noul` question type — bare 0..1 scalar, no criteria; answers the question *as phrased* (validated; see pitfalls).
- [x] Max batch behavior at 64 questions — **measured 2026-11-18**: 64/64 answers,
  1.2 s wall (19 ms/q), payload 19,732 B, no missing answers. Design: 4 probe
  feelings × 16 identical copies so the *same* instruction could be compared early
  vs late in the batch. **No positional decay** (deltas mixed-sign, small). What the
  run did expose is **intra-call variance**: sadness 1.8–13.6 (CV 51%), joy 6.9–19.3
  (CV 30%), frustration 18.2–39.4 (CV 20%), trust 36.0–51.5 (CV 8%) — i.e. a single
  score is a noisy draw, worst in relative terms for low-magnitude feelings. Batch
  size is not the risk; single-sample noise is (hence EMA).
- [ ] Whether `state` as an object/array changes interpretation vs. a string.
- [ ] Heater wiring into `gauges.py` — **DONE 2026-11-16**, see `heater.md`.
