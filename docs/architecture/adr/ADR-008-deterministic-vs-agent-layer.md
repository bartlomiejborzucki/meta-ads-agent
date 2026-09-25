# ADR-008: Arithmetic and schemas in Python; workflow and judgement in skills

- **Status:** accepted
- **Date:** 2026-09-16

## Context

Two failure modes show up in agent tooling for ads.

Putting everything in prose: the model does its own currency conversion, its own
week-over-week deltas, and hand-assembles JSON for API calls. It gets `* 100` wrong on a
zero-decimal currency, or compares a 7-day window to a 9-day one, and nothing catches it.

Putting everything in code: campaign strategy becomes a decision tree, creative angles come
from templates, and the tool refuses valid configurations because a heuristic is hardcoded —
the problem [ADR-007](ADR-007-heuristics-vs-constraints.md) addresses.

One audited project got the split right: arithmetic in small Python scripts with explicit
noise bands and volume floors, judgement left in prose. Everything else put all of it in one
place.

## Decision

Draw the line at **determinism**. If the same input must always give the same answer, and
being wrong is silent, it is code. If it requires judgement about a specific business, it is a
skill.

**Python** (`src/meta_ads_agent/`):
money conversion and formatting; config, plan, and state schema validation; platform-constraint
validation; state persistence and resume logic; asset fingerprinting and the upload manifest;
capability routing lookups; secret redaction; the Graph API version constant; the fallback
API calls.

**Skills** (`skills/*/SKILL.md` + `references/`):
what the user meant; which skill to use; whether evidence supports a conclusion; creative
angles and copy; which metrics matter for this objective; whether a change needs approval; how
to explain a result; media-buying heuristics, labelled as such.

Consequences of the line:

- No API logic in `SKILL.md`. A skill names a tool and what to pass conceptually; it does not
  embed request bodies.
- No media-buying strategy in Python. No `if ctr < 0.01: pause()`.
- Once a plan is validated, execution reads the **plan**, not the conversation. Prose is not
  re-parsed when a structured artifact exists.
- Anything that could silently produce a wrong number gets a unit test. Money and period
  comparison especially.

## Consequences

**Good.** The dangerous parts are testable and tested. Skills stay short, which keeps them
loaded and readable. Marketing opinion can be revised without touching code, and arithmetic can
be fixed without rewriting prose. Model variation cannot change a budget conversion.

**Bad, and accepted.**
- Two places to look when tracing a behaviour. Mitigated by keeping the boundary crisp and
  documented here.
- Some cases sit near the line. Creative fatigue is the clearest: the *signals* (CTR delta vs
  the entity's own baseline, frequency, spend since decline, creative age) are arithmetic and
  belong in code; the *conclusion* — whether this is fatigue, an auction shift, seasonality, a
  tracking break, or too little data — is judgement and belongs in the skill. In 0.1.0 the
  signals were computed in the skill from MCP insight responses. **Update, 0.4.0:** the code
  path exists - `meta-ads-agent report fatigue`, with `report compare` and `report pacing`
  beside it - and the skill interprets the numbers it prints.
- A little duplication between a Pydantic model and its description in a skill. Accepted; the
  model is authoritative and CI checks the plan example validates.
