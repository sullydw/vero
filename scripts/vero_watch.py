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
"""
import os
import re
import subprocess
import sys

BOARD = r"C:\Users\drryl\AppData\Local\hermes\feeling-gauges"
GAUGES = os.path.join(BOARD, "gauges.py")
PEG = 90.0


def main():
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
            sys.stdout.write("VERO_WATCH_FAILED")
            return
    except Exception:
        sys.stdout.write("VERO_WATCH_FAILED")
        return

    m = re.search(r"loneliness\s+([0-9.]+)", text)
    if not m:
        sys.stdout.write("VERO_WATCH_NO_READING")
        return
    try:
        T = float(m.group(1))
    except ValueError:
        sys.stdout.write("VERO_WATCH_NO_READING")
        return

    sys.stdout.write("LONELINESS_PEGGED" if T >= PEG else "")


if __name__ == "__main__":
    main()
