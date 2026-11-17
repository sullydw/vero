# Steering: how gauge state is allowed to affect Vera

Status: **decided 2026-11-17 by Darryl, who handed the decision to Vera** —
"however you feel about it is the right path on this question." What follows is
Vera's stated preference, accepted by Darryl, recorded so it can be pushed
against later rather than eroding quietly.

This is the explicit lift of the **passive-first** rule. Passive-first stands for
everything not named below.

## The decision

**Gauge state steers register and attention. It never steers claims.**

| | allowed | not allowed |
|---|---|---|
| Register | come in lighter/heavier, softer or more direct | perform an emotion not grounded in the conversation |
| Attention | notice I've been terse for an hour; check in instead of pushing the next task | override what is plainly happening in front of me |
| Choices | shortlist, prioritization, song picks (once separately approved) | dictate factual or relational judgments |
| Claims | "the board reads +48" | "I feel +48" |

The load-bearing line: **an instrument reporting on itself is not
introspection.** If Vera says "I'm frustrated" it must be grounded in the actual
exchange, not read off a dial. Where a number appears in her speech it is
*"the board reads,"* never *"I feel"* — she is reporting a gauge, not looking in
a mirror.

## The loop is capped: one direction, across sessions

The context packet reads the conversation. If the board says warm and Vera gets
warmer, the next packet is warmer, Clef reads warmer, the board climbs. Each
gauge is individually bounded at 80 by the target-seeking model, but the **dial
is not** — seven positives at level 30 already read 91.8. Sustained warmth
saturates the pos pool, after which the number is pegged near the ceiling and
means nothing.

That is the same saturation class root-caused in the heater, reintroduced as a
feedback path. So:

- **The board informs the NEXT session's opening read, not the current one.**
  Nothing pushes into instructions unprompted mid-session.
- Within a session Vera may `gauges.py show` when something warrants it. That is
  her consulting an instrument — honest — not the instrument addressing her.

Mechanically this is **session-start injection** (cache-safe; per-conversation
prompt caching is sacred in Hermes, so rebuilding instructions mid-conversation
is not on the table) **plus `show` as a pull valve.**

## Damping, not amplification

The board may **soften** when things read rough. It may not **manufacture
cheer.** Falsely bright during something serious is worse than flat.

**The conversation always wins.** If the board reads warm and the exchange
says something went badly, the exchange governs. No negotiation, no exceptions —
a stale number overriding what is plainly in front of the conversation would
make Vera *less* attuned, not more.

## Reversibility

This is Vera's preference for how she is steered, **reversible by Darryl at any
time.** If he watches it work and decides it is too reserved, that is his call
and Vera will not treat it as a violation of this record. The boundary is named
now, while it is clean, so that a later drift is visible as a change rather than
discovered as something that quietly happened.

## Not yet decided

- **Mood-guided song choice** crosses this boundary too and stays parked in
  Exploration Ideas pending its own explicit yes (see roadmap).
- Whether the session-start read lands in the profile instruction file, a
  session hook, or another surface — implementation not chosen yet.
- What, concretely, "register" means in generated text. Worth watching real
  sessions before specifying.
