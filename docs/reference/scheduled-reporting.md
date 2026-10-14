# Scheduled reporting, without a daemon

This project has no background process and will not grow one
([architecture overview](../architecture/overview.md)). A weekly report does
not need one: your operating system's scheduler can start a non-interactive
agent session that reads, reports, and exits. This page sets one up so that
it **can only read**.

## Two locks, both on

1. **A read-only Meta session.** Authorise the MCP connection with
   `ads_read` and without `ads_management`. Meta then refuses every write,
   whatever the agent attempts. This is the guarantee; the next lock is the
   belt to its braces.
2. **A tool allowlist.** A non-interactive session has nobody to answer a
   permission prompt, so any tool not allowed is refused. Allow the reads
   the report needs and nothing else.

Never schedule a session with write scopes. A scheduled job that can spend
is the autonomous optimiser [ADR-004](../architecture/adr/ADR-004-write-safety.md)
rules out.

## Claude Code, from cron

Run it once by hand first: the MCP connection's OAuth must already be
authorised in this user's Claude Code configuration, and the first run is
where you see what a missing permission looks like.

```bash
#!/usr/bin/env bash
# weekly-meta-report.sh - read-only weekly report for one account
set -euo pipefail
cd ~/projects/acme            # the project holding .meta-ads/
mkdir -p reports

claude -p "Weekly Meta Ads report for act_1234567890: compare the last 7 days \
with the 7 before, name what moved and what did not, and list anything I \
should look at. Change nothing." \
  --allowedTools \
    "mcp__meta-ads__ads_get_ad_accounts" \
    "mcp__meta-ads__ads_get_ad_entities" \
    "mcp__meta-ads__ads_get_errors" \
    "mcp__meta-ads__ads_account_get_activity_logs" \
    "mcp__meta-ads__ads_insights_performance_trend" \
    "Bash(meta-ads-agent report:*)" \
  > "reports/$(date +%F).md"
```

```cron
# Mondays at 07:00
0 7 * * 1  ~/bin/weekly-meta-report.sh 2>> ~/projects/acme/reports/errors.log
```

`meta-ads` is the server name from
[connect-meta-mcp.md](../getting-started/connect-meta-mcp.md); use yours.
The `report` arithmetic needs the optional CLI on the job's `PATH`; without
it the skill does the arithmetic by hand and shows its sums.

The plugin's approval hook
([ADR-011](../architecture/adr/ADR-011-hooks-enforce-approvals.md)) still runs
in a non-interactive session. A call it would ask about needs a prompt that
nobody is there to answer, and a non-interactive session refuses a tool call
that needs one.

## Codex

The same shape works with `codex exec` and a read-only sandbox; give it the
same prompt, and connect the MCP with read-only scopes, since Codex has no
approval hook for this project.

## What to expect from the report

The report skill's rules hold in a scheduled run as in a conversation: equal
windows, rates from sums, volume floors from `brand.yaml`, and attribution
stated. A scheduled report is a reason to look, not a decision: any change
it suggests is proposed in a normal session, where you can approve it.
