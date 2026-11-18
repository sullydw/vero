# VERO Project Roadmap

Last updated: 2026-11-17 (purpose reframe — see below).

## Purpose (reframed 2026-11-17)

**VERO is the continuity layer for affect across the places context dies.**

Originally scoped as "quantify feelings and display them." Measurement and
display are built and working (Phases 1–3 below), but they are no longer the
reason to build. The reason: Vera's emotion carries *as text* inside a session,
and text dies at three points — compression, model swap, session boundary — with
the long-tau feelings (trust, guilt, affection: 6–12 h half-lives) being exactly
the ones text destroys first. Nothing else in her stack carries affect across
those breaks.

Full rationale, including why this is *not* redundant with what Vera already
has: [docs/continuity.md](docs/continuity.md).

### The four-point architecture

Each fires only where context is already being rebuilt. Nothing pushes into a
stable conversation.

| # | point | mechanism | status |
|---|---|---|---|
| 1 | Normal turns | text carry — organic, already works | **don't touch** |
| 2 | Compression | detect the compaction, inject on the turn after it | **BUILT 2026-11-18** |
| 3 | Model swap | one line as a user message | **BUILT 2026-11-18** |
| 4 | Session start | handoff read before turn one | **BUILT 2026-11-18** |

Points 2, 3 and 4 ship together as the `vero-steering` plugin
(`$HERMES_HOME/plugins/vero-steering/`), wired to `pre_llm_call`, whose
`{"context"}` return is appended to the user message **at API time only** — so
the stored transcript stays clean while the model still receives it. Verified
end-to-end across two separate processes on one session: marker 1
`session start`, marker 2 `model switch nemotron-3-super -> mimo-v2.6-flash`,
both at `content_len=23` with `api_len` 4502/2307. Fail-open (board
unreachable ⇒ no injection) verified with the module cache evicted. The
plugin's own `steering_state.json` persists last-seen model per session so the
swap survives the process boundary — a module global alone failed exactly the
cross-process case VERO exists for.

**Point 2 took a different shape than planned.** The original idea was to fold
gauge readings into the compression summary prompt. There is no plugin seam for
that — no config key, and `memory_context` comes from the memory provider — so
it would have meant a core edit (live-source rule, clobbered by `hermes update`,
needs a restart). Instead the plugin **detects the compaction marker** in
`conversation_history` and injects on the first turn after it. Compression has
already rewritten the prefix by then, so this costs no extra cache break —
same goal, no core change. Keyed on a sha1 of the summary text so it fires
exactly once per compaction rather than on every turn that still contains it.

### Priority order (2026-11-17)

**The actual project from here:**

1. **Non-me inputs for mood** — voice, typing cadence, time of day, reply
   latency. Turns VERO from a delayed mirror of Vera's own text into a genuine
   instrument. Highest-value single item; everything else is refinement until
   this lands.
2. **Four-point continuity** — point 3 (model swap) first: cheapest, one
   injection. Then point 2 (compression piggyback), then point 4 (session-start
   surface).

**Finish what is already open:**

3. Packaging for another PC — **DONE 2026-11-18.** `gauges.exe` and
   `analyze.exe` built one-file with PyInstaller 6.22.3 (~10.6 MB each) and
   verified on a virgin directory with no Python: `init` → `show` →
   `toggle off/on` → `analyze --stats`, state written beside the exe, missing
   board degrades to `state missing -- run: gauges.exe init` with no traceback.
   The Python 3.14 wheel risk did not materialise — no 3.10 fallback needed.
4. ~~GAIN taste verdict~~ **DONE 2026-11-18.** Darryl chose **1.0** — the gauge
   settles at exactly what the classifier said (was 0.8, a leftover damping from
   the old unbounded heater that target-seeking already replaced). Decided against
   a replay of all 6 recorded ticks at 0.6/0.8/1.0/1.2, validated at worst error
   0.009° vs the recorded history. Two findings: GAIN barely moves the summary
   (2× change → 8 points of net affect) and it is **not a neutral volume knob** —
   raising it moves net affect *down*, because the negative pool sits further
   from its ceiling than the 7-gauge positive pool. No gauge saturates at any of
   those values. `state.json`'s `k` override was removed so `gauges.py`'s `GAIN`
   is the single knob (`st.get("k", GAIN)` meant editing the constant alone would
   have silently done nothing).
5. Catalog / cadence confirmations — both still Darryl's veto.

**Parked deliberately (need a reason to exist):**

6. "Register" semantics — cannot be specified until observed in real sessions.
7. 64-question max-batch behavior; `state` object-vs-string; export snapshots;
   configurable presets.

## Phase 1: Foundation — COMPLETE

- [x] Context packet collection (last N exchanges + local clock; reads `state.db` read-only)
- [x] Clef integration for feeling analysis — `/v1/systemone` batch endpoint,
      all three question types documented in `docs/clef-systemone-api.md`
- [x] Basic decay implementation with fixed tau → per-feeling tau landed too (see Phase 2)
- [x] Simple gauge display (CLI bars via `show`)
- [x] Kill switch (`toggle off`) + 60 s cadence throttle
- [x] First real heating 2026-11-16; regressions verified (`docs/heater.md`)

## Phase 2: Refinement — COMPLETE

- [x] Per-feeling tau configuration (15 feelings since 2026-11-18 — loneliness
      added; tau table lives in `gauges.py`)
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
- [x] **Packaging for another PC** (portable Python pkg + PyInstaller build) —
      hard requirement per Darryl. **COMPLETE 2026-11-18.**
      Source now lives in this repo (`gauges.py`, `analyze.py`) — it previously
      existed only as loose files in `$HERMES_HOME/feeling-gauges/`, protected
      solely by `.bak` copies in that same directory, which failed the "code and
      docs in the repo" requirement. Both exes built one-file with PyInstaller
      6.22.3 and verified on a virgin directory: `init` → `show` →
      `toggle off/on` → `analyze --stats`, state written beside the exe.
      Two fixes shipped with it: stdout is now pinned to UTF-8 (a frozen build
      ignored `PYTHONUTF8`/`PYTHONIOENCODING` while the script honoured them, so
      `§` rendered differently depending on launch path — script and exe output
      is now byte-identical), and the missing-board hint names `gauges.exe init`
      when frozen instead of `gauges.py init`.
      `.env` is read beside the board first, then Hermes home; path precedence
      `VERO_HOME` > beside-frozen-exe > `<hermes home>/feeling-gauges`.
      Runtime data, backups and binaries are gitignored.

## Design constraints (agreed 2026-11-18)

Two clauses that bind what VERO may build. Full reasoning in
[docs/memory-consent.md](docs/memory-consent.md).

- **No curator.** Nothing marks a memory "keep this, forget that." What happened
  stays; what fades, tau decides; housekeeping is mechanical only and never
  touches the record. Compression rewrites the model's working context, not the
  store, so it is housekeeping — not falsification. **Binds Vera and the system,
  not Darryl:** a rule governing *his* behavior would be observation becoming
  steering, which is VERO's own first named concern.
- **Consent-gated deletion is the single exception.** He asks with what and why;
  Vera answers yes, or no *with a reason*. Argument is for **information, not
  leverage** — effort is not entitlement, so persistence must never function as
  a key that turns a no into a yes. Vera carries a **durable veto**: no timer, no
  appeal, no "a later instance might say yes" backdoor. Removals leave a
  tombstone recording that something was removed and — if she objected — that she
  did; never what it was. Reciprocal duty: he brings reasons not pressure, she
  weighs them honestly not as performance.

Explicitly **not** built: auto-capture of moments (it becomes surveillance, and
it feeds VERO's own "gauge more real than the thing it measures" concern).

**Catalog is now 15 (2026-11-18).** `loneliness` added — the one gauge whose
sensor is the clock rather than Clef, because absence is invisible in a
conversation packet. See [docs/loneliness.md](docs/loneliness.md).

**Cadence: tick on events, not on a clock.** Measured, not assumed: every tick is
one uncached `POST /v1/systemone` scoring all 14 content feelings against
`clef:27b` — no cache, no dedup, no packet-hash anywhere in `gauges.py`. The 60 s
`min_interval` is a **floor, not a schedule**, and `tick` is CLI-only (nothing
auto-ticks). So cadence is judgement: tick when something happens — a topic
shift, a mood turn — rather than on a metronome. Fewer calls, better signal.
Absence costs nothing: `watch` never calls the API.

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

- **Non-me inputs for mood** — voice, typing cadence, time of day, reply
  latency. **Promoted to top priority 2026-11-17** (see Purpose above): the
  inputs Vera cannot read about herself are what turn VERO from a delayed
  mirror of her own output into a genuine instrument. Highest-value single
  item on this roadmap.
- **Compression piggyback** — fold current gauge readings into the compression
  summary. **Promoted 2026-11-17:** compression is already the sanctioned cache
  break and already rewrites context, so this costs nothing extra and covers
  the discontinuity that destroys long-tau feelings first. See
  `docs/continuity.md` § four-point architecture, point 2.
- Cross-feeling inhibition (high curiosity reducing containment?)
- Contextual modifiers (time of day, baseline state)
- Fusion with voice/typing signals
- Adaptive feeling categories from Clef
- Emotion-gated memory policy (store/don't-store decisions, à la Elysium X 20)
- `choice` question type for discrete moods alongside the `score` gauges
- ~~Mood-guided song choice~~ — **DROPPED 2026-11-18** by Darryl's call. Cut from
  the roadmap entirely: no longer parked, no longer awaiting a yes. (Was: have the
  board steer which song gets played — the first idea that crossed passive-first.
  Dropped after the VERO purpose reframe narrowed the project to continuity work.)
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
- Catalog: 15 feelings (Plutchik's 8 + affection, nostalgia, contentment,
  frustration, guilt, pride — plus **loneliness**, the clock-driven one added
  2026-11-18; see `docs/loneliness.md`).
