"""Windows-native Codex driven from a WSL toolchain.

The arrangement: Codex is a Windows application, its integrated terminal is
WSL2, and every runtime - Python, Node, uv, pip, npm - plus the repository
stay on the Linux side. The consequence that catches people out is that the
Codex process cannot see ``/home/you/.agents/skills``. A skills directory
that is obviously correct from the terminal is invisible to the application
reading it.

These tests run on ordinary Linux, so the Windows side is a fake: a directory
standing in for ``C:\\``, and a runner standing in for ``wslpath``,
``cmd.exe`` and ``explorer.exe``. That is a real limit and it is stated in
the documentation - what is verified here is the logic, not Microsoft's
filesystem. The alternative, code that can only be exercised on one person's
laptop, is code nobody can change safely.

No test contacts Meta, opens a real browser, or reads a credential.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

import pytest

from meta_ads_agent.errors import ConfigError
from meta_ads_agent.install import packaged
from meta_ads_agent.install.engine import apply_install, plan_install
from meta_ads_agent.install.manifest import verify_tree
from meta_ads_agent.install.state import InstallState
from meta_ads_agent.install.targets import existing_case_variant, resolve_target, resolve_under
from meta_ads_agent.install.wsl import WslBridge, looks_like_wsl, merge_codex_config

REPO = Path(__file__).resolve().parents[1]

WINDOWS_PROFILE = r"C:\Users\bartl"


@dataclass
class FakeWindows:
    """A stand-in for the Windows side of the boundary."""

    drive_root: Path
    profile: str = WINDOWS_PROFILE
    opened: list[list[str]] = field(default_factory=list)

    def to_posix(self, windows: str) -> Path:
        pure = PureWindowsPath(windows)
        return self.drive_root.joinpath(*pure.parts[1:])

    def to_windows(self, posix: str) -> str:
        relative = Path(posix).relative_to(self.drive_root)
        return str(PureWindowsPath("C:/") / relative)

    def runner(self, argv):
        argv = list(argv)
        if argv[0] == "wslpath" and argv[1] == "-w":
            return _ok(self.to_windows(argv[2]))
        if argv[0] == "wslpath" and argv[1] == "-u":
            return _ok(str(self.to_posix(argv[2])))
        if argv[0] == "cmd.exe" and "echo %USERPROFILE%" in " ".join(argv):
            # cmd.exe really does terminate with CRLF.
            return _ok(self.profile + "\r")
        if argv[0] in ("explorer.exe", "cmd.exe"):
            self.opened.append(argv)
            return _ok("")
        raise AssertionError(f"unexpected call across the boundary: {argv}")


def _ok(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout + "\n", stderr="")


@pytest.fixture
def windows(tmp_path: Path) -> FakeWindows:
    drive = tmp_path / "winfs"
    (drive / "Users" / "bartl").mkdir(parents=True)
    return FakeWindows(drive_root=drive)


@pytest.fixture
def bridge(windows: FakeWindows) -> WslBridge:
    return WslBridge(runner=windows.runner, distro="Ubuntu", available=True)


def windows_home(windows: FakeWindows) -> Path:
    return windows.drive_root / "Users" / "bartl"


def install_to_windows(windows: FakeWindows, bridge: WslBridge, **kwargs):
    target = resolve_target("windows-codex", windows_home=windows_home(windows), bridge=bridge)
    manifest = packaged.release_manifest()
    source = packaged.payload_source()
    plan = plan_install(manifest, source, target, **kwargs)
    return target, manifest, apply_install(plan, source, method="sync-windows")


# ---------------------------------------------------------------------------
class TestDetection:
    def test_wsl_is_recognised_from_the_kernel_string(self) -> None:
        assert looks_like_wsl("5.15.167.4-microsoft-standard-WSL2", env={})
        assert not looks_like_wsl("6.17.0-41-generic", env={})

    def test_wsl_is_recognised_from_the_environment(self) -> None:
        assert looks_like_wsl("6.17.0-41-generic", env={"WSL_DISTRO_NAME": "Ubuntu"})

    def test_a_missing_wslpath_is_a_configuration_fact_not_a_crash(self) -> None:
        def absent(argv):
            raise FileNotFoundError(argv[0])

        with pytest.raises(ConfigError, match="not available here"):
            WslBridge(runner=absent).to_windows("/tmp/x")


class TestPathConversion:
    def test_round_trips_through_wslpath(self, windows: FakeWindows, bridge: WslBridge) -> None:
        posix = windows_home(windows) / ".agents" / "skills"
        as_windows = bridge.to_windows(posix)
        assert as_windows == r"C:\Users\bartl\.agents\skills"
        assert bridge.to_posix(as_windows) == posix

    def test_the_windows_profile_is_asked_for_not_guessed(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        assert bridge.windows_home() == windows_home(windows)

    def test_paths_with_spaces_survive(self, tmp_path: Path) -> None:
        drive = tmp_path / "winfs"
        profile = drive / "Users" / "Bartek Borzucki"
        profile.mkdir(parents=True)
        fake = FakeWindows(drive_root=drive, profile=r"C:\Users\Bartek Borzucki")
        bridge = WslBridge(runner=fake.runner, available=True)

        assert bridge.windows_home() == profile
        target = resolve_target("windows-codex", bridge=bridge)
        assert target.root == profile / ".agents" / "skills"
        assert target.windows_path == r"C:\Users\Bartek Borzucki\.agents\skills"

        manifest = packaged.release_manifest()
        source = packaged.payload_source()
        apply_install(plan_install(manifest, source, target), source)
        assert verify_tree(manifest, target.root).complete


class TestCaseInsensitivity:
    def test_an_existing_directory_is_reused_whatever_its_case(self, tmp_path: Path) -> None:
        (tmp_path / ".Agents" / "Skills").mkdir(parents=True)
        found = resolve_under(tmp_path, Path(".agents") / "skills")
        assert found == tmp_path / ".Agents" / "Skills"

    def test_case_variants_do_not_create_a_second_installation(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        """Two spellings, one install. On Windows they are the same directory."""
        target, manifest, _ = install_to_windows(windows, bridge)
        assert target.root.name == "skills"

        # Now pretend the user asks again with the directory already spelled
        # differently, exactly as a case-preserving filesystem would hand it
        # back.
        renamed = target.root.parent / "Skills"
        target.root.rename(renamed)
        second = resolve_target("windows-codex", windows_home=windows_home(windows), bridge=bridge)
        assert second.root == renamed
        assert second.case_insensitive

        state = InstallState.load(second.root)
        assert state.version == manifest.version
        siblings = sorted(p.name for p in renamed.parent.iterdir())
        assert siblings == ["Skills"], f"a second installation appeared: {siblings}"

    def test_existing_case_variant_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert existing_case_variant(tmp_path, "nothing-here") is None


class TestNativeCodexSeesTheSkills:
    def test_every_skill_lands_in_the_windows_profile(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        target, manifest, result = install_to_windows(windows, bridge)
        assert result.verification.complete
        assert target.root == windows_home(windows) / ".agents" / "skills"
        for skill in manifest.skills:
            assert (target.root / skill / "SKILL.md").is_file(), f"{skill} not visible to Codex"
        assert len(manifest.skills) == 9

    def test_the_windows_spelling_is_reported_back(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        target, _, _ = install_to_windows(windows, bridge)
        assert target.windows_path == r"C:\Users\bartl\.agents\skills"

    def test_files_are_copied_not_symlinked(self, windows: FakeWindows, bridge: WslBridge) -> None:
        """A Windows symlink into the WSL filesystem is the fragile option."""
        target, manifest, _ = install_to_windows(windows, bridge)
        for entry in manifest.entries:
            path = target.root / entry.path
            assert not path.is_symlink(), f"{entry.path} was linked, not copied"

    def test_markdown_references_still_resolve_after_the_copy(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        target, _, _ = install_to_windows(windows, bridge)
        checker = _load_packaging_checker()
        problems = checker.check_tree(target.root, "windows-codex")
        assert problems == [], "\n".join(problems)

    def test_the_method_records_how_it_got_there(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        target, _, _ = install_to_windows(windows, bridge)
        assert InstallState.load(target.root).method == "sync-windows"


def _load_packaging_checker():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_skill_packaging", REPO / "scripts" / "check_skill_packaging.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestNothingLandsOnWindows:
    """The Windows side gets Markdown and data. No runtimes, no packages."""

    ALLOWED_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".txt", ".py"}

    def test_the_payload_is_documentation_and_data(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        target, _, _ = install_to_windows(windows, bridge)
        unexpected = [
            path.relative_to(target.root).as_posix()
            for path in target.root.rglob("*")
            if path.is_file() and path.suffix not in self.ALLOWED_SUFFIXES
        ]
        assert unexpected == [], f"non-payload files copied to Windows: {unexpected}"

    def test_no_package_manager_artefacts_are_created(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        install_to_windows(windows, bridge)
        forbidden = ["node_modules", "site-packages", ".venv", "__pycache__", "pyvenv.cfg"]
        found = [
            str(path.relative_to(windows.drive_root))
            for path in windows.drive_root.rglob("*")
            if path.name in forbidden
        ]
        assert found == [], f"a runtime was installed on Windows: {found}"

    def test_the_installer_only_ever_calls_path_tools_across_the_boundary(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        """Whatever crosses to Windows must not be a package manager."""
        calls: list[list[str]] = []

        def recording(argv):
            calls.append(list(argv))
            return windows.runner(argv)

        recorder = WslBridge(runner=recording, available=True)
        install_to_windows(windows, recorder)
        binaries = {call[0] for call in calls}
        assert binaries <= {"wslpath", "cmd.exe"}, binaries
        assert not any(b in binaries for b in ("pip", "npm", "node", "python", "uv"))


class TestUserFilesOnWindows:
    def test_the_local_connection_note_is_never_touched(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        """Account and app details live outside the repository, and stay there."""
        local_context = windows_home(windows) / ".codex" / "local-context"
        local_context.mkdir(parents=True)
        note = local_context / "meta-ads-connection.md"
        original = "# Connection\n\nApp ID: <private>\nAd account: <private>\n"
        note.write_text(original, encoding="utf-8")
        before = note.stat().st_mtime_ns

        install_to_windows(windows, bridge)

        assert note.read_text(encoding="utf-8") == original
        assert note.stat().st_mtime_ns == before

    def test_unrelated_skills_in_the_windows_directory_survive(
        self, windows: FakeWindows, bridge: WslBridge
    ) -> None:
        skills = windows_home(windows) / ".agents" / "skills"
        other = skills / "someone-elses"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("---\nname: someone-elses\n---\n", encoding="utf-8")

        install_to_windows(windows, bridge)
        assert (other / "SKILL.md").is_file()

    def test_the_note_is_not_in_the_repository(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout
        assert "meta-ads-connection" not in tracked


class TestCodexConfigMerge:
    EXISTING = """\
model = "gpt-5-codex"
approval_policy = "on-request"

# my own server, do not touch
[mcp_servers.nx-mcp]
command = "npx"
args = ["nx", "mcp"]
"""

    def test_an_absent_block_is_appended_and_nothing_else_changes(self) -> None:
        updated, changed = merge_codex_config(
            self.EXISTING, server="meta-ads", url="https://mcp.facebook.com/ads", client_id="123"
        )
        assert changed
        assert self.EXISTING in updated
        assert "[mcp_servers.meta-ads]" in updated
        assert 'client_id = "123"' in updated

    def test_an_existing_block_is_replaced_in_place(self) -> None:
        first, _ = merge_codex_config(
            self.EXISTING, server="meta-ads", url="https://mcp.facebook.com/ads", client_id="111"
        )
        second, changed = merge_codex_config(
            first, server="meta-ads", url="https://mcp.facebook.com/ads", client_id="222"
        )
        assert changed
        assert second.count("[mcp_servers.meta-ads]") == 1
        assert 'client_id = "222"' in second
        assert 'client_id = "111"' not in second

    def test_other_servers_and_comments_are_preserved_exactly(self) -> None:
        updated, _ = merge_codex_config(
            self.EXISTING, server="meta-ads", url="https://mcp.facebook.com/ads", client_id="1"
        )
        assert "# my own server, do not touch" in updated
        assert "[mcp_servers.nx-mcp]" in updated
        assert 'args = ["nx", "mcp"]' in updated
        assert 'model = "gpt-5-codex"' in updated

    def test_rewriting_the_same_block_twice_is_a_no_op(self) -> None:
        once, _ = merge_codex_config(
            self.EXISTING, server="meta-ads", url="https://mcp.facebook.com/ads", client_id="1"
        )
        twice, changed = merge_codex_config(
            once, server="meta-ads", url="https://mcp.facebook.com/ads", client_id="1"
        )
        assert not changed
        assert twice == once

    def test_the_result_is_still_valid_toml(self) -> None:
        import tomllib

        updated, _ = merge_codex_config(
            self.EXISTING, server="meta-ads", url="https://mcp.facebook.com/ads", client_id="9"
        )
        parsed = tomllib.loads(updated)
        assert parsed["mcp_servers"]["meta-ads"]["url"] == "https://mcp.facebook.com/ads"
        assert parsed["mcp_servers"]["meta-ads"]["oauth"]["client_id"] == "9"
        assert parsed["mcp_servers"]["nx-mcp"]["command"] == "npx"
        assert parsed["model"] == "gpt-5-codex"

    def test_an_empty_file_gets_just_the_block(self) -> None:
        updated, changed = merge_codex_config(
            "", server="meta-ads", url="https://mcp.facebook.com/ads", client_id=None
        )
        assert changed
        assert updated.startswith("#")
        assert "oauth" not in updated


class TestOAuthOpensWindowsChrome:
    def test_the_url_goes_to_explorer_exe(
        self, windows: FakeWindows, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "meta_ads_agent.install.wsl.shutil.which",
            lambda name: "/mnt/c/Windows/explorer.exe" if name == "explorer.exe" else None,
        )
        bridge = WslBridge(runner=windows.runner, available=True)
        bridge.open_url("https://www.facebook.com/v23.0/dialog/oauth?client_id=1")
        assert windows.opened and windows.opened[0][0] == "explorer.exe"

    def test_there_is_no_linux_browser_fallback(
        self, windows: FakeWindows, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A browser inside WSL has a different profile; the redirect dies."""
        monkeypatch.setattr("meta_ads_agent.install.wsl.shutil.which", lambda name: None)
        bridge = WslBridge(runner=windows.runner, available=True)
        with pytest.raises(ConfigError) as error:
            bridge.open_url("https://www.facebook.com/dialog/oauth")
        assert "not used as a fallback" in str(error.value)
        assert windows.opened == []

    def test_only_https_urls_are_opened(self, windows: FakeWindows) -> None:
        bridge = WslBridge(runner=windows.runner, available=True)
        for hostile in ("file:///etc/passwd", "http://example.com", 'https://x" && calc'):
            with pytest.raises(ConfigError, match="refusing to open"):
                bridge.open_url(hostile)


class TestCommandsRunThroughWsl:
    """What Codex on Windows invokes is ``wsl.exe -- <command>``.

    The Windows side runs nothing itself, so the only thing that can be
    checked here is that the command on the far end works when started as a
    fresh process with no inherited environment - which is exactly what
    crossing the boundary does to it.
    """

    def _run(self, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-m", "meta_ads_agent", *args],
            cwd=cwd,
            env={"PATH": "/usr/bin:/bin", "HOME": str(cwd), "PYTHONPATH": str(REPO / "src")},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_doctor_runs_as_a_bare_subprocess(self, tmp_path: Path) -> None:
        result = self._run("doctor", "--json", cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["installation"]["status"] in {
            "not-installed",
            "complete",
            "update-available",
            "migration-required",
        }

    def test_the_skill_validator_runs_as_a_bare_subprocess(self, tmp_path: Path) -> None:
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(REPO / "scripts" / "check_skill_packaging.py")],
            cwd=REPO,
            env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_install_runs_as_a_bare_subprocess(self, tmp_path: Path) -> None:
        result = self._run(
            "install",
            "--target",
            "path",
            "--path",
            str(tmp_path / "skills"),
            "--json",
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["action"] == "install"
