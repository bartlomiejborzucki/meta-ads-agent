# Packaging: what a skill directory has to contain

A skill directory is the unit of distribution. Whatever else ships alongside
it, the thing an agent host copies onto a user's machine is a folder with a
`SKILL.md` in it - so anything a skill needs has to be physically inside that
folder.

This is easy to get wrong from a checkout, because in a checkout everything
resolves. `docs/`, `templates/`, `config/` and the other eight skills are all
one relative path away, and a reference to any of them looks fine until the
folder is copied somewhere on its own.

## Supported install methods

These three are tested, by
[`scripts/check_skill_packaging.py`](../../scripts/check_skill_packaging.py)
and [`tests/test_packaging.py`](../../tests/test_packaging.py), on every push:

| | Shape | What arrives |
| --- | --- | --- |
| 1 | Plugin install | the repository, with `skills/` inside it |
| 2 | The whole `skills/` tree copied or symlinked into a skills directory | eleven skill folders, no repository |
| 3 | One `skills/meta-ads-<name>/` folder, copied on its own | that folder only |

Shape 3 is the strict case and the one the tests are written against: if a
single skill directory is self-sufficient, the other two are too.

`meta-ads-core` is worth installing alongside whatever else you take. Nothing
depends on it to *function* - every skill repeats the rules it cannot work
without - but it is where the routing, safety and workspace detail lives.

**Not supported:** installing `references/` or `assets/` separately from the
`SKILL.md` that uses them, and installing the skills expecting the
`meta-ads-agent` CLI to come with them. It does not; see below.

## The rules the checks enforce

1. **A path-shaped reference inside a skill resolves inside that same skill.**
   Relative links may point at `references/`, `assets/`, or `../assets/` -
   never at `../../another-skill/` and never at a repository directory.
2. **Cross-skill and repository pointers are named, plus an absolute URL.**
   "`fatigue-signals.md`, under `references/` in the `meta-ads-optimize`
   skill" followed by a `https://github.com/...` link, rather than a path that
   happens to resolve in a checkout.
3. **Every `meta-ads-agent` command a skill mentions is a real subcommand.**
   Checked against the argument parser, so a renamed command cannot leave a
   skill pointing at a ghost.
4. **Every skill carries the shared preflight block**, which is what makes it
   check for the MCP and for the CLI separately before doing anything.

## One copy of each shared resource

Two problems pull in opposite directions: a skill needs its resources inside
it, and a schema that exists twice will eventually disagree with itself. The
resolution is that there is exactly one copy of everything, and the build
moves it to wherever else it is needed.

**Templates live in the skill that documents them.**

| File | Home | Also reaches |
| --- | --- | --- |
| `brand.yaml`, `voice.md`, `account.yaml`, `offer.yaml` | `skills/meta-ads-core/assets/` | the wheel, as `meta_ads_agent/_data/templates/`, for `meta-ads-agent init` |
| `campaign-plan.yaml` | `skills/meta-ads-campaign/assets/` | read directly; the validator only reports against it |

The wheel copy is made by a `force-include` in `pyproject.toml` at build time.
There is no second copy in the repository, and `tests/test_packaging.py` fails
if a `templates/` directory reappears at the root.

**Shared prose is generated.** A few passages genuinely belong in more than
one skill - the preflight checks above all, and the policy for building
without the CLI. Copying them by hand across nine files is how nine files end
up saying eight different things, so the single copy lives in
`packaging/shared/<name>.md` and
[`scripts/sync_skill_blocks.py`](../../scripts/sync_skill_blocks.py) renders
it between markers in each `SKILL.md`:

```bash
python3 scripts/sync_skill_blocks.py           # rewrite the copies
python3 scripts/sync_skill_blocks.py --check   # what CI runs
```

Edit `packaging/shared/`, never the rendered block. A hand-edited copy fails
the check.

## The CLI does not come with the skills

`meta-ads-agent` is a separate `uv`/`pip` install and most users will not have
it. Every skill therefore probes for it - `meta-ads-agent --version` - before
suggesting anything that needs it, and treats "command not found" as the
normal answer.

What still works with Meta's official MCP and no CLI: audits, reporting, Ad
Library research, previews, tracking diagnosis, creative work, optimisation
diagnosis, and the MCP-side changes that follow it. The workspace files under
`.meta-ads/` can be written by hand from the templates in
`skills/meta-ads-core/assets/`.

What does not: campaign plan validation, and therefore campaign builds; local
image and video upload; video, existing-post and multi-variant creatives; and
deletion.

**Campaign writes stop without the validator.** Plan validation catches the
class of error that is invisible to a careful reader - minor-unit currency
arithmetic, a budget set on two levels, an identity or dataset that is not on
this account, missing EU transparency fields. Rather than write objects
against an unverified plan, the skills stop at the plan and offer the user the
routes forward: run the validator through `uvx` without installing anything,
install the CLI, build from the plan by hand in Ads Manager, or keep the plan
as the deliverable and continue with the read-only work.

The `uvx` route is verified in CI against this package's entry point:

```bash
uvx --from "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git" \
  meta-ads-agent validate-plan <plan>
```

`pipx run --spec …` should work the same way. It is not tested here, so it is
not documented as supported.

## Updating an installed copy

Codex runs nothing for us after it installs a plugin. Its cache lives at
`~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`, the only
documented lifecycle hook is `SessionStart`, and it skips even that until the
user has reviewed and trusted the definition. There is no post-install or
post-update event, so the update path is a command somebody runs:

```bash
meta-ads-agent upgrade            # payload, then workspace migrations
meta-ads-agent upgrade --rollback # restore the backup taken first
meta-ads-agent doctor             # what state is this installation in?
```

Local plugins are the case that bites, because Codex records their version as
`local` and reuses the same cache directory. Its own guidance is to bump a
`+codex.<cachebuster>` suffix and reinstall; that invalidates the cache but
still copies whatever the marketplace source contains, so it is not a
substitute for the checks below.

### The update is a diff, not a copy

An updater that copies "the files that were already there" advances the
version and leaves the new ones behind, which produces an installation
reporting a release it is not running. So the payload is enumerated in
`release-manifest.json` - every file, its SHA-256, its size - and an update
is the difference between two lists:

| bucket | what it means |
| --- | --- |
| added | in the release, not on disk. Includes whole new directories and new scripts |
| updated | on disk with different bytes |
| unchanged | identical, left alone |
| removed | on disk, not in the release. Deleted, so nothing stale survives |
| removed skills | a whole skill the release dropped |

Comparison is by content hash, so a hand-edited file and a half-copied one
both show up. The manifest is generated by
[`scripts/build_release_manifest.py`](../../scripts/build_release_manifest.py)
and CI fails if it disagrees with the tree - a release cannot ship a payload
nobody described.

### Order, and why it survives an interruption

```
backup -> stage -> verify the stage -> swap -> verify the installation -> record the version
```

The version is written **last**. Everything before it happens while the
install state still names the old version and carries an `in_progress` record
with the stage it reached. An update killed at any point therefore leaves an
installation that knows it is half way, and `doctor` says so:

```
INTERRUPTED   an update from 0.1.0 to 0.2.0 stopped during 'swap'
```

Re-running `upgrade` finishes it; the staging directory is rebuilt from the
package, so a resume is the same operation as a first attempt. A resume
reuses the backup the failed attempt took rather than archiving the
half-installed tree over the good copy.

`--rollback` restores that backup. The last three are kept.

Anything the installer creates in the target is named
`.meta-ads-agent-*`, and it only ever deletes a directory that is both named
`meta-ads-*` and contains a `SKILL.md` naming itself. Other people's skills
in the same directory are not touched.

### Workspace migrations are a separate thing

Replacing skill files is replacing code this project owns. Changing anything
under `.meta-ads/` is editing the user's work - their brand voice, offer
briefs, campaign plans, and the state recording which objects exist on Meta.
Those deserve different rules, so they are different steps.

Each migration:

- has an id, recorded in `.meta-ads/.migrations.json` the moment it succeeds;
- **detects** whether its effect is already present, so a deleted ledger
  cannot cause a second run;
- runs after the payload update, never before;
- triggers a copy of the whole workspace into `.meta-ads/.backups/` before the
  first one that changes anything;
- stops the run on failure, so a later migration never sees a workspace an
  earlier one left half-changed;
- never reads a token, contacts Meta, or touches a campaign. The subprocess
  environment for script-backed migrations has the Meta variables stripped.

```bash
meta-ads-agent migrate --dry-run   # what is outstanding
meta-ads-agent migrate             # apply it, once each
```

### Scripts added between versions

Shipping a script does nothing by itself; something has to run it. A release
declares such a migration in the manifest with the script's path **and its
SHA-256**:

```json
{
  "id": "0002-example",
  "description": "...",
  "introduced_in": "0.3.0",
  "script": "meta-ads-core/scripts/example.py",
  "script_sha256": "..."
}
```

Two gates before it executes. The bytes on disk must match the hash the
release declared, and the user must pass `--allow-migration-scripts`. Without
consent the step is reported rather than skipped silently:

```
skipped-needs-consent    0002-example
  runs meta-ads-core/scripts/example.py from the payload;
  re-run with --allow-migration-scripts to let it execute
```

Downloading code and running it because a JSON file said to is not a trust
model, and neither is hoping the host will do it for us.

### Diagnosing an installation

`meta-ads-agent doctor` distinguishes six states, because they need six
different fixes:

| state | meaning | fix |
| --- | --- | --- |
| `complete` | every file matches the manifest | - |
| `update-available` | installed version is older than the package | `upgrade` |
| `migration-required` | payload current, workspace migrations outstanding | `migrate` |
| `interrupted` | an update stopped part way | `upgrade`, or `--rollback` |
| `broken` | files missing, modified, or left over from an earlier release | `install --force` |
| `not-installed` | nothing recorded at the target | `install` |

It also reports version skew between the CLI, the payload it ships, and the
installed skills, and names the specific files in each category rather than
saying the installation is "wrong".

### Releasing

`scripts/build_release_manifest.py` regenerates the manifest; CI runs it with
`--check`. A release therefore cannot go out if the packaged tree differs
from the source tree, and the version is asserted identical across
`pyproject.toml`, `meta_ads_agent.__version__`, both plugin manifests and the
release manifest. CI additionally performs a clean install from the built
wheel and an upgrade over a doctored older installation, asserting that a
file the release dropped does not survive.

## When you add a skill or a reference

```bash
python3 scripts/sync_skill_blocks.py
python3 scripts/build_release_manifest.py
python3 scripts/check_skill_packaging.py
python3 scripts/check_single_skills_tree.py
uv run pytest tests/test_packaging.py tests/test_install_upgrade.py
```

The first command will tell you which markers a new `SKILL.md` is missing.
