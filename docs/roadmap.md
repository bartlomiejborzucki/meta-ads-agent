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

## 0.4 - arithmetic in code (done)

In 0.4.0: `meta-ads-agent report compare`, `fatigue` and `pacing` over
insights rows, with the thresholds from `brand.yaml` printed next to every
label; shorter shared skill blocks; and a trigger-eval suite in `evals/`.

One item changed shape on the way. The roadmap said to replace each skill's
preflight block with a pointer to `meta-ads-core`. That would break 0.2.0's
rule that a skill works when it is the only one installed, so the blocks were
shortened instead (by about a third) and stay in every skill.

The trigger evals have not been run: each run is a paid model call, and the
workflow waits for an `ANTHROPIC_API_KEY` secret and someone to start it.

## 0.5 - verification without a test account (done)

In 0.5.0: contract tests holding every fallback request up to the real SDK's
object descriptions; recorded Graph error responses replayed through the
SDK's real exception; the live tests written, skipping without an account;
`capabilities --compare` for a pasted tool list; and a security review of 0.3
to 0.5. The recorded errors found one real bug - code 368, a policy block,
was treated as retry-safe - and the review found one shell injection in a
workflow.

Two items did not happen as planned:

- **A CI workflow for the live tests** was dropped. `tests/live/README.md`
  already records why CI never runs them: it would put a token with
  `ads_management` on a real ad account into repository secrets.
- **A real Codex install** is still not done: there is no Codex on the
  machine this was built on. It moves to the blocked group below.

## 0.6 - creative formats (done)

In 0.6.0: carousel creatives (2 to 10 cards), Instagram existing-post creatives
built inert rather than boosted, and placement-specific assets through asset
customisation rules. The carousel grows the fallback, argued in
[ADR-010](architecture/adr/ADR-010-carousel-and-instagram-posts.md), which
also records why an Instagram post is not boosted: Meta does not document a
paused boost.

## 0.7 - audiences and experiments (done)

In 0.7.0: the `meta-ads-audiences` and `meta-ads-experiments` skills, and
`meta-ads-agent report power` for sizing a test before it splits delivery.
What was planned:

- **Lookalike audiences:** source selection (size, recency, event quality),
  country and ratio choice, and what to say when a source is too small. The
  MCP creates them; the skill decides what to create and asks first.
- **A/B tests and lift studies** through `ads_experiment_*`. A test splits
  live delivery, so creating one is at least `update_active`: the plan names
  the cells, the metric, the duration, and the minimum detectable effect it
  can resolve at the current volume - computed, not guessed.

## 0.8 - catalogs and more than one account

- **Catalog and dynamic ads:** a skill workflow over the 34 `ads_catalog_*`
  tools - catalog health first, then product sets, then a catalog campaign.
- **More than one ad account per workspace**, with every plan, state file and
  asset record already keyed by account.

## 0.9 - schemas worth promising

The plan, state, workspace and CLI JSON formats are what users and other
tools depend on. Before 1.0 they get an explicit stability policy, a schema
version check on read, and migrations tested from every earlier version.

## Blocked on a test account

No version number until an account exists:

- running the live tests;
- the first campaign created on a real account;
- Meta confirming the fallback's request shapes;
- introspecting the MCP tool list from our own authenticated session (the
  tooling is ready: `capabilities --compare`).

**Blocked on a Codex install:** installing the plugin in Codex on Linux and
on Windows, and writing up what differs from the documented steps.

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
