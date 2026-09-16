# Examples

Realistic, filled-in versions of the files this project reads and writes. Every
id is fake and shaped so it cannot be mistaken for a real one, and CI checks
that nothing here looks like a credential.

| File | What it is | Blank template |
| --- | --- | --- |
| `brand.yaml` | a configured brand workspace | `templates/brand/brand.yaml` |
| `offer.yaml` | a reusable offer brief | `templates/campaign/offer.yaml` |
| `campaign-plan.yaml` | a validated campaign plan | `templates/campaign/campaign-plan.yaml` |
| `state.json` | campaign state **after a failed build** | written by the tool |

Every one of these validates against its model, and CI fails if one stops -
a template that does not validate is worse than no template, because the user
copies it, edits one field, and blames their edit.

```bash
meta-ads-agent validate-plan examples/campaign-plan.yaml --skip-assets
```

`--skip-assets` because the plan references `./creatives/*.jpg`, which are not
committed. Account-dependent checks are reported as skipped: there is no
account context here, and the report says so rather than implying the plan is
cleared for execution.

## What each example demonstrates

**`brand.yaml`** - the separation the whole config rests on. Meta-discoverable
facts (currency, Page, dataset) are cached but not authoritative. DSA entities
are *legal entity* names, which is why they are configured rather than inferred
from the brand name. `thresholds` are this advertiser's own business rules, not
platform limits and not our opinions. `claims_policy` states plainly what may
and may not be claimed.

**`offer.yaml`** - `proof` is the only evidence the creative skill may cite. The
`restrictions` include "do not claim a specific hours-saved figure, we have not
measured it", which is the shape of a useful restriction: it names the tempting
claim and why it is unavailable.

**`campaign-plan.yaml`** - three genuinely different angles (time recovered,
error risk, being the bottleneck), not three rewordings of one. ABO so the test
gets a guaranteed budget. `advantage_audience: false` because the age bounds are
deliberate. `standard_enhancements: false` with the reason stated. Everything
PAUSED, because there is no field for anything else. The `notes` field explains
the structural choices, which is what makes a plan reviewable rather than just
readable.

**`state.json`** - a build that **failed partway**, which is the interesting
case. The campaign, ad set, video, and creative exist; the ads stage never
completed. Three things to notice:

- The video and creative record `provider: api_fallback` - Meta's MCP creates
  single-image link creatives only, so that step used the Business SDK.
- The recorded failure is `retry_safe: false`, carrying Meta's error code
  100/1885183. The next step is to **query Meta** for an ad under the ad set,
  not to retry the create.
- `plan_fingerprint` binds this state to the plan that produced it. Editing the
  plan now blocks the resume, because continuing would apply a different plan
  to existing structure.

```bash
meta-ads-agent state acme-webinar-q4   # from a workspace containing this state
```
