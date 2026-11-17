# VERO

Feelings gauge system for the Vera AI agent. *(VERO = Vera + echo.)*

## Concept

Transform conversational context into quantifiable emotional states that decay
over time, visualized as personalized "temperature" gauges.

One temperature gauge per human feeling; a fast classifier reads a "context
packet" (a slice of live conversation + local clock time) and assigns strengths
across the catalog; strengths inject heat; every gauge cools on its own with a
per-feeling half-life — Newton's law of cooling applied to affect:

    T(t) = T_prev * exp(-dt_min / tau)

Decay is computed lazily on read — there is no daemon and none is wanted.

## Status (2026-11-16)

**v0 core + heater are working.** The board runs on this machine
(`$HERMES_HOME/feeling-gauges/gauges.py`, stdlib-only Python).

- [x] Context packet collection (last N exchanges from the conversation store + clock)
- [x] Clef integration — via the validated `/v1/systemone` batch endpoint
- [x] Decay engine with per-feeling tau (14 feelings, tau table in `gauges.py`)
- [x] CLI gauge display with bars (`show`)
- [x] Kill switch (`toggle off` freezes heat *and* cooling) + 60 s call throttle
- [x] First real heating done; throttle/kill-switch regressions re-verified
- [ ] Dashboard / visualization beyond the CLI
- [ ] Logging & historical analysis
- [ ] Packaging for other PCs (portable Python pkg + PyInstaller exe — planned, not built)

**Design stance:** *passive first.* v0 measures and displays only. How gauges
should affect Vera's replies is deliberately deferred to a later phase.

## Documentation

| Doc | Contents |
|---|---|
| [docs/clef-systemone-api.md](docs/clef-systemone-api.md) | Full Clef `/v1/systemone` contract: schema, all three question types (`score`/`choice`/`noul`), score calibration, validation runs, pitfalls |
| [docs/heater.md](docs/heater.md) | How the heater was wired into `gauges.py`, design decisions, verification evidence, next investigations |
| [docs/history.md](docs/history.md) | Tick history logging: record shape, why local JSONL (not Supermemory), ordering/failure rules |
| [docs/dashboard.md](docs/dashboard.md) | Self-contained dashboard.html: design, verification, regeneration notes |
| [docs/analysis.md](docs/analysis.md) | `analyze.py`: plain-language questions over history, routing, grounding, narrator model |
| [docs/affect-dial.md](docs/affect-dial.md) | Overall affect dial: VA §4.25 per valence pool, why the 14-gauge combine was rejected, bounds and verification |
| [roadmap.md](roadmap.md) | Phased plan with current check-offs |

## Portability requirement

VERO must be installable on another PC. Planned shape: zero-dependency Python
package (stdlib only) with state as plain JSON, plus a PyInstaller one-file
build for machines without Python. The Clef analyzer is cloud-hosted
(`https://ollama.com/v1/systemone` + `OLLAMA_API_KEY`), so no local model
is needed on the target machine.

## External research

Surveyed three existing emotion engines before building — reuse verdicts in
the feeling-gauges skill's `references/emotion-engines-survey.md`
(affectus: decay math + CLI verbs; amygdala-memory: watermark pipeline +
dashboard; Elysium X 20: emotion-gated memory policy; all three: *skipped*
their hardcoded emotion vocabularies — Clef is the analyzer here).
