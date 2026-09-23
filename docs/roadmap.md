# Roadmap

Direction, not commitments. The gap list this is built from is the README's
[What's missing](../README.md#whats-missing); the order below comes from a
review of 0.2.0 on 2026-09-23, whose security findings were fixed in 0.2.1
([SECURITY.md](../SECURITY.md#021-review)).

One constraint shapes the order: **there is no Meta test ad account yet.**
Everything that needs one is collected in a single blocked group at the end,
and nothing before it depends on it.

## 0.3 - local state and the validator

Make what already exists hard to break.

- **File locking** for campaign state, the asset manifest, `actions.jsonl`
  and the installer, using `fcntl` / `msvcrt` with no new dependency. Today
  two sessions read, modify and write the same file and lose each other's
  entries, which for the asset manifest means duplicate uploads. `fsync` the
  parent directory after `os.replace`.
- **A stable plan fingerprint.** It currently hashes defaulted fields too, so
  adding any field with a default to the plan model changes every existing
  fingerprint and falsely blocks resume. Hash with `exclude_defaults` and an
  explicit schema version.
- **Validator gaps:** a lifetime budget at campaign level with no end date;
  `bid_amount` representability; Meta's minimum budgets; a local `.mp4`
  accepted by a `single_image` ad.
- **`Money` edges:** refuse non-finite and negative amounts and fractional
  minor units rather than truncating. Re-check Meta's own currency offsets
  (HUF, TWD, IDR, COP, CRC) against the ISO table.
- **The action log records failures and dry runs**, which `ActionRecord`
  already supports and nothing writes.
- **Declared but not wired:** `naming` / `utm` template substitution,
  `TrackingPlan.utm` assembled into the destination URL, `AssetRef.placement`.
- **Safety policy wording:** `budget_increase` says "any budget change" in its
  body. Decide whether a decrease needs approval and make the name agree.
- **Structure:** split `plan_validator.py` by concern (account, budget,
  targeting, creative); per-command `register(subparsers)` in the CLI; one
  `Provider` enum and one list of video extensions instead of two and three.
- **CI:** `windows-latest` and `macos-latest` jobs (the Windows path is
  advertised and tested only against a fake); ruff over `scripts/`; version
  agreement checked on every PR, not only at release; an issue opened when
  the capability map is 75 days old (the `doctor` warning fires at 90, around
  2026-12-15); `upstream-check` failing when its API calls fail and creating
  its own label; actions pinned by SHA.

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

In the README's order: carousel creatives; Instagram existing-post campaigns
through `ads_boost_ig_post`; lookalike audience workflows; A/B tests through
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
