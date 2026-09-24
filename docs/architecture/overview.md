# Architecture overview

## One sentence

`meta-ads-agent` is a plugin of skills, guardrails, and small deterministic helpers that turns
a coding agent into a careful Meta Ads operator on top of Meta's **official** Ads MCP server,
with a narrow Marketing API fallback for the few things that server cannot do.

## What it is not

- Not a Marketing API client. Meta's MCP and the official Business SDK are the API layer.
- Not an MCP server. The agent talks to `https://mcp.facebook.com/ads` directly; nothing in
  this project sits between them.
- Not a dashboard. The coding agent is the interface.
- Not a spend optimiser. It proposes; the human approves anything that moves money.

## Layers

```
┌──────────────────────────────────────────────────────────────────────┐
│  User intent                                                         │
│  "build a campaign for this offer, three angles, leave it paused"    │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────┐
│  SKILLS — the brain.  skills/meta-ads-*/SKILL.md                     │
│  Intent -> plan. Routing. Safety policy. Approval gates. Diagnosis.  │
│  Prose, loaded by the agent. No API calls live here.                 │
└──────┬──────────────────────────────────────────────────┬────────────┘
       │ reads / writes state, validates plans            │ chooses provider
       │                                                  │
┌──────▼──────────────────────────┐          ┌────────────▼────────────┐
│  DETERMINISTIC HELPERS          │          │  CAPABILITY REGISTRY    │
│  src/meta_ads_agent/            │          │  config/capabilities.   │
│  money · validation · state     │◄─────────┤  yaml                   │
│  fingerprints · redaction       │          │  who owns what, dated   │
└──────┬──────────────────────────┘          └─────────────────────────┘
       │
       │ only for capabilities the MCP lacks
       │
┌──────▼──────────────────────────┐          ┌─────────────────────────┐
│  API FALLBACK (optional)        │          │  OFFICIAL META ADS MCP  │
│  meta-ads-agent api ...         │          │  mcp.facebook.com/ads   │
│  facebook-business SDK          │          │  ~90 tools, Meta OAuth  │
│  local upload · video creative  │          │  PRIMARY for everything │
│  existing post · delete         │          │  it covers              │
└──────┬──────────────────────────┘          └────────────┬────────────┘
       │                                                  │
       └──────────────────┬───────────────────────────────┘
                          ▼
                  Meta Marketing API
```

The agent calls the MCP itself. The fallback CLI is a sibling, not a proxy — see
[ADR-001](adr/ADR-001-mcp-first.md) and [ADR-002](adr/ADR-002-api-fallback.md).

## The eleven skills

| Skill | Posture | Job |
| --- | --- | --- |
| `meta-ads-core` | — | Routing, safety policy, approval classes, workspace, state, error recovery. Every other skill assumes it. |
| `meta-ads-audit` | read-only | Inspect an account. Separate fact from interpretation from recommendation. |
| `meta-ads-campaign` | write, gated | Intent -> plan -> validate -> create PAUSED -> verify -> persist. |
| `meta-ads-creative` | read/plan | Genuinely distinct angles, copy, CTA. Reads brand voice. Never invents evidence. |
| `meta-ads-preview` | read-only | Render placement previews and QA them before anything activates. |
| `meta-ads-optimize` | analyse first | Diagnose, then propose. Mutation is a separate approved step. |
| `meta-ads-report` | read-only | Equal-period comparisons, attribution-aware, few metrics, clear conclusion. |
| `meta-ads-tracking` | read-only | Dataset/pixel health. Configuration is not evidence of delivery. |
| `meta-ads-research` | read-only | Ad Library research for themes, not for cloning. |
| `meta-ads-audiences` | write, gated | Custom and lookalike audiences: source, size, exclusions. Creating and attaching are separate approvals. |
| `meta-ads-experiments` | write, gated | A/B tests and lift studies, sized before they are created, read without picking the metric afterwards. |

One canonical `skills/` directory. Both host manifests point at it — see
[ADR-003](adr/ADR-003-dual-agent-packaging.md).

## Sources of truth

| Question | Authority |
| --- | --- |
| What did the user intend to build? | `.meta-ads/campaigns/<slug>/plan.yaml` |
| What objects exist and what are their ids? | `.meta-ads/campaigns/<slug>/state.json` |
| What are this brand's defaults and voice? | `.meta-ads/brand.yaml`, `.meta-ads/voice.md` |
| Which local asset maps to which remote id? | `.meta-ads/assets/manifest.json` |
| What is the account's **actual** state right now? | **Meta.** Always. |
| Which layer owns a capability? | `config/capabilities.yaml` |

Local state is a convenience for resumability, never an authority over Meta. The user may edit
anything in Ads Manager at any time; reconcile before mutating. See
[ADR-005](adr/ADR-005-local-state.md).

## The campaign pipeline

```
intent → account context → brand/offer context → PLAN → VALIDATE
       → [approval if consequential] → campaign PAUSED → ad set PAUSED
       → assets (dedup, upload once) → creative → ads PAUSED
       → preview → QA → report → awaiting approval
```

Every stage writes its ids to `state.json` the moment they exist. A failure at any stage
leaves a resumable run, not an orphan. Nothing becomes ACTIVE as a side effect of creation
succeeding. See [ADR-004](adr/ADR-004-write-safety.md).

## Risk classes

| Class | Example | Requires |
| --- | --- | --- |
| `read` | insights, audit, preview | nothing |
| `create_paused` | new campaign/ad set/ad, all PAUSED | the user asked to build it |
| `update_inactive` | edit a paused entity | the user asked for the edit |
| `update_active` | retarget or reschedule a live ad set | explicit approval |
| `budget_increase` | change a budget, in either direction | explicit approval, with old and new shown in account currency |
| `activate` | PAUSED -> ACTIVE | explicit approval, after preview and QA |
| `delete` | remove an object | explicit approval, and a stated reason why pause is insufficient |
| `bulk` | anything touching many entities | the affected list shown first, then approval |
| `pii_upload` | customer-list audiences | explicit instruction plus a lawful basis |

Enforced identically whether the operation runs through the MCP or the fallback CLI. The CLI
is not a way around the policy.

## Money

One module, `src/meta_ads_agent/money.py`. A `Money` value carries `minor`, `currency`, and
the currency's `offset`; `* 100` appears nowhere else. Zero-decimal currencies (JPY, KRW, …)
and three-decimal currencies (KWD, …) are handled explicitly, and an unknown currency raises
rather than guessing. The account's currency is read from Meta before any budget is
interpreted: a bare "70" is never assumed to be dollars.

## Capability routing

`config/capabilities.yaml` maps each capability to a `preferred_provider`, an optional
`fallback_provider`, a `risk_level`, and a `last_reviewed` date. The rule is:

1. If the official MCP covers it, use the MCP.
2. Only if it does not, use the fallback.
3. Never use the fallback because it is more convenient.
4. When the agent does use the fallback, it says so and names the gap.

The fallback is expected to **shrink**. When Meta adds a capability, the migration is:
add a test, flip `preferred_provider`, mark the fallback `deprecated`, then delete the code.
See [ADR-002](adr/ADR-002-api-fallback.md) and
[docs/reference/capability-refresh.md](../reference/capability-refresh.md).

## Where things live

| Kind of knowledge | Home | Why |
| --- | --- | --- |
| Workflow and judgement | `skills/*/SKILL.md` | The agent reasons; keep it short |
| Changing Meta specifics, examples | `skills/*/references/*.md` | Progressive disclosure; churns often |
| Arithmetic, schemas, state, I/O | `src/meta_ads_agent/` | Deterministic and testable |
| Who owns which capability | `config/capabilities.yaml` | Machine-readable, dated |
| Version-sensitive constants | `src/meta_ads_agent/api/version.py` | One place to bump |

No API logic in `SKILL.md`. No media-buying strategy in Python. See
[ADR-008](adr/ADR-008-deterministic-vs-agent-layer.md).

## Deliberate non-goals for 0.1.0

No database, no web server, no web UI, no background daemon, no raw "execute any Graph call"
escape hatch, no autonomous budget changes. Local files and a CLI are sufficient, and each
omission removes a way to lose money or leak data.
