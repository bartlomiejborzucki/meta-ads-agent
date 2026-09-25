# meta-ads-agent

**Turn a coding agent into a careful Meta Ads operator.**

Twelve skills, a validated campaign plan, resumable state, and an approval gate on
anything that spends — built on Meta's **official** Ads MCP server, for Claude
Code, Codex, and any agent that reads Markdown skills.

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

> **Status: 1.0.** The formats this project controls are stable; Meta has not
> yet confirmed its requests on a live account. Read [Status](#status) before
> pointing it at an account you care about.

**Contents** —
[What it does](#what-it-does) ·
[How it works](#how-it-works) ·
[Safety model](#safety-model) ·
[Getting started](#getting-started) ·
[Updating](#updating) ·
[The CLI](#the-cli) ·
[The brand workspace](#the-brand-workspace) ·
[Privacy](#privacy) ·
[Status](#status) ·
[What's missing](#whats-missing) ·
[Documentation](#documentation)

---

## What it does

| Skill | Ask it to… | Changes anything? |
| --- | --- | --- |
| `meta-ads-core` | *(read first by every other skill)* routing, the approval model, the workspace, resuming | — |
| `meta-ads-audit` | "audit my account", "why isn't this delivering" | no |
| `meta-ads-campaign` | "build a campaign for this offer" — plan, validate, create PAUSED, verify | yes, gated |
| `meta-ads-creative` | "write three genuinely different angles" | no |
| `meta-ads-preview` | "render the placements and check them before launch" | no |
| `meta-ads-optimize` | "CTR dropped — what's going on?" — diagnose first, then propose | yes, gated |
| `meta-ads-report` | "how did last week compare with the week before?" | no |
| `meta-ads-tracking` | "is my pixel working?", Event Match Quality, CAPI | no |
| `meta-ads-research` | "what are competitors running?" — Ad Library themes, not clones | no |
| `meta-ads-audiences` | lookalikes, custom audiences, exclusions | yes, gated |
| `meta-ads-experiments` | A/B tests and lift studies, sized before they split delivery | yes, gated |
| `meta-ads-catalog` | catalog and feed health, product sets, dynamic-ads readiness | yes, gated |

Every skill's `description` is written as trigger text, so you can just say
what you want; naming the skill is optional.

## How it works

**Meta's MCP does the work.** Meta ships a first-party MCP server at
`https://mcp.facebook.com/ads` with around **90 tools** — accounts, campaigns,
ad sets, ads, creatives, previews, insights, audiences, datasets, pixel rules,
catalogs, experiments, activity logs and Ad Library search. It authenticates
through your browser with Meta OAuth and is generally available. So this
project does **not** rebuild the Marketing API: six of the eleven community
projects in [the ecosystem audit](docs/research/ecosystem-audit.md) do, and
it is a maintenance treadmill with a shrinking payoff.

**This project is the layer above it.** A plan you can review before anything
is created, state that survives a failure, a risk model tied to actual spend,
brand context that lives outside the tool, arithmetic done in code rather than
estimated, and an honest line between what Meta enforces and what a
practitioner believes.

**A small, optional fallback fills what the MCP cannot do.** Built on Meta's
official [`facebook-business`](https://github.com/facebook/facebook-python-business-sdk)
SDK, it covers exactly seven gaps:

| Capability | Why it is not the MCP's job |
| --- | --- |
| Local image upload | no MCP tool ingests a file |
| Local video upload | the same, plus asynchronous transcoding to wait for |
| Video creative | `ads_create_creative` is documented as single-image only |
| Existing-post creative | a Facebook Page post has no MCP tool; `ads_boost_ig_post` is not documented to create a paused boost ([ADR-010](docs/architecture/adr/ADR-010-carousel-and-instagram-posts.md)) |
| Multi-variant and placement-specific creative | `asset_feed_spec` is not exposed |
| Carousel creative | `ads_create_creative` is single-image; carousels need `child_attachments` |
| Delete a campaign, ad set or ad | no MCP delete tool (and pausing is usually better) |

**This list is meant to shrink.** Every entry is a bet that Meta will not ship
the feature, and we expect to lose those bets: when Meta adds one, we flip the
provider, deprecate our code, and delete it
([ADR-002](docs/architecture/adr/ADR-002-api-fallback.md)).

A default install needs no access token, no app secret, and no Developer App
credentials. Only the fallback does.

## Safety model

Nothing spends money without you saying so, about that specific thing.

| Operation | What it needs |
| --- | --- |
| Read anything | nothing |
| Create campaigns, ad sets, ads — **PAUSED** | you asked for something to be built |
| Edit a paused entity | you asked for the edit |
| Change a **live** entity's delivery | explicit approval |
| Change a budget, up or down | explicit approval, with old and new shown in the account currency |
| Activate anything | explicit approval, **after** previews and QA |
| Delete | explicit approval, and why pausing is not enough |
| Touch many entities at once | the list shown first, then approval |
| Upload a customer list | explicit instruction and a lawful basis |

- **Everything is created PAUSED.** The plan format has no field for anything else.
- **"Launch it" is still staged:** build → preview → QA → ask → activate.
- **Approval is specific.** "Sounds good" while reviewing a plan is not
  permission to spend.
- **Pause beats delete.** Deleted objects lose their optimisation history for
  good; paused ones keep it.
- **Money is never ambiguous.** The account currency — and Meta's own minor-unit
  offset for it — is read before any budget is interpreted.

> **Read this honestly:** the model is **advisory**. Meta's MCP write tools
> execute immediately and belong to Meta's server; this project shapes agent
> behaviour through skills but cannot gate a transport it does not own. For a
> hard guarantee, authorise a read-only session — `ads_read` without
> `ads_management` makes the whole write surface unavailable
> ([ADR-004](docs/architecture/adr/ADR-004-write-safety.md)).

## Getting started

### 1. Install the skills

**Claude Code**

```bash
claude plugin marketplace add bartlomiejborzucki/meta-ads-agent
claude plugin install meta-ads-agent@meta-ads-agent
```

Guide, including local development installs:
[install-claude-code.md](docs/getting-started/install-claude-code.md).

**Codex** — type `/plugins`, install, press Space to enable, and **start a new
session** (skills load at session start). Without a marketplace entry, link the
skills straight from a clone:

```bash
git clone https://github.com/bartlomiejborzucki/meta-ads-agent.git
cd meta-ads-agent
mkdir -p ~/.agents/skills
for skill in skills/meta-ads-*; do
  ln -sfn "$PWD/$skill" ~/.agents/skills/"$(basename "$skill")"
done
```

Each skill is self-contained, so copying just the ones you want works too.
Guide, including sandboxing and an `AGENTS.md` snippet that pins the approval
rule: [install-codex.md](docs/getting-started/install-codex.md).

**Codex on Windows, toolchain in WSL** — the Windows app cannot see
`/home/you/.agents/skills`, so the skills are copied into the Windows profile
while Python, uv and the repository stay in WSL:

```bash
uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git" \
  && meta-ads-agent install --target windows-codex
```

Guide, including OAuth through your Windows browser:
[install-windows-wsl.md](docs/getting-started/install-windows-wsl.md).

**Other agents** — the skills are plain Markdown; point the agent's skills or
prompt directory at `skills/`, and connect any streamable-HTTP MCP client to
the endpoint below.

### 2. Connect Meta's official MCP

Once, with the **App ID of a Meta app you control** as the OAuth client id (a
few minutes to create, not a secret):

```bash
# Claude Code
claude mcp add --transport http --client-id <YOUR_META_APP_ID> \
  meta-ads https://mcp.facebook.com/ads

# Codex
codex mcp add meta-ads --url https://mcp.facebook.com/ads \
  --oauth-client-id <YOUR_META_APP_ID>
codex mcp login meta-ads
```

The plugin deliberately does not bundle this server: any client id shipped here
would be wrong for everyone else
([ADR-006](docs/architecture/adr/ADR-006-mcp-connection-is-user-owned.md)).
Walkthrough: [connect-meta-mcp.md](docs/getting-started/connect-meta-mcp.md);
copy-paste templates: [`integrations/`](integrations/README.md).

### 3. Ask

```
Audit my Meta Ads account.
```

```
Build a paused campaign for this offer: <offer>, landing page <url>,
70 PLN/day, Poland, using ./creatives/hero.jpg. Three different angles.
```

With the MCP alone, audits, reporting, research, previews, tracking, creative,
optimisation and the MCP-side changes that follow all work. A worked
walkthrough, including what going wrong looks like:
[first-campaign.md](docs/getting-started/first-campaign.md).

### Optional: the local CLI

A separate install. The skills probe for it (`meta-ads-agent --version`) before
suggesting anything that needs it, so without it you get a plain statement
rather than a command you cannot run.

It is needed for **campaign builds** — plan validation is the gate before the
first write, so without it a build stops at the plan and offers you the routes
forward — and for the seven fallback capabilities and the `report` arithmetic.
Detail: [packaging.md](docs/reference/packaging.md).

```bash
# with the API fallback:
uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git#egg=meta-ads-agent[api]"
# without it - no credentials, ever:
uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git"

meta-ads-agent doctor    # what is ready, and what is not
meta-ads-agent init      # create the brand workspace in this project
```

Not on PyPI yet: publishing there is a deliberate, manual step
([ADR-009](docs/architecture/adr/ADR-009-distribution.md)).

The fallback needs a Marketing API token. Export `META_ACCESS_TOKEN`, or put it
in a `.env` in the directory you work from (`cp .env.example .env` in a clone);
the CLI reads it at start-up, and a variable already in your environment wins.
Tokens are never logged, stored or printed — `doctor` shows a fingerprint so
you can tell *which* token is set. Never paste one into a chat with an agent.
Setup: [api-fallback.md](docs/getting-started/api-fallback.md).

## Updating

| How you installed | How to update |
| --- | --- |
| Claude Code plugin | `claude plugin marketplace update meta-ads-agent`, then `claude plugin update meta-ads-agent@meta-ads-agent` |
| Codex plugin | through `/plugins`, then a new session |
| Symlinks to a clone | `git pull` in the clone |
| The CLI | `uv tool upgrade meta-ads-agent` |
| Skills copied by the CLI (`install --target …`) | `uv tool upgrade meta-ads-agent && meta-ads-agent upgrade --target <the same target>` |

`meta-ads-agent upgrade` replaces the copied skills against a release manifest,
so new files arrive and dropped ones do not linger; it records the version
last, so an interrupted update says so, and `--rollback` restores the backup it
took first. Then it runs any workspace migrations. `meta-ads-agent doctor`
reports one of `complete`, `update-available`, `migration-required`,
`interrupted`, `broken` or `not-installed`.

Upgrading keeps working files: within 1.x, workspaces written by any earlier
release are read and resumed, and newer files are refused with a clear message
([compatibility](docs/reference/compatibility.md)).

## The CLI

Everything the CLI does is local and deterministic; the agent calls Meta through
the MCP. The whole reference is [cli.md](docs/reference/cli.md).

| Command | For |
| --- | --- |
| `doctor` · `init` | readiness checks; creating the workspace |
| `render-plan` | applying the brand's naming and UTM templates to a plan |
| `validate-plan` | the gate before the first write |
| `state` | what exists on Meta for a campaign, and where a resume starts |
| `report compare` · `fatigue` · `pacing` · `power` | period comparisons, fatigue signals, budget pacing, test sizing |
| `capabilities` | what routes where; `--compare` checks a live session's tools against the map |
| `install` · `upgrade` · `migrate` · `mcp-config` · `open-url` | installing and updating skills, and Codex/WSL set-up |
| `api …` | the fallback: uploads, video / existing-post / multi-variant / carousel creatives, deletion |

**Plan, validate, then build.** Validation checks what **Meta** enforces —
account state and payment, currency and its minor units, budget level and
minimums, bids, identities, dataset and events, destinations, EU transparency
fields, special ad categories, placements, local asset types — and nothing
that is merely a media-buying opinion
([ADR-007](docs/architecture/adr/ADR-007-heuristics-vs-constraints.md)).

```
$ meta-ads-agent validate-plan .meta-ads/campaigns/acme-webinar/plan.yaml

ERROR    dsa.missing_fields  targeting PL requires beneficiary, payor
WARNING  currency.unverified plan budgets are in PLN, not verified against the account
INFO     budget.resolved     daily budget at ad_set level: 70.00 PLN (7000 minor units)
INFO     routing.fallback    single_video will use the Business SDK fallback

BLOCKED: 1 error(s), 1 warning(s), 2 note(s)
```

**Interrupted builds resume.** None of the eleven projects audited persists
created ids as it goes, so a failure after the ad set leaves an orphan and a
rerun makes a second campaign. Here every id is written the moment it exists,
and two sessions on one campaign merge rather than overwrite each other:

```
$ meta-ads-agent state acme-webinar-q4

stage      creatives_created (6/11)

campaign   120210000000001  MCP       PAUSED   Acme | OUTCOME_LEADS | 2026-09-16
ad_set     120210000000045  MCP       PAUSED   PL - broad 25-55
video      700000000000031  FALLBACK
creative   120210000000089  FALLBACK

Failures (1)
  ads_created (NOT retry-safe): create_ad failed: Invalid parameter

Resume
  next stage  ads_created
  Before mutating anything, re-read these objects from Meta.
```

Not retry-safe means Meta may have applied the write before failing, so the
next step is to look, not to retry. Local assets are deduplicated by content,
so a retry never uploads a file twice.

**Arithmetic in code, judgement in skills.** `report` computes what is easy to
get quietly wrong by hand — equal windows, rates from sums rather than
averages, noise bands and volume floors, a CTR against the ad's *own* baseline,
test power — prints the rule behind every label, and leaves the conclusion to
the skill ([ADR-008](docs/architecture/adr/ADR-008-deterministic-vs-agent-layer.md)).
Input: insights rows as the Marketing API documents them
([report-input.md](docs/reference/report-input.md)).

## The brand workspace

`meta-ads-agent init` creates `.meta-ads/` in your project — **private by
default**, because it writes its own `.gitignore`. Without the CLI, the agent
writes the same files from the templates in `meta-ads-core`.

```
.meta-ads/
  brand.yaml              naming and UTM templates, EU DSA entities, your thresholds
  voice.md                how your brand sounds
  account.yaml            cached account facts (Meta stays authoritative)
  accounts/<act_id>.yaml  the same, one per account, when there are several
  offers/<slug>.yaml      reusable offer briefs
  campaigns/<slug>/
    plan.yaml             intent — reviewed before anything is created
    state.json            what exists on Meta, and where to resume
    qa.md                 preview QA notes
  assets/manifest.json    local fingerprints → remote ids (upload once, ever)
  actions.jsonl           what this tool did, and when
```

Most of it is optional. Currency, timezone, Pages and datasets are read from
Meta — a stale copy is worse than none. Configure what Meta cannot know: your
voice, banned phrases, claims policy, DSA entities, and cost thresholds. Voice
and structured facts are separate files on purpose: the campaign engine has no
business caring about tone, and the copywriter none caring about billing events.

## Privacy

No backend, no telemetry, no analytics. Everything stays on your machine; the
only network destinations are Meta's MCP endpoint and the Marketing API.

Never stored: access tokens, app secrets, customer data, or reasoning. A test
asserts that no field in the state or action-log models is named like a
credential, and everything written to disk passes through redaction first.
Details: [privacy.md](docs/reference/privacy.md).

## Status

**1.0 — the formats are stable; Meta has not yet confirmed the requests.**

1.0 is a promise about what this project controls: within 1.x the workspace
files, the CLI's `--json` output and exit codes, and the skill and risk-class
names do not break, and tests hold each of those to the promise
([compatibility](docs/reference/compatibility.md)).

It is **not** a claim about Meta's acceptance. No code here has yet created
anything on a real ad account: the fallback's requests are checked offline
against Meta's own SDK descriptions and documentation, and the live tests that
would confirm them are written and have not run — see
[Never run against Meta](#never-run-against-meta). Use it on an account you are
willing to watch, start with paused builds, and read on.

## What's missing

The honest gap list, grouped by what each gap needs.

### Never run against Meta

The largest gap, and the one to read first.

- **Nothing here has created a campaign on a real Meta account.** The MCP path
  is prose the agent follows; the fallback has only run against a faked SDK.
  What *has* been checked offline: every request the fallback builds is held
  to the real `facebook-business` SDK's description of each object — fields,
  types, enum values — and to Meta's documentation, and every documented error
  code is replayed through the SDK's real exception. That rules out misspelt
  fields and invented values; it does not show that Meta accepts the requests.
- **The live tests are written and have never run.** The checks only Meta can
  answer are in [`tests/live/`](tests/live/README.md). They need a designated
  test ad account and never run in CI — by design, so no token with
  `ads_management` sits in repository secrets.
- **The capability map was read, not introspected.** It records Meta's
  published tool reference as of 2026-09-16. Anyone with a connected session
  can check it in one command: `meta-ads-agent capabilities --compare` takes
  the session's tool list and reports every difference.
- **The Codex plugin has not been installed.** Its manifest is checked against
  OpenAI's published specification by
  [a script](scripts/validate_codex_plugin.py), not by a working install.
- **The trigger evals have not run.** [`evals/`](evals/README.md) checks that
  each skill's description selects it; running it is a paid model call.

If you have a test account, a connected session or a Codex install, this is
where help is worth the most — each is one command, and the
[roadmap](docs/roadmap.md) lists them.

### Features not built

| | Why it is not here |
| --- | --- |
| **Lead forms** | No MCP tool creates or reads them. A campaign can use a form id you supply. |
| **Catalog (dynamic) ads** | `meta-ads-catalog` gets the catalog and product sets ready, but the ad's template creative is not something the MCP is documented to build, and catalogs stay MCP-only. Build that ad in Ads Manager. |
| **Scheduled reporting and monitoring** | Deliberately absent — there is no daemon (below). |

### Deliberately out of scope

Decisions, with reasoning, that will not change without an ADR:

- **An autonomous spend optimiser.** It contradicts the approval model
  ([ADR-004](docs/architecture/adr/ADR-004-write-safety.md)).
- **A generic "run any Graph call" command.** It would void every guardrail here.
- **A web dashboard, a database, a background daemon.** The agent is the
  interface; local files are enough
  ([architecture overview](docs/architecture/overview.md)).
- **A proxy in front of Meta's MCP.** It would make the approval model
  enforceable rather than advisory, and was considered and rejected
  ([ADR-001](docs/architecture/adr/ADR-001-mcp-first.md)) — the change to
  revisit, as an opt-in, if the advisory model proves insufficient.
- **Growing the fallback without a reason.** Each of the seven capabilities is
  argued in [ADR-002](docs/architecture/adr/ADR-002-api-fallback.md) or
  [ADR-010](docs/architecture/adr/ADR-010-carousel-and-instagram-posts.md).

### The one that fixes itself

Every capability Meta adds to its official MCP is one we delete. A report that
a tool now covers one of the seven gaps is among the most useful things you can
send: [capability change issue](.github/ISSUE_TEMPLATE/capability_change.yml).

## Documentation

| Getting started | |
| --- | --- |
| [Claude Code](docs/getting-started/install-claude-code.md) · [Codex](docs/getting-started/install-codex.md) · [Codex on Windows + WSL](docs/getting-started/install-windows-wsl.md) | installing the skills |
| [Connect Meta's MCP](docs/getting-started/connect-meta-mcp.md) | the App ID and the OAuth round trip |
| [Your first campaign](docs/getting-started/first-campaign.md) | a worked walkthrough, including failures |
| [The API fallback](docs/getting-started/api-fallback.md) | tokens, `.env`, and what the fallback covers |

| Reference | |
| --- | --- |
| [CLI](docs/reference/cli.md) | every command and flag |
| [Report input](docs/reference/report-input.md) | the insights shape `report` reads |
| [Workspace](docs/reference/workspace.md) | what `.meta-ads/` holds, and what to version |
| [Compatibility](docs/reference/compatibility.md) | what an upgrade may change, and how that is tested |
| [Packaging](docs/reference/packaging.md) | install shapes, updates, migrations, what works without the CLI |
| [Capability refresh](docs/reference/capability-refresh.md) · [API versioning](docs/reference/api-versioning.md) | keeping the map and the Graph version honest |
| [Privacy](docs/reference/privacy.md) · [Publishing](docs/reference/publishing.md) | what is stored; how releases are made |

| Background | |
| --- | --- |
| [Architecture overview](docs/architecture/overview.md) · [ADRs](docs/architecture/adr/) | how the layers fit; ten decisions, with the rejected options |
| [Ecosystem audit](docs/research/ecosystem-audit.md) · [Meta capabilities](docs/research/current-meta-capabilities.md) · [Provenance](docs/research/provenance.md) | eleven projects reviewed; Meta's tools, tool by tool; licences |
| [Roadmap](docs/roadmap.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) | what is next; what changed; how to help |

## Relationship to upstream projects

Eleven community projects were reviewed at pinned commits before any code was
written. **The project contains no adapted third-party material** — every
influence was reimplemented from scratch, and credited anyway in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Three of the eleven could not
legally be copied from — one is BUSL-1.1, one has no licence, and one withholds
rights to its own substance — which is what the
[provenance review](docs/research/provenance.md) exists to catch.

## Contributing and security

Bug reports, capability-change reports and pull requests are welcome; read
[CONTRIBUTING.md](CONTRIBUTING.md) first — the project has opinions about MCP
first, about not encoding heuristics as rules, and about the approval model.

Do not open a public issue for a vulnerability; see [SECURITY.md](SECURITY.md).
Anything that could cause unapproved spending, leak a credential or leak
customer data is the highest-priority class of bug here.

## License and trademarks

[MIT](LICENSE).

**This project is independent. It is not affiliated with, sponsored by, or
endorsed by Meta Platforms, Inc., Facebook, Instagram, OpenAI, or Anthropic.**
"Meta", "Facebook", "Instagram", "Messenger", "WhatsApp", "Advantage+",
"OpenAI", "ChatGPT", "Codex", "Anthropic" and "Claude" are trademarks of their
respective owners, used here only to identify the platforms this project
interoperates with.
