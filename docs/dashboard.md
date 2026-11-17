# Dashboard

Status: **wired and verified** (2026-11-16). Command: `gauges.py dashboard`
writes `dashboard.html` beside `state.json`.

## Design

- **Single self-contained HTML file** — inline CSS, inline SVG sparklines,
  zero JavaScript, zero network requests, zero external assets. Double-click
  opens in any browser; copying the folder to another PC copies the dashboard
  (portability requirement).
- **Read-only w.r.t. state**: reads `state.json` + `history.jsonl`, writes one
  html file. Running it never mutates the board (hash-verified).
- **Two cards:**
  1. *Current board* — 14 gauges sorted by temperature, colored bars
     (cool < 20 ≤ warm < 50 ≤ hot), value + τ per row, computed with lazy
     decay applied (same math as `show`), plus ON/OFF badge and record count.
  2. *History* — per-feeling SVG sparkline of T over the last 200 ticks.
     With < 2 history records a row shows `n/a` (correct: a line needs two
     points), so a fresh install isn't wrong-looking, just empty.
- `--out PATH` writes elsewhere (useful for testing without touching the real
  folder — note it still reads state/history from `$HERMES_HOME`).

## Verification (2026-11-16)

- Real board: HTML parses clean (balanced html/head/body/tables), 14 bars with
  inline widths, state.json sha256 unchanged across the run.
- Harness (241 records): 14/14 polylines render, 0 `n/a`, 35,898 bytes.
- Visual browser check pending — local Chromium not installed for automation;
  file handed to Darryl for his eyes (his call is the acceptance gate).
- Backup: `gauges.py.bak-pre-dashboard`.

## Next investigations

- [ ] Regeneration: currently manual (`dashboard` on demand). Later: regenerate
      after each tick, or a `--watch`/cron option. Manual is fine while ticks
      are sparse.
- [ ] Sparkline axis labels (first/last timestamp) once history spans hours.
- [ ] Overall-affect dial at the top (VA §4.25 combination) — see roadmap.
