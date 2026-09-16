# Privacy

What this project stores, where, and what it never stores.

## What stays on your machine

Everything. This project has no backend, no telemetry, no analytics, and no
network calls other than to Meta.

The brand workspace `.meta-ads/` holds:

| File | Contains |
| --- | --- |
| `brand.yaml` | ad account id, Page id, dataset id, your thresholds, DSA entities |
| `voice.md` | your brand voice |
| `account.yaml` | cached account facts read from Meta |
| `offers/*.yaml` | offer briefs |
| `campaigns/*/plan.yaml` | campaign intent, including budgets |
| `campaigns/*/state.json` | created object ids |
| `assets/manifest.json` | local file fingerprints mapped to remote ids |
| `actions.jsonl` | what this tool did, and when |
| `reports/` | performance exports |

`meta-ads-agent init` writes a `.gitignore` **inside** the workspace excluding
everything, so it is private by default wherever it is created. The repository's
own `.gitignore` also excludes `.meta-ads/`.

Versioning part of it is your call to make deliberately. Reports, exports, and
customer audience files should not be committed.

## What is never stored

- **Access tokens.** Read from the environment, used, discarded. Never written
  to state, the action log, or any workspace file.
- **App secrets.** Same.
- **Customer data.** Customer-list contents are never read into state, logged,
  or cached. The tool has no reason to hold them and does not.
- **Reasoning.** The action log records actions, not chains of thought.

A test asserts that no field name in the state or action-log models contains
`token`, `secret`, `password`, or `credential`, and the state writer scrubs
secret-shaped values on the way to disk as a second line of defence.

## Redaction

Everything user-visible passes through redaction:

- Values named like credentials are masked.
- Meta-token-shaped strings are masked even unnamed, because tokens leak in
  prose too.
- Graph API URLs have their query string replaced when it carries a credential -
  Graph puts `access_token` in the query, so a full request URL in a log is a
  leaked credential.
- `doctor` reports a configured secret as a SHA-256 prefix and a length, never a
  value prefix. A truncated token is still part of a credential.

## What Meta sees

Meta sees what you ask it. Reads, and writes you approve. This project adds no
intermediary: your agent talks to `https://mcp.facebook.com/ads` directly, and
the optional fallback talks to the Marketing API directly.

Meta's handling of that data is governed by their terms, not ours.

## What your agent host sees

Whatever is in your conversation. That includes account data the agent read and
any file contents you shared.

Two consequences worth stating plainly:

- **Never paste an access token into a chat.** Put it in `.env` or the
  environment. Assume anything in a transcript has leaked, and rotate it.
- Performance data and account ids in a conversation are subject to your host's
  data policy, not this project's.

## Customer data and PII

`ads_update_custom_audience_users` uploads hashed personal data and is the
highest-risk operation available.

The skills require: explicit instruction, a confirmed lawful basis and consent,
SHA-256 hashing of email and phone before transmission, no logging, no
persistence, and honouring opt-outs and suppression lists. There is deliberately
**no fallback implementation** for it - one path, maximum scrutiny.

If you are not certain data may be used this way, do not upload it.

## Reporting a problem

If you find a way this project leaks a credential or customer data, please
report it privately. See [SECURITY.md](../../SECURITY.md).
