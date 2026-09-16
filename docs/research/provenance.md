# Provenance and licensing review

**Review date:** 2026-09-16
**Purpose:** record, per third-party source, what was reviewed, under what license, and
exactly what — if anything — entered this repository. This is the audit trail behind
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).

## Terms used

| Term | Meaning |
| --- | --- |
| `dependency` | Installed at runtime from a package registry. Not vendored. Its license governs the installed copy, not ours. |
| `adapted` | Code or text derived from the source, requiring attribution and license notice. |
| `reimplemented` | Idea taken, implementation written from scratch, no expression copied. |
| `reference-only` | Read for orientation. Nothing copied — not code, not text, not structure. |
| `facts-adopted` | Specific factual claims about Meta's platform taken and re-expressed, with the source credited where the claim is recorded. |

**As of 0.1.0 this repository contains no `adapted` material.** Every third-party influence is
`reimplemented`, `facts-adopted`, or `reference-only`. That is a deliberate choice: it keeps
the license story trivially clean and it meant writing our own prose anyway, which we wanted
for consistency of voice.

## Reviewed repositories

### pipeboard-co/meta-ads-mcp
- **License:** Business Source License 1.1 — **not an open-source license**
- **Reviewed SHA:** `2ef198e` · **Reviewed:** 2026-09-16
- **Useful:** breadth of Marketing API coverage; real OAuth with local callback; `META_API_NOTES.md`; the observation that entity duplication is a capability the first-party MCP lacks
- **Depend on it:** no · **Code adapted:** no · **Idea reimplemented:** no · **Reference only:** yes
- **Notes:** BUSL-1.1 permits limited production use but restricts offering a competing
  product and only converts to a permissive license at its change date. Copying anything —
  including prose — would create an obligation this project cannot meet. Read only. Our
  fallback-for-missing-capabilities thesis follows from Meta's tool inventory, not from this
  codebase.

### gomarble-ai/facebook-ads-mcp-server
- **License:** MIT · **SHA:** `a3b555a` · **Reviewed:** 2026-09-16
- **Useful:** `.dxt` desktop-extension and Smithery packaging
- **Depend on it:** no · **Adapted:** no · **Reimplemented:** no · **Reference only:** yes
- **Notes:** MIT would allow reuse. Nothing was taken; the packaging channels do not apply to
  a Codex/Claude Code plugin.

### byadsco/meta-ads-mcp
- **License:** MIT (© 2025 ByAds — Santiago Bastidas) · **SHA:** `139421a` · **Reviewed:** 2026-09-16
- **Useful:** centralised Graph API version module; writes paced separately from reads; a
  Meta error-code reference; pinned Gitleaks version in CI
- **Depend on it:** no · **Adapted:** no · **Reimplemented:** yes · **Reference only:** no
- **Reimplemented as:** `src/meta_ads_agent/api/version.py` (single source for the Graph
  version), the write-vs-read distinction in `config/capabilities.yaml` risk levels and
  `skills/meta-ads-core/references/safety-policy.md`,
  `skills/meta-ads-core/references/meta-errors.md`, and the pinned scanner in
  `.github/workflows/secret-scan.yml`.
- **Notes:** these are architectural practices, not expression. No TypeScript was read into
  Python. Credited in `THIRD_PARTY_NOTICES.md` for the ideas even though attribution is not
  legally required for reimplementation.

### sepivip/meta-ads-skill
- **License:** MIT (© 2026 Beka Zakaidze) · **SHA:** `ab583c5` · **Reviewed:** 2026-09-16
- **Useful:** the only source written against a live official-MCP session. Tool names absent
  from Meta's docs (`ads_creative_upload_image`, `ads_entity_get_report`,
  `ads_entity_schedule_report`); image upload reported URL-only; budgets in minor units;
  `targeting` as a JSON string; flat creative params; `entity_type: ad_set`; account
  eligibility fields (`is_ads_mcp_enabled`, `is_queryable`, `has_payment_method`); the stance
  that a platform VALIDATION error outranks any local note
- **Depend on it:** no · **Adapted:** no · **Reimplemented:** yes · **Facts adopted:** yes
- **Recorded in:** [`current-meta-capabilities.md`](current-meta-capabilities.md), section
  "Community-reported tools absent from Meta's published reference", where the source, SHA,
  license, and **unverified** status are stated inline; and as flagged hints in
  `skills/meta-ads-core/references/mcp-tool-map.md`.
- **Notes:** facts about a third party's API are not themselves copyrightable, but the source
  is credited anyway because it is the reason we know them. Its prose was not copied. Every
  claim is marked unverified pending live introspection.

### Sandy-zippy/meta-ads-stack
- **License:** MIT (© 2026 ZippyScale) · **SHA:** `e82b4c9` · **Reviewed:** 2026-09-16
- **Useful:** skills-are-the-brain/MCP-is-the-hands framing; a monitor that never writes split
  from an executor that only applies approved actions; append-only audit log; PAUSED everywhere
- **Depend on it:** no · **Adapted:** no · **Reimplemented:** yes · **Reference only:** no
- **Reimplemented as:** the audit/optimize skill split, `src/meta_ads_agent/state/actionlog.py`,
  and the paused-by-default rule in `config/capabilities.yaml`.
- **Explicitly rejected:** hardcoded media-buying rules (+20% scaling caps, business-hours
  gates, "copy the top marketers") as engine behaviour. See
  [ADR-007](../architecture/adr/ADR-007-heuristics-vs-constraints.md).

### kelpi-ai/meta-ads-skills
- **License:** MIT (© 2026 Kelpi) · **SHA:** `c046a25` · **Reviewed:** 2026-09-16
- **Useful:** one-skill-per-job decomposition; explicit READ-ONLY markers; require two
  independent signals before declaring creative fatigue; baseline an entity against its own
  history, never a sibling's; enumerate alternative causes; refuse to conclude on thin data
- **Depend on it:** no · **Adapted:** no · **Reimplemented:** yes · **Reference only:** no
- **Reimplemented as:** the nine-skill layout, and
  `skills/meta-ads-optimize/references/fatigue-signals.md`.
- **Changed on purpose:** its fixed thresholds (`frequency > 4.0`, `CTR -30%`) become
  documented, user-overridable defaults rather than rules.

### rafaelszago/meta-ads-mcp
- **License:** MIT (© 2026 Rafael Zago) · **SHA:** `d004a42` · **Reviewed:** 2026-09-16
- **Useful:** the brand-workspace concept; structured account facts (`brand.yaml`) kept
  separate from free-form tone (`voice.md`); minor units named in the field
  (`daily_budget_minor`); tokenised naming conventions reused for UTM construction
- **Depend on it:** no · **Adapted:** no · **Reimplemented:** yes · **Reference only:** no
- **Reimplemented as:** `templates/brand/`, `src/meta_ads_agent/workspace.py`,
  `src/meta_ads_agent/models/brand.py`, and the naming/UTM token handling in
  `src/meta_ads_agent/models/plan.py`.
- **Changed on purpose:** the workspace moves out of the repository into a per-project
  `.meta-ads/` directory that is gitignored by default; Meta stays authoritative for anything
  discoverable rather than mirrored into config the user must maintain.
- **Notes:** our template field names were chosen independently and differ; the concept and
  the facts/voice seam are the borrowed parts.

### mardab96/meta-ads-skills
- **License:** MIT (© 2026 Marek Dabrowski / AdLume) · **SHA:** `388095b` · **Reviewed:** 2026-09-16
- **Useful:** deterministic arithmetic in Python with judgement left in `SKILL.md`; a noise
  band plus a volume floor before flagging a change; thresholds as CLI parameters; documented
  exit codes; always show spend; attribution and modelling caveats as first-class topics
- **Depend on it:** no · **Adapted:** no · **Reimplemented:** yes · **Reference only:** no
- **Reimplemented as:** the code/prose split described in
  [ADR-008](../architecture/adr/ADR-008-deterministic-vs-agent-layer.md),
  `skills/meta-ads-report/references/metrics-and-comparisons.md`, and the
  insufficient-evidence discipline in `skills/meta-ads-optimize/SKILL.md`.
- **Notes:** no script was read into ours; our comparison helpers operate on MCP insight
  responses, not CSV files.

### Digitizers/meta-ads-mcp
- **License:** MIT No Attribution (MIT-0, © 2026 Digitizer) · **SHA:** `bade982` · **Reviewed:** 2026-09-16
- **Useful:** correct current `.claude-plugin/plugin.json` packaging with thin skill plus
  references; **pause-over-delete justified by loss of optimisation history**; special ad
  categories framed as an account-suspension risk; blunt PII rules (hash before transmission,
  lawful basis, honour opt-outs, suppression lists); a release-drift CI workflow
- **Depend on it:** no · **Adapted:** no · **Reimplemented:** yes · **Reference only:** no
- **Reimplemented as:** `.claude-plugin/plugin.json` layout,
  `skills/meta-ads-core/references/safety-policy.md` (pause-first with the history rationale),
  `skills/meta-ads-campaign/references/special-categories-and-dsa.md`, the audience PII rules
  in `skills/meta-ads-core/references/safety-policy.md`, and
  `.github/workflows/upstream-check.yml`.
- **Explicitly rejected:** its single rule table mixing platform constraints with media-buying
  folklore at equal authority.
- **Notes:** MIT-0 requires no attribution at all. Credited voluntarily.

### itsfromgaurav/ultimate-meta-ads-skill
- **License:** MIT template **with a carve-out**; GitHub reports `NOASSERTION` · **SHA:** `269f204` · **Reviewed:** 2026-09-16
- **Useful:** observed only — the skill/references/checklists/templates layout, and the idea of
  isolating newer research in a dated supplement file
- **Depend on it:** no · **Adapted:** no · **Reimplemented:** no · **Reference only:** yes
- **Notes — restricted.** The license covers the repository's organisational structure and
  authored checklists/templates, but states it does **not** grant rights to the underlying
  advertising ideas and frameworks, which belong to the authors of a commercial book and their
  publisher, and directs users to buy the book. The repository therefore cannot sublicense its
  own substance. **Nothing was copied:** no text, no checklist, no template, no framework name.
  `skills/meta-ads-creative/` was written from scratch and deliberately avoids proprietary
  framework names and acronyms.

### lil-j/meta-ads-mcp
- **License:** **none** — no `LICENSE` file; GitHub reports no license · **SHA:** `c815259` · **Reviewed:** 2026-09-16
- **Useful:** observed only — physical read/write separation via two MCP servers; a tracked
  write manifest; preview rendering plus a preview-QA skill as a first-class stage; a test file
  beside nearly every module
- **Depend on it:** no · **Adapted:** no · **Reimplemented:** no · **Reference only:** yes
- **Notes — restricted.** Absent a license, default copyright reserves all rights. Nothing
  copied or quoted. Our read/write separation and preview stage were reached from the ecosystem
  gaps analysis and are implemented differently: because Meta's MCP is a single external
  surface we cannot split servers, so we split skills and place the approval gate in the
  workflow.

## Runtime dependencies

| Package | License | Vendored | Notes |
| --- | --- | --- | --- |
| `facebook-business` | Facebook Platform License (`NOASSERTION` on GitHub) — **not OSI-approved** | **No** | Installed from PyPI only under the optional `api` extra. Permits use in connection with Meta's platform, which is exactly our use. Must never be vendored or redistributed. Keeping it an optional extra means a default MCP-only install does not pull it in at all. |
| `pydantic` | MIT | No | Config, plan, and state validation |
| `PyYAML` | MIT | No | YAML parsing, `safe_load` only |
| `pytest`, `ruff`, `mypy` | MIT · MIT · MIT | No | Dev only |

## Meta documentation

Meta's developer documentation and the Business Help Center are **not** licensed for
redistribution. Tool *names*, endpoint URLs, scope names, and API version numbers are facts
and are recorded as such. No documentation prose is reproduced anywhere in this repository.

## Trademarks

"Meta", "Facebook", "Instagram", "Messenger", "WhatsApp", "Advantage+", "OpenAI", "ChatGPT",
"Codex", "Anthropic", and "Claude" are trademarks of their respective owners, used
descriptively only to identify the platforms this project works with. This project is
independent and is not affiliated with, sponsored by, or endorsed by any of them.

## Review procedure for future contributions

A PR that introduces third-party material must:

1. Name the source repository, its license, and the exact commit SHA.
2. Classify the contribution using the terms at the top of this file.
3. Add a row here and, if the class is `adapted`, an entry in
   [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) preserving the original notice.
4. Be rejected if the source is BUSL, unlicensed, or carries a carve-out withholding rights to
   the material being contributed.

When in doubt, reimplement. It is cheaper than a license audit.
