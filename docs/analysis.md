# Analysis: asking the board a question

`analyze.py` (sits beside `gauges.py`, stdlib only) answers questions about
gauge history *in plain language* rather than dumping numbers.

    python analyze.py --stats              # raw table, NO model call
    python analyze.py "why are you in such a good mood"
    python analyze.py "whats bothering you"
    python analyze.py "how have you been lately"
    python analyze.py "when did i last feel joy"

## Why plain language

You don't ask a partner for a CSV. You ask *why are you in such a good mood*
or *what's bothering you*, and you want a reason — not a mean and a standard
deviation. So the pipeline is:

    question  ->  route  ->  structured findings  ->  ONE chat call  ->  answer

The numbers are computed in stdlib Python and passed to the model as JSON. The
model narrates; it never does arithmetic and never reads files.

## Routing

Keyword match against the question (`route()`):

| route    | triggers | findings pool |
|---|---|---|
| `when`   | a feeling name + `when` / `last time` / `peak` | that feeling's peak tick only |
| `bothered` | bother, bugg, upset, wrong, annoy, frustrat, worri, stress, off | top 4 NEGATIVE by current T |
| `mood`   | mood, happy, good, great, glow, joy, why are you | top 4 POSITIVE by current T |
| `trend`  | how have you been, lately, trend, recently, going | top 6 overall + trend |
| `general`| anything else | top 6 overall |

## Grounding — the part that makes it a reason

Every feeling in the pool carries its **peak tick**: the history record where
that feeling's `T` was highest, plus an `excerpt` of the context packet from
that tick. The narrator is instructed to refer to the excerpt concretely, so
the answer names *the moment* that moved the gauge instead of restating a
number. This is why `history.jsonl` stores the packet alongside the floats —
the receipts were kept so they could be spent here.

`z` (current vs. history mean, in standard deviations) is computed when the
history has variance; it is `None` for a single record and the narrator is
told `data_thin: true` so it admits it has almost nothing to go on rather
than inventing a cause.

## Narration model

`gpt-oss:20b` via `https://ollama.com/v1/chat/completions`.

**Not clef.** `clef:27b` is decision-only and returns 400 on
`/v1/chat/completions` (see `docs/clef-systemone-api.md`). The heater and the
narrator are deliberately different endpoints.

The model returns a `reasoning` field alongside `content`; `narrate()` reads
`content` first and falls back to `reasoning` only if `content` is empty.

## Read-only guarantee

`analyze.py` never calls `save_state()` and never opens `history.jsonl` for
anything but reading. `current_board()` calls `gauges.decay()` on an in-memory
copy of state, which mutates the dict but is never persisted — so the board
you see is decayed-to-now while `state.json` on disk is byte-identical.

Verified: `sha256sum state.json` identical before and after `--stats` and
after three narrated questions; history line count unchanged.

## Failure behaviour

If the narrator call fails (no key, network, timeout), `main()` prints the
exception and dumps the structured findings JSON — the facts are never lost
behind a failed API call.

## Limits at time of writing

History had **1 record** when this landed, so `trend` and `risers` return
`None`/`[]` by design and every answer carries `data_thin: true`. The routes
are mechanical and the data accumulates behind them; expect the answers to get
substantially better once there are a few dozen ticks to peak-hunt over.
