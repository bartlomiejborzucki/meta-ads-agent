# Compatibility: what an upgrade may and may not change

Users keep files in `.meta-ads/`, agents read the CLI's `--json` output, and
scripts depend on its exit codes. This page is the promise about each, and how
it is tested. It takes effect from 1.0; the 0.x releases already follow it,
and the tests below enforce it now.

## The workspace

| File | Schema | Promise |
| --- | --- | --- |
| `campaigns/<slug>/plan.yaml` | `schema_version` 1 | read by every later release |
| `campaigns/<slug>/state.json` | `schema_version` 1 | read, **and resumable**, by every later release |
| `brand.yaml`, `offers/<slug>.yaml` | `schema_version` 1 | read by every later release |
| `account.yaml`, `accounts/<act_id>.yaml` | a cache | safe to delete; rebuilt from Meta |
| `assets/manifest.json` | `schema_version` 1 | read by every later release; losing it costs one re-upload per file, nothing more |
| `actions.jsonl` | one record per line | appended to, never rewritten; unreadable lines are skipped, not fatal |

**Older files are always read.** A release that changes a format ships a
workspace migration (`meta-ads-agent migrate`, run by `upgrade`), which
detects whether its effect is already present, so it is safe to re-run. Until
a format actually changes, "no migration required" is the changelog's answer,
and it is a tested claim: `tests/fixtures/written-by/` holds the files each
earlier release shipped, and `tests/test_compatibility.py` reads every one -
and resumes the saved campaign state against its plan - on every change.

**Newer files are refused, clearly.** A `schema_version` higher than this
release understands is an error that says to upgrade, rather than a newer
format silently read by older rules.

**A resume survives an upgrade.** A campaign part way through a build on one
release resumes on the next. The plan fingerprint that guards a resume leaves
out fields at their default, so a new optional plan field does not look like
an edit; fingerprints written by 0.1 and 0.2 are still compared the way they
were computed.

## The CLI

| Surface | Promise |
| --- | --- |
| Command and flag names | not removed or renamed within a major version; a replacement ships alongside the old name for at least one minor release |
| `--json` output | keys are only ever **added** within a major version. Removing or renaming one is a breaking change. `tests/test_json_contract.py` holds every command's keys to `tests/fixtures/json-contract.json`. |
| Exit codes | `0` success, `1` failed or blocked, `2` bad input or usage, `130` interrupted - per [cli.md](cli.md) |
| Human-readable output | **not** a contract. It changes whenever it can be clearer. Parse `--json`. |

## The skills

Skill names, and the risk classes of the safety policy, are stable within a
major version: other agents' instructions and every action log refer to them.
A risk class keeps its name even when its meaning is clarified - which is why
`budget_increase` also covers a cut.

The prose inside a skill is not a contract. It changes whenever the advice
gets better.

## What is not promised

- Anything Meta changes. Tool names in the capability map are hints, and a
  Meta validation error outranks every local file.
- The API fallback's command list. It is meant to shrink (ADR-002): when
  Meta ships a capability, its fallback command is deprecated for one minor
  release and then removed, with the changelog saying so.
- Python-level imports. The package's modules are the CLI's implementation,
  not a library API.

## When a promise has to be broken

In a major version, with a changelog section that says exactly what changed
and what to do, and a migration for every file format involved.
