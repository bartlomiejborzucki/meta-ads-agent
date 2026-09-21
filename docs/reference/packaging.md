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
| 2 | The whole `skills/` tree copied or symlinked into a skills directory | nine skill folders, no repository |
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

## When you add a skill or a reference

```bash
python3 scripts/sync_skill_blocks.py
python3 scripts/check_skill_packaging.py
python3 scripts/check_single_skills_tree.py
uv run pytest tests/test_packaging.py
```

The first command will tell you which markers a new `SKILL.md` is missing.
