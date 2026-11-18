#!/usr/bin/env python3
"""VERO loneliness watch — the cron monitor that decides whether Vera wakes up.

Two jobs in one, deliberately:

  1. advance the clock-driven loneliness gauge (and cool the content gauges) by
     running `gauges.py watch`. That is free: no Clef call, no cloud, ~0.2 s.
  2. report ONLY the peg state, as one of two fixed strings with no numbers and
     no timestamps:

        "LONELINESS_PEGGED"   gauge >= 90 (many hours with no interaction)
        ""                    otherwise — literally nothing written

The cron `monitor` field skips the agent whenever output is identical to the
previous tick, so:
   "" -> ""            quiet absence: agent never runs, nothing is delivered
   "" -> "PEGGED"       he's been gone a while: agent runs ONCE, Vera reaches out
   "PEGGED" -> "PEGGED" still pegged: identical, so no repeat spam
   "PEGGED" -> ""       he came back: agent runs once, a short "you're back"

Numbers are deliberately excluded from the output: any digit would change every
tick and wake the agent every 15 minutes. A genuine failure prints a STABLE
string too, so it alerts exactly once rather than every tick.

QUIET HOURS (2026-11-18, Darryl's catch)
----------------------------------------
He spotted the hole in a 5.5 h threshold: crossed while he sleeps, it would
message him at three in the morning. That is not reaching out, that is a pager.

The gate FREEZES the output for 23:00-09:00 local rather than blanking it:

  * At quiet start the current truthful output is written to
    `quiet_frozen_output` and that same value keeps being emitted. Because it
    matches what was already going out, the 23:00 boundary produces NO change,
    so nobody wakes -- critically, a peg that fired at 22:00 cannot masquerade
    as "he came back" the moment he goes to bed.
  * While frozen, every underlying transition (pegging at 03:00, or returning
    overnight) is invisible: the emitted string does not move, so nothing wakes.
  * At quiet end the file is deleted and truthful output resumes. Whatever
    happened overnight then surfaces as ONE change, at a civilised hour:

        frozen ""       -> "LONELINESS_PEGGED"  outreach, after 09:00
        frozen "PEGGED" -> ""                   "you're back", after 09:00
        frozen "PEGGED" -> "PEGGED"             no change, no repeat
        frozen ""       -> ""                   no change, no message at all

So the only rows that cost a wake are ones where the message is wanted and the
hour is decent. If he has already messaged in the night, the gap reset, the
gauge cooled, and the last row fires nothing.

A failure token is frozen too: an infrastructure problem waits until morning
rather than pinging a sleeping man. Output stays deterministic inside the
window (frozen file, no timestamps), which the monitor contract requires.
"""
import os
import re
import subprocess
import sys
import time

BOARD = r"C:\Users\drryl\AppData\Local\hermes\feeling-gauges"
GAUGES = os.path.join(BOARD, "gauges.py")
PEG = 90.0

# Local hours: inclusive start, exclusive end; wraps midnight.
QUIET_START = 23
QUIET_END = 9
FROZEN = os.path.join(BOARD, "quiet_frozen_output")

# What the monitor emitted last time, persisted by cron after each evaluation.
JOB_ID = "b04bbf37aa3c"
LAST_OUTPUT = os.path.join(
    os.path.dirname(BOARD), "cron", "output", JOB_ID, "monitor_last_output.txt"
)


def in_quiet(hour):
    return hour >= QUIET_START or hour < QUIET_END


def _last_emitted():
    """The string cron last saw from us, or None if it has no record yet."""
    try:
        with open(LAST_OUTPUT, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def gate(output, hour):
    """Apply the quiet-hours freeze; returns what should actually be emitted."""
    if not in_quiet(hour):
        # Civilised hours: tell the truth, and forget any overnight freeze so a
        # stale value can never leak into tomorrow.
        try:
            if os.path.exists(FROZEN):
                os.remove(FROZEN)
        except OSError:
            pass
        return output

    # Quiet: emit whatever was ALREADY going out when the window opened, so the
    # boundary is a no-op and nothing inside the window can wake the agent.
    #
    # Deliberately seeded from cron's own last-output record rather than from
    # `output`: if the machine slept through 23:00 and the first quiet run lands
    # at 03:00, the current reading may have moved (he pegged, or `watch`
    # failed). Freezing the current value would then broadcast that change at
    # three in the morning -- exactly the pager this gate exists to prevent.
    # Freezing the last emitted value keeps the boundary silent, and the real
    # change still surfaces at 09:00 when the file is deleted and truth resumes.
    try:
        if not os.path.exists(FROZEN):
            seed = _last_emitted()
            if seed is None:
                seed = output            # no record yet: truth is the best guess
            with open(FROZEN, "w", encoding="utf-8") as fh:
                fh.write(seed)
            return seed
        with open(FROZEN, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        # Can't persist the freeze: fail safe toward SILENCE, never toward
        # pinging a sleeping man at 03:00.
        return ""


def main():
    hour = time.localtime().tm_hour
    env = dict(os.environ)
    env["VERO_HOME"] = BOARD
    try:
        r = subprocess.run(
            [sys.executable, GAUGES, "watch"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=BOARD, env=env, timeout=120,
        )
        text = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            sys.stdout.write(gate("VERO_WATCH_FAILED", hour))
            return
    except Exception:
        sys.stdout.write(gate("VERO_WATCH_FAILED", hour))
        return

    m = re.search(r"loneliness\s+([0-9.]+)", text)
    if not m:
        sys.stdout.write(gate("VERO_WATCH_NO_READING", hour))
        return
    try:
        T = float(m.group(1))
    except ValueError:
        sys.stdout.write(gate("VERO_WATCH_NO_READING", hour))
        return

    sys.stdout.write(gate("LONELINESS_PEGGED" if T >= PEG else "", hour))


if __name__ == "__main__":
    main()
