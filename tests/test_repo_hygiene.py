"""Repository hygiene: the things that are easy to break in an unrelated edit.

These assert properties of the repository itself rather than of the code:
that credential-shaped paths are ignored, that both host manifests agree, that
skill content lives in exactly one place, that shipped templates validate, and
that documentation cross-references resolve.

Each one exists because the failure is silent and the consequence is real - a
deleted .gitignore line is a leaked account id, and a stale manifest version is
a release that ships two different answers.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def run_script(name: str) -> subprocess.CompletedProcess[str]:
    import sys

    return subprocess.run(  # noqa: S603 - fixed argv, repo-local script
        [sys.executable, str(SCRIPTS / name)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


class TestSecretExclusion:
    """A deleted .gitignore line is a leaked credential. Assert, do not assume."""

    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            ".env.local",
            ".env.production",
            "private.pem",
            "server.key",
            "credentials.json",
            "secrets.yaml",
            ".meta-ads/brand.yaml",
            ".meta-ads/account.yaml",
            ".meta-ads/actions.jsonl",
            ".meta-ads/campaigns/acme/state.json",
            ".meta-ads/assets/manifest.json",
            ".meta-ads/reports/2026-09.md",
        ],
    )
    def test_credential_and_workspace_paths_are_ignored(self, path: str) -> None:
        result = subprocess.run(  # noqa: S603 - fixed argv, parametrised literal
            ["git", "check-ignore", "-q", "--no-index", path],
            cwd=REPO,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"{path} is not gitignored and must be"

    @pytest.mark.parametrize(
        "path",
        [
            ".env.example",
            "templates/brand/brand.yaml",
            "templates/campaign/campaign-plan.yaml",
            "examples/brand.yaml",
            "examples/state.json",
            "config/capabilities.yaml",
            "skills/meta-ads-core/SKILL.md",
            "upstreams.yaml",
        ],
    )
    def test_things_that_must_ship_are_not_ignored(self, path: str) -> None:
        result = subprocess.run(  # noqa: S603 - fixed argv, parametrised literal
            ["git", "check-ignore", "-q", "--no-index", path],
            cwd=REPO,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 1, f"{path} is gitignored and must not be"

    def test_the_gitignore_check_script_passes(self) -> None:
        result = run_script("check_gitignore.py")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_no_credential_files_are_tracked(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        pattern = re.compile(r"(^|/)\.env($|\.)|\.pem$|\.key$|credentials\.json$|secrets\.ya?ml$")
        offenders = [path for path in tracked if pattern.search(path) and path != ".env.example"]
        assert offenders == [], f"credential-shaped files are tracked: {offenders}"

    def test_no_brand_workspace_is_tracked(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        offenders = [p for p in tracked if ".meta-ads/" in p]
        assert offenders == [], f"a private workspace is tracked: {offenders}"


class TestNoRealLookingCredentials:
    """An example that looks like a credential invites someone to use it."""

    # Long enough to be a plausible real token, unlike our deliberate fixtures.
    TOKEN_SHAPED = re.compile(r"\bEAA[A-Za-z0-9]{40,}\b")
    APP_SECRET_SHAPED = re.compile(r"\b\d{15,17}\|[A-Za-z0-9_\-]{25,}\b")

    # Files whose purpose is to contain credential-shaped strings: the fixtures
    # and the redaction tests. Kept in step with .gitleaks.toml's path
    # allowlist, and asserted below - a divergence means one of the two scanners
    # is checking something the other is not.
    EXEMPT = frozenset({"tests/conftest.py", "tests/test_redaction.py"})

    def _tracked_text_files(self) -> list[Path]:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        suffixes = {".md", ".yaml", ".yml", ".json", ".py", ".toml", ".example", ""}
        return [
            REPO / path
            for path in tracked
            if (REPO / path).is_file() and Path(path).suffix in suffixes and path not in self.EXEMPT
        ]

    def test_nothing_tracked_contains_a_plausible_meta_token(self) -> None:
        offenders = [
            path.relative_to(REPO)
            for path in self._tracked_text_files()
            if self.TOKEN_SHAPED.search(path.read_text(encoding="utf-8", errors="replace"))
        ]
        assert offenders == [], f"token-shaped strings found in: {offenders}"

    def test_nothing_tracked_contains_a_plausible_app_secret(self) -> None:
        offenders = [
            path.relative_to(REPO)
            for path in self._tracked_text_files()
            if self.APP_SECRET_SHAPED.search(path.read_text(encoding="utf-8", errors="replace"))
        ]
        assert offenders == [], f"app-secret-shaped strings found in: {offenders}"

    def test_the_exemptions_match_the_gitleaks_allowlist(self) -> None:
        config = (REPO / ".gitleaks.toml").read_text(encoding="utf-8")
        for path in self.EXEMPT:
            escaped = path.replace(".", r"\.")
            assert escaped in config, f"{path} is exempt here but not allowlisted in .gitleaks.toml"

    def test_the_env_example_has_no_values(self) -> None:
        for line in (REPO / ".env.example").read_text(encoding="utf-8").splitlines():
            if line.startswith("META_") and "=" in line:
                key, _, value = line.partition("=")
                # Only the Graph version and the workspace path may carry a value.
                if key.strip() not in {"META_GRAPH_API_VERSION", "META_ADS_WORKSPACE"}:
                    assert value.strip() == "", f"{key} has a value in .env.example"


class TestManifests:
    def test_the_claude_manifest_is_valid_json(self) -> None:
        manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        assert manifest["name"] == "meta-ads-agent"
        # A "./"-prefixed path is required; "skills" and ["skills"] both fail
        # `claude plugin validate`. Found by testing, not from documentation.
        assert manifest["skills"] == "./skills"

    def test_the_codex_manifest_passes_the_structural_check(self) -> None:
        result = run_script("validate_codex_plugin.py")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_the_manifests_agree_on_name_version_and_license(self) -> None:
        claude = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        codex = json.loads((REPO / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        for field in ("name", "version", "license"):
            assert claude[field] == codex[field], f"{field} differs between manifests"

    def test_the_manifest_version_matches_the_package(self) -> None:
        from meta_ads_agent import __version__

        claude = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        assert claude["version"] == __version__

    def test_the_changelog_documents_the_current_version(self) -> None:
        from meta_ads_agent import __version__

        changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
        assert f"## [{__version__}]" in changelog

    def test_the_marketplace_entry_points_at_this_plugin(self) -> None:
        marketplace = json.loads(
            (REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        assert marketplace["plugins"][0]["name"] == "meta-ads-agent"

    def test_no_mcp_server_is_bundled(self) -> None:
        """ADR-006: the Meta connection is user-owned.

        A bundled server would need an OAuth client id, and any value shipped
        here would be wrong for every user.
        """
        for relative in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            manifest = json.loads((REPO / relative).read_text(encoding="utf-8"))
            assert "mcpServers" not in manifest, f"{relative} bundles an MCP server"
        assert not (REPO / ".mcp.json").exists(), "a root .mcp.json would auto-load"


class TestSkillsTree:
    def test_exactly_one_canonical_skills_directory(self) -> None:
        result = run_script("check_single_skills_tree.py")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_every_skill_has_frontmatter_naming_itself(self) -> None:
        for skill in sorted((REPO / "skills").glob("*/SKILL.md")):
            text = skill.read_text(encoding="utf-8")
            assert text.startswith("---\n"), f"{skill} has no frontmatter"
            end = text.index("\n---", 4)
            frontmatter = yaml.safe_load(text[4:end])
            assert frontmatter["name"] == skill.parent.name
            assert frontmatter.get("description"), f"{skill} has no description"

    def test_skill_descriptions_say_when_to_use_the_skill(self) -> None:
        # A description that only says what a skill *is* does not get it loaded.
        for skill in sorted((REPO / "skills").glob("*/SKILL.md")):
            text = skill.read_text(encoding="utf-8")
            frontmatter = yaml.safe_load(text[4 : text.index("\n---", 4)])
            description = frontmatter["description"].lower()
            assert "use " in description or "use for" in description, (
                f"{skill.parent.name}: description should say when to use it"
            )

    def test_no_skill_names_a_host(self) -> None:
        """ADR-003: skill content is host-neutral."""
        host_words = re.compile(r"\b(claude code|codex cli|in codex|in claude)\b", re.I)
        offenders = []
        for path in sorted((REPO / "skills").rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            if host_words.search(text):
                offenders.append(path.relative_to(REPO))
        assert offenders == [], f"host-specific content in skills: {offenders}"

    def test_no_skill_embeds_a_json_request_body(self) -> None:
        """ADR-008: no API logic in a SKILL.md."""
        for skill in sorted((REPO / "skills").glob("*/SKILL.md")):
            text = skill.read_text(encoding="utf-8")
            assert "object_story_spec" not in text, (
                f"{skill.parent.name}: API request shapes belong in references, not in a SKILL.md"
            )

    def test_every_skill_is_reachable_from_the_core_skill(self) -> None:
        core = (REPO / "skills" / "meta-ads-core" / "SKILL.md").read_text(encoding="utf-8")
        for skill in sorted((REPO / "skills").glob("*/SKILL.md")):
            name = skill.parent.name
            if name == "meta-ads-core":
                continue
            assert name in core, f"{name} is not mentioned in meta-ads-core"


class TestTemplatesAndExamples:
    def test_every_template_and_example_validates(self) -> None:
        result = run_script("validate_examples.py")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_example_ids_cannot_be_mistaken_for_real_ones(self) -> None:
        text = (REPO / "examples" / "brand.yaml").read_text(encoding="utf-8")
        assert "act_0000000000000001" in text
        text = (REPO / "examples" / "campaign-plan.yaml").read_text(encoding="utf-8")
        assert "act_0000000000000001" in text


class TestDocumentationLinks:
    """A broken cross-reference is a doc that quietly stops being usable."""

    LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)")

    def _markdown_files(self) -> list[Path]:
        tracked = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        return [REPO / path for path in tracked]

    def test_relative_links_resolve(self) -> None:
        broken: list[str] = []
        for path in self._markdown_files():
            for target in self.LINK.findall(path.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    broken.append(f"{path.relative_to(REPO)} -> {target}")
        assert broken == [], "broken relative links:\n  " + "\n  ".join(broken)


class TestIndependenceDisclaimer:
    def test_the_readme_disclaims_affiliation(self) -> None:
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        assert "not affiliated with" in readme.lower()
        for vendor in ("Meta Platforms", "Facebook", "Instagram", "OpenAI", "Anthropic"):
            assert vendor in readme, f"{vendor} is not named in the disclaimer"

    def test_the_readme_states_the_advisory_limitation(self) -> None:
        # The safety model's honesty is the property most worth protecting.
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        assert "advisory" in readme.lower()

    def test_third_party_notices_cover_every_reimplemented_source(self) -> None:
        notices = (REPO / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        provenance = (REPO / "docs" / "research" / "provenance.md").read_text(encoding="utf-8")
        for repo in (
            "byadsco/meta-ads-mcp",
            "sepivip/meta-ads-skill",
            "Sandy-zippy/meta-ads-stack",
            "kelpi-ai/meta-ads-skills",
            "rafaelszago/meta-ads-mcp",
            "mardab96/meta-ads-skills",
            "Digitizers/meta-ads-mcp",
            "pipeboard-co/meta-ads-mcp",
            "lil-j/meta-ads-mcp",
            "itsfromgaurav/ultimate-meta-ads-skill",
        ):
            assert repo in notices, f"{repo} missing from THIRD_PARTY_NOTICES.md"
            assert repo in provenance, f"{repo} missing from provenance.md"


class TestUpstreams:
    def test_every_entry_records_what_a_review_needs(self) -> None:
        document = yaml.safe_load((REPO / "upstreams.yaml").read_text(encoding="utf-8"))
        for entry in document["upstreams"]:
            for field in ("repo", "purpose", "license", "review_date", "integration_type"):
                assert field in entry, f"{entry.get('repo')} is missing {field}"

    def test_restricted_sources_are_not_watched_or_depended_on(self) -> None:
        document = yaml.safe_load((REPO / "upstreams.yaml").read_text(encoding="utf-8"))
        for entry in document["upstreams"]:
            if entry["integration_type"] == "restricted":
                assert entry.get("watch") == "none"
                assert not entry.get("affected_areas")

    def test_the_sdk_dependency_is_not_vendored(self) -> None:
        document = yaml.safe_load((REPO / "upstreams.yaml").read_text(encoding="utf-8"))
        sdk = next(e for e in document["upstreams"] if e.get("package") == "facebook-business")
        assert sdk["vendored"] is False
