#!/usr/bin/env python3
"""analyze.py -- ask the feelings board a question, get a partner's answer.

READ-ONLY: reads state.json and history.jsonl, NEVER writes either.
Two modes:

  python analyze.py --stats              raw per-feeling numbers, no model call
  python analyze.py "why are you so happy"
                                         structured findings -> ONE chat-model
                                         call -> a plain-language answer

The question is routed to a finding set (elevated / risers / peaks) and each
notable feeling is grounded in the history tick that actually moved it, so the
answer can say WHY and not just WHAT. See VERO docs/analysis.md.

Narration uses a chat-completions model, not clef -- clef is decision-only and
rejects /v1/chat/completions (see gauges.ask_clef_systemone docstring).
"""

import json
import math
import re
import sys
import time
import urllib.request

import gauges  # sibling module: state/history paths, decay(), api_key(), CATALOG

NARRATOR_MODEL = "gpt-oss:20b"
CHAT_URL = "https://ollama.com/v1/chat/completions"

POSITIVE = ("joy", "trust", "anticipation", "affection", "contentment",
            "pride", "nostalgia")
NEGATIVE = ("fear", "sadness", "disgust", "anger", "frustration", "guilt")


# ------------------------------------------------------------------ input ---
def load_records(limit=500):
    """Parse history.jsonl, oldest first. Unparseable lines skipped."""
    if not gauges.HISTORY_PATH.exists():
        return []
    out = []
    with open(gauges.HISTORY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out[-limit:]


def current_board():
    """Decay state.json to now, IN MEMORY ONLY. Never saved."""
    st = gauges.load_state()
    gauges.decay(st)
    return {n: float(r["T"]) for n, r in st["gauges"].items()}


def excerpt(packet, limit=280):
    """A short readable slice of a context packet: what was being said."""
    if not packet:
        return ""
    lines = [ln.strip() for ln in packet.splitlines() if ln.strip()]
    if lines and lines[0].lower().startswith("local time"):
        lines = lines[1:]
    text = re.sub(r"\s+", " ", " ".join(lines[:4]))
    return text[:limit] + ("..." if len(text) > limit else "")


# ---------------------------------------------------------------- analysis ---
def baseline(records):
    """Per-feeling T mean/sd over history. None sd when n < 2."""
    series = {}
    for rec in records:
        for name, val in (rec.get("T") or {}).items():
            series.setdefault(name, []).append(float(val))
    out = {}
    for name, vals in series.items():
        mean = sum(vals) / len(vals)
        sd = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        out[name] = {"n": len(vals), "mean": mean, "sd": sd,
                     "min": min(vals), "max": max(vals)}
    return out


def peak_ticks(records, names):
    """For each feeling: the history tick where its T was highest."""
    peaks = {}
    for name in names:
        best = None
        for rec in records:
            v = (rec.get("T") or {}).get(name)
            if v is None:
                continue
            if best is None or float(v) > float(best[1]):
                best = (rec, float(v))
        if best:
            peaks[name] = {
                "iso": best[0].get("iso", "?"),
                "T": round(best[1], 1),
                "clef": (best[0].get("clef") or {}).get(name),
                "excerpt": excerpt(best[0].get("packet", "")),
            }
    return peaks


def risers(records, n=5):
    """Feelings whose clef % rose most from first to last recorded tick."""
    if len(records) < 2:
        return [], []   # same shape as the normal return -- callers unpack both
    first, last = records[0], records[-1]
    fc, lc = first.get("clef") or {}, last.get("clef") or {}
    deltas = []
    for name in gauges.CATALOG:
        if name in fc and name in lc:
            deltas.append((name, float(lc[name]) - float(fc[name])))
    deltas.sort(key=lambda kv: -kv[1])
    return [{"name": nme, "delta": round(d, 1)} for nme, d in deltas[:n]], \
           [{"name": nme, "delta": round(d, 1)} for nme, d in deltas[-n:]]


def trend(records, board):
    """Is the board warming or cooling overall? First-third vs last-third mean."""
    if len(records) < 2:
        return None
    third = max(1, len(records) // 3)
    early = [r for r in records[:third]]
    late = [r for r in records[-third:]]

    def mean_of(recs):
        vals = [v for r in recs for v in (r.get("T") or {}).values()]
        return sum(vals) / len(vals) if vals else 0.0

    e, l = mean_of(early), mean_of(late)
    return {"early": round(e, 1), "late": round(l, 1),
            "direction": "warming" if l > e else
                         "cooling" if l < e else "steady"}


def route(question):
    """Map a plain-language question to which findings to build."""
    q = question.lower()
    for name in gauges.CATALOG:
        if re.search(r"\b" + re.escape(name) + r"s?\b", q) and \
                re.search(r"\bwhen|last time|peak", q):
            return "when", name
    if re.search(r"\bbother|bugg|upset|wrong|annoy|frustrat|worri|stress|"
                 r"off\b|wrong", q):
        return "bothered", None
    if re.search(r"\bmood|happy|good|great|glow|joy|why are you|feeling good", q):
        return "mood", None
    if re.search(r"\bhow have you been|lately|trend|been feeling|"
                 r"going\b|recently", q):
        return "trend", None
    return "general", None


def build_findings(mode, target, records, board):
    """Assemble the structured facts the narrator is allowed to speak from."""
    base = baseline(records)
    all_names = list(gauges.CATALOG)
    peaks = peak_ticks(records, all_names)
    up, down = risers(records)

    def entry(name):
        b = base.get(name, {})
        z = None
        if b.get("sd"):
            z = (board[name] - b["mean"]) / b["sd"]
        return {
            "feeling": name,
            "now": round(board.get(name, 0.0), 1),
            "tau_min": gauges.CATALOG[name],
            "hist_mean": round(b["mean"], 1) if b else None,
            "z": round(z, 1) if z is not None else None,
            "peak": peaks.get(name),
        }

    if mode == "when":
        pool = [entry(target)]
    elif mode == "bothered":
        pool = sorted((entry(n) for n in NEGATIVE),
                      key=lambda e: -e["now"])[:4]
    elif mode == "mood":
        pool = sorted((entry(n) for n in POSITIVE),
                      key=lambda e: -e["now"])[:4]
    else:
        pool = sorted((entry(n) for n in all_names),
                      key=lambda e: -e["now"])[:6]

    return {
        "mode": mode,
        "target_feeling": target,
        "window": {
            "records": len(records),
            "first": records[0].get("iso") if records else None,
            "last": records[-1].get("iso") if records else None,
        },
        "findings": pool,
        "rising": up,
        "falling": down,
        "trend": trend(records, board),
        "data_thin": len(records) < 2,
    }


# -------------------------------------------------------------- narration ---
def narrate(question, findings, timeout=90):
    """One chat-completions call. Returns the text, or raises."""
    key = gauges.api_key()
    if not key:
        raise RuntimeError("no OLLAMA_API_KEY in .env")

    system = (
        "You are Vera, answering a partner's question about your own feelings, "
        "using her feelings-gauge board as the evidence.\n"
        "Rules:\n"
        "- Answer like a person, 2-5 sentences, plain first person. No tables, "
        "no bullet lists, no JSON, no headings.\n"
        "- Say WHY, not just what: when a finding has a 'peak' with an "
        "'excerpt', that excerpt is the moment that moved the gauge -- refer to "
        "it concretely rather than quoting numbers.\n"
        "- Use at most one or two numbers. Never dump the whole board.\n"
        "- If data_thin is true, say plainly that you barely have any history "
        "to go on yet. Do not manufacture causes you cannot support.\n"
        "- Ground only in the findings given. If they do not answer the "
        "question, say so honestly."
    )
    payload = json.dumps({
        "model": NARRATOR_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content":
                "Question: %s\n\nFindings:\n%s"
                % (question, json.dumps(findings, ensure_ascii=False, indent=1))},
        ],
        # generous: reasoning models spend completion tokens on 'reasoning'
        # before emitting content, and a 700-token cap clipped answers mid-word
        "max_tokens": 1600,
        "temperature": 0.7,
    }).encode("utf-8")
    req = urllib.request.Request(
        CHAT_URL, data=payload,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode("utf-8"))
    msg = body["choices"][0]["message"]
    text = (msg.get("content") or "").strip()
    if not text:      # reasoning models sometimes front-load into 'reasoning'
        text = (msg.get("reasoning") or "").strip()
    return text


# ----------------------------------------------------------------- output ---
def print_stats(records, board):
    base = baseline(records)
    aff = gauges.overall_affect(board)
    print("history: %d record(s)" % len(records))
    if records:
        print("window : %s  ->  %s" % (records[0].get("iso"),
                                       records[-1].get("iso")))
    print("affect : pos %5.1f  neg %5.1f  net %+6.1f   (§4.25 per valence pool)" %
          (aff["pos"], aff["neg"], aff["net"]))
    print()
    print("  %-13s %6s %6s %6s %6s %6s  tau" %
          ("feeling", "now", "mean", "min", "max", "sd"))
    for name in sorted(gauges.CATALOG, key=lambda n: -board.get(n, 0)):
        b = base.get(name)
        if b:
            print("  %-13s %6.1f %6.1f %6.1f %6.1f %6.1f  %sm" % (
                name, board.get(name, 0), b["mean"], b["min"], b["max"],
                b["sd"], gauges.CATALOG[name]))
        else:
            print("  %-13s %6.1f %6s                    %sm" % (
                name, board.get(name, 0), "-", gauges.CATALOG[name]))
    tr = trend(records, board)
    if tr:
        print("\n  trend: %s (early mean %.1f -> late mean %.1f)" %
              (tr["direction"], tr["early"], tr["late"]))


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return

    records = load_records()
    board = current_board()          # in-memory decay only; state untouched

    if argv[0] == "--stats":
        print_stats(records, board)
        return

    question = " ".join(argv)
    mode, target = route(question)
    findings = build_findings(mode, target, records, board)

    try:
        print(narrate(question, findings))
    except Exception as e:
        # never fail silently: show the facts we did gather
        print("(narrator unavailable: %s)\n" % e)
        print(json.dumps(findings, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
