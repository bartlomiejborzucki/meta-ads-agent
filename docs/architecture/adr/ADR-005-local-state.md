# ADR-005: Local state exists for resumability; Meta remains authoritative

- **Status:** accepted
- **Date:** 2026-09-16

## Context

Creating a campaign is a multi-write sequence: campaign, ad set, asset uploads, creative, ads.
Any step can fail — validation error, rate limit, expired token, closed socket, or the user
walking away.

Not one of the eleven audited projects persists ids as it goes. So a failure after the ad set
is created leaves an orphan, and a rerun creates a second campaign. This is the most common
real failure in agent-driven campaign creation and it is universally unhandled.

Ambiguous failures make it worse: a timeout does not tell you whether Meta created the object.

The opposite error is treating local state as truth. Users edit campaigns in Ads Manager, other
tools touch the account, and Meta changes statuses on its own (rejections, spend limits).

## Decision

**Persist ids the moment they exist.** Each `create` writes to
`.meta-ads/campaigns/<slug>/state.json` before the next begins — id, type, provider,
timestamp, and the pipeline stage.

**Resume, never restart.** A rerun loads state, verifies each recorded object still exists on
Meta, and continues from the first incomplete stage.

**Verify before retrying an ambiguous write.** After a timeout or unknown error, query Meta for
the object before retrying. Reads may be retried with backoff; writes may not be retried
blindly.

**Meta is authoritative.** Before mutating anything from saved state, re-read it from Meta. If
local and remote disagree, report the mismatch and stop — never silently overwrite a change a
human made.

**Deduplicate assets by content.** `.meta-ads/assets/manifest.json` maps a local file's
SHA-256 (plus size and account) to its remote image hash or video id, so a retry never
re-uploads.

**Never store secrets in state.** No tokens, no app secrets, no customer data. A test asserts
this.

**The workspace lives outside the plugin.** `.meta-ads/` sits in the user's project, gitignored
by default. Plugin directories hold code; user data never mixes in.

## Consequences

**Good.** Interrupted creation resumes without duplicates. Retries are safe. Concurrent human
edits are detected rather than clobbered. Repeated uploads of the same file cost nothing. The
plan/state split keeps intent separable from outcome.

**Bad, and accepted.**
- State can go stale, which is why every mutation path re-reads Meta first. Staleness is a
  detectable condition, not a silent one.
- Two people running against one account from different checkouts have two state files. Out of
  scope for 0.1.0; Meta reconciliation keeps it merely inconvenient rather than dangerous.
- Local files are not transactional. A crash mid-write could truncate `state.json`. Mitigated
  with atomic replace (write temp, `os.replace`).
- A deleted workspace loses resumability, not data — Meta still has the objects, and the
  account can be re-read.

## Alternatives rejected

**SQLite or another database.** Nothing here needs transactions across entities or queries
beyond "load this campaign". A JSON file is diffable, greppable, and human-fixable. A database
would also make the private workspace opaque to the user who owns it.

**Reconstruct state from Meta each time by naming convention.** Names are not unique, users
rename things, and it makes resumability depend on a naming scheme.

**Keep state in the plugin directory.** Mixes user data with installed code and is wiped on
reinstall.
