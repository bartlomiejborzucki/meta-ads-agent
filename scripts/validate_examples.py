#!/usr/bin/env python3
"""Validate every shipped template and example against its model.

A template that does not validate is worse than no template: the user copies
it, edits one field, and blames their edit. Examples are also the only place a
fake id could accidentally look real, so this checks for that too.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from meta_ads_agent.capabilities import load_registry  # noqa: E402
from meta_ads_agent.models.brand import BrandConfig, Offer  # noqa: E402
from meta_ads_agent.models.plan import CampaignPlanDocument  # noqa: E402
from meta_ads_agent.models.state import CampaignState  # noqa: E402

TARGETS: tuple[tuple[str, type], ...] = (
    ("templates/brand/brand.yaml", BrandConfig),
    ("templates/campaign/offer.yaml", Offer),
    ("templates/campaign/campaign-plan.yaml", CampaignPlanDocument),
    ("examples/brand.yaml", BrandConfig),
    ("examples/offer.yaml", Offer),
    ("examples/campaign-plan.yaml", CampaignPlanDocument),
)

JSON_TARGETS: tuple[tuple[str, type], ...] = (("examples/state.json", CampaignState),)

# A string that could be mistaken for a real Meta credential must not appear in
# an example, so nobody copies one into a real account or a secret scanner.
TOKEN_SHAPED = re.compile(r"\bEAA[A-Za-z0-9]{12,}\b")
APP_SECRET_SHAPED = re.compile(r"\b\d{15,17}\|[A-Za-z0-9_\-]{20,}\b")


def main() -> int:
    problems: list[str] = []

    for relative, model in TARGETS:
        path = REPO / relative
        if not path.is_file():
            problems.append(f"{relative}: missing")
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            problems.append(f"{relative}: invalid YAML: {exc}")
            continue
        try:
            model.model_validate(raw)
        except ValidationError as exc:
            problems.append(f"{relative}: failed {model.__name__} validation")
            for error in exc.errors():
                location = ".".join(str(part) for part in error["loc"]) or "(root)"
                problems.append(f"    {location}: {error['msg']}")
            continue
        print(f"ok  {relative} ({model.__name__})")

    import json

    for relative, model in JSON_TARGETS:
        path = REPO / relative
        if not path.is_file():
            problems.append(f"{relative}: missing")
            continue
        try:
            model.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError) as exc:
            problems.append(f"{relative}: failed {model.__name__} validation: {exc}")
            continue
        print(f"ok  {relative} ({model.__name__})")

    for path in sorted((REPO / "examples").rglob("*")) + sorted((REPO / "templates").rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if TOKEN_SHAPED.search(text):
            problems.append(f"{path.relative_to(REPO)}: contains a token-shaped string")
        if APP_SECRET_SHAPED.search(text):
            problems.append(f"{path.relative_to(REPO)}: contains an app-secret-shaped string")

    registry = load_registry(REPO / "config" / "capabilities.yaml")
    print(
        f"ok  config/capabilities.yaml "
        f"({len(registry.capabilities)} capabilities, {len(registry.gaps())} gaps)"
    )

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nall templates and examples validate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
