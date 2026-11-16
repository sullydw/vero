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

## Next investigations

- [ ] Context packet currently comes from `state.db` last-session slice — confirm
      cadence/`--min-interval` defaults with Darryl (60s default stands meanwhile).
- [ ] `choice` / `noul` question types still unexercised (see `clef-systemone-api.md`).
- [ ] Whether independent-strength scaling (vs. sum-to-100) wants a GAIN retune after
      watching a few hours of real ticks.
- [ ] Passive-first still holds: nothing reads gauge state into reply behavior.
