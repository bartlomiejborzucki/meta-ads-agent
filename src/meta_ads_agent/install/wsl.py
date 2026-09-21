"""The Windows boundary, for a native Codex app driven from a WSL toolchain.

The arrangement this supports: Codex runs as a Windows application, its
integrated terminal runs WSL2, and every language runtime - Python, Node, uv,
pip, npm - and the repository itself stay on the Linux side. Nothing in this
module installs anything on Windows. It converts paths, copies files across
the boundary, edits one block of one Windows config file, and hands a URL to
the browser the user is already signed into.

Every call out to Windows goes through :class:`WslBridge`, which takes its
subprocess runner as a parameter. That is not ceremony: without it none of
this could be tested anywhere except on a Windows machine with WSL, and code
that can only be tested on one person's laptop is code nobody can change.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from meta_ads_agent.errors import ConfigError

OSRELEASE = Path("/proc/sys/kernel/osrelease")

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _default_runner(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    # cwd matters: cmd.exe warns and falls back to C:\Windows when the working
    # directory is a UNC path, which every WSL path is from its point of view.
    cwd = "/mnt/c" if Path("/mnt/c").is_dir() else None
    return subprocess.run(  # noqa: S603 - fixed argv built from known binaries
        list(argv), capture_output=True, text=True, timeout=30, check=False, cwd=cwd
    )


def looks_like_wsl(osrelease_text: str | None = None, env: dict[str, str] | None = None) -> bool:
    """True inside WSL, by either of the two signals Microsoft actually sets."""
    environment = os.environ if env is None else env
    if environment.get("WSL_DISTRO_NAME") or environment.get("WSL_INTEROP"):
        return True
    if osrelease_text is None:
        try:
            osrelease_text = OSRELEASE.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
    lowered = osrelease_text.lower()
    return "microsoft" in lowered or "wsl" in lowered


@dataclass(slots=True)
class WslBridge:
    """Path conversion and Windows hand-offs, with the boundary injectable."""

    runner: Runner = _default_runner
    distro: str | None = None
    available: bool = True

    @classmethod
    def detect(cls, *, runner: Runner | None = None) -> WslBridge:
        return cls(
            runner=runner or _default_runner,
            distro=os.environ.get("WSL_DISTRO_NAME"),
            available=looks_like_wsl(),
        )

    def _run(self, argv: Sequence[str]) -> str:
        try:
            result = self.runner(argv)
        except OSError as exc:
            # Not on Windows, or the interop binaries are not on PATH. A
            # missing wslpath is a configuration fact, not a crash.
            raise ConfigError(f"{argv[0]} is not available here: {exc}") from exc
        if result.returncode != 0:
            raise ConfigError(
                f"{argv[0]} failed ({result.returncode}): "
                f"{(result.stderr or result.stdout or '').strip()}"
            )
        # cmd.exe terminates lines with CRLF and echoes a trailing newline.
        return (result.stdout or "").strip().strip("\r")

    # -- paths -------------------------------------------------------------
    def to_windows(self, path: Path | str) -> str:
        """POSIX path -> Windows path, via ``wslpath -w``."""
        return self._run(["wslpath", "-w", str(path)])

    def to_posix(self, path: str) -> Path:
        """Windows path -> POSIX path, via ``wslpath -u``."""
        return Path(self._run(["wslpath", "-u", str(path)]))

    def windows_home(self) -> Path:
        """The POSIX path of ``%USERPROFILE%``.

        Asked of Windows rather than guessed. ``/mnt/c/Users/<login>`` is
        wrong often enough - redirected profiles, a different drive, a
        Microsoft account login that does not match the folder name - that
        guessing it would be the first thing to break.
        """
        raw = self._run(["cmd.exe", "/c", "echo %USERPROFILE%"])
        if not raw or "%USERPROFILE%" in raw:
            raise ConfigError(
                "could not read %USERPROFILE% from Windows. Pass --windows-home "
                "with the POSIX path of your Windows user directory, for example "
                "--windows-home /mnt/c/Users/you"
            )
        return self.to_posix(raw)

    # -- browser -----------------------------------------------------------
    def open_url(self, url: str) -> None:
        """Open a URL in the Windows browser the user is already signed into.

        Deliberately no Linux fallback. A browser launched inside WSL has its
        own empty profile, so the OAuth round trip would ask the user to sign
        in to Facebook again in a window that is not the one holding their
        session - and the redirect would land in the wrong place. Failing with
        the URL printed is more useful than succeeding into the wrong browser.
        """
        if not re.match(r"^https://[^\s\"'<>]+$", url):
            raise ConfigError(f"refusing to open {url!r}: only https URLs are opened")
        for argv in (["explorer.exe", url], ["cmd.exe", "/c", "start", "", url]):
            if shutil.which(argv[0]) is None:
                continue
            # explorer.exe returns 1 on success often enough that its exit
            # code cannot be trusted; absence of an exception is the signal.
            try:
                self.runner(argv)
                return
            except OSError:  # pragma: no cover - which() said it was there
                continue
        raise ConfigError(
            "no Windows browser launcher found (tried explorer.exe and cmd.exe). "
            f"Open this URL in your Windows browser by hand:\n    {url}\n"
            "A browser started inside WSL is not used as a fallback: it has a "
            "different profile and the OAuth redirect would not reach it."
        )


# ---------------------------------------------------------------------------
# Windows Codex configuration
# ---------------------------------------------------------------------------

# The managed region is fenced. Without the fence the second write finds only
# the table header, leaves the comment lines the first write added, and
# duplicates them - which is how a config file grows a paragraph of our
# comments every time somebody re-runs the installer.
BEGIN_MARK = "# >>> meta-ads-agent managed block - do not edit inside >>>"
END_MARK = "# <<< meta-ads-agent managed block <<<"


def render_mcp_block(*, server: str, url: str, client_id: str | None) -> str:
    lines = [
        BEGIN_MARK,
        "# Only this block is managed. Everything else in this file is yours",
        "# and is left exactly as it was.",
        f"[mcp_servers.{server}]",
        f'url = "{url}"',
    ]
    if client_id:
        lines += ["", f"[mcp_servers.{server}.oauth]", f'client_id = "{client_id}"']
    lines.append(END_MARK)
    return "\n".join(lines) + "\n"


def _fenced_span(text: str) -> tuple[int, int] | None:
    start = text.find(BEGIN_MARK)
    if start == -1:
        return None
    end = text.find(END_MARK, start)
    if end == -1:
        return None
    end += len(END_MARK)
    if text[end : end + 1] == "\n":
        end += 1
    return start, end


def _table_span(text: str, table: str) -> tuple[int, int] | None:
    """Find a hand-written ``[mcp_servers.<name>]`` block and its sub-tables.

    Located by text rather than by parsing and re-emitting the document. A
    round trip through a TOML writer would silently drop the user's comments
    and reorder their keys, in a file this project has no claim on.
    """
    pattern = re.compile(rf"^\[{re.escape(table)}(?:\.[^\]]+)?\]\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    start = matches[0].start()
    end = len(text)
    for candidate in re.compile(r"^\[", re.MULTILINE).finditer(text, matches[-1].end()):
        end = candidate.start()
        break
    return start, end


def merge_codex_config(
    original: str, *, server: str, url: str, client_id: str | None
) -> tuple[str, bool]:
    """Replace one managed block, leave the rest of the file untouched.

    Returns the new text and whether anything changed. The user's Codex
    config is theirs - model settings, other MCP servers, approval policy,
    comments - and a project installer that rewrites the whole file is a
    project installer that eventually eats something important.
    """
    block = render_mcp_block(server=server, url=url, client_id=client_id)
    span = _fenced_span(original) or _table_span(original, f"mcp_servers.{server}")

    if span is None:
        prefix = original if not original or original.endswith("\n") else original + "\n"
        separator = "\n" if prefix.strip() else ""
        return prefix + separator + block, True

    start, end = span
    updated = original[:start] + block + original[end:]
    return updated, updated != original
