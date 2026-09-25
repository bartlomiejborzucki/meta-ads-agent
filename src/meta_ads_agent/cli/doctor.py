"""``meta-ads-agent doctor`` - local prerequisites and connection status.

The output distinguishes three readiness states, because they need different
fixes:

* **READY FOR MCP** - everything needed to use Meta's official Ads MCP. This is
  the default path and needs no credentials.
* **READY FOR API FALLBACK** - the optional extra and a token are present, so
  local uploads and the other gap capabilities will work.
* **MISSING OPTIONAL FALLBACK CONFIG** - normal, and not a problem, unless the
  user wants those capabilities.

Absent fallback credentials are never reported as an error. Most users will
never need them.

It also reports on the installation itself, and keeps those answers distinct
because they need different fixes: an installation can be *complete*, have an
*update available*, need a *migration*, be *interrupted* half way through an
update, or be *broken* - files missing, modified, or left behind by an older
version. "It says 0.2.0" is not evidence of any of them, which is why the
check compares the tree against the release manifest rather than reading a
version number back.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from meta_ads_agent import __version__
from meta_ads_agent.api.version import DEFAULT_GRAPH_API_VERSION, graph_api_version
from meta_ads_agent.capabilities import load_registry
from meta_ads_agent.cli.output import echo, emit_json, heading, status_line
from meta_ads_agent.errors import MetaAdsAgentError
from meta_ads_agent.redaction import fingerprint
from meta_ads_agent.workspace import Workspace

MCP_ENDPOINT = "https://mcp.facebook.com/ads"

# Mirrors requires-python. Kept as data so doctor can report the requirement
# rather than only the outcome.
MIN_PYTHON = (3, 11)

# How the MCP appears in each host's configuration. Used to detect an existing
# connection, not to create one - see ADR-006.
_CLAUDE_CONFIG_CANDIDATES = (
    Path.home() / ".claude.json",
    Path.home() / ".claude" / "settings.json",
)
_CODEX_CONFIG_CANDIDATES = (
    Path.home() / ".codex" / "config.toml",
    Path.home() / ".codex" / "mcp.json",
)


@dataclass(slots=True)
class Check:
    label: str
    status: str
    detail: str = ""
    fix: str | None = None


@dataclass(slots=True)
class Diagnosis:
    checks: list[Check] = field(default_factory=list)
    mcp_ready: bool = False
    fallback_ready: bool = False
    installation: dict[str, Any] = field(default_factory=dict)

    def add(self, label: str, status: str, detail: str = "", fix: str | None = None) -> Check:
        check = Check(label, status, detail, fix)
        self.checks.append(check)
        return check

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "mcp_ready": self.mcp_ready,
            "api_fallback_ready": self.fallback_ready,
            "installation": self.installation,
            "checks": [
                {"label": c.label, "status": c.status, "detail": c.detail, "fix": c.fix}
                for c in self.checks
            ],
        }


def run_doctor(*, as_json: bool = False, workspace_hint: str | None = None) -> int:
    """Run every check. Returns a process exit code."""
    diagnosis = Diagnosis()

    _check_runtime(diagnosis)
    _check_package(diagnosis)
    _check_installation(diagnosis)
    _check_hosts(diagnosis)
    _check_mcp_connection(diagnosis)
    _check_workspace(diagnosis, workspace_hint)
    _check_fallback(diagnosis)

    hard_failures = [c for c in diagnosis.checks if c.status == "FAIL"]
    diagnosis.mcp_ready = not hard_failures

    if as_json:
        emit_json(diagnosis.as_dict())
        return 1 if hard_failures else 0

    _render(diagnosis)
    return 1 if hard_failures else 0


def _check_runtime(diagnosis: Diagnosis) -> None:
    version = ".".join(str(v) for v in sys.version_info[:3])
    required = ".".join(str(v) for v in MIN_PYTHON)
    if tuple(sys.version_info[:2]) >= MIN_PYTHON:
        diagnosis.add("python", "OK", version)
    else:
        diagnosis.add(
            "python",
            "FAIL",
            f"{version} (need {required}+)",
            f"Install Python {required} or newer",
        )

    uv = shutil.which("uv")
    diagnosis.add("uv", "OK" if uv else "OPTIONAL", uv or "not found (pip works too)")
    git = shutil.which("git")
    diagnosis.add("git", "OK" if git else "OPTIONAL", git or "not found")

    ffprobe = shutil.which("ffprobe")
    diagnosis.add(
        "ffprobe",
        "OK" if ffprobe else "OPTIONAL",
        ffprobe or "not found - video dimensions and duration will not be checked before upload",
        None if ffprobe else "Install ffmpeg for pre-upload video QA",
    )


def _check_package(diagnosis: Diagnosis) -> None:
    diagnosis.add("meta-ads-agent", "OK", __version__)
    try:
        registry = load_registry()
    except MetaAdsAgentError as exc:
        diagnosis.add("capability registry", "FAIL", str(exc), "Reinstall the package")
        return

    stale = registry.stale(older_than_days=90)
    detail = (
        f"{len(registry.capabilities)} capabilities, "
        f"{len(registry.gaps())} fallback gap(s), reviewed {registry.reviewed}"
    )
    if stale:
        diagnosis.add(
            "capability registry",
            "INFO",
            f"{detail}; {len(stale)} entry/entries not reviewed in 90 days",
            "Run the capability refresh: docs/reference/capability-refresh.md",
        )
    else:
        diagnosis.add("capability registry", "OK", detail)

    configured = graph_api_version()
    diagnosis.add(
        "graph api version",
        "OK" if configured == DEFAULT_GRAPH_API_VERSION else "INFO",
        configured
        + (
            ""
            if configured == DEFAULT_GRAPH_API_VERSION
            else f" (overridden; default is {DEFAULT_GRAPH_API_VERSION})"
        ),
    )


# How each installation status is surfaced. Separated rather than collapsed
# into ok/not-ok because the fix differs in every row, and a user reading
# "problem" learns nothing.
_INSTALL_STATUS = {
    "complete": ("OK", False),
    "update-available": ("INFO", False),
    "migration-required": ("MISSING", False),
    "interrupted": ("FAIL", True),
    "broken": ("FAIL", True),
    "not-installed": ("OPTIONAL", False),
}


def _check_installation(diagnosis: Diagnosis) -> None:
    """Is the installed payload complete, current, and not mid-update?"""
    from meta_ads_agent.cli.install_cmd import installation_report

    try:
        report = installation_report()
    except MetaAdsAgentError as exc:  # pragma: no cover - defensive
        diagnosis.add("skills installation", "FAIL", str(exc), "meta-ads-agent install")
        return

    diagnosis.installation = report
    status, _fatal = _INSTALL_STATUS.get(report["status"], ("INFO", False))
    diagnosis.add(
        "skills installation",
        status,
        f"{report['status']}: {report.get('detail', '')}",
        report.get("fix"),
    )

    release = report.get("release_version")
    installed = report.get("installed_version")
    if release and release != __version__:
        diagnosis.add(
            "version skew",
            "FAIL",
            f"CLI {__version__} ships release manifest {release} - the package is inconsistent",
            "Reinstall the CLI: uv tool install --force "
            '"git+https://github.com/bartlomiejborzucki/meta-ads-agent.git"',
        )
    elif installed and installed != release:
        diagnosis.add(
            "version skew",
            "INFO",
            f"skills {installed}, CLI {__version__}",
            "meta-ads-agent upgrade",
        )
    else:
        diagnosis.add("version skew", "OK", f"CLI, payload and skills all {__version__}")

    verification = report.get("verification") or {}
    for key, label in (
        ("missing", "files missing"),
        ("modified", "files modified"),
        ("orphaned", "files from an older version"),
    ):
        entries = verification.get(key) or []
        if entries:
            shown = ", ".join(entries[:4]) + (" ..." if len(entries) > 4 else "")
            diagnosis.add(
                label,
                "FAIL",
                f"{len(entries)}: {shown}",
                "meta-ads-agent install --force",
            )


def _check_hosts(diagnosis: Diagnosis) -> None:
    for name, binary in (("Claude Code", "claude"), ("Codex", "codex")):
        path = shutil.which(binary)
        if not path:
            diagnosis.add(f"{name} CLI", "OPTIONAL", "not detected on PATH")
            continue
        diagnosis.add(f"{name} CLI", "OK", f"{path} {_binary_version(path)}".strip())


def _binary_version(path: str) -> str:
    try:
        result = subprocess.run(  # noqa: S603 - absolute path from which(), fixed argv
            [path, "--version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or result.stderr or "").strip().splitlines()[0][:40]


def _check_mcp_connection(diagnosis: Diagnosis) -> None:
    """Look for a configured Meta MCP server in either host's config.

    Detection only. Whether the OAuth session is live can only be established
    by a running agent listing the server's tools, which is why the core skill
    tells it to do exactly that before starting Meta work.
    """
    found: list[str] = []
    for path in (*_CLAUDE_CONFIG_CANDIDATES, *_CODEX_CONFIG_CANDIDATES):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "mcp.facebook.com/ads" in text:
            found.append(str(path))

    if found:
        diagnosis.add(
            "Meta Ads MCP configured",
            "READY",
            f"{MCP_ENDPOINT} referenced in {', '.join(found)}",
        )
    else:
        diagnosis.add(
            "Meta Ads MCP configured",
            "MISSING",
            f"no reference to {MCP_ENDPOINT} found in the host configs checked",
            "claude mcp add --transport http --client-id <META_APP_ID> "
            f"meta-ads {MCP_ENDPOINT}\n"
            f"    (Codex: codex mcp add meta-ads --url {MCP_ENDPOINT} "
            "--oauth-client-id <META_APP_ID>, then codex mcp login meta-ads)",
        )


def _check_workspace(diagnosis: Diagnosis, hint: str | None) -> None:
    workspace = Workspace.locate(hint, required=False)
    if not workspace.exists:
        diagnosis.add(
            "brand workspace",
            "MISSING",
            f"no .meta-ads/ found from {Path.cwd()}",
            "meta-ads-agent init",
        )
        return

    parts = [f"{workspace.root}"]
    parts.append("brand.yaml" if workspace.brand_file.is_file() else "no brand.yaml")
    parts.append("voice.md" if workspace.voice_file.is_file() else "no voice.md")
    campaigns = workspace.list_campaigns()
    parts.append(f"{len(campaigns)} campaign(s)")
    diagnosis.add("brand workspace", "OK", ", ".join(parts))

    gitignored = (workspace.root / ".gitignore").is_file()
    diagnosis.add(
        "workspace private",
        "OK" if gitignored else "MISSING",
        "ignored by git from inside the workspace"
        if gitignored
        else "no .gitignore inside the workspace - account ids and reports could be committed",
        None if gitignored else "meta-ads-agent init (safe to re-run)",
    )


def _check_fallback(diagnosis: Diagnosis) -> None:
    try:
        import facebook_business

        sdk_version = getattr(facebook_business, "__version__", "unknown")
        sdk_present = True
    except ImportError:
        sdk_version = ""
        sdk_present = False

    diagnosis.add(
        "Meta Business SDK",
        "OK" if sdk_present else "OPTIONAL",
        f"facebook-business {sdk_version}"
        if sdk_present
        else "not installed - only needed for the API fallback",
        None if sdk_present else 'uv pip install "meta-ads-agent[api]"',
    )

    from meta_ads_agent import envfile

    if envfile.loaded_from is not None:
        diagnosis.add(
            ".env",
            "OK",
            f"read {envfile.loaded_from}: {', '.join(envfile.loaded_keys) or 'nothing new'}"
            " (the environment wins where both set a value)",
        )
    # Stripped the way ApiClient strips it, so the fingerprint shown is the
    # token that will be used, and a whitespace-only value reads as unset.
    token = os.environ.get("META_ACCESS_TOKEN", "").strip()
    diagnosis.add(
        "META_ACCESS_TOKEN",
        "OK" if token else "OPTIONAL",
        fingerprint(token) if token else "not set - only needed for the API fallback",
    )
    account = os.environ.get("META_AD_ACCOUNT_ID", "")
    diagnosis.add(
        "META_AD_ACCOUNT_ID",
        "OK" if account else "OPTIONAL",
        account or "not set - pass --account instead",
    )
    for name in ("META_APP_ID", "META_APP_SECRET"):
        value = os.environ.get(name, "")
        diagnosis.add(
            name,
            "OK" if value else "OPTIONAL",
            ("set" if name == "META_APP_ID" else fingerprint(value))
            if value
            else "not set - rarely needed",
        )

    diagnosis.fallback_ready = bool(sdk_present and token)


def _render(diagnosis: Diagnosis) -> None:
    heading(f"meta-ads-agent doctor  ({__version__})")
    for check in diagnosis.checks:
        status_line(check.label, check.status, check.detail)

    heading("Installation")
    status = diagnosis.installation.get("status", "unknown")
    colour = {
        "complete": "green",
        "update-available": "yellow",
        "migration-required": "yellow",
        "interrupted": "red",
        "broken": "red",
        "not-installed": "dim",
    }.get(status, "dim")
    echo(f"  {status.upper():<28}  {diagnosis.installation.get('detail', '')}", colour)
    target = diagnosis.installation.get("target") or {}
    if target:
        echo(f"    target: {target.get('windows_path') or target.get('root')}", "dim")

    heading("Readiness")
    mcp_configured = any(
        c.label == "Meta Ads MCP configured" and c.status == "READY" for c in diagnosis.checks
    )
    failures = [c for c in diagnosis.checks if c.status == "FAIL"]

    if failures:
        echo("  READY FOR MCP                 no", "red")
    elif mcp_configured:
        echo("  READY FOR MCP                 yes", "green")
    else:
        echo("  READY FOR MCP                 local prerequisites ok, MCP not connected", "yellow")

    if diagnosis.fallback_ready:
        echo("  READY FOR API FALLBACK        yes", "green")
    else:
        echo("  MISSING OPTIONAL FALLBACK CONFIG", "dim")
        echo(
            "    Expected unless you need local asset upload, video or "
            "existing-post creatives, or deletion.",
            "dim",
        )

    fixes = [c for c in diagnosis.checks if c.fix]
    if fixes:
        heading("Suggested next steps")
        for check in fixes:
            echo(f"  {check.label}:")
            for line in check.fix.splitlines():  # type: ignore[union-attr]
                echo(f"    {line}")


def doctor_json() -> str:
    """Diagnosis as a JSON string, for tests and programmatic callers."""
    diagnosis = Diagnosis()
    _check_runtime(diagnosis)
    _check_package(diagnosis)
    _check_installation(diagnosis)
    _check_hosts(diagnosis)
    _check_mcp_connection(diagnosis)
    _check_workspace(diagnosis, None)
    _check_fallback(diagnosis)
    diagnosis.mcp_ready = not [c for c in diagnosis.checks if c.status == "FAIL"]
    return json.dumps(diagnosis.as_dict(), indent=2)
