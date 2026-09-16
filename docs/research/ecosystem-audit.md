# Meta Ads agent ecosystem audit

**Review date:** 2026-09-16
**Reviewer:** project maintainer
**Method:** shallow-cloned each repository at the SHA below, read the manifests, every
`SKILL.md`, guardrail/reference files, source tree, license, and CI. GitHub API supplied
license SPDX, stars, and last-push timestamps. Stars are recorded but were not used to rank
anything.

**Why this exists:** before writing code, establish what the ecosystem already solves well
(so we don't rebuild it), what it solves badly (so we can do better), and what nobody is
doing (which is where the value is). The conclusion is in
[What is actually missing](#what-is-actually-missing).

## Summary table

| # | Repository | Kind | License | Stars | Last push | SHA | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `pipeboard-co/meta-ads-mcp` | Hosted + local MCP server (Python) | **BUSL-1.1** | 1261 | 2026-08-19 | `2ef198e` | Reference only — license forbids reuse |
| 2 | `gomarble-ai/facebook-ads-mcp-server` | Single-file MCP server (Python) | MIT | 365 | 2026-08-05 | `a3b555a` | Ignore for implementation |
| 3 | `byadsco/meta-ads-mcp` | Production MCP server (TypeScript) | MIT | 14 | 2026-09-15 | `139421a` | Adapt ideas, reimplement |
| 4 | `sepivip/meta-ads-skill` | Single skill for the official MCP | MIT | 14 | 2026-07-31 | `ab583c5` | **Highest-value input.** Facts adopted, text not copied |
| 5 | `Sandy-zippy/meta-ads-stack` | 6 Claude Code skills | MIT | 5 | 2026-06-16 | `e82b4c9` | Adopt architecture stance, reimplement |
| 6 | `kelpi-ai/meta-ads-skills` | 18 narrow skills | MIT | 3 | 2026-07-02 | `c046a25` | Adopt decomposition + evidence discipline |
| 7 | `rafaelszago/meta-ads-mcp` | Custom MCP + brand workspace (TS) | MIT | 3 | 2026-05-22 | `d004a42` | **Adopt the brand-workspace concept** |
| 8 | `mardab96/meta-ads-skills` | 20 diagnostic skills + Python scripts | MIT | 3 | 2026-08-14 | `388095b` | Adopt the deterministic-script split |
| 9 | `Digitizers/meta-ads-mcp` | Claude plugin, skill + references | MIT-0 | 1 | 2026-09-14 | `bade982` | Adopt packaging shape; reject the hard thresholds |
| 10 | `itsfromgaurav/ultimate-meta-ads-skill` | Strategy skill + templates | MIT **with carve-out** | 2 | 2026-06-13 | `269f204` | **Reference only** — content rights not granted |
| 11 | `lil-j/meta-ads-mcp` | Read/write split MCP + preview QA (TS) | **none** | 0 | 2026-07-30 | `c815259` | **Reference only** — no license = all rights reserved |

---

## 1. `pipeboard-co/meta-ads-mcp`

The most-starred project in the space. A Python MCP server with OAuth, a hosted option, a
Meta Business Partner badge, and broad coverage: accounts, campaigns, ad sets, ads,
creatives, insights, reports, targeting, budget schedules, duplication, Ad Library.

**Does well.** Breadth. Real OAuth with a local callback server rather than "paste a token".
`META_API_NOTES.md` captures hard-won Graph API quirks — the kind of knowledge that only
comes from production traffic. Duplication (`duplication.py`) is a genuinely useful primitive
that Meta's MCP does not expose. Ships a `server.json`, Docker image, and Smithery config.

**Does badly.** It is a complete Marketing API reimplementation, which is now largely
redundant with Meta's own first-party MCP — a maintenance liability that grows every time
Meta ships a version. No PAUSED-by-default guarantee and no approval gate: the tools are
thin wrappers, so spend safety is entirely the model's problem. Business logic and transport
are interleaved.

**Missing.** Campaign plans, validated state, resumability, brand context, an approval model.

**License.** Business Source License 1.1. Not open source. Grants limited production use and
converts to a permissive license only after a change date. **No code, text, or structure may
be copied into this project.** Read for orientation; that is all.

**Idea worth adopting.** That a capability like duplication is worth having locally *because*
the first-party MCP lacks it. That is the fallback thesis — reached independently, not taken
from this codebase.

**Verdict: reference only. Do not depend on, do not adapt.**

## 2. `gomarble-ai/facebook-ads-mcp-server`

A single `server.py` exposing the Marketing API over MCP, distributed as a `.dxt` desktop
extension with a `manifest.json` and Smithery config.

**Does well.** Radically simple. One file, one `requirements.txt`, easy to audit end to end.
The packaging story (desktop extension + Smithery) is the smoothest install in this list.

**Does badly.** Token-in-argv authentication. No write safety of any kind. No tests. Zero
separation between read and write. One file means the Graph surface is hardcoded inline.

**Missing.** Everything above the transport layer.

**Idea worth adopting.** Packaging polish, not architecture. `.dxt`/Smithery is not our
distribution channel, so even that does not transfer.

**Verdict: ignore for implementation.** MIT, so reuse would be legal; there is simply nothing
here we want.

## 3. `byadsco/meta-ads-mcp`

The best-engineered third-party server in the set. TypeScript, 192 files, and the module list
reads like someone who has been paged at 3am: `meta/circuit-breaker.ts`,
`meta/rate-limiter.ts`, `meta/write-pacer.ts`, `meta/paginator.ts`, `meta/api-version.ts`,
`meta/targeting-compat.ts`, `meta/errors.ts`, per-entity type modules, encrypted token
storage, multi-tenant OAuth, an email allowlist, Gitleaks with a pinned version, Dependabot,
CI, a deploy guard implemented as its own skill.

**Does well.** Operational maturity. A dedicated **write pacer** separate from the read rate
limiter is a distinction most projects miss entirely. `api-version.ts` centralises the Graph
version instead of scattering it. `errors.ts` maps Meta error codes to actionable meaning.
The `.github/pre-deploy-guard/` skill that gates its own releases is a nice touch. Full
governance set: CODEOWNERS, SECURITY.md, issue templates, CHANGELOG.

**Does badly.** Same strategic problem as pipeboard: it is a full Marketing API client
competing with Meta's first-party MCP. Firestore, Docker, and multi-tenant OAuth make it a
service to operate, not a plugin to install. Heavy for a solo advertiser.

**Missing.** The agent layer. It is superb hands with no brain: no campaign plan, no brand
context, no resumable workflow, no approval semantics.

**Ideas worth adopting** (reimplemented, not copied):
- Centralise the Graph API version in exactly one module.
- Treat writes as a separate rate class from reads.
- Maintain a Meta error-code reference built from real errors.
- Pin the secret scanner's version so CI is reproducible.

**Verdict: adapt ideas, reimplement from scratch.** MIT permits copying; we don't need to,
because we are not building a server.

## 4. `sepivip/meta-ads-skill`

Six files. A single `SKILL.md` plus `references/tool-contracts.md`,
`references/launch-playbook.md`, `references/troubleshooting.md`. And it is the most useful
repository in this audit, because it is the only one written against a **live official Meta
MCP session** and it records what the tools actually do rather than what the Graph API used
to do.

**Does well.** Its thesis — *the official MCP's tool contracts are not the Graph API you
remember, and they differ exactly where it breaks calls* — is correct and load-bearing. Its
launch table pairs each pipeline step with the specific mistake that step invites. It names
three tools Meta's docs pages omit (`ads_creative_upload_image`,
`ads_entity_get_report`, `ads_entity_schedule_report`) and notes that image upload is
URL-only. It tells the agent to treat a VALIDATION error's "Supported fields are:" list as
outranking the skill's own notes — the right epistemic posture for a platform that drifts.
Documents account eligibility fields (`is_ads_mcp_enabled`, `is_queryable`,
`has_payment_method`) that cause failures at delivery time rather than create time.

**Does badly.** One monolithic skill, so everything loads even for a read-only report. Some
content is tuned to one market (Georgia/Tbilisi, Georgian-language ads), which is fine for
its author and wrong as a general default. The observed contracts are undated, so there is no
way to tell which are stale. No deterministic code — the agent still hand-assembles JSON.

**Missing.** Plan/validate/apply, state, resumability, local asset handling, brand context.

**Ideas worth adopting.** All of the epistemics: MCP contracts ≠ Graph API; introspect rather
than assume; platform errors outrank local docs; verify account eligibility before writing;
date every observation. These are adopted as *facts and stance*, restated in our own words.

**Verdict: facts adopted, stance adopted, text not copied.** MIT would permit copying with
attribution; our references are written from scratch, and the specific factual claims are
recorded in [`current-meta-capabilities.md`](current-meta-capabilities.md) flagged unverified
and credited there.

## 5. `Sandy-zippy/meta-ads-stack`

Six Claude Code skills — `strategy-intel`, `ad-creative-engine`, `campaign-builder`,
`ad-watchdog`, `ad-optimizer`, `ad-audit` — plus a launchd/cron watchdog and a shell audit
log with a test.

**Does well.** States the correct architectural principle out loud: skills are the brain, MCP
is the hands, and the human approves. Splits the **watchdog that never writes** from the
**optimizer that only executes pre-approved actions** — a clean read/write separation at the
skill level, which is the right level when the server is external and not yours. Everything
created PAUSED. Every write appended to an audit log. Names its own fallback explicitly.

**Does badly.** `strategy-intel` builds structure from "what the top performance marketers are
doing right now", i.e. influencer opinion promoted to system rule. The optimizer's "never
exceed +20% per scale" and business-hours restriction are hardcoded media-buying heuristics
presented with the same authority as platform constraints. Install is "copy these folders
into `.claude/skills/`" — no plugin manifest. No Python, no schemas, no tests beyond the
audit-log shell test. Depends on a BUSL-licensed project as its fallback.

**Missing.** Validation, state, resumability, typed config, packaging.

**Ideas worth adopting** (reimplemented): watchdog-never-writes; optimizer-executes-only-
approved; append-only action log; PAUSED everywhere. Explicitly **rejected**: encoding
media-buying heuristics as engine rules. Ours live in skills, labelled as heuristics, and
thresholds are user-configurable — see
[ADR-007](../architecture/adr/ADR-007-heuristics-vs-constraints.md).

**Verdict: adopt the architectural stance, reimplement, reject the dogma.**

## 6. `kelpi-ai/meta-ads-skills`

Eighteen narrow skills, each with a `SKILL.md` and a `skill.meta.json`: `angle-writer`,
`audience-builder`, `brand-reader`, `budget-pacer`, `buyer-language-miner`,
`catalog-commerce`, `competitor-ad-teardown`, `copy-formulas`, `creative-director`,
`daily-auditor`, `fatigue-detector`, `lead-gen-builder`, `media-buyer`, `pain-to-promise`,
`performance-analyst`, `pixel-conversions`, and more, over a `GROWTH-OS.md` spine.

**Does well.** The decomposition is the best in this list: each skill is one job, with a
`When to use` section, an explicit READ-ONLY marker where applicable, and a `Guardrails`
block. `fatigue-detector` is the standout — it opens by naming the *misdiagnosis*
("CTR down, CPM up, must be fatigue"), requires two independent conditions before flagging,
insists an ad be judged against **its own** historical baseline rather than a sibling's, and
enumerates the likelier alternative causes (auction shift, seasonality, tracking change,
insufficient spend) for ads that look tired but fail the rule. That is real diagnostic
discipline, and it is rare.

**Does badly.** Skills are prompt blocks the agent is told to run verbatim, which is brittle.
Thresholds are hardcoded numbers (`frequency > 4.0`, `CTR down 30%+`) presented as a rule
rather than a default. Doctrine sections cite the owner's anecdotes as evidence. No plugin
manifest, no code, no tests, no state.

**Missing.** Deterministic execution, validation, packaging, resumability.

**Ideas worth adopting** (reimplemented): one skill per job with explicit read/write posture;
require multiple independent signals before declaring fatigue; baseline an entity against its
own history; always enumerate alternative explanations; say *insufficient evidence* instead of
guessing. Our fatigue thresholds are **configurable defaults** with the reasoning stated, not
constants.

**Verdict: adopt decomposition and evidence discipline, reimplement, parameterise thresholds.**

## 7. `rafaelszago/meta-ads-mcp`

A custom TypeScript MCP server (`src/tools/{campaigns,adsets,ads,creatives,insights,brand}.ts`,
`src/schemas.ts`) with five `.claude/skills/` and — the interesting part — a **brand
workspace**: `brand/brand.yaml.example`, `brand/voice.md.example`, `brand/manifest.json`,
`brand/campaigns/_template/{brief.md,copy.yaml}`, `brand/assets/{images,videos}/`,
`config/optimization-targets.example.yaml`.

**Does well.** The brand workspace is the best idea in the ecosystem and this is the cleanest
expression of it. `brand.yaml` holds structured account facts (ids, currency, market,
timezone, page/IG identity, defaults) while free-form tone lives in a **separate**
`voice.md` — the right seam, because the campaign engine must not care about writing tone and
the copywriter must not care about billing events. Budgets are stored in minor units with the
unit named in the field (`daily_budget_minor`). Naming conventions are templates with tokens
(`{brand} | {objective} | {date}`) reused for UTM construction, so names can be parsed back
into facets during reporting. Ships `.env.example` and never `.env`. Real docs, including
`flip-fb-app-to-live.md`, which is exactly the kind of thing people get stuck on.

**Does badly.** Rebuilds the Marketing API as a local MCP server, so the same obsolescence
problem applies. The workspace lives **inside the repository**, which means user data and
tool code share a directory — wrong for a distributable plugin. Zod schemas validate tool
input but nothing validates a campaign plan as a whole. Skills as slash commands rather than
model-invoked. `brand.yaml` duplicates the account id already in `.env`, inviting drift. No
tests.

**Missing.** Resumability, asset deduplication, approval gating, first-party MCP use.

**Ideas worth adopting** (reimplemented): the brand-workspace concept; structured facts
separated from free-form voice; minor units named in the field; tokenised naming reused for
UTMs. **Fixed in ours:** the workspace moves *out* of the plugin into a per-project
`.meta-ads/` directory, gitignored by default, with Meta as the authority for anything
discoverable rather than a copy the user must maintain.

**Verdict: adopt the concept, relocate the workspace, reimplement.**

## 8. `mardab96/meta-ads-skills`

Twenty diagnostic skills, one directory each, plus four standalone Python scripts:
`wow_delta.py`, `fatigue_trend.py`, `placement_index.py`, `classify_budget.py`. Topics skew
toward measurement honesty: `attribution-credit-check`, `modeled-conversions-review`,
`conversion-lag-read`, `ios-reporting-gap`, `click-to-session-gap`,
`incrementality-test-design`, `learning-phase-check`, `audience-overlap-review`.

**Does well.** The only project here that puts arithmetic in **code** and judgement in
**prose**. `wow_delta.py` computes week-over-week deltas and applies a **noise band**: a row
is flagged only if it moved more than the band *and* rests on enough volume
(`--band`, `--min-conv`, `--min-clicks`), with spend always shown. That is small-sample safety
implemented rather than merely recommended, and the thresholds are flags, not constants.
Scripts are stdlib-only with documented exit codes and tolerant CSV header matching. The
topic selection shows unusual sophistication about what Meta's numbers actually mean.

**Does badly.** CSV in, CSV out — no MCP integration, so the human is the data bus. Scripts
are not a package and have no tests. Twenty top-level directories with a `-meta-ads` suffix
on each is an awkward layout. No plugin manifest.

**Ideas worth adopting** (reimplemented): deterministic arithmetic in Python, judgement in
`SKILL.md`; a noise band plus a volume floor before any regression is called; thresholds as
parameters with defaults; documented exit codes; always show spend. Also the insight that
attribution and modelling caveats deserve first-class treatment, which shapes our
[reporting skill](../../skills/meta-ads-report/SKILL.md).

**Verdict: adopt the split and the statistics, reimplement inside a real package with tests.**

## 9. `Digitizers/meta-ads-mcp`

A Claude Code plugin: `.claude-plugin/plugin.json`, one skill, seven reference files
(`safety-guardrails`, `campaign-architecture`, `campaign-operations`,
`budget-and-audience`, `creative-and-copy`, `tracking-and-retargeting`,
`intake-questions`), `scripts/validate-skill.py`, CI, and a release-drift workflow.

**Does well.** Correct current packaging — a real `.claude-plugin/plugin.json` with skills
under a directory, which most projects in this list lack. Progressive disclosure done
properly: a thin skill that points at references. The safety reference is strong where it
matters: **prefer pause over delete, because deleted objects lose optimisation history
permanently while paused objects keep it** — the best single argument for pause-first, and
the reason our delete path is a guarded last resort rather than a convenience. Declares
special ad categories as a suspension risk. The privacy rules are correct and blunt: hash
email/phone before transmission, never send PII without lawful basis and consent, honour
opt-outs, maintain suppression lists. A `release-drift` workflow is a good idea.

**Does badly.** Mixes platform constraints and media-buying folklore in one table with equal
authority: "never increase budget by more than 20% at a time", "never touch campaigns in
Learning Phase (first 7 days / ~50 events)", "never edit targeting, creative, and budget
simultaneously". Some are defensible heuristics; none are platform rules; the table does not
distinguish. Headings retain numbering from a larger document ("## 15. SAFETY GUARDRAILS")
which suggests bulk generation. No state, no resumability, no code beyond a skill validator.

**Ideas worth adopting** (reimplemented): thin-skill-plus-references packaging; pause-over-
delete **with the optimisation-history reasoning stated**; special-ad-category declaration as
a policy risk; the PII rules; a drift-detection workflow (ours watches upstreams).
**Rejected:** presenting heuristics as constraints.

**Verdict: adopt packaging and the pause rationale; reject the undifferentiated rule table.**
Licensed MIT-0, so even copying would need no attribution — we still wrote our own.

## 10. `itsfromgaurav/ultimate-meta-ads-skill`

A strategy-heavy skill: one `SKILL.md`, 18 references, 10 checklists, 8 templates
(`hook-formulas.md`, `offer-frameworks.md`, `video-script-EDIE.md`,
`13-elements-persuasive-copy.md`, `audience-research-BCOP.md`, `7-power-questions.md`).

**Does well.** By far the deepest creative and offer-strategy material in the audit, and
well organised into skill / references / checklists / templates. The checklists
(`pre-launch`, `creative-qa`, `ad-copy-qa`, `pre-scale-readiness`) are the kind of concrete
QA gates that belong in a launch workflow. A `SUPPLEMENT-2025.md` separates newer research
from the base material, which is an honest way to handle staleness.

**Does badly.** No MCP integration, no code, no packaging, no tests — it is a library of
marketing doctrine, not an operator. Undated platform claims. Frameworks are presented as
established practice without evidence.

**License — read carefully.** The file is an MIT template with an appended carve-out: the
license covers "the organizational structure, the SUPPLEMENT-2025 research, checklists, and
templates authored in this repository" but explicitly **does not grant rights to the
underlying advertising ideas and frameworks, which belong to the authors of a commercial book
and their publisher**, and asks users to buy the book. GitHub classifies it `NOASSERTION`.
The substance is therefore third-party copyrighted material the repository cannot
sublicense.

**Verdict: reference only. No text, no templates, no checklists, no framework names copied.**
Our creative skill was written independently and deliberately avoids proprietary framework
names. This is the clearest instance of the risk the provenance review exists to catch.

## 11. `lil-j/meta-ads-mcp`

A TypeScript project with a deliberate read/write split at the **server** level — separate
`server.ts`/`tools.ts` and `writer-server.ts`/`writer-tools.ts`/`writer-client.ts`/
`writer-manifest.ts` — plus `preview-renderer.ts`, `analytics.ts`, `export-file.ts`, a
`skills/meta-ads-upload-qa/` skill with `references/preview-qa.md` and an
`agents/openai.yaml`, CI, a SECURITY.md, and — uniquely in this audit — a `.test.ts` beside
nearly every module.

**Does well.** Two servers, so read-only usage cannot physically reach a write tool. A
`writer-manifest` implies tracked write intent, which is close to our plan/apply split.
Dedicated preview rendering plus a preview-QA skill treats creative QA as a first-class stage
rather than an afterthought. Test coverage discipline is the best here. `agents/openai.yaml`
shows awareness of cross-host packaging.

**Does badly.** Another custom Marketing API client. No release, no stars, no docs beyond the
README.

**License: none.** No `LICENSE` file, and GitHub reports no license, so default copyright
applies and **no rights are granted**. Not usable, not quotable.

**Idea worth adopting** (arrived at independently, implemented differently): physical
read/write separation. Because Meta's MCP is external and single-surfaced, we cannot split
servers; we split *skills* and put the approval gate in the workflow instead. Preview-as-a-
stage is adopted as our [preview skill](../../skills/meta-ads-preview/SKILL.md).

**Verdict: reference only.**

---

## Cross-cutting observations

**Everyone is building the wrong layer.** Six of eleven projects are Marketing API clients.
Meta shipped a first-party MCP with ~90 tools covering accounts, campaigns, creatives,
previews, insights, audiences, datasets, catalogs, experiments, activity logs, and Ad Library
search. Rebuilding that surface is now a maintenance treadmill with a shrinking payoff. The
scarce layer is the operator above it.

**Guardrails are stated, not enforced.** Every skill-based project says "created PAUSED" and
"you approve spend". None can enforce it, because the enforcement point is a prose
instruction. Nothing validates a plan before the first write, and nothing records what was
created.

**Nobody survives a partial failure.** Not one project persists created object ids as it
goes. A campaign creation that fails after the ad set is created leaves an orphan and a rerun
duplicates it. This is the most common real-world failure in agent-driven campaign creation
and it is universally unhandled.

**Heuristics wear the costume of platform rules.** "+20% budget increases", "frequency > 4.0",
"don't touch learning phase", "use broad targeting" appear in the same tables as genuine
constraints like "special ad categories must be declared". Users cannot tell which claims
Meta will enforce and which are one practitioner's opinion.

**Money is handled carelessly.** Minor-unit conversion appears as inline `* 100`. Two
projects name the unit in the field (`daily_budget_minor`), which is better. Nobody handles
zero-decimal currencies, so a PLN account and a JPY account are silently treated the same.

**Local assets are the sharpest real gap.** Meta's MCP lists uploaded images and videos but
has no local-file ingestion path, and image upload — where it exists at all — is reported to
be URL-only. An agent working from a user's filesystem hits this on day one. No project
solves it against the first-party MCP.

**Licensing needs care.** Of eleven repositories: seven permissive (MIT/MIT-0), one BUSL-1.1
(not open source), one unlicensed (all rights reserved), one MIT with a carve-out that
withholds rights to its actual substance. Three of eleven cannot be copied from. The most
strategically-content-rich repository is the one whose content is least available.

## What is actually missing

Nothing in this ecosystem provides, against the **first-party** MCP:

1. **A validated campaign plan as an artifact** — reviewable before any write, and the single
   source of truth for intent.
2. **Persisted state with resumability** — ids written the moment they exist, so an
   interrupted run continues instead of duplicating.
3. **A risk model tied to spend** — read / create-paused / activate / budget-increase /
   delete / PII-upload as distinct classes with distinct approval requirements.
4. **A capability registry** — declaring which layer owns each capability, dated, so the
   fallback can shrink as Meta's MCP grows.
5. **Local asset ingestion with deduplication** — fingerprint, upload once, cache the hash or
   video id, never re-upload on retry.
6. **Correct money handling** — one tested module, explicit currency offsets, zero-decimal
   currencies handled.
7. **A brand workspace outside the plugin** — private by default, with Meta authoritative for
   anything discoverable.
8. **Honest separation of constraint from heuristic from business rule.**
9. **One canonical skill set packaged for both Codex and Claude Code** — every project here
   targets one host, or ships loose folders.
10. **Tests.** Two projects have meaningful tests. Neither tests the safety model.

That list is this project's scope. It is deliberately *not* another Marketing API client:
items 1-10 are all above the transport layer, which is precisely the layer Meta now owns.
