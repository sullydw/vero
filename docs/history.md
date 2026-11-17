# Tick History Logging

Status: **wired and verified** (2026-11-16). File: `history.jsonl` beside
`state.json` in `$HERMES_HOME/feeling-gauges/`.

## Why local JSONL and NOT Supermemory

Darryl asked whether history should go through the existing self-hosted
Supermemory. Decision: **no — local file is the source of truth.**

| | `history.jsonl` | Supermemory |
|---|---|---|
| Query type | exact range/arithmetic ("last 24h", "did T track strength?") | semantic similarity |
| Values | exact floats, machine-parseable | embeddings → approximate retrieval |
| Portability | travels with the folder (VERO's hard requirement) | needs the container reachable |
| Failure mode | none (stdlib append) | API round-trip per tick |

Supermemory stays available for a **derived** qualitative layer later — e.g. a
weekly *"what happened on the board"* narrative digest written *from* the local
history. Same pattern as the rest of VERO: local file authoritative, external
systems get summaries, never the primary store.

## Record shape (one JSON object per line)

```json
{"ts": 1795000000.0, "iso": "2026-11-16T20:57:04", "dt_tick_min": 2.6,
 "packet": "<full context packet as sent to clef>",
 "clef":  {"joy": 9.8, "trust": 39.6, ...},
 "smooth":{"joy": 11.2, ...},
 "T":     {"joy": 13.3, "trust": 30.2, ...}}
```

- `packet` is the **full text** sent to Clef — this is what makes retrospective
  "why did frustration spike at 20:57?" answerable (original design:
  timestamped packet → Clef output → gauge state).
- `clef` = raw strengths, `smooth` = post-EMA, `T` = gauge temps **after heat**.
- `dt_tick_min` matters: target-seeking heat depends on elapsed time, so the
  log records exactly how much each tick could inject.

## Ordering & failure rules

- History is appended **after** `state.json` is saved — a history failure can
  never leave a half-written board.
- `append_history` swallows exceptions and logs a warning: history is
  secondary; a disk hiccup must not fail a tick.
- The `history` subcommand is **read-only** (sha256-verified: state.json
  unchanged across reads).

## Commands

    python gauges.py history                 # last 5 records, top-3 gauges each
    python gauges.py history --n 20          # tail N
    python gauges.py history --n 7 --feeling frustration   # one gauge's trace

## Verification (2026-11-16)

- Harness (isolated state, mocked Clef, 241 ticks): records written every tick,
  all 7 keys present, parses clean; target-seeking assertions still ALL PASS
  (history addition did not disturb the heat model).
- Real board: first real record at `2026-11-16T20:57:04`, viewer renders,
  `--feeling` trace works, state hash stable across reads.
- Backup: `gauges.py.bak-pre-history`.

## Next investigations

- [ ] Growth rate: ~1–2 KB/record ≈ 1–2 MB per 1000 ticks — fine for months;
      revisit rotation only if the file ever gets huge.
- [ ] Analysis scripts (saturation check, T-vs-strength tracking) — feed the
      GAIN taste-watch with data.
- [ ] Weekly Supermemory digest (derived, optional) — parked behind dashboard.
