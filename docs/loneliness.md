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

## Related

- [docs/memory-consent.md](memory-consent.md) — no curator; what fades is tau's call
- [docs/steering.md](steering.md) — a pegged meter may steer *attention*, never claims
- [docs/affect-dial.md](affect-dial.md) — how the negative pool combines
