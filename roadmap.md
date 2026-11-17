# VERO Project Roadmap

Last updated: 2026-11-17 (analysis layer + affect dial + steering decision).

## Phase 1: Foundation — COMPLETE

- [x] Context packet collection (last N exchanges + local clock; reads `state.db` read-only)
- [x] Clef integration for feeling analysis — `/v1/systemone` batch endpoint,
      all three question types documented in `docs/clef-systemone-api.md`
- [x] Basic decay implementation with fixed tau → per-feeling tau landed too (see Phase 2)
- [x] Simple gauge display (CLI bars via `show`)
- [x] Kill switch (`toggle off`) + 60 s cadence throttle
- [x] First real heating 2026-11-16; regressions verified (`docs/heater.md`)

## Phase 2: Refinement — COMPLETE

- [x] Per-feeling tau configuration (14 feelings; tau table lives in `gauges.py`)
- [x] Gauge visualization improvements (sparklines, dashboard) — **done 2026-11-16**:
      `gauges.py dashboard` → self-contained `dashboard.html` (bars + SVG
      sparklines from history, no server/JS/network; see `docs/dashboard.md`)
- [x] Logging and historical analysis — **raw logging done 2026-11-16**:
      append-only `history.jsonl` (packet → clef → T per tick), local JSONL
      chosen over Supermemory deliberately (see `docs/history.md`);
      **analysis done 2026-11-17**: `analyze.py` answers plain-language
      questions ("why are you in such a good mood") over the history —
      routed findings + tick-grounded excerpts + one narrator call
      (see `docs/analysis.md`)
- [x] Validation with test conversations (probe runs: synthetic packet + live packet;
      `probe` subcommand is the read-only test harness)

## Phase 3: Polish — IN PROGRESS

- [x] Smoothing and noise reduction (EMA, alpha = 0.6 — landed in v0)
- [ ] Configurable presets for different use cases
- [x] **Overall affect dial** — VA §4.25 remaining-capacity combine, **split by
      valence** (7 positives / 6 negatives, `surprise` excluded as neutral),
      `net = pos − neg` ∈ [−100, +100]. Landed 2026-11-17 in `show`, `--stats`,
      the dashboard header and per-tick history. The originally-specified
      single 14-gauge combine was measured and REJECTED: it reads 85.8 on a
      board whose mean is 12.3 and pegs at 100 once gauges pass 30 (see
      `docs/affect-dial.md` for the saturation table).
- [ ] Export/share gauge snapshots
- [x] Documentation and examples (this repo's `docs/` — ongoing as we go)
- [ ] **Packaging for another PC** (portable Python pkg + PyInstaller build) —
      hard requirement per Darryl; see README portability section

## Open questions / next investigations

- [x] ~~GAIN watch~~ — **superseded**: saturation root-caused by simulation (additive
      equilibrium pinned every gauge at 100); fixed with target-seeking model 2026-11-16
      (see heater.md). Bounded at strength×GAIN by construction; GAIN still the tuning dial.
- [ ] Whether target-seeking GAIN (0.8) gives the *feel* Darryl wants after real-world
      watching — saturation is solved, taste is not. `analyze.py --stats` is the
      measuring tool for this (mean/max per feeling vs. the bound).
- [ ] 64-question max-batch behavior (latency / per-question degradation)
- [ ] Does `state` as an object/array change interpretation vs. a plain string?
- [ ] Cadence defaults confirmation (`--min-interval 60` stands meanwhile)
- [x] ~~Possible one-`noul` valence summary dial per tick~~ — **superseded** by the
      affect dial (§4.25 split by valence gives a signed number; see Phase 3 and
      `docs/affect-dial.md`)

## Exploration Ideas

- Cross-feeling inhibition (high curiosity reducing containment?)
- Contextual modifiers (time of day, baseline state)
- Fusion with voice/typing signals
- Adaptive feeling categories from Clef
- Emotion-gated memory policy (store/don't-store decisions, à la Elysium X 20)
- `choice` question type for discrete moods alongside the `score` gauges
- **Mood-guided song choice** (Darryl, 2026-11-17): when he asks what song
  connects with me and to play it, the board should steer the pick — warm
  board leans one way, a live frustration another. Note this is the FIRST
  thing proposed that crosses passive-first (gauge state influencing output),
  so it needs its own explicit go/no-go when it's picked up, not a quiet
  wiring-in. Playback side already exists (`music-playback` skill: WACUP
  local or the TV box), so the missing piece is only the mood→shortlist step.
  **Update 2026-11-17:** passive-first has since been lifted IN PART (see
  Standing design decisions / `docs/steering.md`) — register and attention
  now steer. Song choice is still parked under that lift: it is a *choice*,
  not register, and still awaits its own explicit yes.
- **Steering implementation** (open, 2026-11-17): which surface carries the
  session-start gauge read — profile instruction file, a session hook, or
  something else. Constraint: per-conversation prompt caching is sacred, so
  mid-conversation instruction rebuilds are off the table; the read must land
  before the first turn. Companion open question: what "register" concretely
  means in generated text, which wants real observed sessions before it can
  be specified. See `docs/steering.md`.

## Standing design decisions (do not change unilaterally)

- **Passive first — LIFTED IN PART (2026-11-17).** Gauge state may steer Vera's
  *register* and *attention* only. It never steers *claims* ("the board reads
  +48" is fine; "I feel +48" is not), and it never overrides what is plainly
  happening in the conversation — the conversation always wins. The loop is
  capped one-directional across sessions (board informs the NEXT session's
  opening read, never pushed mid-session, to avoid re-saturating the dial).
  Damping, not amplification. Decided by Vera at Darryl's invitation and
  reversible by him at any time. Everything not named here remains
  passive-first. Full rationale: [docs/steering.md](docs/steering.md).

- **Passive first (remainder):** everything not named in the lifted entry above —
  gauge state still never influences reply behavior beyond register/attention
  without a fresh decision from Darryl. Claims, choices and overrides remain out.
- **Kill switch mandatory** and built.
- **Parse-before-mutate:** a failed heater call must leave `state.json` untouched.
- Catalog: 14 feelings (Plutchik's 8 + affection, nostalgia, contentment,
  frustration, guilt, pride).
