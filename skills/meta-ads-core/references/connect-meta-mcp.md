# Connecting Meta's official Ads MCP

This is the one setup step that cannot be skipped. Without it there are no
`ads_` tools in the session, and nothing in these skills can touch an account.

Host-neutral on purpose: the exact command differs per agent host, and the
host-specific walkthroughs are linked at the bottom. What is the same
everywhere is below.

**Endpoint:** `https://mcp.facebook.com/ads` - a streamable-HTTP MCP server
with OAuth.

## What the user needs

- Admin access to a Meta ad account.
- A **Meta App ID**, used purely as the OAuth client id.

The App ID is the part that surprises people. For this endpoint the OAuth
client id is the App ID of an app the user controls, so nobody can ship a
working default and this project deliberately does not try
([ADR-006](https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/docs/architecture/adr/ADR-006-mcp-connection-is-user-owned.md)).

To be precise about what is *not* needed: no access token, no app secret, and
no OAuth implementation. Just an id, which is not a secret.

Getting one: create or reuse an app at <https://developers.facebook.com/apps/>,
add the **Facebook Login for Business** product, register the redirect URL the
MCP client uses, and copy the App ID from the dashboard.

## Connecting

Whatever the host, the three inputs are the same:

| Input | Value |
| --- | --- |
| transport | HTTP (streamable) |
| url | `https://mcp.facebook.com/ads` |
| OAuth client id | the user's Meta App ID |

Most hosts have an `mcp add` command that takes exactly those and then an
authorisation step that opens a browser. A redirect-URL mismatch between the
app's Facebook Login settings and what the client sent is the most common
first-run failure, so check that before anything else.

## Scopes

Meta documents these for this server. Grant only what the work needs -
reading and reporting do not require `ads_management`, and a read-only grant
is the one hard safety guarantee available here.

| Scope | For |
| --- | --- |
| `ads_mcp_management` | the MCP server itself |
| `ads_read` | reading campaigns and insights |
| `ads_management` | creating and editing |
| `catalog_management` | catalog tools |
| `business_management` | business and Page discovery |
| `pages_show_list` | listing Pages |
| `instagram_basic` | Instagram identity |

## Verifying, from inside a session

Configuration is not connection. The only proof is a tool call:

1. List the session's tools. Names begin `ads_`.
2. Call `ads_get_ad_accounts`. Accounts with a `currency` and a `timezone`
   coming back means it works.

If a `meta-ads-agent` CLI is installed, `meta-ads-agent doctor` additionally
reports whether the endpoint appears in the host's configuration files - but
it reads config, not the live session, so step 2 still decides.

## When it does not work

| Symptom | Usually |
| --- | --- |
| no `ads_` tools at all | not configured, or the host needs a restart - most hosts load MCP servers at session start |
| "app is in development mode" | the Meta app is not live, and the user is not a test user on it |
| "no permissions available" while authorising | the signed-in account has no role on any ad account, or the app lacks Facebook Login for Business |
| redirect URL mismatch | the app's registered redirect differs from what the client sent |
| connected, but no accounts | no role on an ad account, or a scope set that excludes it. Check `is_ads_mcp_enabled` on the account |
| sporadic failures on a large account | rate limiting. Prefer one aggregated query with breakdowns over a loop of per-entity queries |

Meta publishes no rate-limit figure for this server, so do not quote one.

## Host-specific walkthroughs

Full commands, screenshots of the failure modes, and the configuration-file
route:
<https://github.com/bartlomiejborzucki/meta-ads-agent/blob/master/docs/getting-started/connect-meta-mcp.md>.
