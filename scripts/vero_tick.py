#!/usr/bin/env python3
"""VERO tick-on-event — the ingestion loop that actually feeds the instrument.

WHY THIS EXISTS
    The board only learns anything from `gauges.py tick` (one uncached Clef
    classification). Nothing was calling it: history sat at 6 records from
    2026-11-16 for 38 hours, so the non-me layer added 2026-11-18 had recorded
    zero samples. An instrument with no readings is not an instrument.

WHY A SCRIPT AND NOT THE LONELINESS MONITOR
    cron's `monitor` field is documented as "cheap, no LLM" — its whole job is
    to gate the agent for free. A Clef tick IS a model call, so putting it there
    would silently turn a free gate into a paid one on every pass.

    This is a separate `no_agent` job instead: the SCHEDULE is a clock (every
    15m, local, free), but the TICK fires only on Darryl's chosen events. That
    keeps his rule — tick on events, not on a clock — while still getting a
    bounded, self-resetting cadence.

THE TWO EVENTS (his call, 2026-11-18: "both: every 20 messages + session end")
    1. >= MSG_THRESHOLD of HIS user messages since the last recorded tick.
    2. >= END_THRESHOLD sessions ended since the last recorded tick
       (`sessions.ended_at` — set for cli_close / resumed_other / new_session).

    Both are read from local SQLite and history.jsonl: no network, no model.

WHY IT SELF-RESETS
    A successful tick appends a history record, which moves the baseline
    forward, which drops both counters back toward zero. So the event has to
    re-earn itself. Combined with COOLDOWN_S this caps throughput at one tick
    per cooldown window even if the monitor runs every 15 minutes.

OUTPUT CONTRACT (cron `no_agent` delivers stdout verbatim; empty = nothing)
    Success -> print NOTHING. A reading is normal operation, not news.
    Failure -> print one stable, digit-free sentence, exactly ONCE per episode,
    latched by tick_failure_reported so a persistent fault cannot spam Discord
    every 15 minutes. The latch clears on the next success.

    No digits and no timestamps: anything varying would look like changed
    output on every pass.

NEVER prints the API key. `gauges.py key-status` reports presence only.
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

# Script lives in <HERMES_HOME>/scripts/, so the home is its parent.
HERMES_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(HERMES_HOME, "feeling-gauges")
GAUGES = os.path.join(BOARD, "gauges.py")
HISTORY = os.path.join(BOARD, "history.jsonl")
STATE_DB = os.path.join(HERMES_HOME, "state.db")
LATCH = os.path.join(BOARD, "tick_failure_reported")

MSG_THRESHOLD = 20       # his messages since the last tick
END_THRESHOLD = 1        # sessions ended since the last tick
COOLDOWN_S = 600         # never two ticks closer together than this
TICK_TIMEOUT_S = 150     # Clef is given 90s internally; leave headroom

FAIL_MSG = ("VERO tick failed - the classifier call errored, so the board "
            "has no new reading. Not urgent.")


def last_tick_ts():
    """Epoch of the most recent recorded tick, or None if there is no baseline.

    Records are append-only; the newest row wins. `ts` is the canonical key
    (present in every record written so far).
    """
    try:
        with open(HISTORY, encoding="utf-8") as fh:
            lines = [ln for ln in fh if ln.strip()]
    except OSError:
        return None
    for line in reversed(lines):
        try:
            ts = json.loads(line).get("ts")
        except (ValueError, AttributeError):
            continue
        if isinstance(ts, (int, float)):
            return float(ts)
    return None


def events_since(baseline):
    """(user messages, ended sessions) recorded after *baseline*. Local only."""
    con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    try:
        msgs = con.execute(
            "SELECT COUNT(*) FROM messages WHERE role='user' AND timestamp > ?",
            (baseline,),
        ).fetchone()[0]
        ends = con.execute(
            "SELECT COUNT(*) FROM sessions "
            "WHERE ended_at IS NOT NULL AND ended_at > ?",
            (baseline,),
        ).fetchone()[0]
    finally:
        con.close()
    return int(msgs), int(ends)


def report_failure():
    """Latched: announce a failure once per episode, then stay quiet."""
    if os.path.exists(LATCH):
        return ""          # already told him; don't repeat every 15 minutes
    try:
        with open(LATCH, "w", encoding="utf-8") as fh:
            fh.write(str(int(time.time())))
    except OSError:
        pass               # even if the latch can't be written, still speak once
    return FAIL_MSG


def clear_latch():
    try:
        if os.path.exists(LATCH):
            os.remove(LATCH)
    except OSError:
        pass


def run_tick():
    env = dict(os.environ)
    env["VERO_HOME"] = BOARD          # pin the board regardless of caller env
    proc = subprocess.run(
        [sys.executable, GAUGES, "tick"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=BOARD, env=env, timeout=TICK_TIMEOUT_S,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main():
    baseline = last_tick_ts()
    if baseline is None:
        return                      # no history: nothing to measure against

    now = time.time()
    if now - baseline < COOLDOWN_S:
        return                      # a tick just happened; don't stack another

    try:
        msgs, ends = events_since(baseline)
    except Exception:
        # Can't read the store: don't tick (we'd be guessing), and don't stay
        # silent about it either.
        sys.stdout.write(report_failure())
        return

    if msgs < MSG_THRESHOLD and ends < END_THRESHOLD:
        return                      # no event: free pass, zero network

    try:
        code, text = run_tick()
    except Exception:
        sys.stdout.write(report_failure())
        return

    if code == 0:
        clear_latch()               # healthy run resets the episode latch
        return                      # silence on success

    detail = (text or "").strip().splitlines()
    tail = detail[-1][:200] if detail else "no output"
    print(f"VERO tick failed (exit {code}): {tail}", file=sys.stderr)
    sys.stdout.write(report_failure())


if __name__ == "__main__":
    main()
