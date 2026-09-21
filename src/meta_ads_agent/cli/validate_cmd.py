"""``meta-ads-agent validate-plan`` - the gate before any write.

Loads a plan, optionally loads brand config and cached account facts, and
reports platform-constraint findings. Errors block; warnings do not.

Exit codes:
  0  valid (warnings may be present)
  1  blocked by at least one error
  2  the plan file itself could not be read or parsed
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError as PydanticValidationError

from meta_ads_agent.cli.output import echo, emit_json, fail, heading
from meta_ads_agent.errors import MetaAdsAgentError
from meta_ads_agent.models.brand import BrandConfig
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.validation import AccountContext, validate_plan
from meta_ads_agent.workspace import Workspace


def run_validate_plan(
    plan_path: str,
    *,
    account_path: str | None = None,
    brand_path: str | None = None,
    as_json: bool = False,
    skip_assets: bool = False,
    strict: bool = False,
) -> int:
    target = Path(plan_path).expanduser()
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        fail(f"{target} not found")
        return 2
    except yaml.YAMLError as exc:
        fail(f"{target} is not valid YAML: {exc}")
        return 2

    try:
        doc = CampaignPlanDocument.model_validate(raw)
    except PydanticValidationError as exc:
        fail(f"{target} is not a valid campaign plan:")
        for error in exc.errors():
            location = ".".join(str(p) for p in error["loc"]) or "(root)"
            echo(f"  {location}: {error['msg']}")
        echo("")
        echo("The plan schema is documented in skills/meta-ads-campaign/assets/campaign-plan.yaml")
        return 2

    workspace = Workspace.locate(required=False)
    brand = _load_brand(brand_path, workspace)
    account = _load_account(account_path, workspace)

    try:
        report = validate_plan(
            doc,
            account=account,
            brand=brand,
            # Local asset paths in a plan are relative to the plan's own
            # directory, so a workspace is portable between machines.
            asset_base=target.parent,
            check_assets=not skip_assets,
        )
    except MetaAdsAgentError as exc:
        fail(str(exc))
        return 2

    if as_json:
        emit_json(
            {
                "plan": str(target),
                "slug": doc.slug,
                "ad_account_id": doc.ad_account_id,
                "ok": report.ok,
                "account_context": account is not None,
                "uses_api_fallback": report.uses_fallback,
                "providers": report.providers_used,
                "findings": [
                    {
                        "severity": f.severity.value,
                        "code": f.code,
                        "path": f.path,
                        "message": f.message,
                    }
                    for f in report.findings
                ],
            }
        )
    else:
        heading(f"Validating {target}")
        echo(f"  campaign  {doc.campaign.name}")
        echo(f"  account   {doc.ad_account_id}")
        echo(
            f"  structure {len(doc.campaign.ad_sets)} ad set(s), "
            f"{doc.campaign.total_ads()} ad(s), "
            f"{doc.campaign.budget_level.value}-level budget"
        )
        if account is None:
            echo("  account context: NOT LOADED - fewer checks ran", "yellow")
        echo("")
        echo(report.render())

        if report.uses_fallback:
            heading("Execution routing")
            for capability, provider in sorted(report.providers_used.items()):
                echo(f"  {capability:<34} {provider}")
            echo("")
            echo("  Steps marked api_fallback run through the Meta Business SDK")
            echo("  because Meta's official Ads MCP does not expose them.")

    if not report.ok:
        return 1
    if strict and report.warnings:
        fail(f"--strict: {len(report.warnings)} warning(s) treated as failure")
        return 1
    return 0


def _load_brand(explicit: str | None, workspace: Workspace) -> BrandConfig | None:
    path = Path(explicit).expanduser() if explicit else workspace.brand_file
    if not path.is_file():
        return None
    try:
        return BrandConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except (PydanticValidationError, yaml.YAMLError) as exc:
        fail(f"ignoring {path}: {exc}")
        return None


def _load_account(explicit: str | None, workspace: Workspace) -> AccountContext | None:
    """Load cached account facts.

    Absence is normal and produces a warning in the report rather than an
    error: a plan should be reviewable before the agent has read the account.
    """
    path = Path(explicit).expanduser() if explicit else workspace.account_file
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        fail(f"ignoring {path}: {exc}")
        return None
    # The template ships with every value null; treat that as "not read yet".
    if not raw.get("id"):
        return None
    try:
        return AccountContext.from_meta({k: v for k, v in raw.items() if v is not None})
    except PydanticValidationError as exc:
        fail(f"ignoring {path}: {exc}")
        return None
