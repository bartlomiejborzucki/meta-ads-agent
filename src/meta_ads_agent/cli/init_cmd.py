"""``meta-ads-agent init`` - create the brand workspace.

Creates ``.meta-ads/`` in the current project, seeded from the bundled
templates, and makes it private by writing a ``.gitignore`` inside it. Safe to
re-run: existing files are never overwritten unless ``--force`` is given.

The workspace deliberately lives in the user's project, not in the plugin
directory - see docs/architecture/adr/ADR-005-local-state.md.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from meta_ads_agent.cli.output import echo, fail, heading, warn
from meta_ads_agent.errors import WorkspaceError
from meta_ads_agent.models.brand import BrandConfig, Offer
from meta_ads_agent.workspace import Workspace, atomic_write

_TEMPLATE_FILES = (
    ("brand.yaml", "brand.yaml"),
    ("voice.md", "voice.md"),
    ("account.yaml", "account.yaml"),
    ("offer.yaml", "offers/example.yaml"),
)


def template_root() -> Path:
    """Locate the workspace templates in a wheel or a source checkout.

    The originals live in ``skills/meta-ads-core/assets/`` so that the skill
    still has them when it is installed on its own, without the CLI. The build
    copies that directory into the wheel rather than keeping a second copy in
    the repository - see docs/reference/packaging.md.
    """
    packaged = Path(__file__).resolve().parents[1] / "_data" / "templates"
    if packaged.is_dir():
        return packaged
    repo = Path(__file__).resolve().parents[3] / "skills" / "meta-ads-core" / "assets"
    if repo.is_dir():
        return repo
    raise WorkspaceError(f"Could not find bundled templates. Looked in {packaged} and {repo}.")


def run_init(
    *,
    path: str | None = None,
    brand_name: str | None = None,
    force: bool = False,
    check_only: bool = False,
) -> int:
    """Create or verify a workspace. Returns a process exit code."""
    workspace = (
        Workspace.at(Path(path).expanduser() / ".meta-ads")
        if path
        else Workspace.locate(required=False)
    )

    if check_only:
        return _check(workspace)

    heading("Creating brand workspace")
    created = workspace.create()
    echo(f"  workspace: {workspace.root}")
    for directory in created:
        echo(f"  created    {directory.relative_to(workspace.root.parent)}")
    if not created:
        echo("  (directories already existed)")

    templates = template_root()
    for source_rel, target_rel in _TEMPLATE_FILES:
        source = templates / source_rel
        target = workspace.root / target_rel
        if target.exists() and not force:
            echo(f"  kept       {target_rel} (already exists)")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_text(encoding="utf-8")
        if brand_name and target_rel == "brand.yaml":
            content = content.replace("name: Your Brand", f"name: {brand_name}")
        atomic_write(target, content)
        echo(f"  wrote      {target_rel}")

    echo("")
    echo("The workspace is private by default: a .gitignore inside it excludes")
    echo("everything. It holds ad account ids, performance data, campaign state,")
    echo("and creative assets - none of which belongs in a git history.")

    heading("Next")
    echo("  1. Fill in .meta-ads/brand.yaml (only what you want to pin - most")
    echo("     of it is discoverable from Meta) and .meta-ads/voice.md.")
    echo("  2. Connect Meta's official Ads MCP if you have not:")
    echo(
        "     https://github.com/bartlomiejborzucki/meta-ads-agent"
        "/blob/master/docs/getting-started/connect-meta-mcp.md"
    )
    echo("  3. Check everything:  meta-ads-agent doctor")
    echo('  4. In your agent, say:  "Audit my Meta Ads account."')
    return 0


def _check(workspace: Workspace) -> int:
    """Validate the files in an existing workspace."""
    heading("Checking brand workspace")
    if not workspace.exists:
        fail(f"no workspace found at {workspace.root}. Run 'meta-ads-agent init'.")
        return 1

    echo(f"  workspace: {workspace.root}")
    problems = 0

    if workspace.brand_file.is_file():
        problems += _validate_file(workspace.brand_file, BrandConfig, "brand.yaml")
    else:
        warn("no brand.yaml - the agent will have no brand defaults or voice")

    if not workspace.voice_file.is_file():
        warn("no voice.md - the creative skill will have no tone guidance")

    if workspace.offers_dir.is_dir():
        for offer_file in sorted(workspace.offers_dir.glob("*.yaml")):
            problems += _validate_file(offer_file, Offer, offer_file.name)

    if not (workspace.root / ".gitignore").is_file():
        warn(
            "no .gitignore inside the workspace - account ids and reports could "
            "be committed. Re-run 'meta-ads-agent init' to add one."
        )

    campaigns = workspace.list_campaigns()
    echo(f"  campaigns: {len(campaigns)}" + (f" ({', '.join(campaigns)})" if campaigns else ""))

    if problems:
        fail(f"{problems} file(s) failed validation")
        return 1
    echo("")
    echo("  workspace ok")
    return 0


def _validate_file(path: Path, model: type[BaseModel], label: str) -> int:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        fail(f"{label} is not valid YAML: {exc}")
        return 1
    try:
        model.model_validate(raw)
    except PydanticValidationError as exc:
        fail(f"{label} failed validation:")
        for error in exc.errors():
            location = ".".join(str(p) for p in error["loc"]) or "(root)"
            echo(f"    {location}: {error['msg']}")
        return 1
    echo(f"  ok         {label}")
    return 0


def write_account_cache(workspace: Workspace, payload: dict[str, object]) -> Path:
    """Persist account facts read from Meta into ``account.yaml``.

    A cache for the validator, explicitly stamped with a read time so nobody
    mistakes it for current truth.
    """
    data = {"schema_version": 1, "read_at": _dt.datetime.now(_dt.UTC).isoformat()}
    data.update(payload)
    workspace.write_yaml(
        workspace.account_file,
        data,
        header=(
            "# Cached account facts read from Meta. A cache, not a source of\n"
            "# truth - Meta is authoritative. Safe to delete."
        ),
    )
    return workspace.account_file
