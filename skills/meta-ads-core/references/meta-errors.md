# Meta error reference

Built from Meta's documented error codes and from failures encountered in
development. **Nothing here is invented** - if a code is not listed, say so
rather than guessing at its meaning.

When a call fails: show the code, the subcode, and Meta's message. Say which
stage failed and what already exists. Then decide whether a retry is safe.

## Retry rules

| Kind | Rule |
| --- | --- |
| Read | Retry with backoff, a few times at most. |
| Write | **Never retry blindly.** Query Meta for the object first. |

A timeout does not tell you whether Meta applied the write. Retrying a create
after a timeout is how duplicate campaigns appear. `meta-ads-agent state <slug>`
marks a recorded failure `retry_safe: false` for exactly this reason.

## Codes

### Transient - a read may be retried

| Code | Meaning | Do |
| --- | --- | --- |
| 1 | Unknown / transient API error | Back off, retry the read once or twice |
| 2 | Service temporarily unavailable | Back off |
| 4 | Application-level rate limit | Stop, wait, reduce request volume |
| 17 | User-level rate limit | Same, and batch more aggressively |
| 341 | Application limit reached | Wait; do not loop |
| 368 | Temporarily blocked for policy violations | Stop. Do not retry. Investigate. |
| 613 | Custom-level throttling | Slow down; reduce concurrency |

Rate limiting means your query pattern is wrong. One aggregated query with
breakdowns beats a loop over entities.

### Authentication

| Code | Meaning | Do |
| --- | --- | --- |
| 102 | Session invalid | Re-authenticate. For MCP, reconnect the server. For the fallback, mint a new token. |
| 190 | Access token expired or invalid | Same. Never print the token while diagnosing this. |
| 200 | Permission denied | The token or session lacks a scope, or the user lacks a role on the account. Check `ads_management`. |
| 294 | Missing ads management permission | The user needs an admin role on the ad account. |

### Request and validation

| Code | Meaning | Do |
| --- | --- | --- |
| 100 | Invalid parameter | Read the subcode and message. The message often lists the supported fields - **that list outranks any local documentation**. |
| 100 / subcode 1487079 | Invalid budget | Usually a minor-unit mistake or below the account minimum. Check the currency offset. |
| 100 / subcode 1885183 | Invalid creative spec | A required field for the creative type is missing. |
| 100 / subcode 1487036 | Invalid targeting spec | Often `targeting` sent as an object where a JSON string is expected. |
| 400 | Malformed request | Usually a shape problem, not a value problem. |

### Account and delivery

| Code | Meaning | Do |
| --- | --- | --- |
| 1487742 | Account has a spending limit that has been reached | Tell the user. Do not raise it yourself - that is a `budget_increase`. |
| 1359188 | Special ad category restriction | The campaign must declare the correct category. Do not try to bypass it. |
| 2635 | Deprecated API version or field | Check the configured Graph version. See `docs/reference/api-versioning.md`. |

An account can also fail *without* an error: no payment method, a disabled
status, or a zero spend limit all let objects be created and never deliver.
Check `account_status` and `has_payment_method` before a build, not after.

## Diagnosing a failure mid-build

1. `meta-ads-agent state <slug>` - what exists, what stage failed.
2. Query Meta for the objects state claims exist. Confirm they do.
3. If the failed write may have partially applied, look for the object by name
   and parent before creating anything.
4. Fix the cause. Re-validate the plan.
5. Resume from the recorded stage. Do not restart.

## Reporting a failure to the user

Include: what you were doing, the exact Meta error, what already exists, what
is safe to retry, and what you need from them. Do not summarise an error into
"something went wrong" - the code is the most useful thing on the screen.

`ads_get_errors` returns delivery-blocking errors for an account or entity, and
`ads_get_help_article` searches Meta's own Help Center. Both beat speculation
about policy.

## Adding to this file

Only add a code you have actually seen, or that appears in Meta's
documentation. Record what it meant in context and what resolved it. An
invented error code is worse than no entry, because someone will act on it.
