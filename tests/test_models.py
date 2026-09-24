"""Model validation: brand config, campaign plan, and their constraints.

Malformed agent-generated YAML must fail at the model boundary, not inside an
API call.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from conftest import plan_dict
from meta_ads_agent.models.brand import BrandConfig, Offer
from meta_ads_agent.models.plan import BudgetLevel, CampaignPlanDocument, CreativeMode


def build(mutate=None, **overrides):  # type: ignore[no-untyped-def]
    """Build a plan document, optionally mutating the raw dict first."""
    raw = plan_dict(**overrides)
    if mutate:
        mutate(raw)
    return CampaignPlanDocument.model_validate(raw)


class TestBrandConfig:
    def test_minimal_config_is_valid(self) -> None:
        brand = BrandConfig(name="Acme")
        assert brand.profile == "standard"
        assert brand.thresholds.min_conversions_for_decision == 30

    def test_unknown_fields_are_rejected(self) -> None:
        # Silently dropping a field means the user reviews a setting that will
        # never be applied.
        with pytest.raises(ValidationError):
            BrandConfig(name="Acme", dailly_budget=70)  # type: ignore[call-arg]

    def test_account_id_shape_is_enforced(self) -> None:
        with pytest.raises(ValidationError, match="act_"):
            BrandConfig(name="Acme", account={"ad_account_id": "1234567890"})

    def test_currency_is_normalised(self) -> None:
        brand = BrandConfig(name="Acme", account={"currency": "pln"})
        assert brand.account.currency == "PLN"

    def test_country_codes_are_normalised(self) -> None:
        brand = BrandConfig(name="Acme", account={"countries": ["pl", "de"]})
        assert brand.account.countries == ["PL", "DE"]

    def test_website_becomes_the_default_destination(self) -> None:
        brand = BrandConfig(name="Acme", website="https://acme.example.com")
        assert brand.default_destination_url == "https://acme.example.com"

    def test_explicit_destination_is_not_overwritten(self) -> None:
        brand = BrandConfig(
            name="Acme",
            website="https://acme.example.com",
            default_destination_url="https://acme.example.com/offer",
        )
        assert brand.default_destination_url.endswith("/offer")

    def test_profile_is_constrained(self) -> None:
        with pytest.raises(ValidationError):
            BrandConfig(name="Acme", profile="aggressive")

    def test_thresholds_are_user_business_rules_not_defaults_with_opinions(self) -> None:
        # An unset threshold is absent, not an opinion. See ADR-007.
        brand = BrandConfig(name="Acme")
        assert brand.thresholds.max_cpa_display is None
        assert brand.thresholds.min_roas is None

    def test_fatigue_threshold_is_overridable(self) -> None:
        brand = BrandConfig(name="Acme", thresholds={"ctr_decline_pct_for_fatigue": 45})
        assert brand.thresholds.ctr_decline_pct_for_fatigue == 45


class TestOffer:
    def test_valid_offer(self) -> None:
        offer = Offer(
            name="Webinar",
            landing_page="https://acme.example.com/webinar",
            audience="Marketing leads",
            problem="Manual reporting",
            outcome="Report builds itself",
        )
        assert offer.proof == []

    def test_landing_page_must_be_a_url(self) -> None:
        with pytest.raises(ValidationError):
            Offer(
                name="x",
                landing_page="acme.example.com",
                audience="a",
                problem="b",
                outcome="c",
            )


class TestPlanStructure:
    def test_fixture_plan_is_valid(self) -> None:
        doc = build()
        assert doc.campaign.currency == "PLN"
        assert doc.campaign.budget_level is BudgetLevel.AD_SET
        assert doc.campaign.total_ads() == 1

    def test_slug_must_be_directory_safe(self) -> None:
        with pytest.raises(ValidationError):
            build(slug="Acme Webinar Q4!")

    def test_status_cannot_be_active(self) -> None:
        # There is no field for creating something active, by design.
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["status"] = "ACTIVE"

        with pytest.raises(ValidationError):
            build(mutate)

    def test_ad_status_cannot_be_active(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["status"] = "ACTIVE"

        with pytest.raises(ValidationError):
            build(mutate)

    def test_objective_shape_is_checked_but_values_are_not_whitelisted(self) -> None:
        # Meta's objective set changes every version; a local allowlist would
        # reject valid new values. Shape only.
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["objective"] = "OUTCOME_SOMETHING_NEW_IN_V29"

        assert build(mutate).campaign.objective == "OUTCOME_SOMETHING_NEW_IN_V29"

    def test_lowercase_objective_is_rejected(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["objective"] = "outcome_leads"

        with pytest.raises(ValidationError, match="UPPER_SNAKE_CASE"):
            build(mutate)

    def test_a_campaign_needs_at_least_one_ad_set(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"] = []

        with pytest.raises(ValidationError):
            build(mutate)

    def test_an_ad_set_needs_at_least_one_ad(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"] = []

        with pytest.raises(ValidationError):
            build(mutate)


class TestBudgetLevel:
    def test_budget_on_both_levels_is_rejected(self) -> None:
        # Meta rejects it too; catching it locally saves a half-built campaign.
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["budget"] = {
                "level": "campaign",
                "type": "daily",
                "amount": "200",
                "currency": "PLN",
            }

        with pytest.raises(ValidationError, match="both at once"):
            build(mutate)

    def test_no_budget_anywhere_is_rejected(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            del raw["campaign"]["ad_sets"][0]["budget"]

        with pytest.raises(ValidationError, match="no budget anywhere"):
            build(mutate)

    def test_campaign_budget_alone_is_valid_cbo(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            del raw["campaign"]["ad_sets"][0]["budget"]
            raw["campaign"]["budget"] = {
                "level": "campaign",
                "type": "daily",
                "amount": "200",
                "currency": "PLN",
            }

        assert build(mutate).campaign.budget_level is BudgetLevel.CAMPAIGN

    def test_one_ad_set_missing_a_budget_under_abo_is_rejected(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            second = dict(raw["campaign"]["ad_sets"][0])
            second["name"] = "DE broad"
            second.pop("budget")
            raw["campaign"]["ad_sets"].append(second)

        with pytest.raises(ValidationError, match="have no budget"):
            build(mutate)

    def test_budget_level_must_match_where_it_is_declared(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["budget"]["level"] = "campaign"

        with pytest.raises(ValidationError, match="level=ad_set"):
            build(mutate)

    def test_mixed_currencies_are_rejected(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            second = {
                "name": "DE broad",
                "budget": {
                    "level": "ad_set",
                    "type": "daily",
                    "amount": "70",
                    "currency": "EUR",
                },
                "targeting": {"countries": ["DE"]},
                "ads": raw["campaign"]["ad_sets"][0]["ads"],
            }
            raw["campaign"]["ad_sets"].append(second)

        with pytest.raises(ValidationError, match="mixes currencies"):
            build(mutate)

    def test_zero_budget_is_rejected(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["budget"]["amount"] = "0"

        with pytest.raises(ValidationError):
            build(mutate)

    def test_budget_amount_is_a_display_amount(self) -> None:
        # 70 means seventy zloty, not seventy grosz. Nothing pre-multiplies.
        assert build().campaign.ad_sets[0].budget.amount == Decimal("70")


class TestTargeting:
    def test_at_least_one_country_is_required(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["targeting"]["countries"] = []

        with pytest.raises(ValidationError):
            build(mutate)

    def test_inverted_age_range_is_rejected(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["targeting"].update(age_min=55, age_max=25)

        with pytest.raises(ValidationError, match="below age_min"):
            build(mutate)

    def test_manual_placements_need_positions(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["placements"] = {"mode": "manual"}

        with pytest.raises(ValidationError, match="at least one placement"):
            build(mutate)

    def test_positions_without_manual_mode_are_rejected(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["placements"] = {
                "mode": "automatic",
                "positions": ["facebook_feed"],
            }

        with pytest.raises(ValidationError, match="only meaningful"):
            build(mutate)


class TestCreativeModes:
    def test_asset_needs_exactly_one_source(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"] = [
                {"local_path": "./a.jpg", "image_hash": "abc"}
            ]

        with pytest.raises(ValidationError, match="exactly one"):
            build(mutate)

    def test_asset_with_no_source_is_rejected(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"] = [
                {"placement": "instagram_stories"}
            ]

        with pytest.raises(ValidationError, match="exactly one"):
            build(mutate)

    def test_single_image_rejects_a_local_video_file(self) -> None:
        # A video_id was refused, a local .mp4 was not.
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"] = [
                {"local_path": "./clip.MP4"}
            ]

        with pytest.raises(ValidationError, match="cannot use a video asset"):
            build(mutate)

    def test_single_image_rejects_a_video_asset(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"] = [{"video_id": "999"}]

        with pytest.raises(ValidationError, match="cannot use a video"):
            build(mutate)

    def test_single_video_needs_a_video(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["mode"] = "single_video"

        with pytest.raises(ValidationError, match="needs a video asset"):
            build(mutate)

    def test_single_video_accepts_a_local_mp4(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "single_video"
            creative["assets"] = [{"local_path": "./clip.mp4"}]

        assert build(mutate).campaign.ad_sets[0].ads[0].creative.mode is (CreativeMode.SINGLE_VIDEO)

    def test_existing_post_requires_a_post_id(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "existing_post"
            creative["assets"] = []
            creative["variants"] = []

        with pytest.raises(ValidationError, match="exactly one of post_id"):
            build(mutate)

    def test_existing_post_refuses_assets_so_engagement_is_not_lost(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "existing_post"
            creative["post_id"] = "1111111111_2222222222"

        with pytest.raises(ValidationError, match="lose the original post"):
            build(mutate)

    def test_existing_post_is_valid_on_its_own(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "existing_post"
            creative["post_id"] = "1111111111_2222222222"
            creative["assets"] = []
            creative["variants"] = []
            creative.pop("destination_url")

        assert build(mutate).campaign.ad_sets[0].ads[0].creative.post_id

    def test_post_id_is_rejected_outside_existing_post_mode(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["post_id"] = "1_2"

        with pytest.raises(ValidationError, match="only valid with mode=existing_post"):
            build(mutate)

    def test_single_image_takes_one_variant(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["variants"].append(
                {"angle": "price", "primary_text": "Cheaper than a spreadsheet."}
            )

        with pytest.raises(ValidationError, match="multi_variant"):
            build(mutate)

    def test_multi_variant_takes_several(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "multi_variant"
            creative["variants"].append(
                {"angle": "price", "primary_text": "Cheaper than a spreadsheet."}
            )

        assert len(build(mutate).campaign.ad_sets[0].ads[0].creative.variants) == 2

    def test_a_creative_needs_a_destination(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            del raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["destination_url"]

        with pytest.raises(ValidationError, match="destination_url"):
            build(mutate)

    def test_a_creative_needs_copy(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["variants"] = []

        with pytest.raises(ValidationError, match="copy variant"):
            build(mutate)


class TestCarouselAndInstagram:
    @staticmethod
    def _carousel(cards: int):  # type: ignore[no-untyped-def]
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "carousel"
            creative["assets"] = []
            creative["cards"] = [
                {"asset": {"image_hash": f"hash{i}"}, "headline": f"card {i}"} for i in range(cards)
            ]

        return mutate

    @pytest.mark.parametrize("cards", [2, 10])
    def test_two_to_ten_cards_are_accepted(self, cards: int) -> None:
        assert len(build(self._carousel(cards)).campaign.ad_sets[0].ads[0].creative.cards) == cards

    @pytest.mark.parametrize("cards", [0, 1, 11])
    def test_other_card_counts_are_refused(self, cards: int) -> None:
        with pytest.raises(ValidationError, match="2 to 10 cards"):
            build(self._carousel(cards))

    def test_cards_outside_a_carousel_are_refused(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["cards"] = [
                {"asset": {"image_hash": "x"}}
            ]

        with pytest.raises(ValidationError, match="only valid with mode=carousel"):
            build(mutate)

    def test_an_instagram_post_needs_its_account(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative.update(mode="existing_post", assets=[], variants=[])
            creative["instagram_media_id"] = "17900000000000001"

        with pytest.raises(ValidationError, match="instagram_account_id"):
            build(mutate)

    def test_an_unknown_placement_is_refused(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"][0]["placement"] = (
                "tiktok_feed"
            )

        with pytest.raises(ValidationError, match="not one this project maps"):
            build(mutate)


class TestSchedule:
    def test_end_before_start_is_rejected(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["schedule"] = {
                "start": "2026-10-01T00:00:00Z",
                "end": "2026-09-01T00:00:00Z",
            }

        with pytest.raises(ValidationError, match="after start"):
            build(mutate)

    def test_mixing_offset_and_naive_times_is_a_validation_error(self) -> None:
        # Comparing them raised TypeError, which escaped pydantic as a crash.
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["schedule"] = {
                "start": "2026-10-01T00:00:00Z",
                "end": "2026-10-08T00:00:00",
            }

        with pytest.raises(ValidationError, match="UTC offset"):
            build(mutate)
