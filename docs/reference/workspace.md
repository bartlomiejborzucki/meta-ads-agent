# The brand workspace

`.meta-ads/` in your project. Created by `meta-ads-agent init`, and **private by
default** — `init` writes a `.gitignore` inside it excluding everything.

## Why it is outside the plugin

Plugin directories hold installed code. They are wiped on reinstall, shared
between projects, and not yours to put data in. Account ids, performance
exports, campaign state, and creative assets belong to your project.

So the workspace lives in your project and the plugin never writes to itself —
[ADR-005](../architecture/adr/ADR-005-local-state.md).

## Layout

```
.meta-ads/
  .gitignore              written by init; excludes everything
  brand.yaml              defaults, naming, UTMs, DSA entities, your thresholds
  voice.md                brand voice, free-form prose
  account.yaml            cached account facts. A cache, not the truth.
  offers/<slug>.yaml      reusable offer briefs
  assets/
    manifest.json         local fingerprint -> remote image hash / video id
    <your files>          if you keep creative here
  campaigns/<slug>/
    plan.yaml             intent
    state.json            what exists on Meta
    creatives.json        creative detail as built
    qa.md                 preview QA notes
    report.md             latest report
  reports/                account-level reports
  actions.jsonl           append-only audit log
  state/                  scratch for resumable operations
```

## Structured facts, free-form voice

`brand.yaml` holds structured settings. `voice.md` holds prose.

That seam is deliberate: the campaign engine has no business caring about tone,
and the copywriter has no business caring about billing events. Keeping them in
one file means every change to either touches both.

## Almost nothing is required

Currency, timezone, Pages, Instagram identities, and datasets are all readable
from Meta. A cached copy that drifts is worse than no copy, so prefer reading.

Configure what Meta cannot tell us:

| Worth configuring | Because |
| --- | --- |
| `voice.md`, `banned_phrases`, `claims_policy` | Meta has no idea how you sound or what you may claim |
| `dsa.beneficiary`, `dsa.payor` | legal entity names, which must never be invented |
| `thresholds` | your cost ceilings and evidence floors are yours |
| `naming`, `utm` | conventions only you can choose |
| `special_ad_category` | a standing declaration, if one applies |
| `advantage_defaults` | so you are never silently enrolled in creative changes |

## Relocating it

```bash
export META_ADS_WORKSPACE=~/work/acme/.meta-ads
```

Useful for sharing one workspace across several checkouts. Otherwise the
workspace is found by walking up from the current directory, the way git finds
a repository — so a command run from a subdirectory still works.

## Versioning part of it

`init` writes `.meta-ads/.gitignore` containing `*`, so nothing in the workspace
is committed by accident. The repository's own `.gitignore` also excludes
`.meta-ads/`.

If you deliberately want to share some of it with a team — `brand.yaml`,
`voice.md`, and `offers/` are the reasonable candidates — delete that
`.gitignore` and add targeted rules to your project's own instead:

```gitignore
.meta-ads/*
!.meta-ads/brand.yaml
!.meta-ads/voice.md
!.meta-ads/offers/
```

**Do not commit** `reports/`, `campaigns/*/state.json`, `actions.jsonl`, raw
exports, creative assets, or anything derived from a customer list. State in
particular is machine-written, per-machine, and useless to anyone else.

That is a deliberate decision to make, not a default to drift into.

## Validating it

```bash
meta-ads-agent init --check
```

Validates `brand.yaml` and every offer brief, warns if `voice.md` is missing,
and checks the internal `.gitignore` is present. Exits `1` if a file fails
validation.

## Deleting it

Safe. You lose resumability for in-flight builds and the local action log;
everything else is still on Meta and can be read again.

Uninstalling the plugin does **not** remove it. It is your data.
