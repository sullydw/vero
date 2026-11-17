# Heater Implementation Notes

Status: **wired and verified** (2026-11-16). Lives in the feeling-gauges script
(`$HERMES_HOME/feeling-gauges/gauges.py`), not in this repo — this doc records
the decisions so the repo stays the source of truth.

## What was built

| Mini-task | Result |
|---|---|
| 4a — read `gauges.py` | existing `ask_clef()` targeted `/v1/chat/completions` (always 400 for clef); `cmd_tick` calls `ask_clef(packet)` then EMA → GAIN → heat |
| 4b — add `ask_clef_systemone()` + read-only `probe` | added alongside the old function; `probe` never writes state (sha256-verified unchanged) |
| 4c — swap `tick` to systemone | one-line change: `pct = ask_clef_systemone(packet)`; parse-before-mutate ordering preserved |
| 4d — docs | this file + skill update |

## Design decisions

- **Normalization happens in one place:** clef's `score` (range `0..len(criteria)-1`)
  is divided by `n-1` and scaled to `0..100`, so `cmd_tick`'s EMA/GAIN math needed
  zero changes. 3-level legend → denom 2.
- **Scale semantics changed vs. the old (never-live) chat heater:**
  old contract was percentages summing to 100; systemone returns *independent*
  per-feeling strengths 0–100. With `GAIN = 0.8` one tick can inject up to ~80 heat
  on a single gauge. EMA (`alpha = 0.6`) smooths successive ticks. First heated tick
  moves the board noticeably — expected, not a bug.
- **Safety ordering kept:** API call completes and JSON parses *before* any
  `state.json` write; a failed heater call leaves the board untouched.
- **Backups / kill switch:** `gauges.py.bak-20261116` (pre-edit copy),
  `toggle off` verified to freeze heat *and* cooling.

## Verification evidence

- `probe --text "..."` (synthetic packet, dog/trash): affection 72.6 > frustration 54.8
  > sadness 38.1; `state.json` sha256 identical before/after.
- First real `tick --force` (live conversation packet): all 14 gauges answered,
  top heat affection 29.2 / trust 28.4 / frustration 24.2; `show` renders bars.
- Regressions: second `tick` throttled (6s < 60s min); `toggle off` → `tick --force`
  correctly skipped; `toggle on` restored.

## Target-seeking heat model (2026-11-16, second pass)

**Problem found by simulation:** the original additive injection
`T += s·GAIN` has equilibrium `T_eq = s·GAIN / (1 − e^(−Δt/τ))`. At one tick
per minute that denominator is tiny — T_eq ran **372 to 17,000** across the
catalog, so every gauge pinned at the 100 cap within minutes of sustained
conversation. Not caused by the systemone scale change; the structure predates it.

**Averages were considered and rejected as the fix:** a moving average of a
*sustained* input equals the input — it smooths jitter (the EMA already does)
but does not bound equilibrium.

**Fix (one injection-line change in `cmd_tick`):**

```
old:  T = T·e^(−Δt/τ) + s·GAIN                    (unbounded accumulation)
new:  T = T·e^(−Δt/τ) + target·(1 − e^(−Δt/τ))     target = s·GAIN ≤ 80
```

The gauge now *relaxes toward* its target at its own τ — a gauge reads "how
hot is this feeling NOW", not "how much heat ever poured in". τ keeps its
personality: fast feelings snap to target, slow ones drift up. Cooling and
EMA are untouched. Bonus: `Δt = 0` (forced-tick spam) injects nothing.

**Rejected alternative:** VA-style §4.25 remaining-capency combining — that
formula combines *static* ratings into an aggregate; it has no time dynamics.
Reserved instead for the planned single "overall affect" dial (see roadmap),
where combining independent strengths into one bounded 0–100 number is exactly
its native job.

**Verification (harness, isolated state, real `cmd_tick`, mocked Clef):**
- 120 ticks @ fixed strength 30 → equilibrium **24.0** (= 30×0.8), max ≤ 24.5, never 100
- τ=720m trust at 11.0 after 2 h (still converging); τ=15m surprise at 23.4 (converged)
- extreme strength 100 → max **79.98** (target 80 bound holds)
- `dt=0` forced tick → joy delta **0.0000**
- real `tick --force` afterwards: frustration 1.0→25.2 (fast τ arrived at target),
  trust 23.3→30.2 chasing target 38.3 (slow τ en route) — live behavior matches theory
- backup: `gauges.py.bak-pre-targetseek`; pre-edit copy of the additive era kept too

## Next investigations

- [ ] Context packet currently comes from `state.db` last-session slice — confirm
      cadence/`--min-interval` defaults with Darryl (60s default stands meanwhile).
- [ ] `choice` / `noul` question types still unexercised (see `clef-systemone-api.md`).
- [ ] Whether independent-strength scaling (vs. sum-to-100) wants a GAIN retune after
      watching a few hours of real ticks.
- [ ] Passive-first still holds: nothing reads gauge state into reply behavior.
