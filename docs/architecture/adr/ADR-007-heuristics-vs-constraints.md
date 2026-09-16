# ADR-007: Constraints, heuristics, and business rules are three different things

- **Status:** accepted
- **Date:** 2026-09-16

## Context

Advertising skill repositories routinely mix three kinds of claim in one table with equal
authority:

- "Special ad categories must be declared" — a platform rule Meta enforces, with account
  suspension as the penalty.
- "Never increase a budget by more than 20% at a time" — a widely-repeated media-buying
  heuristic. Sometimes reasonable. Not a platform rule, and not universally true.
- "We never advertise above 30 PLN CPA" — a specific advertiser's business rule, correct for
  them and meaningless elsewhere.

Presented together, a user cannot tell which the platform will enforce, which is one
practitioner's opinion, and which somebody's finance team decided. Worse, encoding the middle
category in deterministic code means the tool refuses technically valid configurations for
reasons it cannot justify.

The audited projects do this consistently: hardcoded `frequency > 4.0`, "don't touch learning
phase for 7 days", "+20% max scaling", "copy what the top marketers are doing", all stated as
rules.

## Decision

Three categories, kept separate, treated differently:

| Category | Definition | Where it lives | Enforcement |
| --- | --- | --- | --- |
| **Platform constraint** | Meta rejects the call or penalises the account | `src/meta_ads_agent/validation/`, and surfaced in skills | **Blocks.** A validation error. |
| **Media-buying heuristic** | Practitioner judgement; often useful, sometimes wrong | `skills/*/references/*.md`, labelled as a heuristic with a default and its reasoning | **Advises.** Never blocks. |
| **User business rule** | This advertiser's policy | `.meta-ads/brand.yaml` thresholds, offer configs, profiles | **Blocks if the user configured it to.** |

Rules that follow:

- The validator only enforces what Meta enforces. It never rejects a valid configuration
  because a heuristic dislikes it.
- Every heuristic in a skill states that it is a heuristic, gives its default, and says what
  the default is trying to protect against.
- Every numeric threshold in a heuristic is overridable from the brand workspace. Thresholds
  are defaults, not constants.
- Strategy claims are labelled with their confidence. When current platform behaviour matters,
  the skill prefers Meta's documentation, the account's own data, tool schemas, and
  `ads_get_field_context` over any remembered practice.
- Skills do not cite influencer consensus as evidence.

## Consequences

**Good.** Users can tell what will actually break. Advanced users are not fought by the tool.
The validator stays small and defensible — every rule in it can point at a platform behaviour.
Heuristics can be improved or discarded without touching code.

**Bad, and accepted.**
- A user can configure something ill-advised but valid. Correct: it is their money and their
  account. The agent advises, notes the risk, and proceeds.
- More words per heuristic than a bare table. Worth it — the reasoning is what makes it
  overridable.
- Deciding the category is a judgement call at contribution time, so `CONTRIBUTING.md` asks
  for it explicitly: a PR adding a hard validation rule must cite the platform behaviour it
  enforces.
