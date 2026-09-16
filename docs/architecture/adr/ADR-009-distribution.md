# ADR-009: Plugin marketplaces first, PyPI as a manual, gated step

- **Status:** accepted
- **Date:** 2026-09-16

## Context

There are two things to distribute, and they are not the same thing.

**The plugin** - the skills, references, and manifests. Installed through the
host's own mechanism: `claude plugin marketplace add` and `claude plugin
install`, or Codex's `/plugins`. This is what most users need, and it requires
nothing from us but a tagged repository.

**The CLI** - the Python package. Needed only for `doctor`, `init`,
`capabilities`, `validate-plan`, `state`, and the six fallback capabilities.
A user whose work is entirely covered by Meta's official MCP never installs it.

Publishing to PyPI would shorten the CLI install from a git clone to
`uv tool install "meta-ads-agent[api]"`. It also means claiming a name in a
global namespace, taking on the obligation to keep publishing, and making every
release a public artifact rather than a tag.

## Decision

**Host plugin marketplaces are the primary distribution channel.** A tagged
repository is sufficient for the plugin, which is what the project mostly is.

**The CLI is installable from a clone or a git URL** at 0.1.0:

```bash
uv tool install "git+https://github.com/OWNER/meta-ads-agent.git#egg=meta-ads-agent[api]"
# or
git clone ... && uv pip install -e ".[api]"
```

**A GitHub release is created on every `v*` tag**, with built wheel and sdist
attached, notes extracted from `CHANGELOG.md`, and `0.x` marked pre-release.
Before building, the workflow verifies that the tag, `__version__`, and **both**
plugin manifests agree, and that the changelog has an entry - a version
mismatch between the two manifests is exactly the drift ADR-003 warns about, so
it fails the release rather than shipping.

**PyPI publishing exists but is never automatic.** It requires a manual
`workflow_dispatch` with `publish_to_pypi: true`, a `pypi` environment that can
require a reviewer, and Trusted Publishing via OIDC - so no API token is stored
in the repository at all.

## Why not publish automatically

- **The name is a commitment.** Claiming `meta-ads-agent` on PyPI at 0.1.0,
  with a name the README says is provisional, is the wrong order.
- **Automatic publishing makes a tag irreversible.** A GitHub release can be
  deleted; a PyPI version cannot be replaced.
- **The CLI is optional.** Optimising its install path before the plugin path is
  the wrong priority.
- **Trusted Publishing needs configuring on PyPI's side** before the workflow
  can succeed, and that is a deliberate act by a maintainer, not a default.

## When to revisit

Publish to PyPI when all of these hold:

1. The project name is settled (it is currently provisional).
2. The CLI surface has been stable across at least one release.
3. Enough people need the fallback that a git install is real friction.
4. A maintainer has configured Trusted Publishing and will keep publishing.

At that point, flip the default and update
`docs/getting-started/install-claude-code.md`. Nothing else changes.

## Consequences

**Good.** No namespace claimed prematurely. No stored publishing token. Release
notes come from a changelog that must exist. A version mismatch across the
manifests cannot ship. The plugin path - the one most users take - needs no
packaging infrastructure at all.

**Bad, and accepted.** Installing the CLI is a longer command than
`pip install meta-ads-agent`, and that is documented rather than hidden. Users
who want the fallback have slightly more friction, which is consistent with the
fallback being the exception rather than the path.
