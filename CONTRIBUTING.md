# Contributing

Thanks for looking. This project has a few opinions that shape what changes fit,
so they are stated up front rather than discovered in review.

## The three that matter most

**1. MCP first.** Meta's official Ads MCP is the execution layer for everything
it covers. A change that adds a local implementation of something the MCP
already does will be declined. The fallback exists for seven specific gaps and is
expected to **shrink** - see
[ADR-002](docs/architecture/adr/ADR-002-api-fallback.md).

**2. Constraints, heuristics, and business rules are different things.** The
validator enforces only what Meta enforces. Media-buying opinions live in skill
references, labelled as heuristics with their reasoning and a configurable
default. A user's own thresholds live in their workspace. See
[ADR-007](docs/architecture/adr/ADR-007-heuristics-vs-constraints.md).

**3. Nothing spends without explicit approval.** New objects are PAUSED.
Activation, budget increases, deletion, and customer-list uploads all require
the user to say so specifically. The CLI must not become a way around that. See
[ADR-004](docs/architecture/adr/ADR-004-write-safety.md).

## Setup

```bash
git clone https://github.com/bartlomiejborzucki/meta-ads-agent.git
cd meta-ads-agent
uv sync --extra dev
uv run pytest
```

One command for the whole check:

```bash
uv run pytest && uv run ruff format --check src tests && \
  uv run ruff check src tests && uv run mypy
```

Tooling is deliberately small: `ruff` for format and lint, `mypy` for types,
`pytest` for tests. Please do not add a fourth overlapping tool.

## Where things go

| Kind of change | Home |
| --- | --- |
| Workflow, judgement, advice | `skills/*/SKILL.md` |
| Changing Meta specifics, examples, playbooks | `skills/*/references/*.md` |
| A template or schema a skill documents | `skills/*/assets/*` |
| A passage that belongs in several skills | `packaging/shared/*.md`, then re-run the sync script |
| Arithmetic, schemas, state, I/O | `src/meta_ads_agent/` |
| Who owns a capability | `config/capabilities.yaml` |
| Host packaging | `.claude-plugin/`, `.codex-plugin/`, `integrations/` |

Two rules follow from
[ADR-008](docs/architecture/adr/ADR-008-deterministic-vs-agent-layer.md): no API
request bodies in a `SKILL.md`, and no media-buying strategy in Python.

## Skills

One canonical `skills/` directory. Both host manifests point at it, and CI fails
if a second directory containing `SKILL.md` files appears
([ADR-003](docs/architecture/adr/ADR-003-dual-agent-packaging.md)).

- Keep `SKILL.md` short. Detail goes in `references/`.
- Do not name a host. Skills describe the Meta workflow.
- Frontmatter needs `name` (matching the directory) and a `description` that
  says **when** to use the skill, including the phrases a user would actually
  type.
- Label heuristics as heuristics. Give the reasoning and the default.
- Do not present a practitioner's view as a platform fact.

### A skill has to work on its own

A skill directory is the unit of distribution, and one of the supported
install shapes is a single `skills/meta-ads-<name>/` folder copied out of
here. So a relative path inside a skill must resolve inside that same skill.
Cross-skill and repository pointers are named in prose plus an absolute URL -
never a path that only resolves in a checkout.

Shared passages are generated rather than copied, so twelve files cannot end
up saying eleven different things. Edit `packaging/shared/<name>.md`, never the
rendered block in a `SKILL.md`.

```bash
python3 scripts/sync_skill_blocks.py        # rewrite the generated copies
python3 scripts/check_skill_packaging.py    # install each skill alone, resolve everything
```

Both run in CI. The rules and the reasoning:
[docs/reference/packaging.md](docs/reference/packaging.md).

## Third-party material

Before adapting anything from another project, check its license. Three of the
eleven projects reviewed in
[the ecosystem audit](docs/research/ecosystem-audit.md) cannot be copied from:
one is BUSL-1.1, one has no license, and one has a carve-out withholding rights
to its own substance.

A PR introducing third-party material must:

1. Name the source repository, its license, and the exact commit SHA.
2. Classify it: `adapted`, `reimplemented`, `facts-adopted`, or
   `reference-only`.
3. Add a row to [`docs/research/provenance.md`](docs/research/provenance.md),
   and to [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) if `adapted`.

**When in doubt, reimplement.** It is cheaper than a license audit, and 0.1.0
contains no adapted third-party material at all.

## Adding a validation rule

Only for **platform constraints** - something Meta rejects, or that makes an ad
undeliverable. The PR must be able to point at the behaviour.

A heuristic goes in a skill reference. A user's business rule goes in
`brand.yaml`. The validator refusing a technically valid configuration is a bug.

## Changing the API fallback

**Growing it needs justification.** State which MCP tool you checked and why it
is insufficient - with the error or the missing field. "Easier this way" is not
a reason.

**Shrinking it is the goal.** If Meta ships a tool that closes a gap, please
open a [capability change issue](.github/ISSUE_TEMPLATE/capability_change.yml)
or follow
[docs/reference/capability-refresh.md](docs/reference/capability-refresh.md).

Either way: destructive and spend-affecting commands support `--dry-run`, and
there is no generic "run any Graph call" command. There will not be one.

## Tests

Required for anything that could silently produce a wrong answer. Money and
period comparison especially.

- **No test may contact Meta.** Mock the SDK boundary; `tests/test_api_fallback.py`
  shows the pattern.
- Fake credentials must not look real. Use the values in `tests/conftest.py`.
- Live tests are opt-in, marked `live`, and never run in CI. See
  [`tests/live/README.md`](tests/live/README.md).
- Test the safety model, not only the happy path: the interesting assertions are
  that an active object is refused, an ambiguous write is not retried, and a
  changed plan blocks a resume.

## Documentation

- Do not claim support for something tests do not demonstrate.
- Date anything about Meta's platform. It changes.
- Mark what you **verified** versus what you assume. The capability document
  keeps community-reported observations in their own section, flagged
  unverified, for exactly this reason.

## Commits and PRs

Logical commits with messages that explain **why**. The PR template asks about
provenance, validation scope, fallback changes, and write safety - please fill
in the sections that apply and delete the ones that do not.

## Security

Do not open a public issue for a vulnerability. See
[SECURITY.md](SECURITY.md). Anything that could leak a credential or customer
data, or bypass an approval gate, is the highest-priority class of bug here.

## Code of conduct

[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
