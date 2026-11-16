# VERO Project Roadmap

Last updated: 2026-11-16 (post-heater session with Vera).

## Phase 1: Foundation — COMPLETE

- [x] Context packet collection (last N exchanges + local clock; reads `state.db` read-only)
- [x] Clef integration for feeling analysis — `/v1/systemone` batch endpoint,
      all three question types documented in `docs/clef-systemone-api.md`
- [x] Basic decay implementation with fixed tau → per-feeling tau landed too (see Phase 2)
- [x] Simple gauge display (CLI bars via `show`)
- [x] Kill switch (`toggle off`) + 60 s cadence throttle
- [x] First real heating 2026-11-16; regressions verified (`docs/heater.md`)

## Phase 2: Refinement — IN PROGRESS

- [x] Per-feeling tau configuration (14 feelings; tau table lives in `gauges.py`)
- [ ] Gauge visualization improvements (sparklines, dashboard)
- [ ] Logging and historical analysis
- [x] Validation with test conversations (probe runs: synthetic packet + live packet;
      `probe` subcommand is the read-only test harness)

## Phase 3: Polish

- [x] Smoothing and noise reduction (EMA, alpha = 0.6 — landed in v0)
- [ ] Configurable presets for different use cases
- [ ] Export/share gauge snapshots
- [x] Documentation and examples (this repo's `docs/` — ongoing as we go)
- [ ] **Packaging for another PC** (portable Python pkg + PyInstaller build) —
      hard requirement per Darryl; see README portability section

## Open questions / next investigations

- [ ] Watch real ticks before any `GAIN` retune — systemone returns independent
      0–100 strengths (not sum-to-100), so ticks run hotter than the original
      chat-heater design intended
- [ ] 64-question max-batch behavior (latency / per-question degradation)
- [ ] Does `state` as an object/array change interpretation vs. a plain string?
- [ ] Cadence defaults confirmation (`--min-interval 60` stands meanwhile)
- [ ] Possible one-`noul` valence summary dial per tick (see API doc's noul section)

## Exploration Ideas

- Cross-feeling inhibition (high curiosity reducing containment?)
- Contextual modifiers (time of day, baseline state)
- Fusion with voice/typing signals
- Adaptive feeling categories from Clef
- Emotion-gated memory policy (store/don't-store decisions, à la Elysium X 20)
- `choice` question type for discrete moods alongside the `score` gauges

## Standing design decisions (do not change unilaterally)

- **Passive first:** gauge state never influences reply behavior without a
  fresh decision from Darryl.
- **Kill switch mandatory** and built.
- **Parse-before-mutate:** a failed heater call must leave `state.json` untouched.
- Catalog: 14 feelings (Plutchik's 8 + affection, nostalgia, contentment,
  frustration, guilt, pride).
