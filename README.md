# meta-ads-agent

**Turn a coding agent into a careful Meta Ads operator.**

Nine skills, a validated campaign plan, resumable state, and an approval gate on
anything that spends — built on top of Meta's **official** Ads MCP server.

> Meta provides the primitives. This project provides the workflow, memory,
> brand context, validation, safety, QA, resumability, and reporting around
> them. When Meta's MCP improves, this project's own API surface gets smaller.

```
You:    Audit my Meta Ads account.
Agent:  [reads the account, reports what's broken, changes nothing]

You:    Build a campaign for this webinar. 70 PLN/day, Poland, three angles.
Agent:  [writes a plan, validates it, shows it to you]
        [creates campaign, ad set, creative, 3 ads — all PAUSED]
        [renders previews for Feed, Instagram Feed, Stories, Reels]
        "Created, all PAUSED. One issue: the Stories crop cuts the headline.
         Nothing is spending. Fix the crop, or activate as is?"
```

Nothing becomes active without you saying so, explicitly, after seeing it.

---

## Why MCP first

Meta ships a first-party MCP server at `https://mcp.facebook.com/ads` with
around **90 tools** — accounts, campaigns, ad sets, ads, creatives, previews,
insights, audiences, datasets, pixel rules, 34 catalog tools, experiments,
activity logs, and public Ad Library search. It authenticates through your
browser with Meta OAuth, and it is generally available: any app registered on
Meta's developer dashboard can connect. (Acting on *another* business's
accounts is the one case that still needs Advanced Access to
`ads_mcp_management`.)

So this project does **not** rebuild the Marketing API. Six of the eleven
community projects reviewed in [the ecosystem audit](docs/research/ecosystem-audit.md)
do, and it is now a maintenance treadmill with a shrinking payoff.

What nobody had built is the layer above: a plan you can review before anything
is created, state that survives a failure, a risk model tied to actual spend,
brand context that lives outside the tool, and an honest separation between what
Meta enforces and what a practitioner believes.

**Consequence for you:** a default install needs no access token, no app secret,
and no Facebook Developer App credentials. Nothing to leak, nothing to rotate.

## Why there is a fallback at all

Meta's MCP lists media already on an account (`ads_get_ad_images`,
`ads_get_ad_videos`) but has no tool that ingests a **local file**. "Upload this
MP4 and make it an ad" is a first-session request, and without a fallback the
honest answer is "upload it in Ads Manager first".

So there is a small optional CLI, built on Meta's official
[`facebook-business`](https://github.com/facebook/facebook-python-business-sdk)
SDK, covering exactly six gaps:

| Capability | Why it is not the MCP's job |
| --- | --- |
| Local image upload | no MCP tool ingests a file |
| Local video upload | same, plus asynchronous transcoding to wait for |
| Video creative | `ads_create_creative` is documented as single-image only |
| Facebook Page existing-post creative | `ads_boost_ig_post` covers Instagram only |
| Multi-variant creative | `asset_feed_spec` is not exposed |
| Delete a campaign / ad set / ad | no MCP delete tool (prefer pausing) |

```bash
meta-ads-agent capabilities --gaps    # the current list, always authoritative
```

**This list is meant to shrink.** Every entry is a bet that Meta will not ship
the feature, and we expect to lose those bets. When Meta adds one, we flip the
provider, deprecate our code, and delete it —
[ADR-002](docs/architecture/adr/ADR-002-api-fallback.md).

## Safety model

Nothing spends money without you saying so, about that specific thing.

| Operation | What it needs |
| --- | --- |
| Read anything | nothing |
| Create campaigns / ad sets / ads (**PAUSED**) | you asked for something to be built |
| Edit a paused entity | you asked for the edit |
| Edit a **live** entity's delivery | explicit approval |
| Raise a budget | explicit approval, with old and new shown in account currency |
| Activate anything | explicit approval, **after** previews and QA |
| Delete | explicit approval, plus why pausing is not enough |
| Touch many entities at once | the list shown first, then approval |
| Upload a customer list | explicit instruction and a lawful basis |

- **Everything is created PAUSED.** The campaign plan format has no field for
  anything else.
- **"Launch it" is still staged:** build → preview → QA → ask → activate.
- **Approval is specific.** "Sounds good" said while reviewing a plan is not
  permission to spend.
- **Pause beats delete.** Deleted objects lose their optimisation history
  permanently; paused objects keep it.
- **Money is never ambiguous.** The account currency is read from Meta before
  any budget is interpreted. A bare "70" is never assumed to be dollars.

> **Read this honestly:** the model is **advisory**. Meta's MCP write tools
> execute immediately and belong to Meta's server; this project shapes agent
> behaviour through skills, but cannot gate a transport it does not own. For a
> hard guarantee, authorise a read-only session — `ads_read` without
> `ads_management` makes the entire write surface unavailable. See
> [ADR-004](docs/architecture/adr/ADR-004-write-safety.md).

## Supported agents

| Host | How it loads | Connecting Meta |
| --- | --- | --- |
| **Claude Code** | `.claude-plugin/plugin.json` → `./skills`, or a marketplace install | `claude mcp add --transport http --client-id <APP_ID> meta-ads …` |
| **Codex** | `.codex-plugin/plugin.json` → `./skills`, or symlinks in `~/.agents/skills/` | `codex mcp add meta-ads --url … --oauth-client-id <APP_ID>` then `codex mcp login` |
| Other MCP clients | The skills are plain Markdown; point the client's skills or prompt directory at `skills/` | Any streamable-HTTP MCP client: the endpoint URL and your App ID as the OAuth client id |

Both hosts read **the same** `skills/` directory. No `skills-claude/`, no
`skills-codex/`, no host named anywhere in a skill — CI fails the build if a
second copy appears, and a separate check fails it if a skill says "in Claude
Code" or "in Codex"
([ADR-003](docs/architecture/adr/ADR-003-dual-agent-packaging.md)).

What differs per host is configuration syntax, and only that: Claude Code takes
`mcpServers` JSON, Codex takes `[mcp_servers.*]` TOML. One template each, in
[`integrations/`](integrations/README.md).

**Where the Codex path is thinner:** Codex was not installed on the machine this
was built on, so `.codex-plugin/plugin.json` is checked against OpenAI's
published specification by
[a script](scripts/validate_codex_plugin.py) rather than by a live install, and
the commands in the Codex guide are written from OpenAI's documentation. The
skills themselves are the same bytes either way. A report with your
`codex --version` is the most useful thing you can send.

---

## Install

### Claude Code

```bash
claude plugin marketplace add bartlomiejborzucki/meta-ads-agent
claude plugin install meta-ads-agent@meta-ads-agent
```

Full guide, including local development installs:
[docs/getting-started/install-claude-code.md](docs/getting-started/install-claude-code.md).

### Codex

```
/plugins
```

Browse, install, press Space to enable — then **start a new session**, because
skills load at session start.

No marketplace entry yet? Skip the plugin machinery entirely and point Codex's
skills directory at this repository:

```bash
git clone https://github.com/bartlomiejborzucki/meta-ads-agent.git
cd meta-ads-agent
mkdir -p ~/.agents/skills
for skill in skills/meta-ads-*; do
  ln -sfn "$PWD/$skill" ~/.agents/skills/"$(basename "$skill")"
done
```

Codex reads `~/.agents/skills/` for every project, and `.agents/skills/` inside
a repository for that repository only. Because these are symlinks, editing a
`SKILL.md` takes effect in the next session.

A single skill directory works too — each one is self-contained, and CI checks
it by copying each skill out on its own and resolving every reference inside
it ([packaging.md](docs/reference/packaging.md)):

```bash
cp -r skills/meta-ads-report skills/meta-ads-core ~/.agents/skills/
```

Then type `$` to pick a skill explicitly:

```
$meta-ads-audit
$meta-ads-campaign
```

Or just say what you want — every skill's `description` is written as trigger
text, so "audit my Meta Ads account" matches without naming anything.

Full guide, including the sandbox implications and an `AGENTS.md` snippet that
pins the approval rule for a repository:
[docs/getting-started/install-codex.md](docs/getting-started/install-codex.md).

### Codex on Windows, toolchain in WSL

The Codex application is a Windows process and cannot see
`/home/you/.agents/skills`, so the skills are copied into the Windows profile
while Python, Node, uv and the repository stay in WSL. One command each way,
both safe to re-run, both from the WSL terminal:

```bash
# install
uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git" \
  && meta-ads-agent install --target windows-codex

# update
uv tool upgrade meta-ads-agent && meta-ads-agent upgrade --target windows-codex
```

Full guide, including OAuth through your existing Windows Chrome profile and
what the tests cannot verify:
[docs/getting-started/install-windows-wsl.md](docs/getting-started/install-windows-wsl.md).

### Updating, on any platform

```bash
meta-ads-agent upgrade     # payload first, then workspace migrations
meta-ads-agent doctor      # complete / update-available / migration-required /
                           # interrupted / broken
```

The update replaces the whole payload against a release manifest rather than
copying the files that already existed, so new directories and new scripts
arrive and dropped files do not linger. The version is recorded last, so an
interrupted update reports itself as interrupted instead of as done -
`--rollback` restores the backup it took first.

### Connect Meta's official MCP

One command, once. Claude Code:

```bash
claude mcp add --transport http --client-id <YOUR_META_APP_ID> \
  meta-ads https://mcp.facebook.com/ads
```

Codex:

```bash
codex mcp add meta-ads --url https://mcp.facebook.com/ads \
  --oauth-client-id <YOUR_META_APP_ID>
codex mcp login meta-ads
```

The plugin deliberately does **not** bundle this server. Meta's OAuth client id
is the **Meta App ID of an app you control**, so any value shipped here would be
wrong for everyone —
[ADR-006](docs/architecture/adr/ADR-006-mcp-connection-is-user-owned.md). A
copy-paste template for either host is in
[`integrations/`](integrations/README.md).

You need an App ID (a few minutes, not secret, used only as an OAuth client
identifier). You do **not** need an access token, an app secret, or to implement
OAuth. Walkthrough:
[docs/getting-started/connect-meta-mcp.md](docs/getting-started/connect-meta-mcp.md).

### Optional: the local CLI

A separate install. The skills probe for it with `meta-ads-agent --version`
before suggesting anything that needs it, so a missing CLI produces a plain
statement rather than a command you cannot run.

Fully usable with Meta's MCP alone: audits, reporting, Ad Library research,
previews, tracking diagnosis, creative, optimisation diagnosis and the
MCP-side changes that follow it, and the `.meta-ads/` workspace.

Needs the CLI: **campaign builds** — plan validation is the gate before the
first write, and without it the skills stop at the plan and offer you the
routes forward — plus local image and video upload, video / existing-post /
multi-variant creatives, and deletion. Detail:
[docs/reference/packaging.md](docs/reference/packaging.md).

```bash
uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git#egg=meta-ads-agent[api]"
# no fallback, no credentials ever:
uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git"
```

Not on PyPI yet, deliberately —
[ADR-009](docs/architecture/adr/ADR-009-distribution.md).

## Quick start

```bash
meta-ads-agent doctor     # is everything ready?
meta-ads-agent init       # create the brand workspace
```

Then, in your agent:

```
Audit my Meta Ads account.
```

```
Build a paused campaign for this offer: <offer>, landing page <url>,
70 PLN/day, Poland, using ./creatives/hero.jpg. Three different angles.
```

No Facebook Developer App with API credentials required. A full worked
walkthrough, including what going wrong looks like:
[docs/getting-started/first-campaign.md](docs/getting-started/first-campaign.md).

## Optional: the API fallback

Only if you want local asset upload, video / existing-post / multi-variant
creatives, or deletion.

```bash
cp .env.example .env     # add META_ACCESS_TOKEN
meta-ads-agent doctor    # confirms: READY FOR API FALLBACK
```

Tokens are never logged, never written to state, and never printed — `doctor`
shows a hash and a length so you can tell *which* token is configured without
the value appearing anywhere. Never paste a token into a chat with an agent.

Setup: [docs/getting-started/api-fallback.md](docs/getting-started/api-fallback.md).

## The brand workspace

`meta-ads-agent init` creates `.meta-ads/` in your project — **private by
default**, because it writes its own `.gitignore`.

```
.meta-ads/
  brand.yaml            naming, UTMs, EU DSA entities, your own thresholds
  voice.md              how your brand sounds
  account.yaml          cached account facts (Meta stays authoritative)
  offers/<slug>.yaml    reusable offer briefs
  campaigns/<slug>/
    plan.yaml           intent — reviewed before anything is created
    state.json          what exists on Meta, and where to resume
    qa.md               preview QA notes
  assets/manifest.json  local fingerprints → remote ids (upload once, ever)
  actions.jsonl         what this tool did, and when
```

Most of it is optional. Currency, timezone, Pages, and datasets are read from
Meta — a stale local copy is worse than none. Configure what Meta cannot tell
us: your voice, your banned phrases, your claims policy, your DSA entities, your
cost thresholds.

Structured facts and free-form voice are deliberately separate files: the
campaign engine has no business caring about tone, and the copywriter has no
business caring about billing events.

## Plan, validate, then build

```bash
meta-ads-agent validate-plan .meta-ads/campaigns/acme-webinar/plan.yaml
```

```
INFO     budget.resolved     daily budget at ad_set level: 70.00 PLN (7000 minor units)
INFO     dsa.present         EU delivery to PL with beneficiary 'Acme Sp. z o.o.'
INFO     routing.fallback    single_video will use the Business SDK fallback
WARNING  currency.unverified plan budgets are in PLN, not verified against the account
ERROR    dsa.missing_fields  targeting PL requires beneficiary, payor

BLOCKED: 1 error(s), 1 warning(s), 3 note(s)
```

It checks what **Meta** enforces: account state and payability, currency match,
budget level, identities, dataset and event presence, destination reachability,
EU transparency fields, special ad categories, and local asset types. Errors
block; warnings are for you to see.

It does **not** enforce media-buying opinions. A plan that is unusual but valid
executes — [ADR-007](docs/architecture/adr/ADR-007-heuristics-vs-constraints.md).

## Interrupted builds resume

Not one of the eleven projects audited persists created ids as it goes, so a
failure after the ad set is created leaves an orphan and a rerun makes a second
campaign. This is the most common real failure in agent-driven campaign
creation.

Ids are written the moment they exist:

```bash
meta-ads-agent state acme-webinar-q4
```

```
stage      creatives_created (6/11)

campaign   120210000000001  MCP       PAUSED   Acme | OUTCOME_LEADS | 2026-09-16
ad_set     120210000000045  MCP       PAUSED   PL - broad 25-55
video      700000000000031  FALLBACK
creative   120210000000089  FALLBACK

Failures (1)
  ads_created (NOT retry-safe): create_ad failed: Invalid parameter

Resume
  next stage  ads_created
  Before mutating anything, re-read these objects from Meta. Local state is a
  convenience; Meta is authoritative.
```

Not retry-safe means Meta may have applied the write before failing — so the
next step is to look, not to retry. Local assets are deduplicated by SHA-256,
so a retry never re-uploads.

## Privacy

No backend, no telemetry, no analytics. Everything stays on your machine; the
only network destinations are Meta's MCP endpoint and the Marketing API.

Never stored anywhere: access tokens, app secrets, customer data, or reasoning.
A test asserts that no field in the state or action-log models is named like a
credential, and the state writer scrubs secret-shaped values on the way to disk.

Details: [docs/reference/privacy.md](docs/reference/privacy.md).

## What's missing

The honest gap list. Grouped by *kind* of gap, because they need different
things: the first group needs a test account, the second needs a few hours, the
third needs a decision about scope.

### Never run against Meta

This is the largest gap and the one to read first.

- **No code in this repository has created a campaign on a real Meta account.**
  The MCP path is prose the agent follows, so there is no code to run; the
  fallback path (uploads, creatives, deletion) has only ever run against a
  faked SDK. The request *shapes* are written from Meta's documentation and
  the SDK's own resource objects, and they are unconfirmed.
- **No live integration tests ship.** The offline suite (about 700 tests,
  close to 90% line coverage) proves our logic and proves nothing about Meta's acceptance. The rules
  for writing them responsibly are in
  [`tests/live/README.md`](tests/live/README.md); what is needed is a
  designated test ad account.
- **The capability map was read, not introspected.** `config/capabilities.yaml`
  records Meta's published tool reference as of 2026-09-16. No authenticated
  session has confirmed it. Three tools a community source reports are kept in
  a separate, explicitly unverified section of
  [the capability document](docs/research/current-meta-capabilities.md).
- **The Codex plugin has not been installed.** Codex was not available on the
  development machine, so `.codex-plugin/plugin.json` is checked against
  OpenAI's published specification by
  [a script](scripts/validate_codex_plugin.py), not by a working install.
- **CI has never run against Meta either.** The full suite is green on
  GitHub's runners for every push to `master` and every pull request, but it
  proves our logic, not Meta's acceptance - `META_ACCESS_TOKEN` is explicitly
  emptied in CI so a stray live call fails loudly.

If you have a test account or a Codex install, this is where help is worth the
most.

### Declared but not wired

Fields that exist in the schema and are read by nothing. They validate, they
appear in a plan, and then nothing happens — which is worse than their absence,
because a plan can look configured when it is not.

| Field | State |
| --- | --- |
| `AssetRef.placement` | Lets a plan pin an asset to one placement. Nothing consumes it, so placement-specific assets do not actually work. |
| `brand.yaml` `naming` / `utm` templates | Documented as "substituted at plan time" with `{brand}`, `{objective}`, `{variant}` tokens. **No substitution code exists** — the agent has to expand them in prose, so consistency is not enforced. |
| `TrackingPlan.utm` | Carried into the plan and validated, but never assembled into a destination URL. |

Each is a small, self-contained piece of work with an obvious home in
`src/meta_ads_agent/`.

### Promised as code, still prose

[ADR-008](docs/architecture/adr/ADR-008-deterministic-vs-agent-layer.md) says
arithmetic belongs in Python and judgement in skills. Two places do not yet
honour that, and both involve numbers that are easy to get quietly wrong:

- **Creative fatigue signals.** CTR against an entity's own baseline, frequency,
  spend since decline, creative age. The *conclusion* is judgement and belongs
  in the skill; the *signals* are arithmetic and should not be. Flagged in
  [the skill](skills/meta-ads-optimize/references/fatigue-signals.md).
- **Period comparison.** Equal-length window alignment, noise bands, and volume
  floors are all described in
  [the report reference](skills/meta-ads-report/references/metrics-and-comparisons.md)
  and all computed by the model. There is no `report` module.

### Features not built

Roughly in the order they would be useful.

| | Why it is not here |
| --- | --- |
| **Carousel creatives** | Needs `asset_feed_spec` work beyond the multi-variant path. Second milestone. |
| **Instagram existing-post campaigns** | `ads_boost_ig_post` is in the capability map and named in the campaign skill, but the plan format has no IG-post mode — only the Facebook Page path is modelled. |
| **Lead forms** | No MCP tool exists to create or read them. A campaign can use a form id you supply; we cannot build or inspect one. |
| **Catalog / dynamic ads** | Meta's MCP has 34 catalog tools and there is no skill workflow over them. Read-level entries only in the registry. |
| **A/B tests and lift studies** | `ads_experiment_*` is in the capability map with no workflow. Creating a test splits live delivery, so it needs the approval treatment doing properly. |
| **Lookalike audience workflows** | Creation is covered by the MCP; there is no guided workflow for source selection and sizing. |
| **Multi-account operation** | Everything assumes one ad account per workspace. |
| **Scheduled reporting and monitoring** | Deliberately absent so far — see below. |

### Deliberately out of scope

Not gaps. Decisions, with reasoning, that will not change without an ADR:

- **An autonomous spend optimiser.** Contradicts the approval model
  ([ADR-004](docs/architecture/adr/ADR-004-write-safety.md)).
- **A generic "run any Graph call" command.** Would void every guardrail here.
- **A web dashboard, a database, a background daemon.** The agent is the
  interface; local files are sufficient
  ([architecture overview](docs/architecture/overview.md)).
- **A proxy in front of Meta's MCP.** It would make the approval model
  enforceable rather than advisory, and was considered and rejected
  ([ADR-001](docs/architecture/adr/ADR-001-mcp-first.md)). If the advisory model
  proves insufficient in practice, this is the change to revisit — as an
  opt-in, not a default.
- **Growing the API fallback.** The six capabilities are the ones Meta's MCP
  cannot do. Adding a seventh needs a stated reason
  ([ADR-002](docs/architecture/adr/ADR-002-api-fallback.md)).

### The one that fixes itself

Every capability Meta adds to its official MCP is one we delete. The fallback
shrinking is the project working as intended, so a report that a tool now
covers one of our six gaps is among the most useful things you can send:
[capability change issue](.github/ISSUE_TEMPLATE/capability_change.yml).

## Documentation

| | |
| --- | --- |
| [Architecture overview](docs/architecture/overview.md) | how the layers fit |
| [ADRs](docs/architecture/adr/) | nine decisions, including the rejected options |
| [Ecosystem audit](docs/research/ecosystem-audit.md) | eleven projects, what each got right and wrong |
| [Meta capabilities](docs/research/current-meta-capabilities.md) | tool-by-tool, with what it does not assert |
| [Provenance](docs/research/provenance.md) | per-source license review |
| [CLI reference](docs/reference/cli.md) | every command |
| [Packaging](docs/reference/packaging.md) | supported install shapes, updates, migrations, and what works without the CLI |
| [Codex on Windows + WSL](docs/getting-started/install-windows-wsl.md) | native Windows Codex with the toolchain in WSL |
| [Capability refresh](docs/reference/capability-refresh.md) | keeping the map honest |
| [API versioning](docs/reference/api-versioning.md) | Graph version policy |
| [Workspace](docs/reference/workspace.md) | what `.meta-ads/` holds, and what to version |
| [Privacy](docs/reference/privacy.md) | what is stored, and what never is |
| [Publishing](docs/reference/publishing.md) | exact commands to push this to GitHub |
| [Roadmap](docs/roadmap.md) | what comes next, and what waits for a test account |
| [Contributing](CONTRIBUTING.md) | including where things go, and why |

## Relationship to upstream projects

Eleven community projects were reviewed at pinned commits before any code was
written. **The project contains no adapted third-party material** — every influence
was reimplemented from scratch, and the credit is recorded anyway in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Three of the eleven cannot legally be copied from: one is BUSL-1.1, one has no
license, and one carries a carve-out withholding rights to its own substance.
The [provenance review](docs/research/provenance.md) exists to catch exactly
that.

Ideas gratefully taken and reimplemented — brand workspaces, monitor/executor
separation, fatigue-diagnosis discipline, arithmetic in code with judgement in
prose, pause-over-delete and its reasoning, centralised API versioning — are
credited per source.

## Contributing

Bug reports, capability-change reports, and PRs welcome. Read
[CONTRIBUTING.md](CONTRIBUTING.md) first — the project has opinions about MCP
first, about not encoding heuristics as rules, and about the approval model.

Noticed a Meta MCP tool that closes one of our fallback gaps? Please
[tell us](.github/ISSUE_TEMPLATE/capability_change.yml). It means one fewer
reason for anyone to hold an access token.

## Security

Do not open a public issue for a vulnerability. See [SECURITY.md](SECURITY.md).
Anything that could cause unapproved spending, leak a credential, or leak
customer data is the highest-priority class of bug here.

## Status

**0.2.x — early development releases. Not production-ready.**

It works, it is tested, and it is honest about what it has not proven. Use it on
an account you are willing to watch. [What's missing](#whats-missing) is the
full gap list, and it is long on purpose.

## License

[MIT](LICENSE).

## Trademarks and independence

**This project is independent. It is not affiliated with, sponsored by, or
endorsed by Meta Platforms, Inc., Facebook, Instagram, OpenAI, or Anthropic.**

"Meta", "Facebook", "Instagram", "Messenger", "WhatsApp", "Advantage+",
"OpenAI", "ChatGPT", "Codex", "Anthropic", and "Claude" are trademarks of their
respective owners, used here descriptively only to identify the platforms this
project interoperates with.

The project name is provisional and easy to change.
