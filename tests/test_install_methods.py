"""Every supported install method, and the skew between components.

Three destinations are supported and they are genuinely different places, so
"it works on mine" proves one of them. The version-skew tests cover the other
half of the same problem: an installation can be internally consistent and
still be running a payload that does not match the CLI that installed it.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from meta_ads_agent import __version__
from meta_ads_agent.cli.install_cmd import installation_report
from meta_ads_agent.cli.main import main
from meta_ads_agent.install import packaged
from meta_ads_agent.install.engine import apply_install, plan_install
from meta_ads_agent.install.manifest import build_manifest, verify_tree
from meta_ads_agent.install.state import InstallState
from meta_ads_agent.install.targets import resolve_target
from meta_ads_agent.install.wsl import WslBridge
from test_windows_wsl import FakeWindows

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("META_ACCESS_TOKEN", "META_APP_SECRET", "META_ADS_WORKSPACE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def _windows_bridge(tmp_path: Path) -> tuple[FakeWindows, WslBridge, Path]:
    drive = tmp_path / "winfs"
    profile = drive / "Users" / "bartl"
    profile.mkdir(parents=True)
    fake = FakeWindows(drive_root=drive)
    return fake, WslBridge(runner=fake.runner, available=True), profile


class TestEverySupportedMethod:
    """Install, then upgrade, through each destination the docs promise."""

    def _cycle(self, target) -> None:
        manifest = packaged.release_manifest()
        source = packaged.payload_source()

        first = apply_install(plan_install(manifest, source, target), source)
        assert first.plan.action == "install"
        assert first.verification.complete

        # A stale file from an imaginary older release, then an upgrade.
        stale = target.root / "meta-ads-core" / "references" / "from-an-older-release.md"
        stale.write_text("# old\n", encoding="utf-8")
        (target.root / "meta-ads-core" / "SKILL.md").write_text("tampered\n", encoding="utf-8")

        second = apply_install(plan_install(manifest, source, target), source)
        assert second.verification.complete
        assert not stale.exists(), "an orphan survived the upgrade"
        assert InstallState.load(target.root).version == manifest.version

    def test_explicit_path(self, tmp_path: Path) -> None:
        self._cycle(resolve_target("path", path=tmp_path / "skills"))

    def test_the_agents_skills_directory(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        target = resolve_target("agents", home=home)
        assert target.root == home / ".agents" / "skills"
        self._cycle(target)

    def test_a_repository_scoped_skills_directory(self, tmp_path: Path) -> None:
        self._cycle(resolve_target("path", path=tmp_path / "repo" / ".agents" / "skills"))

    def test_the_windows_codex_profile(self, tmp_path: Path) -> None:
        _fake, bridge, profile = _windows_bridge(tmp_path)
        self._cycle(resolve_target("windows-codex", windows_home=profile, bridge=bridge))

    def test_a_development_symlink_is_not_clobbered_by_a_path_install(self, tmp_path: Path) -> None:
        """A symlinked skill belongs to the developer who made it."""
        skills = tmp_path / "skills"
        skills.mkdir()
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        (checkout / "SKILL.md").write_text("---\nname: my-own-skill\n---\n", encoding="utf-8")
        link = skills / "my-own-skill"
        link.symlink_to(checkout, target_is_directory=True)

        target = resolve_target("path", path=skills)
        manifest = packaged.release_manifest()
        apply_install(
            plan_install(manifest, packaged.payload_source(), target), packaged.payload_source()
        )

        assert link.is_symlink()
        assert link.resolve() == checkout.resolve()


class TestVersionSkew:
    def test_a_current_installation_reports_complete(self, tmp_path: Path) -> None:
        target = resolve_target("path", path=tmp_path / "skills")
        source = packaged.payload_source()
        manifest = packaged.release_manifest()
        apply_install(plan_install(manifest, source, target), source)

        report = installation_report(target_kind="path", path=str(target.root))
        assert report["status"] == "complete"
        assert report["installed_version"] == __version__

    def test_an_older_installed_version_reports_an_update(self, tmp_path: Path) -> None:
        target = resolve_target("path", path=tmp_path / "skills")
        source = packaged.payload_source()
        apply_install(plan_install(packaged.release_manifest(), source, target), source)

        state = InstallState.load(target.root)
        state.version = "0.0.9"
        state.save()

        report = installation_report(target_kind="path", path=str(target.root))
        assert report["status"] == "update-available"
        assert "0.0.9" in report["detail"]
        assert report["fix"] == "meta-ads-agent upgrade"

    def test_a_damaged_installation_reports_broken(self, tmp_path: Path) -> None:
        target = resolve_target("path", path=tmp_path / "skills")
        source = packaged.payload_source()
        apply_install(plan_install(packaged.release_manifest(), source, target), source)
        (target.root / "meta-ads-report" / "SKILL.md").unlink()

        report = installation_report(target_kind="path", path=str(target.root))
        assert report["status"] == "broken"
        assert "--force" in report["fix"]

    def test_an_interrupted_update_reports_interrupted(self, tmp_path: Path) -> None:
        target = resolve_target("path", path=tmp_path / "skills")
        source = packaged.payload_source()
        apply_install(plan_install(packaged.release_manifest(), source, target), source)

        state = InstallState.load(target.root)
        state.begin(to_version="0.9.0", stage="swap")

        report = installation_report(target_kind="path", path=str(target.root))
        assert report["status"] == "interrupted"
        assert "swap" in report["detail"]

    def test_an_empty_target_reports_not_installed(self, tmp_path: Path) -> None:
        report = installation_report(target_kind="path", path=str(tmp_path / "nothing"))
        assert report["status"] == "not-installed"
        assert report["fix"] == "meta-ads-agent install"

    def test_the_plugin_manifests_agree_with_the_package(self) -> None:
        for relative in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            manifest = json.loads((REPO / relative).read_text(encoding="utf-8"))
            assert manifest["version"] == __version__, relative

    def test_pyproject_agrees_with_the_package(self) -> None:
        pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
        assert pyproject["project"]["version"] == __version__

    def test_the_release_manifest_agrees_with_the_package(self) -> None:
        assert packaged.release_manifest().version == __version__

    def test_doctor_surfaces_the_installation_status(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["doctor", "--json"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["installation"]["status"] in {
            "not-installed",
            "complete",
            "update-available",
            "migration-required",
            "broken",
        }
        assert any(c["label"] == "version skew" for c in payload["checks"])


class TestCliSurface:
    def test_install_is_idempotent_from_the_command_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = ["install", "--target", "path", "--path", str(tmp_path / "skills"), "--json"]
        assert main(argv) == 0
        first = json.loads(capsys.readouterr().out)
        assert first["action"] == "install"

        assert main(argv) == 0
        second = json.loads(capsys.readouterr().out)
        assert second["action"] == "up-to-date"
        assert second["added"] == [] and second["updated"] == []

    def test_a_dry_run_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        skills = tmp_path / "skills"
        code = main(["install", "--target", "path", "--path", str(skills), "--dry-run", "--json"])
        assert code == 0
        assert json.loads(capsys.readouterr().out)["action"] == "install"
        assert not skills.exists() or not any(skills.iterdir())

    def test_upgrade_runs_the_workspace_migrations_too(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from meta_ads_agent.workspace import Workspace

        workspace = Workspace.at(tmp_path / ".meta-ads")
        workspace.create()
        (workspace.root / ".gitignore").unlink()

        code = main(
            [
                "upgrade",
                "--target",
                "path",
                "--path",
                str(tmp_path / "skills"),
                "--workspace",
                str(workspace.root),
                "--json",
            ]
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert "0001-workspace-gitignore" in payload["migrations"]["applied"]
        assert payload["action"] == "install"
        assert (workspace.root / ".gitignore").is_file()

    def test_rollback_from_the_command_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        skills = tmp_path / "skills"
        target = resolve_target("path", path=skills)
        source = packaged.payload_source()
        manifest = packaged.release_manifest()
        apply_install(plan_install(manifest, source, target), source)

        # A second install takes a backup; then roll it back.
        (skills / "meta-ads-core" / "SKILL.md").write_text("broken\n", encoding="utf-8")
        apply_install(plan_install(manifest, source, target), source)

        code = main(["upgrade", "--target", "path", "--path", str(skills), "--rollback", "--json"])
        assert code == 0
        restored = json.loads(capsys.readouterr().out)
        assert Path(restored["rolled_back_to"]).is_dir()
        assert verify_tree(manifest, skills).missing == []

    def test_mcp_config_only_touches_its_own_block(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = tmp_path / "config.toml"
        config.write_text('model = "gpt-5-codex"\n', encoding="utf-8")
        code = main(["mcp-config", "--config", str(config), "--client-id", "42", "--json"])
        assert code == 0
        assert json.loads(capsys.readouterr().out)["changed"] is True

        parsed = tomllib.loads(config.read_text(encoding="utf-8"))
        assert parsed["model"] == "gpt-5-codex"
        assert parsed["mcp_servers"]["meta-ads"]["oauth"]["client_id"] == "42"

        assert main(["mcp-config", "--config", str(config), "--client-id", "42", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["changed"] is False

    def test_open_url_refuses_when_there_is_no_windows_browser(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("meta_ads_agent.install.wsl.shutil.which", lambda name: None)
        code = main(["open-url", "https://example.com/oauth", "--json"])
        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["opened"] is False
        assert "fallback" in payload["error"]


class TestWheelCarriesThePayload:
    """One install command only works if the wheel has the skills in it."""

    def test_the_build_maps_the_payload_into_the_package(self) -> None:
        pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
        include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
        assert include["skills"] == "meta_ads_agent/_data/skills"
        assert include["release-manifest.json"] == "meta_ads_agent/_data/release-manifest.json"

    def test_the_source_checkout_resolves_the_payload(self) -> None:
        source = packaged.payload_source()
        assert (source / "meta-ads-core" / "SKILL.md").is_file()

    def test_the_manifest_describes_the_payload_it_ships_with(self) -> None:
        manifest = packaged.release_manifest()
        assert verify_tree(manifest, packaged.payload_source()).complete

    def test_rebuilding_the_manifest_from_the_payload_gives_the_same_digest(
        self, tmp_path: Path
    ) -> None:
        import shutil

        base = tmp_path / "copy"
        shutil.copytree(packaged.payload_source(), base / "skills")
        rebuilt = build_manifest(base, __version__)
        assert rebuilt.digest == packaged.release_manifest().digest
