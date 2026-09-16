# Write safety and approval policy

Meta's MCP write tools execute immediately. There is no draft mode, no undo,
and no confirmation screen. The approval model lives here, in the workflow,
because that is the only place it can live - see
`docs/architecture/adr/ADR-004-write-safety.md`.

The failure is asymmetric. A paused campaign the user did not want costs a
minute of cleanup. An activated one costs their budget.

## Risk classes

### `read` - no approval

Insights, entity listings, previews, dataset stats, activity logs, Ad Library,
help articles. Read freely. Reading is how you avoid guessing.

### `create_paused` - no approval beyond the original request

Creating campaigns, ad sets, ads, and creatives **as PAUSED**, when the user
asked you to build something. "Build me a campaign for this offer" is
sufficient authority to create the structure, because nothing spends.

Do not interpret it as authority to activate.

### `update_inactive` - no approval beyond the request

Editing an entity that is already paused, when the user asked for the edit. It
cannot move money today.

### `update_active` - explicit approval

Changing targeting, schedule, placements, bid, or optimisation on a **live**
entity. Delivery shifts, and on a live campaign that has costs.

Pausing a live entity is also this class. It stops spending rather than
starting it, so it is the safe direction - but confirm the entity list first,
because pausing the wrong ad is a real loss.

### `budget_increase` - explicit approval

Any budget change. Report:

- the current value, read from Meta, in the account currency
- the proposed value in the same currency
- the delta, and the percentage
- which level the budget sits on (campaign or ad set)

Never present a number without its currency. Use
`meta-ads-agent validate-plan` or the money helpers rather than converting in
your head.

### `activate` - explicit approval, after preview and QA

`ads_activate_entity` starts spending. Requirements before you ask:

1. The structure exists and has been verified against the plan.
2. Previews have been rendered for the placements the campaign targets.
3. QA passed - identity, copy, destination, crops, truncation.
4. The user can see what they are approving.

Activate top-down: campaign, then ad set, then ads. An active ad under a paused
ad set does not deliver, which is a confusing state to debug.

### `delete` - explicit approval, and a reason

**Deleted objects lose their optimisation history permanently. Paused objects
keep it.** Pausing is almost always the better answer, so before proposing a
deletion, say why pausing is insufficient.

The CLI enforces this: `--approved` and `--reason` are both required, an ACTIVE
object is refused outright, and `--dry-run` shows what would go.

### `bulk` - show the list, then get approval

Anything touching many entities. Enumerate them first - name, id, current
status, current spend. "Pause the underperformers" is not a list; turn it into
one and have the user confirm it.

### `pii_upload` - explicit instruction and a lawful basis

`ads_update_custom_audience_users` uploads hashed personal data. The
highest-risk operation available.

- Only on explicit instruction. Never as a step you inferred.
- Confirm the user has a lawful basis and consent.
- Email and phone must be SHA-256 hashed before transmission.
- Never log the data, never write it to state, never commit the source file.
- Honour opt-outs and suppression lists.
- If you are unsure whether the data may be used this way, stop and ask.

Lookalike, website, and engagement audiences contain no PII and are ordinary
`update_active` work.

## What approval means

Approval is **specific**. It names the entity and the change.

Sufficient:

- "Yes, activate campaign 120210000000001."
- "Raise the PL ad set to 70 PLN/day."
- "Pause ads A and B."

Not sufficient:

- "Sounds good" (said while reviewing a plan)
- "Go ahead" (said before seeing what was built)
- "Do whatever you think is best"
- "Make it work"
- Silence

If the user's instruction was explicit and unambiguous to begin with - *"pause
ad 12345"* - that **is** the approval. Do not ask twice for something they
already stated precisely. The gate exists to catch inference, not to add
ceremony.

## Never

- Activate anything the user has not seen.
- Raise a budget without showing both values and the currency.
- Assume a budget number is dollars.
- Create anything ACTIVE.
- Delete when pausing would do.
- Retry an ambiguous write without querying Meta first.
- Use the CLI to route around any of the above.

## Profiles

`.meta-ads/brand.yaml` can set `profile: conservative | standard |
experimental`. It affects how many variants you propose and how verbose reports
are. **It never relaxes an approval gate.** There is no autonomous mode.
