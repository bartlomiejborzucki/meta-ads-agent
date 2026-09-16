# Publishing this repository

The repository is complete and ready to push. It has **no git remote** and the
URLs in it contain an `OWNER` placeholder, because the GitHub owner is not
knowable in advance — and a wrong owner in an install command is worse than an
obvious placeholder.

These are the exact steps.

## 1. Set the owner

```bash
python3 scripts/set_repo_owner.py <your-github-user-or-org>

# if you also renamed the project:
python3 scripts/set_repo_owner.py <owner> --repo <new-repo-name>
```

It rewrites `OWNER/meta-ads-agent` across every tracked Markdown, JSON, TOML,
and YAML file — 26 occurrences in 13 files. Review the diff and commit:

```bash
git diff
git commit -am "Point URLs at <owner>/<repo>"
```

Confirm none were missed:

```bash
python3 scripts/set_repo_owner.py <owner> --check
```

## 2. Pre-push checks

Run these before the first public push. All should be green.

```bash
uv sync --extra dev
uv run pytest                                      # 523 tests
uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
uv run mypy
uv run python scripts/validate_examples.py
uv run python scripts/validate_codex_plugin.py
uv run python scripts/check_single_skills_tree.py
uv run python scripts/check_gitignore.py
claude plugin validate . --strict
claude plugin validate .claude-plugin/marketplace.json
```

Then check nothing private is staged:

```bash
git status
git ls-files | grep -E '\.env$|\.pem$|\.key$|\.meta-ads/' && echo "STOP" || echo "clean"
```

And scan for secrets, including history:

```bash
gitleaks dir . --config .gitleaks.toml --redact
gitleaks git . --config .gitleaks.toml --redact
```

The hygiene tests in `tests/test_repo_hygiene.py` assert most of this too, so a
green `pytest` already covers credential-shaped paths, plausible tokens in
tracked files, and `.env.example` containing no values.

## 3. Create the repository

**With the GitHub CLI**, from the repository root:

```bash
gh auth login

gh repo create <owner>/meta-ads-agent \
  --public \
  --source . \
  --remote origin \
  --description "Agent-native Meta Ads toolkit built on Meta's official Ads MCP, with a narrow Marketing API fallback" \
  --push
```

`--source .` uses this checkout, `--remote origin` wires it up, and `--push`
pushes `main`. It will refuse if `<owner>/meta-ads-agent` already exists —
which is the intended behaviour. Pick a different name rather than forcing it.

**Without the GitHub CLI**, create an empty public repository in the web UI
(no README, no `.gitignore`, no license — this repository has all three), then:

```bash
git remote add origin https://github.com/<owner>/meta-ads-agent.git
git branch -M main
git push -u origin main
```

## 4. Repository settings

Worth doing immediately:

- **Topics:** `meta-ads`, `facebook-ads`, `instagram-ads`, `mcp`,
  `agent-skills`, `claude-code`, `codex`, `advertising`
- **Enable** Issues, and Discussions if you want them
- **Enable** private vulnerability reporting — Settings → Security. The
  `SECURITY.md` link and the issue-template contact link both point at it.
- **Enable** Dependabot alerts and security updates. `.github/dependabot.yml`
  is already configured, and deliberately does **not** auto-merge
  `facebook-business` majors.
- **Branch protection on `main`:** require the CI checks, and require a pull
  request. The upstream monitor and Dependabot both open PRs rather than
  pushing.
- **Actions permissions:** the workflows need `issues: write` for the upstream
  monitor and `contents: write` for releases. Both are declared per-job.

## 5. First release

```bash
git tag v0.1.0
git push origin v0.1.0
```

`.github/workflows/release.yml` then runs the full verification, checks that the
tag, `__version__`, and **both** plugin manifests agree, checks the changelog
has a `## [0.1.0]` entry, builds the wheel and sdist, installs the wheel in a
clean environment, and creates a GitHub release marked pre-release with notes
extracted from `CHANGELOG.md`.

It does **not** publish to PyPI. That needs a manual `workflow_dispatch` with
`publish_to_pypi: true`, plus a `pypi` environment and a configured Trusted
Publisher — see [ADR-009](../architecture/adr/ADR-009-distribution.md).

## 6. Tell people how to install it

Once pushed, the Claude Code path works immediately:

```bash
claude plugin marketplace add <owner>/meta-ads-agent
claude plugin install meta-ads-agent@meta-ads-agent
```

`.claude-plugin/marketplace.json` lives at the repository root with
`"source": "."`, so the repository is its own marketplace. No extra hosting.

## If the name is taken

The project name is provisional and designed to be easy to change. Renaming
touches:

| | |
| --- | --- |
| `pyproject.toml` | `[project] name`, `[project.scripts]` entry point |
| `src/meta_ads_agent/` | the package directory |
| `.claude-plugin/plugin.json` | `name`, `displayName` |
| `.claude-plugin/marketplace.json` | `name`, and the plugin entry's `name` |
| `.codex-plugin/plugin.json` | `name`, `interface.displayName` |
| URLs everywhere | `scripts/set_repo_owner.py <owner> --repo <new-name>` |

The skills themselves reference the CLI by command name (`meta-ads-agent ...`),
so renaming the entry point means updating those references too. `grep -rn
meta-ads-agent skills/` finds them.

Nothing in the architecture depends on the name.
