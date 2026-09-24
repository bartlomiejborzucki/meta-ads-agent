# Security

## Reporting a vulnerability

**Do not open a public issue.** Use
[GitHub's private advisory form](https://github.com/bartlomiejborzucki/meta-ads-agent/security/advisories/new).

Please include what you found, how to reproduce it, and what an attacker could
achieve. If a credential of yours was exposed while finding it, rotate it first.

We will acknowledge, investigate, and credit you unless you would rather not be.

## What counts as a vulnerability here

This project has an unusual threat model: it operates an ad account with real
money in it, on behalf of a non-deterministic agent. The highest-severity
issues are not the usual ones.

**Critical**

- A way to make money move without the user's explicit approval - an
  activation, a budget increase, or anything that starts delivery.
- A credential leak: an access token or app secret reaching a log, an error
  message, a state file, the action log, or terminal output.
- Customer data leaking, being logged, or being persisted.
- A path that lets the CLI bypass an approval gate.

**High**

- Command injection, or `shell=True` reached with user-controlled input.
- Path traversal through a plan, workspace, or asset path.
- Arbitrary code execution through a config file - for example, unsafe YAML
  loading.
- A way to make the agent operate on the wrong ad account.

**Moderate**

- Overwriting a change a human made in Ads Manager without reporting the
  mismatch.
- Duplicate object creation after a partial failure.
- A validation rule that can be bypassed with crafted input.

## What this project already does

Stated so you know what to test, and what the intended behaviour is.

**Credentials**

- Read from the environment only. Never from a workspace file, never from a
  conversation.
- Never written to campaign state, the asset manifest, or the action log. A
  test asserts that no field name in those models contains `token`, `secret`,
  `password`, or `credential`, and the state writer scrubs secret-shaped values
  on the way to disk.
- Never printed. `doctor` reports a configured secret as a SHA-256 prefix and a
  length, not a value prefix - a truncated token is still part of a credential.
- Graph API URLs have their query string replaced before display, because Graph
  puts `access_token` in the query.
- `.env` is gitignored, `.env.example` contains no real-looking values, and CI
  runs a pinned Gitleaks against both the working tree and the full history.

**Subprocesses**

- `shell=True` is never used.
- The only subprocesses are `ffprobe` and version probes of `claude` / `codex`,
  all invoked with a fixed argument list and an absolute path resolved through
  `shutil.which`.

**Config parsing**

- `yaml.safe_load` only. Never `yaml.load`. A workspace file could come from
  anywhere, and full-loader YAML can construct arbitrary Python objects. A test
  asserts a `!!python/object/apply` payload is rejected.
- Everything read from disk is validated against a Pydantic model that rejects
  unknown fields.

**File writes**

- State is written atomically - temp file plus `os.replace` - so a crash cannot
  truncate the record of objects that already exist on Meta.

**Write safety**

- New campaigns, ad sets, and ads are created PAUSED. The plan model has no
  field for anything else.
- Activation, budget increases, deletion, bulk changes, and customer-list
  uploads require explicit approval.
- Deletion requires `--approved` **and** a stated reason, and refuses an ACTIVE
  object.
- There is no generic "run any Graph call" command. Adding one would void every
  guardrail here.

**Network**

- No backend, no telemetry, no analytics. The only network destinations are
  Meta's MCP endpoint and the Marketing API.
- Asset uploads go through the official SDK; we do not follow redirects
  ourselves.

## Known limitations

Stated plainly, because a security policy that only lists strengths is not
useful.

**The approval model is advisory.** Meta's MCP write tools execute immediately,
and they belong to Meta's server. This project shapes agent behaviour through
skills; it cannot gate a transport it does not own. A sufficiently confused
agent can still call `ads_activate_entity`. Mitigating this properly would mean
proxying Meta's MCP, which was considered and rejected - see
[ADR-001](docs/architecture/adr/ADR-001-mcp-first.md) and
[ADR-004](docs/architecture/adr/ADR-004-write-safety.md).

If this matters for your use, grant your token or OAuth session read-only
scopes. `ads_read` without `ads_management` makes the whole write surface
unavailable, which is a real guarantee rather than an advisory one.

**Your agent host sees your conversation.** Account data the agent read, and
anything you pasted, are subject to your host's data policy. Never paste an
access token into a chat.

**The workspace is unencrypted.** `.meta-ads/` holds account ids, performance
data, and campaign state in plain files. It is gitignored by default; it is not
protected from anything with read access to your disk.

**Live tests need a real token.** They are opt-in, marked `live`, excluded from
CI, and documented in [`tests/live/README.md`](tests/live/README.md). CI sets
`META_ACCESS_TOKEN=""` so a stray live test fails rather than picking up a
credential.

## If you leaked a token

1. Revoke it. For a user token, remove the app's access in your Facebook
   security settings. For a system user token, revoke it in Business Settings.
2. Check the ad account's activity log for changes you did not make.
3. Check the account spending limit.
4. Generate a new token and put it in `.env`, not in a conversation.

Assume anything pasted into a transcript, an issue, or a screenshot has leaked.

## Pre-release review record

A security review was performed before the 0.1.0 tag. Recorded so the next
reviewer knows what was already checked, and so a regression is visible.

**Reviewed 2026-09-16.** Findings and their resolution:

| Area | Result |
| --- | --- |
| `shell=True`, `os.system`, `eval`, `exec`, `pickle` | none present anywhere in `src/` or `scripts/` |
| Subprocess calls | three, all with a fixed argument list. `ffprobe` and host version probes resolve the binary through `shutil.which`; the repo scripts invoke `git` from `PATH` in a developer or CI checkout only. |
| YAML loading | `yaml.safe_load` exclusively. A test asserts a `!!python/object/apply` payload is rejected. |
| Network in our own code | none. `urllib.parse` is used for parsing only. All Meta traffic goes through the official SDK or the agent's MCP client. |
| Credential leakage | tokens never written to state, the asset manifest, or the action log; scrubbed on the way to disk; `doctor` prints a SHA-256 prefix and a length, never a value prefix |
| Graph URLs in output | query string replaced when it carries a credential |
| Path traversal via a slug | `slugify` strips `..`, `/`, and `\`; a campaign directory cannot escape the workspace. Tested. |
| Arbitrary file as an asset | **a bug was found here** — see finding 1 below. Now: only a recognised image or video container header is accepted; an extension and the caller's requested kind are both untrusted. Tested against shell scripts, text, HTML, and passwd-shaped content under image and video extensions. |
| Symlinked assets | a symlink to a non-media file is rejected; a symlink to a real image is accepted and fingerprints identically to its target |
| File permissions | state, config, and the workspace `.gitignore` are written `0600` (owner-only) |
| Temporary files | one site, `tempfile.mkstemp` in the destination directory, `os.replace`d into place, unlinked on failure |
| Large files | fingerprinted and probed in chunks; never read whole into memory |
| Unicode and spaces in paths | tested, including the workspace, assets, and the CLI |
| HTTP redirects on upload | handled by the official SDK; we do not follow redirects ourselves |
| Arbitrary file upload | only paths a plan names, and only if they pass media detection |

**Three bugs were found and fixed during the review:**

1. **Arbitrary file upload.** `probe_asset` accepted an explicitly requested
   asset kind without confirming it against the file's contents, and separately
   treated a video *extension* as proof of a video. Together that meant a plan
   naming any readable path — a shell script, `/etc/passwd`, an arbitrary text
   file — could have had that file uploaded to the user's ad account by
   `api upload-image` or `api upload-video`. The caller's request and the
   filename are now both treated as untrusted: only a recognised image or video
   container header counts, with ffprobe as a second opinion for unusual
   containers. Fixed, with parametrised regression tests for each vector.
2. A slug of one character was refused, because both the slug pattern and the
   plan model required at least two. A single-character campaign slug is
   legitimate. Fixed, with a test.
3. `probe_asset` read an asset's header with a bare `open()`, which leaked the
   file handle and let a raw `PermissionError` escape instead of the project's
   own error type. Fixed, with a test.

A fabricated image header also reported `0x0` dimensions rather than
"unknown", which would have let downstream code reason about an aspect ratio of
zero. Now reported as unknown, with a warning.

### 0.2.1 review

**Reviewed 2026-09-23**, over 0.2.0. Three findings, fixed in 0.2.1 with
regression tests that fail against the 0.2.0 code:

1. **Secret-named keys printed in full.** `redact_mapping` lowered keys before
   normalising them, so `metaAccessToken` became `metaaccesstoken` and matched
   nothing; `pageAccessToken` and `X-Access-Token` were not listed at all. The
   test claiming camelCase was covered passed only because its sample value
   looked like an `EAA` token. Keys are now split on case, and any key ending
   in `_token`, `_secret`, `_password` or `_api_key` is masked.
2. **Credentials in URL queries.** `redact_url` removed the query only when
   one of three named parameters was present, so `fb_exchange_token`, `code`
   and `input_token` were printed. A query now survives only if every
   parameter is on a short known-harmless list; `user:pass@` is always
   removed; `Authorization: OAuth <token>` is masked like Bearer.
3. **A shell in `open-url`.** The fallback launcher was `cmd.exe /c start`,
   which treats `&` as a command separator, and an https URL may contain one.
   Replaced by `rundll32.exe url.dll,FileProtocolHandler`, which parses
   nothing. Checked against a fake Windows only.

Also fixed: with no ad account configured, a real `api` call targeted
`act_<no account configured>` instead of being refused.

### 0.5.0 review

**Reviewed 2026-09-23**, over what 0.3.0 to 0.5.0 added: file locking,
`render-plan`, the `report` arithmetic, `capabilities --compare`, the live
tests, and three workflows.

| Area | Result |
| --- | --- |
| Workflow inputs in shell | **one finding, fixed**: the trigger-evals workflow spliced `inputs.max_cost_usd` into its `run:` script, so whoever could dispatch it could run shell code with the Anthropic key in the environment. It now arrives through `env` and is checked to be a number. No other `${{ }}` expression reaches a script. |
| Actions | every `uses:` is pinned to a commit SHA, enforced by a test |
| Secrets in workflows | the Anthropic key only in the on-demand eval workflow; no Meta token anywhere, and still no workflow runs the live tests (tests/live/README.md) |
| Lock files | `.<name>.lock` beside the file, opened with `O_CREAT` and never truncated or written; a planted symlink could at most make the lock file exist elsewhere. They sit in the user's own workspace or install target. |
| Concurrent state | a merge never drops an id; a conflict keeps both, then raises |
| `report` input | parsed by pydantic, no code execution; non-finite numbers are refused on the way in |
| `capabilities --compare` input | regex over pasted text, linear in its length; nothing is executed or written |
| `render-plan --write` | writes only the plan path it was given, atomically; like every atomic write here, it replaces a symlink with a file |
| Live tests | skip without an explicit opt-in, a designated account and a token; create only inert, prefixed objects; never delete or activate |
| Action log | failure details pass through the same redaction as every record |

## Supported versions

1.x is supported; fixes land on `master` and are released as 1.x patches.
The live-account caveat in the README's Status section applies to security
as much as to anything else. There is no backport policy yet.
