"""Where the skills go, and how to find an install that is already there.

Three destinations are supported, and they are genuinely different places
rather than three names for one:

``agents``
    ``~/.agents/skills`` on the machine the CLI runs on. The normal case.
``windows-codex``
    ``%USERPROFILE%\\.agents\\skills``, reached from inside WSL. The Codex
    application is a Windows process and does not see the Linux home
    directory, so a "skills directory" that means ``/home/you/.agents/skills``
    is invisible to it no matter how correct it looks from the terminal.
``path``
    An explicit directory, for a repository-scoped ``.agents/skills`` or a
    test.

Files are copied, not symlinked, when the destination is on Windows. A
Windows symlink into the WSL filesystem needs Developer Mode or an elevated
shell to create, breaks when the distribution is not running, and resolves
through a 9P file server that the Codex process may or may not reach. Copying
is boring, and boring is the correct property for the thing that decides
whether the skills load at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meta_ads_agent.errors import ConfigError
from meta_ads_agent.install.wsl import WslBridge, looks_like_wsl

AGENTS_SKILLS = Path(".agents") / "skills"

TARGET_KINDS = ("agents", "windows-codex", "path")


def existing_case_variant(parent: Path, name: str) -> Path | None:
    """Find ``name`` under ``parent`` ignoring case, if the filesystem did.

    Windows filesystems are case-insensitive but case-preserving, and a WSL
    mount of one behaves the same way. Resolving ``.agents`` against an
    existing ``.Agents`` rather than creating a sibling is what stops a second
    installation appearing next to the first, each half-updated and neither
    obviously wrong.
    """
    if not parent.is_dir():
        return None
    exact = parent / name
    if exact.exists():
        return exact
    folded = name.casefold()
    for child in parent.iterdir():
        if child.name.casefold() == folded:
            return child
    return None


def resolve_under(base: Path, relative: Path) -> Path:
    """Join, reusing any component that already exists in a different case."""
    current = base
    for part in relative.parts:
        found = existing_case_variant(current, part)
        current = found if found is not None else current / part
    return current


@dataclass(frozen=True, slots=True)
class InstallTarget:
    """A resolved destination for the payload."""

    root: Path
    kind: str
    label: str
    case_insensitive: bool = False
    windows_path: str | None = None

    @property
    def is_windows(self) -> bool:
        return self.kind == "windows-codex"

    def describe(self) -> str:
        if self.windows_path:
            return f"{self.label}: {self.windows_path}  (WSL: {self.root})"
        return f"{self.label}: {self.root}"

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "root": str(self.root),
            "windows_path": self.windows_path,
            "case_insensitive": self.case_insensitive,
        }


def resolve_target(
    kind: str = "agents",
    *,
    path: str | Path | None = None,
    home: Path | None = None,
    bridge: WslBridge | None = None,
    windows_home: str | Path | None = None,
) -> InstallTarget:
    """Work out where to install, without creating anything."""
    if kind not in TARGET_KINDS:
        raise ConfigError(f"unknown install target {kind!r}; expected one of {TARGET_KINDS}")

    if kind == "path":
        if not path:
            raise ConfigError("--target path needs --path")
        root = Path(path).expanduser()
        return InstallTarget(root=root, kind="path", label="explicit path")

    if kind == "agents":
        base = Path(home).expanduser() if home else Path.home()
        return InstallTarget(
            root=resolve_under(base, AGENTS_SKILLS), kind="agents", label="skills directory"
        )

    # windows-codex
    resolved_bridge = bridge or WslBridge.detect()
    if windows_home is not None:
        profile = Path(windows_home).expanduser()
    else:
        if not resolved_bridge.available and not looks_like_wsl():
            raise ConfigError(
                "--target windows-codex only works from inside WSL, because it "
                "installs into the Windows user profile that the native Codex "
                "application reads. Pass --windows-home to override the "
                "detection if you know what you are doing."
            )
        profile = resolved_bridge.windows_home()

    if not profile.is_dir():
        raise ConfigError(
            f"{profile} is not a directory. That should be your Windows user "
            "profile seen from WSL - check that the drive is mounted, or pass "
            "--windows-home explicitly."
        )

    root = resolve_under(profile, AGENTS_SKILLS)
    windows_path: str | None = None
    try:
        windows_path = resolved_bridge.to_windows(root)
    except ConfigError:
        # wslpath is absent or refused; the POSIX path is still correct and
        # the Windows spelling is only for the message we print.
        windows_path = None

    return InstallTarget(
        root=root,
        kind="windows-codex",
        label="Windows Codex skills",
        case_insensitive=True,
        windows_path=windows_path,
    )
