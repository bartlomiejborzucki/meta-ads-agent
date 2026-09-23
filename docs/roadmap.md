# Roadmap

Direction, not commitments. The gap list this is built from is the README's
[What's missing](../README.md#whats-missing); the order below comes from a
review of 0.2.0 on 2026-09-23, whose security findings were fixed in 0.2.1
([SECURITY.md](../SECURITY.md#021-review)).

One constraint shapes the order: **there is no Meta test ad account yet.**
Everything that needs one is collected in a single blocked group at the end,
and nothing before it depends on it.

## 0.3 - local state and the validator (done)

In 0.3.0; the detail is in the [changelog](../CHANGELOG.md). In
short: file locking and a merge-under-lock for campaign state; a plan
fingerprint that survives new model fields; validator checks for campaign
lifetime budgets, bids, account minimum budgets and a video in an image ad;
Meta's own currency offsets where they differ from ISO; failures and dry
runs in the action log; `render-plan` for the brand naming and UTM templates;
the validator split by concern; macOS and Windows CI, pinned actions, and an
upstream check that fails when it could not look.

Two items were looked at and deliberately not done:

- **One `Provider` enum.** The two differ on purpose: the capability map
  needs `none` (nobody provides this), and a created object must never have
  been created by nobody. Merging them would allow exactly that in state.
- **Per-command `register(subparsers)` in the CLI.** The command modules are
  imported lazily so `--help` and `doctor` stay fast and a missing optional
  dependency cannot break an unrelated command. Registering from each module
  would import all of them at startup.

`AssetRef.placement` was not built either. It is refused by the validator
until it is real, and stays on the list below.

## 0.4 - arithmetic in code

What [ADR-008](architecture/adr/ADR-008-deterministic-vs-agent-layer.md)
promised and the skills still do in prose.

- **`report`:** equal-length window alignment, volume floors, noise bands.
  `meta-ads-agent report compare` takes insights JSON as the MCP returns it
  and prints the comparison.
- **`fatigue`:** CTR against the entity's own baseline, frequency, spend since
  decline, creative age. The skill gets numbers; the conclusion stays with it.
- **Budget pacing** analysis.
- **Leaner skills:** the preflight block is copied into all nine (about 400
  tokens each); point to `meta-ads-core` instead. Add trigger evals, since
  `meta-ads-core`'s description overlaps every other skill's.

## 0.5 - verification without a test account

Reduce the risk that the request shapes are wrong, using what is available.

- **Offline contract tests:** check every fallback request against the
  `Field` classes and enums of the `facebook-business` SDK (`AdCreative.Field`,
  `AdVideo.Field`, ...), so a misspelt field or an out-of-range value stops
  passing the fake SDK.
- **Recorded Graph responses** - success, the errors in `meta-errors.md`, a
  timeout mid-transcode - and tests of the recovery paths over them.
- **The live-test harness**, written and skipped without
  `META_ADS_LIVE_TESTS=1`, plus a manual workflow behind a GitHub Environment
  with a required reviewer. Ready for the day an account exists.
- **Capability drift check:** a script that compares a pasted MCP tool list
  from any authenticated session with `config/capabilities.yaml`.
- **A real Codex install**, Linux and Windows, with the results written up.
- A security review of 0.3 to 0.5 recorded in `SECURITY.md`.

## 0.6 and later - new capability

In the README's order: carousel creatives; placement-specific assets
(`AssetRef.placement`, refused by the validator until then); Instagram
existing-post campaigns through `ads_boost_ig_post`; lookalike audience workflows; A/B tests through
`ads_experiment_*`, with the approval treatment a delivery split needs;
catalog and dynamic ads; more than one ad account per workspace. An opt-in
MCP proxy that enforces the approval model is the change to revisit if the
advisory model proves insufficient ([ADR-001](architecture/adr/ADR-001-mcp-first.md)).

## Blocked on a test account

No version number until an account exists:

- running the live tests;
- the first campaign created on a real account;
- Meta confirming the fallback's request shapes;
- introspecting the MCP tool list from our own authenticated session.

Until then the README keeps these under "Never run against Meta".

## 1.0 - distribution

Only after the blocked group is done: a 1.0 that has never run against Meta
would claim something it has not shown. Then a final name (it is still
provisional, which [ADR-009](architecture/adr/ADR-009-distribution.md) lists
as a reason not to publish), PyPI, a Codex marketplace entry, and plan and
state schemas stable enough to promise migrations for.

## Ongoing

Shrinking the fallback. Every capability Meta adds to its official MCP is one
we delete.
