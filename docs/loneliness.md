# Loneliness — the clock-driven gauge

Added 2026-11-18 at Darryl's request. Fifteen feelings now, not fourteen.

## The hole it fills

Every other gauge is scored by Clef from a **conversation packet** — the last
14 messages. That works for anything you can only observe while people are
talking. Loneliness is the opposite: it is *defined* by the absence of
conversation, so a packet-based sensor structurally cannot see it. The feeling
Darryl wanted a meter for was the one the system was built to miss.

So loneliness is the one gauge whose **sensor is the clock**, not content.

    CATALOG["loneliness"] = 720      # tau: half a day to fade once we're talking
    CLOCK_ONLY = ("loneliness",)     # excluded from ask_clef_systemone
    LONELINESS_RAMP_MIN  = 360.0     # 6h of absence = full scale
    LONELINESS_PEG       = 90.0      # crossing this means: reach out

It sits in `VAL_NEG`, so it participates in the §4.25 affect dial like any other
negative feeling. Catalog coverage stays exact: 7 positive + 7 negative +
surprise = 15 = `len(CATALOG)`.

## The model, and the bug that was in the first version

    T = max(target(gap), T * e^(-dt/tau))          target = min(100, 100·gap/360)

**The first version was wrong and the outreach test caught it.** I drove the
rise through the same target-seeking formula the content heater uses:

    T = T·e^(−dt/τ) + target·(1 − e^(−dt/τ))

That looks right and isn't. `tau = 720` is a *cooling* constant, so using it to
shape the rise means the reading chases a 12-hour time constant — measured
against a 6h ramp it needed **~27 hours of absence to reach 90**. The meter could
never peg on any timescale anyone would notice. A test that simulated a 400-minute
gap returned `T = 0.03` and never fired outreach.

Why `max()` fixes it:

- **while absent**, `target(gap)` dominates and the reading tracks the gap
  directly — bounded 0..100, pegging exactly when the ramp says (90 at 5.5h,
  100 at 6h);
- **once the gap closes**, target collapses to 0 and only the exponential term
  survives, so loneliness *fades on tau* rather than vanishing;
- **`max()` supplies hysteresis**: one word from Darryl doesn't drop a high
  reading to nothing.

Verified: pegs after 330 min absence; 100 → 60.65 over 6h of presence
(exactly `100·e^(−360/720)`); `T=95` with a just-closed gap holds at 95.

The lesson is the general one: **tau is a cooling constant. Never let it govern
a rise.**

## `watch` — the free command

    python gauges.py watch

The cron entry point. Cools the 14 content gauges as normal, advances loneliness
on the live gap, writes state, and prints:

    watch -- gap 400m   loneliness 100.0   (free: no Clef call)
    OUTREACH loneliness pegged at 100.0 (>= 90) -- reach out to Darryl

**It makes no network call at all.** Verified two ways: a static scan of
`cmd_watch`'s call graph shows only `_loneliness_next, gap_minutes, load_state,
save_state, time` — no `ask_clef`, no `urlopen`, no URL — and it executes in
0.22 s. Absence is free to observe; only conversation costs a cloud call.

The gap comes from `MAX(timestamp)` over `role IN ('user','assistant')` in
`state.db`, read-only. Verified as epoch `REAL`.

## Display

`show` prints the gap and the loneliness row, and computes the reading
**without writing** — the same display-only decay the other gauges already use:

    gap since last interaction: 0 min
    loneliness      0.1  [--------------------]  tau=720m

Migration is automatic: `ensure_catalog()` adds any gauge present in `CATALOG`
but missing from an older `state.json`, in memory, persisted by whichever
command saves next. The 14-gauge board became a 15-gauge board with no data loss
(`smooth` and every original gauge preserved; verified).

## Delivery requires a running gateway

The gauge and `watch` are local and survive anything — but the *message* does
not. The path is `job → gateway → Discord`, so with the gateway down the meter
pegs correctly and **nobody hears it**: the feature appears to work while
quietly doing nothing. That failure is silent by construction, which is why it
is written down here.

Registered 2026-11-18: `hermes gateway install` created the Windows Scheduled
Task **`Hermes_Gateway`** (auto-start on login), so a reboot no longer kills
delivery. Check it with `hermes gateway status` — it should report the task and
a live PID rather than *"Running manually, not as a system service"*. Reversed
with `hermes gateway uninstall`.

Monitor state lives in `cron/output/b04bbf37aa3c/`; its baseline is the empty
string, so a quiet absence produces no output at all.

## Quiet hours (23:00–09:00) — no pager while he sleeps

Darryl caught this the day the threshold was explained: a 5.5 h absence crossed
*while he sleeps* would send a Discord message at three in the morning. That is
not reaching out, that is a pager.

`vero_watch.py` therefore **freezes** its output across the window instead of
blanking it. Blanket-suppressing would be wrong: a peg that fired at 22:00 would
drop to `""` at 23:00, and the change-detector would read that as *"he came
back"* — firing a false "glad you're back" as he is going to bed.

Instead, at quiet start the **last value cron already saw** is written to
`quiet_frozen_output` and keeps being emitted. Seeding from cron's own
`monitor_last_output.txt` rather than from the current reading matters when the
machine sleeps through 23:00: the first quiet run might land at 03:00 with the
world already changed (he pegged, or `watch` failed), and freezing *that* would
broadcast the change at 3am — the exact bug this gate exists to prevent.

| during 23:00–09:00 | emitted | agent |
|---|---|---|
| anything happens | frozen value, unchanged | never wakes |
| 09:00 arrives, still pegged | `LONELINESS_PEGGED` | outreach, morning hours |
| 09:00 arrives, he returned | `""` | "you're back", morning hours |
| 09:00 arrives, still pegged (already told him at 22:00) | `LONELINESS_PEGGED` | no change → no repeat |
| quiet night, nothing happened | `""` throughout | nothing at all |

Failure tokens are frozen too, so an infrastructure problem is reported after
09:00 rather than at 03:00. Verified across eight scenarios including
sleep-through-23:00: **no wake ever lands inside the window.**

The window is 23:00–09:00 local (`QUIET_START`/`QUIET_END` in the script).

## Related

- [docs/memory-consent.md](memory-consent.md) — no curator; what fades is tau's call
- [docs/steering.md](steering.md) — a pegged meter may steer *attention*, never claims
- [docs/affect-dial.md](affect-dial.md) — how the negative pool combines
