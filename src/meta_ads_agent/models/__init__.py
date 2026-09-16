"""Validated data models: brand config, campaign plan, campaign state.

Every structure that crosses a boundary - written to disk, read from disk, or
handed to Meta - is defined here as a Pydantic model. Malformed
agent-generated YAML or JSON must fail at the model boundary, not inside an
API call. See docs/architecture/adr/ADR-008-deterministic-vs-agent-layer.md.
"""

from meta_ads_agent.models.brand import AccountDefaults, BrandConfig, Offer
from meta_ads_agent.models.plan import (
    AdPlan,
    AdSetPlan,
    CampaignPlan,
    CampaignPlanDocument,
    CreativePlan,
    DsaFields,
    TargetingPlan,
)
from meta_ads_agent.models.state import (
    AssetManifest,
    AssetRecord,
    CampaignState,
    CreatedObject,
    Stage,
)

__all__ = [
    "AccountDefaults",
    "AdPlan",
    "AdSetPlan",
    "AssetManifest",
    "AssetRecord",
    "BrandConfig",
    "CampaignPlan",
    "CampaignPlanDocument",
    "CampaignState",
    "CreatedObject",
    "CreativePlan",
    "DsaFields",
    "Offer",
    "Stage",
    "TargetingPlan",
]
