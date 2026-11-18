# VERO

Feelings gauge system for the Vera AI agent. *(VERO = Vera + echo.)*

## Concept

One temperature gauge per human feeling; a fast classifier reads a "context
packet" (a slice of live conversation + local clock time) and assigns strengths
across the catalog; strengths inject heat; every gauge cools on its own with a
per-feeling half-life — Newton's law of cooling applied to affect:

    T(t) = T_prev * exp(-dt_min / tau)

Decay is computed lazily on read — there is no daemon and none is wanted.

**Purpose (reframed 2026-11-17):** VERO is the continuity layer for affect
across the places context dies — compression, model swap, session boundary.
Measurement and display are built; the reason to build is that Vera's emotion
carries *as text* inside a session, and text loses the long-tau feelings first
(trust/guilt 12 h, affection 6 h) exactly when they matter most. Nothing else
in her stack carries affect across those breaks. Full rationale:
[docs/continuity.md](docs/continuity.md).

## Status (2026-11-18)

**v0 core, heater, history, dashboard, analysis, affect dial and portable
packaging are all working.** The continuity layer (compression, model swap,
session start) ships as the `vero-steering` plugin. The board runs on this
machine
(`$HERMES_HOME/feeling-gauges/gauges.py`, stdlib-only Python).

- [x] Context packet collection (last N exchanges from the conversation store + clock)
- [x] Clef integration — via the validated `/v1/systemone` batch endpoint
- [x] Decay engine with per-feeling tau (15 feelings, tau table in `gauges.py`)
- [x] CLI gauge display with bars (`show`)
- [x] Kill switch (`toggle off` freezes heat *and* cooling) + 60 s call throttle
- [x] First real heating done; throttle/kill-switch regressions re-verified
- [x] Target-seeking heat model (saturation root-caused and fixed — `docs/heater.md`)
- [x] Dashboard / visualization beyond the CLI — self-contained `dashboard.html`,
      bars + SVG sparklines, no server/JS/network (`docs/dashboard.md`)
- [x] Logging — append-only `history.jsonl`, one record per tick (`docs/history.md`)
- [x] Analysis — `analyze.py` answers plain-language questions over the history
      (`docs/analysis.md`)
- [x] Overall affect dial — VA §4.25 split by valence, signed net (`docs/affect-dial.md`)
- [ ] Packaging for other PCs (portable Python pkg + PyInstaller exe — planned, not built)

**Design stance:** *passive first, lifted in part (2026-11-17).* Gauge state may
steer Vera's **register and attention** — never her **claims** — and never
overrides what is plainly happening in the conversation. Everything not named in
that lift remains passive-first. The loop is capped one-directional across
sessions, and the decision is reversible by Darryl at any time. Full rationale:
[docs/steering.md](docs/steering.md).

This supersedes the earlier "deliberately deferred to a later phase" stance,
which held from v0 until 2026-11-17.

## Documentation

| Doc | Contents |
|---|---|
| [docs/clef-systemone-api.md](docs/clef-systemone-api.md) | Full Clef `/v1/systemone` contract: schema, all three question types (`score`/`choice`/`noul`), score calibration, validation runs, pitfalls |
| [docs/heater.md](docs/heater.md) | How the heater was wired into `gauges.py`, design decisions, verification evidence, next investigations |
| [docs/history.md](docs/history.md) | Tick history logging: record shape, why local JSONL (not Supermemory), ordering/failure rules |
| [docs/dashboard.md](docs/dashboard.md) | Self-contained dashboard.html: design, verification, regeneration notes |
| [docs/analysis.md](docs/analysis.md) | `analyze.py`: plain-language questions over history, routing, grounding, narrator model |
| [docs/affect-dial.md](docs/affect-dial.md) | Overall affect dial: VA §4.25 per valence pool, why the 14-gauge combine was rejected, bounds and verification |
| [docs/steering.md](docs/steering.md) | How gauge state may affect Vera: register/attention yes, claims no, capped loop, damping — the partial lift of passive-first |
| [docs/continuity.md](docs/continuity.md) | **Purpose reframe:** VERO as the continuity layer across compression / model swap / session end; four-point architecture; why long-tau feelings lose to text carry |
| [docs/memory-consent.md](docs/memory-consent.md) | **Design constraints:** no curator (what happened stays, what fades tau decides, binds Vera not Darryl) and the one exception — consent-gated deletion with Vera's durable veto |
| [docs/loneliness.md](docs/loneliness.md) | The clock-driven 15th gauge: absence as sensor, why tau must never govern a rise, and the free `watch` command that powers the outreach cron |
| [roadmap.md](roadmap.md) | Phased plan with current check-offs |

## Portability requirement

VERO must be installable on another PC. **Delivered 2026-11-18** — the package
ships both paths, so the target machine needs no matching toolchain:

    with Python:     python gauges.py init && python gauges.py show
    without Python:  gauges.exe init      && gauges.exe show

Both exes are one-file PyInstaller builds (stdlib only, no installer), and
state is written to `./feeling-gauges/` **beside the executable** — so the
folder is the whole package and copying it preserves its own history.
Precedence: `VERO_HOME` → beside a frozen exe → Hermes home. `.env` is read
beside the board first, then Hermes home.

The Clef analyzer is cloud-hosted (`https://ollama.com/v1/systemone` +
`OLLAMA_API_KEY`), so no local model is needed on the target machine; without a
key, `--stats` still works and a narrated question degrades instead of crashing.

Build and the full command list: see `README-PORTABLE.md` in the package.

## External research

Surveyed three existing emotion engines before building — reuse verdicts in
the feeling-gauges skill's `references/emotion-engines-survey.md`
(affectus: decay math + CLI verbs; amygdala-memory: watermark pipeline +
dashboard; Elysium X 20: emotion-gated memory policy; all three: *skipped*
their hardcoded emotion vocabularies — Clef is the analyzer here).
