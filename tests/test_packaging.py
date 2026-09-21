"""Packaging: what survives being installed the way an agent host installs it.

Everything in this repository resolves from a checkout, which is exactly why
the skills drifted into depending on one. A host does not hand an agent the
repository - it hands it a skill directory, sometimes the whole ``skills/``
tree and sometimes a single ``meta-ads-*`` folder copied out of it. These
tests copy the skills out first and only then ask whether they still work.

The second half covers the other thing a checkout hides: the optional
``meta-ads-agent`` CLI is installed here and absent almost everywhere else.
A skill that assumes it exists sends the user after a command they do not
have, so the skills must check, and what they do when the answer is "no" is
asserted here too.

No test in this file contacts Meta, and none needs credentials.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
SKILL_NAMES = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))

# Skills whose whole job is reading. None of them may need the CLI, because
# the MCP covers every tool they use and a user who only wants a report
# should never be told to install a Python package.
READ_ONLY_SKILLS = ("meta-ads-audit", "meta-ads-report", "meta-ads-research")

GIT_SPEC = "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git"


def _load(name: str) -> Any:
    """Import a repo script as a module, so tests can use its pieces."""
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


packaging = _load("check_skill_packaging")


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, repo-local script
        [sys.executable, str(REPO / "scripts" / name), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def install(skill: str, into: Path) -> Path:
    """Copy one skill directory out, the way an installer would."""
    into.mkdir(parents=True, exist_ok=True)
    destination = into / skill
    shutil.copytree(SKILLS / skill, destination)
    return destination


class TestStandaloneInstall:
    """A single ``skills/meta-ads-*`` directory has to be complete on its own."""

    def test_the_packaging_check_passes(self) -> None:
        result = run_script("check_skill_packaging.py")
        assert result.returncode == 0, result.stdout + result.stderr

    @pytest.mark.parametrize("skill", SKILL_NAMES)
    def test_every_reference_resolves_inside_the_installed_skill(
        self, skill: str, tmp_path: Path
    ) -> None:
        root = tmp_path / "agents-skills"
        install(skill, root)
        problems = packaging.check_tree(root, "standalone")
        assert problems == [], "\n".join(problems)

    @pytest.mark.parametrize("skill", SKILL_NAMES)
    def test_an_installed_skill_carries_its_own_references_and_assets(
        self, skill: str, tmp_path: Path
    ) -> None:
        installed = install(skill, tmp_path / "agents-skills")
        assert (installed / "SKILL.md").is_file()
        # Whatever the repository has under the skill must arrive with it.
        for relative in sorted(
            p.relative_to(SKILLS / skill) for p in (SKILLS / skill).rglob("*") if p.is_file()
        ):
            assert (installed / relative).is_file(), f"{skill}: {relative} did not install"

    def test_the_whole_skills_tree_also_resolves(self, tmp_path: Path) -> None:
        tree = tmp_path / "skills"
        shutil.copytree(SKILLS, tree)
        problems = packaging.check_tree(tree, "full tree")
        assert problems == [], "\n".join(problems)

    def test_the_check_would_notice_a_reference_that_escapes_the_skill(
        self, tmp_path: Path
    ) -> None:
        """A guard nobody has seen fail is a guard nobody should trust."""
        installed = install("meta-ads-core", tmp_path / "agents-skills")
        skill_md = installed / "SKILL.md"
        skill_md.write_text(
            skill_md.read_text(encoding="utf-8") + "\nSee `docs/getting-started/whatever.md`.\n",
            encoding="utf-8",
        )
        problems = packaging.check_tree(tmp_path / "agents-skills", "standalone")
        assert any("whatever.md" in problem for problem in problems), problems

    def test_the_check_would_notice_a_missing_asset(self, tmp_path: Path) -> None:
        installed = install("meta-ads-campaign", tmp_path / "agents-skills")
        (installed / "assets" / "campaign-plan.yaml").unlink()
        problems = packaging.check_tree(tmp_path / "agents-skills", "standalone")
        assert any("campaign-plan.yaml" in problem for problem in problems), problems


class TestSharedBlocks:
    """The duplicated passages are generated, so they cannot drift apart."""

    def test_the_shared_blocks_are_in_sync(self) -> None:
        result = run_script("sync_skill_blocks.py", "--check")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_the_sync_script_notices_an_edited_copy(self, tmp_path: Path) -> None:
        sync = _load("sync_skill_blocks")
        pattern = sync.block_pattern("preflight")
        text = (SKILLS / "meta-ads-report" / "SKILL.md").read_text(encoding="utf-8")
        match = pattern.search(text)
        assert match, "the preflight block should be findable in meta-ads-report"
        tampered = (
            text[: match.start()]
            + sync.rendered("preflight", "edited by hand")
            + text[match.end() :]
        )
        assert tampered != text

    @pytest.mark.parametrize("skill", SKILL_NAMES)
    def test_every_skill_carries_the_preflight_block(self, skill: str) -> None:
        text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
        assert "<!-- shared:preflight start" in text
        assert "meta-ads-agent --version" in text, f"{skill}: no CLI probe"
        assert "ads_" in text, f"{skill}: no MCP check"


class TestCliAvailability:
    """Present and absent are both normal. Neither may surprise a user."""

    @pytest.mark.parametrize("skill", SKILL_NAMES)
    def test_every_command_a_skill_names_actually_exists(self, skill: str) -> None:
        problems = [p for p in packaging.check_cli_mentions() if f"skills/{skill}/" in p]
        assert problems == [], "\n".join(problems)

    @pytest.mark.parametrize("skill", SKILL_NAMES)
    def test_no_skill_suggests_a_command_before_saying_to_check_for_it(self, skill: str) -> None:
        """Order matters: the probe has to be read before the suggestion."""
        text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
        probe = text.index("meta-ads-agent --version")
        early = [
            match.group(0)
            for match in packaging.CLI_MENTION.finditer(text)
            if match.start() < probe
        ]
        assert early == [], f"{skill}: {early} appears before the availability probe"

    @pytest.mark.parametrize("skill", READ_ONLY_SKILLS)
    def test_read_only_skills_need_no_cli_at_all(self, skill: str) -> None:
        text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
        mentions = sorted({m.group(0) for m in packaging.CLI_MENTION.finditer(text)})
        assert mentions == [], f"{skill} should work with the MCP alone: {mentions}"

    @pytest.mark.parametrize("skill", ("meta-ads-core", "meta-ads-campaign"))
    def test_the_writing_skills_stop_before_writing_when_the_cli_is_absent(
        self, skill: str
    ) -> None:
        text = " ".join((SKILLS / skill / "SKILL.md").read_text(encoding="utf-8").split())
        assert "stop before the first write" in text
        assert "Do not create objects and validate afterwards" in text
        # And it must be a fork in the road, not a dead end.
        assert "uvx --from" in text
        assert "uv tool install" in text
        assert "Ads Manager" in text

    def test_the_documented_no_install_route_matches_this_package(self) -> None:
        """``uvx --from <spec> meta-ads-agent`` only works if both halves are right."""
        block = (REPO / "packaging" / "shared" / "no-cli-writes.md").read_text(encoding="utf-8")
        pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
        entry_points = pyproject["project"]["scripts"]
        assert "meta-ads-agent" in entry_points
        assert GIT_SPEC in block
        homepage = pyproject["project"]["urls"]["Homepage"]
        assert f"git+{homepage}.git" == GIT_SPEC
        for command in ("validate-plan", "doctor"):
            assert command in block

    def test_an_absent_cli_is_detectable_without_running_anything(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PATH", str(tmp_path))
        assert shutil.which("meta-ads-agent") is None


def doctor(home: Path, cwd: Path) -> dict[str, Any]:
    """Run ``doctor`` in a controlled HOME so its findings are deterministic."""
    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PYTHONPATH": str(REPO / "src"),
    }
    for name in ("META_ACCESS_TOKEN", "META_APP_ID", "META_APP_SECRET", "META_ADS_WORKSPACE"):
        env.pop(name, None)
    result = subprocess.run(
        [sys.executable, "-m", "meta_ads_agent", "doctor", "--json"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


class TestMcpAvailability:
    """The MCP check and the CLI check are separate, and doctor keeps them so."""

    def test_no_host_config_means_the_mcp_reads_as_missing(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        payload = doctor(home, tmp_path)
        check = next(c for c in payload["checks"] if c["label"] == "Meta Ads MCP configured")
        assert check["status"] == "MISSING"
        assert "mcp.facebook.com/ads" in (check["fix"] or "")

    def test_a_configured_host_flips_it_to_ready(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        (home / ".codex").mkdir(parents=True)
        (home / ".codex" / "config.toml").write_text(
            '[mcp_servers.meta-ads]\nurl = "https://mcp.facebook.com/ads"\n', encoding="utf-8"
        )
        payload = doctor(home, tmp_path)
        check = next(c for c in payload["checks"] if c["label"] == "Meta Ads MCP configured")
        assert check["status"] == "READY"

    def test_a_missing_fallback_is_never_a_failure(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        payload = doctor(home, tmp_path)
        assert payload["api_fallback_ready"] is False
        assert [c for c in payload["checks"] if c["status"] == "FAIL"] == []


class TestBundledTemplates:
    """One copy of each template, in the skill, reachable from both consumers."""

    def test_the_wheel_takes_its_templates_from_the_skill(self) -> None:
        pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
        include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
        assert include["skills/meta-ads-core/assets"] == "meta_ads_agent/_data/templates"

    def test_init_finds_every_template_in_a_source_checkout(self) -> None:
        from meta_ads_agent.cli.init_cmd import _TEMPLATE_FILES, template_root

        root = template_root()
        for source, _target in _TEMPLATE_FILES:
            assert (root / source).is_file(), f"{source} missing from {root}"

    def test_the_templates_live_in_exactly_one_place(self) -> None:
        assert not (REPO / "templates").exists(), (
            "templates/ is back. The originals belong inside the skill that "
            "documents them, or a standalone install loses them."
        )
        for name in ("brand.yaml", "voice.md", "account.yaml", "offer.yaml"):
            assert (SKILLS / "meta-ads-core" / "assets" / name).is_file()
        assert (SKILLS / "meta-ads-campaign" / "assets" / "campaign-plan.yaml").is_file()
