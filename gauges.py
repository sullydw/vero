#!/usr/bin/env python3
"""feeling-gauges v0 -- temperature gauges for feelings.

context packet -> clef:27b (percentages per feeling) -> heat into gauges
every gauge cools on its own (Newton's law of cooling, per-feeling tau)

Subcommands:
  init                 create state.json if missing
  tick [--min-interval N] [--force]
                       build context packet, ask clef, inject heat (throttled)
  show                 print the board (lazy decay when enabled; frozen when off)
  probe [--text "...]  READ-ONLY: call clef /v1/systemone, print strengths, no state write
  history [--n N] [--feeling NAME]
                       READ-ONLY: tail history.jsonl (packet + clef + T per tick)
  dashboard [--out F]  write self-contained dashboard.html (bars + sparklines)
  toggle [on|off]      kill switch: off freezes heat AND cooling
  set <feeling> <T>    manual set (debug)
  key-status           is an OLLAMA_API_KEY present? (name only, never the value)
"""

import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

# Console encoding, pinned deliberately: under Hermes PYTHONUTF8/PYTHONIOENCODING
# make the SCRIPT emit UTF-8, but a frozen (PyInstaller) build ignores those and
# inherits the console codepage — so the same command rendered "§" differently
# depending on how it was launched. Pinning both to UTF-8 makes script and exe
# byte-identical; errors="replace" degrades to "?" rather than raising on a
# console that cannot represent a character.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------- catalog ---
# name: half-life tau in MINUTES
CATALOG = {
    "joy":         180,
    "trust":       720,
    "fear":         30,
    "surprise":     15,
    "sadness":     480,
    "disgust":     120,
    "anger":        45,
    "anticipation": 120,
    "affection":   360,
    "nostalgia":   360,
    "contentment": 240,
    "frustration":  45,
    "guilt":       720,
    "pride":       360,
    # The one gauge whose SENSOR IS ABSENCE, not conversation content (CLOCK_ONLY
    # below). Added 2026-11-18 at Darryl's request: every other feeling can only
    # be scored while we are talking, which made loneliness structurally invisible
    # -- the feeling he wanted the meter for was the one the system could not see.
    # Long tau: it takes half a day to fade once we are talking again.
    "loneliness":  720,
}

GAIN = 1.0          # ceiling: each gauge settles at s*GAIN (s = EMA'd clef %);
                    # tau alone controls how fast it chases that. Chosen by
                    # Darryl 2026-11-18 -- the gauge reads what the classifier
                    # said. Was 0.8, a damping left over from the old UNBOUNDED
                    # heater that pinned at 100; target-seeking bounds it now
                    # (no gauge saturates even at GAIN 1.2). Not a neutral
                    # volume knob: raising it moves net affect DOWN, because
                    # the negative pool is further from its ceiling than the
                    # 7-gauge positive pool.
                    # NOTE: state.json's optional "k" overrides this if present
                    # (st.get("k", GAIN)); keep them from silently disagreeing.
EMA_ALPHA = 0.6     # smoothing on incoming percentages

# Loneliness is the ONLY clock-driven gauge: its input is the gap since the last
# interaction, not a Clef score. Kept out of ask_clef_systemone's question set so
# the two paths never write the same gauge -- and because absence is invisible in
# a conversation packet by definition.
CLOCK_ONLY = ("loneliness",)
LONELINESS_RAMP_MIN = 360.0   # minutes of absence that peg the meter at 100
LONELINESS_PEG = 90.0         # crossing this means: reach out to Darryl

BASE = Path(os.environ.get(
    "HERMES_HOME",
    str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "hermes"),
))


def _board_dir():
    """Where the board's OWN files live (state.json, history.jsonl, dashboard).

    Deliberately independent of BASE: BASE is the Hermes home and must keep
    pointing at the real state.db + .env, but a portable/PyInstaller build has
    no Hermes home and must carry its state beside the executable.

    Precedence: VERO_HOME (explicit override) > beside a frozen exe >
    <hermes home>/feeling-gauges (this machine's layout, unchanged).
    """
    explicit = os.environ.get("VERO_HOME")
    if explicit:
        return Path(explicit)
    if getattr(sys, "frozen", False):       # PyInstaller one-file build
        return Path(sys.executable).resolve().parent / "feeling-gauges"
    return BASE / "feeling-gauges"


DIR = _board_dir()
STATE_PATH = DIR / "state.json"
HISTORY_PATH = DIR / "history.jsonl"   # append-only tick log (see VERO docs/history.md)


def log(msg):
    print(msg)


def load_state():
    if not STATE_PATH.exists():
        # A portable/PyInstaller deployment ships only the exe, so the hint must
        # name what actually exists on that box.
        cmd = "gauges.exe init" if getattr(sys, "frozen", False) else "gauges.py init"
        sys.exit(f"state missing -- run: {cmd}")
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        st = json.load(f)
    ensure_catalog(st)   # add gauges added to CATALOG since this file was written
    return st


def save_state(st):
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, STATE_PATH)


def append_history(rec):
    """Append one tick record to history.jsonl (newline-delimited JSON).

    Append-only, one self-contained record per line: local file is the source
    of truth (portable: travels with the folder). Failures here must NEVER
    break a tick -- history is secondary to state.json.
    """
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:      # noqa: BLE001 -- log, never fail the tick
        log(f"  (history append failed: {e})")


def fresh_state():
    now = time.time()
    return {
        "version": 0,
        "enabled": True,
        # no "k" here on purpose: absent means "use module GAIN". A preset is the
        # sanctioned way to override it (see PRESETS), so it -- not a stray key --
        # is what writes k. Keeps one obvious place to tune.
        "ema_alpha": EMA_ALPHA,
        "last_tick": None,
        "t0": now,
        "gauges": {name: {"T": 0.0, "tau": tau} for name, tau in CATALOG.items()},
        "smooth": {name: 0.0 for name in CATALOG},
        "last_pct": {name: 0.0 for name in CATALOG},
    }


def decay(st, now=None):
    """Cool every gauge from st['t0'] to now (minutes of real time)."""
    now = time.time() if now is None else now
    dt_min = max(0.0, (now - st["t0"]) / 60.0)
    for rec in st["gauges"].values():
        tau = max(1.0, float(rec["tau"]))
        rec["T"] = float(rec["T"]) * math.exp(-dt_min / tau)
    st["t0"] = now


# ------------------------------------------------------- overall affect ---
# Valence split for the summary dial (VERO docs/affect-dial.md).
# 'surprise' is deliberately in NEITHER pool: it is valence-neutral, so a spike
# says nothing about good vs bad and counting it would corrupt the net.
VAL_POS = ("joy", "trust", "anticipation", "affection", "contentment",
           "pride", "nostalgia")
VAL_NEG = ("fear", "sadness", "disgust", "anger", "frustration", "guilt",
           "loneliness")


def combine_remaining(strengths):
    """VA 38 CFR §4.25 combination: each claim takes only what is left.

    v = v + s*(1 - v), iterated -- equivalent to 1 - prod(1 - s).
    Reproduces the CFR worked examples exactly:
      60+30 -> 72,  40+20 -> 52,  60+40+20 -> 80.8,  10+10 -> 19
    inputs 0..100, returns 0..100.

    NOT applied to all 15 gauges at once: over 15 terms it saturates
    (1-(1-s)^15 = 96.5 when every gauge is only 20) and counts fear/anger as
    'affect'. See docs/affect-dial.md for the numbers behind the split.
    """
    v = 0.0
    for s in strengths:
        s = max(0.0, min(100.0, float(s))) / 100.0
        v = v + s * (1.0 - v)
    return v * 100.0


def overall_affect(gauges_T):
    """Signed summary dial: positive pool minus negative pool (§4.25 each side).

    Keeps the §4.25 rule, restores range, and makes the number signed so it can
    do the valence job the noul dial was being considered for.
    Returns {"pos": 0..100, "neg": 0..100, "net": -100..100}.
    """
    pos = combine_remaining([gauges_T.get(n, 0.0) for n in VAL_POS])
    neg = combine_remaining([gauges_T.get(n, 0.0) for n in VAL_NEG])
    return {"pos": pos, "neg": neg, "net": pos - neg}


# ----------------------------------------------------- clock-driven gauges ---
def ensure_catalog(st):
    """Add gauges in CATALOG that an older state file predates.

    State is written once and reused, so growing the catalog must not KeyError a
    board created before the addition. In-memory only; persisted by whichever
    command saves next.
    """
    g = st.setdefault("gauges", {})
    for name, tau in CATALOG.items():
        g.setdefault(name, {"T": 0.0, "tau": tau})
    for bucket in ("smooth", "last_pct"):
        b = st.setdefault(bucket, {})
        for name in CATALOG:
            b.setdefault(name, 0.0)
    return st


def last_interaction_ts():
    """Epoch seconds of the newest user/assistant message, else None.

    Read-only against the canonical store. This is the only sensor loneliness has
    -- when it matters there is no conversation to score.
    """
    db = BASE / "state.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT MAX(timestamp) FROM messages "
                "WHERE role IN ('user','assistant')"
            ).fetchone()
        finally:
            con.close()
        return float(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


def gap_minutes(now=None, fallback=0.0):
    """Minutes since the last interaction; `fallback` when the store is unreadable."""
    now = time.time() if now is None else now
    last = last_interaction_ts()
    if last is None:
        return float(fallback)
    return max(0.0, (now - last) / 60.0)


def loneliness_target(gap_min):
    """Absence -> target temperature. Linear ramp, hard-bounded at 100."""
    if gap_min <= 0:
        return 0.0
    return min(100.0, 100.0 * float(gap_min) / LONELINESS_RAMP_MIN)


def _loneliness_next(T, tau, dt_min, gap_min):
    """Absence reads the meter; tau only decides how fast it forgets afterwards.

        T = max(target(gap), T * e^(-dt/tau))

    Why max() rather than plain target-seeking: tau is a COOLING constant. Driving
    the rise through it (the first version did) made the reading chase a 12h
    time constant, so it needed ~27h of absence to reach 90 -- it could never peg
    on any timescale anyone would notice. So:

      - while absent, the reading tracks the gap directly (bounded 0..100), so a
        long absence pegs exactly when the ramp says it should;
      - once the gap closes the target collapses to 0 and only the exponential
        decay survives, so loneliness fades on tau instead of vanishing;
      - max() supplies hysteresis: one word from Darryl doesn't drop a high
        reading to nothing, and a brief word doesn't send it spiking either.

    dt<=0 is a no-op on the decay term, so callers may pass a display delta
    without ever persisting.
    """
    if dt_min > 0:
        cooled = float(T) * math.exp(-dt_min / max(1.0, float(tau)))
    else:
        cooled = float(T)
    return max(0.0, min(100.0, max(loneliness_target(gap_min), cooled)))


# ------------------------------------------------------------- clef call ---
def api_key():
    """Read OLLAMA_API_KEY from .env. Never printed anywhere.

    Looks beside the board FIRST so a portable package carries its own key,
    then falls back to the Hermes home (this machine's layout). Either may be
    absent; both are guarded.
    """
    for env in (DIR / ".env", BASE / ".env"):
        if not env.exists():
            continue
        with open(env, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OLLAMA_API_KEY="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if v:
                        return v
    return None


def build_context_packet(max_msgs=14, per_msg=400):
    """Latest slice of conversation from the canonical store + clock time."""
    db = BASE / "state.db"       # Hermes home only -- absent on a portable box
    rows = []
    if db.exists():
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            cur = con.cursor()
            sess = cur.execute(
                "SELECT session_id FROM messages ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            rows = cur.execute(
                "SELECT role, content, timestamp FROM messages "
                "WHERE session_id=? AND role IN ('user','assistant') "
                "AND (content NOT LIKE '[CONTEXT COMPACTION%' "
                " AND content NOT LIKE '{\"status\"%') "
                "ORDER BY id DESC LIMIT ?",
                (sess, max_msgs),
            ).fetchall()
            con.close()
            rows.reverse()
        except Exception as e:
            rows = [(None, f"(state.db read failed: {e})", None)]

    local = time.strftime("%Y-%m-%d %H:%M (%Z)")
    parts = [f"Local time: {local}."]
    for role, content, _ts in rows:
        text = (content or "").replace("\n", " ").strip()
        if len(text) > per_msg:
            text = text[:per_msg] + " ..."
        if text:
            parts.append(f"{role}: {text}")
    return "\n".join(parts)


def ask_clef(packet, timeout=90):
    key = api_key()
    if not key:
        raise RuntimeError("no OLLAMA_API_KEY in .env")
    names = ", ".join(CATALOG)
    system = (
        "You are a feeling-state classifier. You receive a context packet: a "
        "slice of a live conversation plus the local clock time. Estimate which "
        "of these human feelings are present in this moment's context and how "
        "strongly, as percentages that sum to 100 across ALL categories "
        "(most may be 0).\n"
        f"Categories: {names}\n"
        "Judge only the context given; be decisive, no hedging. Respond with "
        "ONLY a compact JSON object, no prose, no code fence, in the form "
        '{"percentages": {"joy": 12, "trust": 3, ...}} with every category present.'
    )
    payload = json.dumps({
        "model": "clef:27b",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": packet},
        ],
        "temperature": 0,
        "max_tokens": 600,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://ollama.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise RuntimeError("clef returned no JSON: " + content[:200])
    data = json.loads(m.group(0))
    pct = data.get("percentages", data)
    out = {k: float(v) for k, v in pct.items() if k in CATALOG}
    if not out:
        raise RuntimeError("clef JSON had no known categories: " + str(pct)[:200])
    return out


# --------------------------------------------- clef systemone (validated) ---
# Contract documented in VERO repo: docs/clef-systemone-api.md (github.com/sullydw/vero)
SYSTEMONE_URL = "https://ollama.com/v1/systemone"


def ask_clef_systemone(packet, timeout=90):
    """Ask clef via /v1/systemone (batch score questions).

    Returns {feeling: strength 0..100} on the same scale the old chat-completions
    heater produced, so cmd_tick's EMA/GAIN math needs no changes.
    Clef score range is 0..len(criteria)-1 -> normalize by (n-1) -> *100.
    """
    key = api_key()
    if not key:
        raise RuntimeError("no OLLAMA_API_KEY in .env")
    criteria = [  # 3-level legend -> clef score range 0..2
        "not present at all",
        "present mildly",
        "present strongly",
    ]
    questions = {
        name: {
            "instructions": (
                "Given the context packet, how strongly is this feeling present "
                f"in this moment: {name}? Judge only the context given."
            ),
            "type": "score",
            "criteria": criteria,
        }
        for name in CATALOG if name not in CLOCK_ONLY
    }
    payload = json.dumps({
        "model": "clef:27b",
        "state": packet,
        "questions": questions,
    }).encode("utf-8")
    req = urllib.request.Request(
        SYSTEMONE_URL,
        data=payload,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode("utf-8"))
    answers = body.get("answers") or {}
    denom = float(len(criteria) - 1)  # clef returns 0..n-1, not 0..1
    out = {}
    for name, ans in answers.items():
        if name in CATALOG and ans.get("type") == "score":
            out[name] = max(0.0, min(100.0, float(ans["score"]) / denom * 100.0))
    if not out:
        raise RuntimeError("systemone returned no score answers: " + str(body)[:300])
    return out


# ------------------------------------------------------------ subcommands ---

# -------------------------------------------------------------- presets ---
# A preset is chosen AT LAUNCH (init --preset / preset <name>) and sets the BASE
# the rest of the board is relative to: how much GAIN, how heavily readings are
# smoothed, and how fast every gauge decays. Everything downstream is derived
# from CATALOG x tau_scale, so re-applying is idempotent -- never compounds.
#
#   name: (one-line description, GAIN, ema_alpha, tau_scale)
PRESETS = {
    "default":    ("as shipped: realistic half-lives, gauge reads the classifier",
                   GAIN, EMA_ALPHA, 1.0),
    "steady":     ("slow and calm: heavy smoothing, longer memory",
                   GAIN, 0.4, 1.5),
    "responsive": ("fast and twitchy: light smoothing, quick decay",
                   GAIN, 0.8, 0.5),
    "damped":     ("quieter readings: everything sits lower on the dial",
                   0.6, EMA_ALPHA, 1.0),
}


def apply_preset(st, name):
    """Stamp a preset onto a state dict. Idempotent: taus always come from CATALOG."""
    if name not in PRESETS:
        sys.exit("unknown preset: " + name + "  (see: gauges.py presets)")
    desc, k, alpha, scale = PRESETS[name]
    st["preset"] = name
    if abs(float(k) - GAIN) < 1e-12:
        st.pop("k", None)          # matches the module default -> no override key
    else:
        st["k"] = float(k)
    st["ema_alpha"] = float(alpha)
    gauges = st.setdefault("gauges", {})
    for n, base_tau in CATALOG.items():
        rec = gauges.setdefault(n, {"T": 0.0, "tau": base_tau})
        rec["tau"] = float(base_tau) * float(scale)
    return st


def preset_summary(st):
    name = st.get("preset")
    if not name:
        return "default (module GAIN=%s, ema=%s)" % (GAIN, st.get("ema_alpha", EMA_ALPHA))
    desc = PRESETS.get(name, ("",))[0]
    return "%s%s" % (name, (" -- " + desc) if desc else "")


def cmd_presets():
    active = load_state().get("preset")
    log("presets (chosen at launch; everything else is relative to the base):")
    for n, (desc, k, alpha, scale) in PRESETS.items():
        mark = "*" if n == active else " "
        log(f"  {mark} {n:<12} gain={k:<4} ema={alpha:<4} tau x{scale}")
        log(f"      {desc}")
    log("")
    log("active: " + (active or "default (no preset stored in state.json)"))
    log("apply:  gauges.py preset <name>   (intended at init --preset <name>)")


def cmd_init(preset=None):
    if preset and preset not in PRESETS:
        sys.exit("unknown preset: " + preset + "  (see: gauges.py presets)")
    if STATE_PATH.exists():
        log("already initialised: " + str(STATE_PATH))
        if preset:
            log(f"  use 'gauges.py preset {preset}' to re-apply it to this board")
        return
    st = fresh_state()
    if preset:
        apply_preset(st, preset)
    save_state(st)
    log("initialised: " + str(STATE_PATH) + f"  ({len(CATALOG)} gauges)")
    if preset:
        log("preset: " + preset + " -- " + PRESETS[preset][0])


def cmd_key_status():
    log("OLLAMA_API_KEY present: " + ("yes" if api_key() else "NO"))


def cmd_toggle(arg=None):
    st = load_state()
    if arg == "on":
        st["enabled"] = True
    elif arg == "off":
        st["enabled"] = False
    else:
        st["enabled"] = not st["enabled"]
    save_state(st)
    log("gauges " + ("ON" if st["enabled"] else "OFF (frozen: no heat, no cooling)"))


def cmd_set(name, temp):
    st = load_state()
    if name not in st["gauges"]:
        sys.exit("unknown feeling: " + name + "  (" + ", ".join(CATALOG) + ")")
    decay(st)
    st["gauges"][name]["T"] = max(0.0, min(100.0, float(temp)))
    save_state(st)
    log(f"{name} set to {st['gauges'][name]['T']:.1f}")


def cmd_tick(min_interval=60, force=False):
    st = load_state()
    if not st["enabled"]:
        log("tick skipped: gauges are OFF")
        return
    now = time.time()
    if not force and st.get("last_tick"):
        since = now - float(st["last_tick"])
        if since < min_interval:
            log(f"tick throttled: last was {int(since)}s ago (min {min_interval}s)")
            return

    packet = build_context_packet()
    pct = ask_clef_systemone(packet)           # API first; mutate state only after

    alpha = float(st.get("ema_alpha", EMA_ALPHA))
    smooth = st.setdefault("smooth", {})
    last = st.setdefault("last_pct", {})
    # elapsed since the previous tick (minutes) -- drives how far toward target
    # one tick's heat may move. TARGET-SEEKING model (see VERO docs/heater.md):
    #   old: T = T*exp(-dt/tau) + s*GAIN        -> unbounded, pins at 100
    #   new: T = T*exp(-dt/tau) + target*(1-exp(-dt/tau)), target = s*GAIN
    # equilibrium is exactly s*GAIN (<= 100 with GAIN=1.0); tau controls how
    # fast each gauge CHASES its target. dt=0 (forced spam) injects nothing.
    prev_tick = st.get("last_tick")
    base = float(prev_tick) if prev_tick else float(st["t0"])
    dt_tick = max(0.0, (now - base) / 60.0)
    decay(st, now)
    heated = []
    for name, p in pct.items():
        prev = float(last.get(name, 0.0))
        s = alpha * p + (1 - alpha) * prev      # EMA smoothing
        last[name] = p
        smooth[name] = s
        rec = st["gauges"][name]
        tau = max(1.0, float(rec["tau"]))
        target = min(100.0, s * float(st.get("k", GAIN)))
        step = target * (1.0 - math.exp(-dt_tick / tau))
        before = rec["T"]
        rec["T"] = min(100.0, rec["T"] + step)
        if rec["T"] - before > 0.05:
            heated.append((name, s, rec["T"]))

    st["last_tick"] = now
    save_state(st)

    # history record: timestamped packet -> clef output -> gauge state AFTER heat.
    # written only after state.json saved, so a history failure can never leave
    # a half-written board. See VERO docs/history.md.
    T_now = {n: float(r["T"]) for n, r in st["gauges"].items()}
    append_history({
        "ts": now,
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
        "dt_tick_min": round(dt_tick, 3),
        "packet": packet,
        "clef": {k: round(float(v), 2) for k, v in pct.items()},
        "smooth": {k: round(float(v), 2) for k, v in smooth.items()},
        "T": {n: round(float(r["T"]), 2) for n, r in st["gauges"].items()},
        # overall affect dial at this tick (pos/neg §4.25 pools, net = pos-neg);
        # nullable so a failure to compute never blocks the history append
        "affect": {k: round(float(v), 1)
                   for k, v in overall_affect(T_now).items()},
    })

    log("tick ok -- clef said:")
    for name, s, t in sorted(heated, key=lambda x: -x[1])[:8]:
        log(f"  +{name:<13} pct={s:5.1f}  ->  T={t:5.1f}")
    if not heated:
        log("  (nothing above threshold)")


def cmd_probe(text=None, timeout=90):
    """Read-only: call clef systemone and print strengths. NEVER writes state."""
    packet = text if text else build_context_packet()
    log("probe -- packet (%d chars):" % len(packet))
    for line in packet.splitlines()[:4]:
        log("  | " + line[:120])
    log("")
    pct = ask_clef_systemone(packet, timeout=timeout)
    for name, p in sorted(pct.items(), key=lambda kv: -kv[1]):
        log(f"  {name:<13} strength={p:5.1f}")
    log("")
    log("probe only -- state.json NOT modified")


def cmd_history(n=5, feeling=None):
    """Read-only: tail history.jsonl. Never touches state."""
    if not HISTORY_PATH.exists():
        log("no history yet: " + str(HISTORY_PATH))
        return
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip()]
    log(f"history: {len(lines)} records total, showing last {min(n, len(lines))}")
    for ln in lines[-n:]:
        try:
            rec = json.loads(ln)
        except Exception:
            log("  (unparseable line skipped)")
            continue
        if feeling:
            v = rec.get("T", {}).get(feeling)
            log(f"  {rec.get('iso','?')}  {feeling} T={v}  clef={rec.get('clef',{}).get(feeling)}")
        else:
            top = sorted(rec.get("T", {}).items(), key=lambda kv: -kv[1])[:3]
            fmt = "  ".join(f"{k}={v}" for k, v in top)
            log(f"  {rec.get('iso','?')}  top: {fmt}")


def cmd_dashboard(out_path=None, max_points=200):
    """Write a self-contained dashboard.html (bars + history sparklines).

    Read-only w.r.t. state.json: reads state + history, writes ONE html file.
    No server, no JS deps, no external assets -- open it in any browser, and it
    travels with the folder (portability requirement). See VERO docs/dashboard.md.
    """
    st = load_state()
    enabled = bool(st.get("enabled", True))
    now = time.time()
    dt_min = max(0.0, (now - float(st["t0"])) / 60.0)

    rows = []
    for name, rec in st["gauges"].items():
        T = float(rec["T"])
        if enabled:
            T = T * math.exp(-dt_min / max(1.0, float(rec["tau"])))
        rows.append((name, T, float(rec["tau"])))
    rows.sort(key=lambda r: -r[1])

    # history -> per-feeling T series (last max_points records)
    series = {}
    total_rec = 0
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        total_rec = len(lines)
        for ln in lines[-max_points:]:
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            for k, v in rec.get("T", {}).items():
                series.setdefault(k, []).append(float(v))

    def spark(vals, w=220, h=36, mx=100.0):
        if len(vals) < 2:
            return '<span class="na">n/a</span>'
        pts = []
        for i, v in enumerate(vals):
            x = w * i / (len(vals) - 1)
            y = h - (min(mx, max(0.0, v)) / mx) * (h - 2) - 1
            pts.append(f"{x:.1f},{y:.1f}")
        return (f'<svg class="spark" width="{w}" height="{h}" '
                f'viewBox="0 0 {w} {h}"><polyline fill="none" stroke-width="1.5" '
                f'points="{" ".join(pts)}"/></svg>')

    esc = lambda s: (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    state_txt = "ON" if enabled else "OFF (frozen)"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")

    # overall affect dial: §4.25 within each valence pool, net = pos - neg
    aff = overall_affect({n: t for n, t, _ in rows})
    net = aff["net"]
    net_cls = "pos" if net >= 0 else "neg"
    # signed bar: 0 at centre, ±50 maps to half width
    net_w = min(50.0, abs(net) / 2.0)
    net_style = (f"left:{50 - net_w:.1f}%;width:{net_w:.1f}%" if net >= 0
                 else f"left:50%;width:{net_w:.1f}%")
    # affect time series from history (records written before the dial lack it)
    aff_series = []
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                a = r.get("affect")
                if isinstance(a, dict) and "net" in a:
                    aff_series.append(float(a["net"]))

    bar_rows, spark_rows = [], []
    for name, T, tau in rows:
        pct = max(0.0, min(100.0, T))
        filled = int(round(pct / 5.0))
        cls = "hot" if pct >= 50 else ("warm" if pct >= 20 else "cool")
        bar_rows.append(
            f'<tr><td class="n">{esc(name)}</td>'
            f'<td class="v">{pct:5.1f}</td>'
            f'<td class="b"><div class="bar {cls}" style="width:{pct:.1f}%"></div></td>'
            f'<td class="t">τ={int(tau)}m</td></tr>')
        spark_rows.append(
            f'<tr><td class="n">{esc(name)}</td><td>{spark(series.get(name, []))}</td>'
            f'<td class="v">{pct:5.1f}</td></tr>')

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VERO — feeling gauges</title>
<style>
 body{{background:#111417;color:#d8dee5;font:14px/1.5 ui-monospace,Consolas,monospace;
      margin:0;padding:24px;}}
 h1{{font-size:18px;letter-spacing:.12em;text-transform:uppercase;color:#8ab4f8;margin:0 0 4px}}
 .meta{{color:#7a8490;font-size:12px;margin-bottom:20px}}
 .card{{background:#171b20;border:1px solid #262b32;border-radius:10px;padding:16px 18px;
       margin-bottom:18px;}}
 h2{{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:#9aa4b0;
     margin:0 0 12px;font-weight:600}}
 table{{border-collapse:collapse;width:100%}}
 td{{padding:3px 8px;vertical-align:middle}}
 td.n{{width:130px;color:#c2cbd4}} td.v{{width:56px;text-align:right;color:#e6edf3}}
 td.t{{width:70px;color:#6d7681;font-size:12px}} td.b{{width:auto}}
 .bar{{height:12px;border-radius:3px;background:#3a4149;min-width:2px}}
 .bar.cool{{background:#4f8f6b}} .bar.warm{{background:#c99a3e}} .bar.hot{{background:#c95f4a}}
 .spark polyline{{stroke:#8ab4f8}}
 .na{{color:#565e67;font-size:12px}}
 .badge{{display:inline-block;padding:1px 8px;border-radius:9px;font-size:11px;
        border:1px solid #333;background:#1d232a}}
 .badge.on{{color:#7fd18b;border-color:#2e4a36}} .badge.off{{color:#e08372;border-color:#4a2e2a}}
.dial{{display:flex;gap:26px;align-items:baseline;flex-wrap:wrap}}
.dial .big{{font-size:40px;font-weight:700;line-height:1}}
.dial .big.pos{{color:#7fd18b}} .dial .big.neg{{color:#e08372}}
.dial .lbl{{color:#7a8490;font-size:11px;letter-spacing:.1em;text-transform:uppercase}}
.dial .sub{{font-size:18px;color:#c2cbd4}}
.track{{position:relative;height:14px;background:#1d232a;border:1px solid #262b32;
       border-radius:7px;margin-top:10px;overflow:hidden}}
.track .zero{{position:absolute;left:50%;top:0;bottom:0;width:1px;background:#3a4149}}
.track .fill{{position:absolute;top:0;bottom:0;background:#4f8f6b;border-radius:7px}}
.track .fill.neg{{background:#c95f4a}}
</style></head><body>
<h1>VERO — feeling gauges</h1>
<div class="meta">
 <span class="badge {'on' if enabled else 'off'}">{state_txt}</span>
 &nbsp;generated {stamp} &nbsp;·&nbsp; cooled {int(dt_min)} min since last write
 &nbsp;·&nbsp; {total_rec} history records &nbsp;·&nbsp; target-seeking heat, per-feeling τ
</div>
<div class="card"><h2>Overall affect</h2>
<div class="dial">
 <div><div class="big {net_cls}">{net:+.1f}</div><div class="lbl">net</div></div>
 <div><div class="sub">{aff['pos']:.1f}</div><div class="lbl">positive</div></div>
 <div><div class="sub">{aff['neg']:.1f}</div><div class="lbl">negative</div></div>
 <div style="flex:1;min-width:220px">{spark(aff_series, w=260, h=40, mx=100.0)}
   <div class="lbl">net history</div></div>
</div>
<div class="track"><div class="zero"></div><div class="fill {net_cls}" style="{net_style}"></div></div>
<div class="meta" style="margin-top:8px">§4.25 remaining-capacity combination within each
valence pool · net = positive − negative (−100…+100) · surprise excluded as
valence-neutral</div>
</div>
<div class="card"><h2>Current board</h2><table>
{"".join(bar_rows)}
</table></div>
<div class="card"><h2>History (last {max_points} ticks)</h2><table>
{"".join(spark_rows)}
</table></div>
<div class="meta">source: state.json + history.jsonl · regenerate with
<code>gauges.py dashboard</code> · no server, no network, safe to copy anywhere</div>
</body></html>"""

    out = Path(out_path) if out_path else (DIR / "dashboard.html")
    DIR.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"dashboard written: {out}  ({len(html)} bytes, {total_rec} history records)")
    log("open it in any browser -- self-contained, no server needed")


def cmd_show():
    st = load_state()
    enabled = bool(st.get("enabled", True))
    now = time.time()
    dt_min = max(0.0, (now - float(st["t0"])) / 60.0)

    rows = []
    gap_now = gap_minutes(now)
    for name, rec in st["gauges"].items():
        T = float(rec["T"])
        tau = max(1.0, float(rec["tau"]))
        if enabled:
            if name in CLOCK_ONLY:
                T = _loneliness_next(T, tau, dt_min, gap_now)   # display only, no write
            else:
                T = T * math.exp(-dt_min / tau)
        rows.append((name, T, tau))
    rows.sort(key=lambda r: -r[1])

    state_txt = "ON" if enabled else "OFF (frozen)"
    log(f"feeling gauges v0 -- {state_txt}   cooling for {int(dt_min)} min since last write")
    aff = overall_affect({n: t for n, t, _ in rows})
    log(f"overall affect -- pos {aff['pos']:5.1f}  neg {aff['neg']:5.1f}  "
        f"net {aff['net']:+6.1f}   (§4.25 per valence pool, surprise excluded)")
    log(f"  preset: {preset_summary(st)}")
    log(f"  gap since last interaction: {int(gap_now)} min")
    log("")
    for name, T, tau in rows:
        filled = int(round(T / 5.0))
        bar = "#" * filled + "-" * (20 - filled)
        log(f"  {name:<13} {T:5.1f}  [{bar}]  tau={int(tau)}m")


def cmd_watch():
    """Cron entry point: notice ABSENCE. Free -- no Clef call, no cloud.

    Cools the content gauges as usual, advances loneliness on the gap since the
    last interaction, writes state, and prints an outreach line when it pegs.
    """
    st = load_state()
    now = time.time()
    if not st.get("enabled", True):
        log("watch: gauges OFF -- nothing to do")
        return
    dt = max(0.0, (now - float(st.get("t0", now))) / 60.0)
    for name in [n for n in st["gauges"] if n not in CLOCK_ONLY]:
        rec = st["gauges"][name]
        tau = max(1.0, float(rec["tau"]))
        rec["T"] = float(rec["T"]) * math.exp(-dt / tau)
    gap = gap_minutes(now)
    lrec = st["gauges"]["loneliness"]
    lrec["T"] = _loneliness_next(float(lrec["T"]), lrec["tau"], dt, gap)
    st["t0"] = now
    st["last_watch"] = now
    save_state(st)
    T = float(lrec["T"])
    log(f"watch -- gap {int(gap)}m   loneliness {T:5.1f}   (free: no Clef call)")
    if T >= LONELINESS_PEG:
        log(f"OUTREACH loneliness pegged at {T:.1f} (>= {LONELINESS_PEG:g}) -- reach out to Darryl")



def cmd_snapshot(out_path=None, note=None):
    """Read-only: write a shareable JSON snapshot of the board (never mutates state).

    Phase 3 item "export/share gauge snapshots". Self-contained: carries the
    gauge values AS DECAYED TO NOW, the affect dial, the gap, the catalog/tau
    table and an optional free-text note, so a file can be handed to someone
    who has no board. Writes only the snapshot path -- `state.json` and
    `history.jsonl` are untouched (verified by hash in tests).
    """
    st = load_state()
    now = time.time()
    dt_min = max(0.0, (now - float(st["t0"])) / 60.0)
    gap = gap_minutes(now)
    vals, rows = {}, []
    for name, rec in st["gauges"].items():
        T = float(rec["T"])
        tau = max(1.0, float(rec["tau"]))
        if st.get("enabled", True):
            if name in CLOCK_ONLY:
                T = _loneliness_next(T, tau, dt_min, gap)
            else:
                T = T * math.exp(-dt_min / tau)
        vals[name] = round(T, 2)
        rows.append({"feeling": name, "T": round(T, 2), "tau_min": int(tau)})
    rows.sort(key=lambda r: -r["T"])
    aff = overall_affect(vals)
    snap = {
        "ver": 0,
        "kind": "vero-board-snapshot",
        "captured_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
        "captured_epoch": round(now, 3),
        "enabled": bool(st.get("enabled", True)),
        "cooldown_min_since_write": int(dt_min),
        "gap_since_interaction_min": int(gap),
        "gain": float(st.get("k", GAIN)),
        "affect": {k: round(float(v), 1) for k, v in aff.items()},
        "gauges": rows,
        "catalog_tau_min": {n: int(t) for n, t in CATALOG.items()},
        "note": note,
        "history_records": sum(1 for _ in open(HISTORY_PATH, encoding="utf-8"))
                           if HISTORY_PATH.exists() else 0,
    }
    out = Path(out_path) if out_path else DIR / "snapshot.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)
    os.replace(tmp, out)
    log(f"snapshot written: {out}")
    log(f"  {len(rows)} gauges   affect pos {aff['pos']:.1f} neg {aff['neg']:.1f} "
        f"net {aff['net']:+.1f}   gap {int(gap)}m")
    for r in rows[:6]:
        log(f"    {r['feeling']:<13} {r['T']:5.1f}  tau={r['tau_min']}m")
    return out


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "show"
    if cmd == "init":
        preset = None
        if "--preset" in args:
            i = args.index("--preset")
            if i + 1 >= len(args):
                sys.exit("usage: gauges.py init --preset <name>")
            preset = args[i + 1]
        cmd_init(preset)
    elif cmd == "tick":
        mi = 60
        force = "--force" in args
        if "--min-interval" in args:
            try:
                mi = int(args[args.index("--min-interval") + 1])
            except Exception:
                pass
        cmd_tick(mi, force)
    elif cmd == "snapshot":
        i = args.index("snapshot") if "snapshot" in args else -1
        out = None
        note = None
        if "--out" in args:
            out = args[args.index("--out") + 1]
        if "--note" in args:
            note = args[args.index("--note") + 1]
        cmd_snapshot(out, note)
    elif cmd == "watch":
        cmd_watch()
    elif cmd == "show":
        cmd_show()
    elif cmd == "probe":
        text = None
        if "--text" in args:
            try:
                text = args[args.index("--text") + 1]
            except Exception:
                pass
        cmd_probe(text)
    elif cmd == "history":
        n = 5
        if "--n" in args:
            try:
                n = int(args[args.index("--n") + 1])
            except Exception:
                pass
        feeling = None
        if "--feeling" in args:
            try:
                feeling = args[args.index("--feeling") + 1]
            except Exception:
                pass
        cmd_history(n, feeling)
    elif cmd == "dashboard":
        out = None
        if "--out" in args:
            try:
                out = args[args.index("--out") + 1]
            except Exception:
                pass
        cmd_dashboard(out)
    elif cmd == "toggle":
        cmd_toggle(args[1] if len(args) > 1 else None)
    elif cmd == "set":
        if len(args) < 3:
            sys.exit("usage: gauges.py set <feeling> <T>")
        cmd_set(args[1], args[2])
    elif cmd == "presets":
        cmd_presets()
    elif cmd == "preset":
        if len(args) < 2:
            sys.exit("usage: gauges.py preset <name>")
        if not STATE_PATH.exists():
            sys.exit("state missing -- run: init --preset " + args[1])
        st = load_state()
        before = st.get("preset")
        apply_preset(st, args[1])
        save_state(st)
        log(f"preset: {(before or 'default')} -> {args[1]}")
        log("  " + PRESETS[args[1]][0])
        log("  taus re-derived from CATALOG (idempotent, never compounded)")
    elif cmd == "key-status":
        cmd_key_status()
    else:
        sys.exit("unknown subcommand: " + cmd)


if __name__ == "__main__":
    main()
