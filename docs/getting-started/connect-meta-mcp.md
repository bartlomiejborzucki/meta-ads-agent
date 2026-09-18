# Connecting Meta's official Ads MCP

This is the one setup step you cannot skip. Everything else in this project is
optional.

**Endpoint:** `https://mcp.facebook.com/ads`

Meta's ads MCP server is generally available: any app registered on the
developer dashboard can connect to it. Managing another business's ad accounts
on their behalf is the one case that still needs review - Advanced Access to
`ads_mcp_management`. Operating your own accounts does not.

## What you need

- A Meta ad account you have admin access to.
- A **Meta App ID**. This is the part that surprises people, so read the next
  section before concluding you do not need one.

## Why an App ID, when there is no API token

Per Meta's own get-started documentation, the OAuth client id for this endpoint
is the **Meta App ID of an app you control**, and the redirect URL must match
the MCP client you are connecting from.

So the honest version of "no developer app needed" is:

- You do **not** need an access token.
- You do **not** need an app secret.
- You do **not** need to implement OAuth.
- You **do** need an App ID, used purely as an OAuth client identifier.

Creating one takes a few minutes and you never handle a credential. If Meta
later publishes a public client id, this step disappears.

## 1. Get a Meta App ID

1. Go to <https://developers.facebook.com/apps/> and sign in.
2. Create an app, or reuse one you already have.
3. Add the **Facebook Login for Business** product.
4. In its settings, add the redirect URL your MCP client uses. Claude Code
   handles this during `claude mcp add`; `codex mcp login` prints the callback
   URL to register; other clients document their own.
5. Copy the **App ID** from the app dashboard. It is a long number and it is
   not secret.

## 2. Connect it

### Claude Code

```bash
claude mcp add --transport http \
  --client-id <YOUR_META_APP_ID> \
  meta-ads https://mcp.facebook.com/ads
```

Scope it with `--scope user` for every project, or `--scope project` to share
the configuration with a team through git. If Meta requires a fixed redirect
port, `--callback-port` pins it.

Then restart Claude Code and confirm:

```bash
claude mcp list
```

### Codex

Codex keeps MCP servers in `~/.codex/config.toml`, not in a `mcpServers` JSON
block. Let the CLI write it:

```bash
codex mcp add meta-ads --url https://mcp.facebook.com/ads \
  --oauth-client-id <YOUR_META_APP_ID>
codex mcp login meta-ads
```

`codex mcp login` prints the callback URL to register in the app's Facebook
Login for Business settings.

By hand, with the full template in
[`integrations/codex/config.toml`](../../integrations/codex/config.toml):

```toml
[mcp_servers.meta-ads]
url = "https://mcp.facebook.com/ads"
# scopes = ["ads_mcp_management", "ads_read"]   # read-only setup

[mcp_servers.meta-ads.oauth]
client_id = "<YOUR_META_APP_ID>"
# callback_port = 1455                          # pin a registered redirect
```

Then `codex mcp list`, and start a new session. On older Codex builds remote
HTTP servers sat behind `experimental_use_rmcp_client = true`; if `url` seems
ignored, update Codex before reaching for that flag.

### Other MCP clients

The endpoint is a standard streamable-HTTP MCP server with OAuth. Any compliant
client works: give it the URL and your App ID as the OAuth client id.

Programmatic access is also possible with
`Authorization: Bearer <ACCESS_TOKEN>`, but that is the token path this project
avoids for normal use.

## 3. Authorise

The first Meta tool call opens a browser to Facebook Login for Business. Sign
in and grant access.

Scopes Meta documents for this server:

| Scope | For |
| --- | --- |
| `ads_mcp_management` | the MCP server itself |
| `ads_read` | reading campaigns and insights |
| `ads_management` | creating and editing |
| `catalog_management` | catalog tools |
| `business_management` | business and Page discovery |
| `pages_show_list` | listing Pages |
| `instagram_basic` | Instagram identity |

Grant only what you need. Reading and reporting do not require
`ads_management`, so a read-only setup is a reasonable way to start.

## 4. Verify

```bash
meta-ads-agent doctor
```

Look for:

```
Meta Ads MCP configured       READY    https://mcp.facebook.com/ads referenced in ...
```

`doctor` checks **configuration**, not the live session - only a running agent
can prove the connection works. So also ask your agent:

> List your available Meta Ads tools, then show me my ad accounts.

Tool names begin `ads_`. If you get accounts back with a currency and timezone,
you are connected.

## Troubleshooting

**No `ads_` tools.** The server is not configured, or the host needs a restart.
`claude mcp list` for Claude Code; `codex mcp list` and `codex mcp login
meta-ads` for Codex.

**"App that is in development mode."** Your Meta app has not been switched to
live, or your account is not a test user on it. Either switch the app to live
mode or add yourself as a test user.

**"No permissions available" during authorisation.** The signed-in account has
no role on any ad account, or the app is missing Facebook Login for Business.

**Redirect URL mismatch.** The redirect registered in your app does not match
what the client sent. Check the app's Facebook Login settings against your
client's documented redirect.

**Connected, but no accounts returned.** The signed-in user has no role on an
ad account, or you granted a scope set that excludes it. Check the account's
`is_ads_mcp_enabled` field, then your roles in Business Manager.

**Rate limits.** Meta does not publish a figure for this server, and we will
not quote one we cannot verify. Community reports suggest limits are easy to hit
on large accounts, so prefer one aggregated query with breakdowns over a loop of
per-entity queries.

## What this gives you

Around 90 tools, covering accounts, Pages, Instagram identities, campaigns, ad
sets, ads, single-image creatives, previews, insights and trend analysis,
custom audiences, datasets and pixel rules, catalogs, experiments, activity
logs, delivery errors, and public Ad Library search.

Current inventory:
[docs/research/current-meta-capabilities.md](../research/current-meta-capabilities.md).

What it does **not** cover, and what this project fills in:
[api-fallback.md](api-fallback.md).
