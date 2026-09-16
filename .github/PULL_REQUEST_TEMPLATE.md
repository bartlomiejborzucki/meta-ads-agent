## What and why

<!-- What changes, and what problem it solves. -->

## Checks

- [ ] `uv run pytest` passes
- [ ] `uv run ruff format --check src tests` and `uv run ruff check src tests` pass
- [ ] `uv run mypy` passes
- [ ] `claude plugin validate . --strict` passes, if a manifest changed

## Third-party material

<!-- Delete this section if nothing came from another project. -->

- Source repository and license:
- Reviewed commit SHA:
- Class (`adapted` / `reimplemented` / `facts-adopted` / `reference-only`):
- [ ] `docs/research/provenance.md` updated
- [ ] `THIRD_PARTY_NOTICES.md` updated, if the class is `adapted`

**Not acceptable:** material from a BUSL-licensed, unlicensed, or
carve-out-licensed source. When in doubt, reimplement - it is cheaper than a
license audit.

## If this adds a validation rule

- [ ] It enforces a **platform constraint** - something Meta rejects, or that
      makes an ad undeliverable - and I can point at the behaviour.

A media-buying heuristic belongs in a skill reference, labelled as a heuristic
with its reasoning and a configurable default. A user's business rule belongs in
`brand.yaml`. See
`docs/architecture/adr/ADR-007-heuristics-vs-constraints.md`.

## If this changes the API fallback

- [ ] I checked whether Meta's official MCP can do this, and named the tool
- [ ] The capability is in `config/capabilities.yaml` with a `last_reviewed` date
- [ ] `tests/test_capability_routing.py` gap assertion updated deliberately
- [ ] Destructive or spend-affecting commands support `--dry-run`

The fallback is expected to **shrink**. Growing it needs a stated reason;
"easier this way" is not one. See
`docs/architecture/adr/ADR-002-api-fallback.md`.

## If this touches write safety

- [ ] New objects are still created PAUSED
- [ ] Activation, budget increases, deletion, and PII uploads still require
      explicit approval
- [ ] Nothing here lets the CLI bypass the approval model

## Anything else

<!-- Known limitations, follow-up work, things you were unsure about. -->
