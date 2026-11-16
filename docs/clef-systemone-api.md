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
- `type=choice` requires `criteria` to be an **object** (not yet exercised — untested).
- `noul` type: purpose unknown — not yet exercised.
- `state` is where the context packet goes: a plain string worked fine.

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

- [ ] `choice` question type — criteria object shape untested.
- [ ] `noul` question type — purpose unknown.
- [ ] Max batch behavior at 64 questions (latency, any per-question degradation).
- [ ] Whether `state` as an object/array changes interpretation vs. a string.
- [ ] Heater wiring into `gauges.py` — NOT done yet; parse-first-then-mutate rule applies.
