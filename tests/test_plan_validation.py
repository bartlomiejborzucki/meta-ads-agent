"""Platform-constraint validation.

Scope discipline: errors here must correspond to something Meta rejects or
something that makes an ad undeliverable. Media-buying opinions produce
warnings at most, and the validator must never block a valid-but-unusual plan.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import plan_dict, write_png
from meta_ads_agent.models.brand import BrandConfig
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.validation import AccountContext, Severity, validate_plan


def build(mutate=None, **overrides):  # type: ignore[no-untyped-def]
    raw = plan_dict(**overrides)
    if mutate:
        mutate(raw)
    return CampaignPlanDocument.model_validate(raw)


def codes(report, severity=None):  # type: ignore[no-untyped-def]
    return {f.code for f in report.findings if severity is None or f.severity is severity}


class TestHappyPath:
    def test_a_complete_plan_with_full_account_context_validates(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        report = validate_plan(plan, account=account, check_assets=False)
        assert report.ok, report.render()
        assert report.errors == []

    def test_rendering_includes_a_verdict(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        assert "VALID" in validate_plan(plan, account=account, check_assets=False).render()


class TestAccountContext:
    def test_absent_context_warns_rather_than_blocking(self, plan) -> None:  # type: ignore[no-untyped-def]
        # A plan should be reviewable before the agent has read the account.
        report = validate_plan(plan, check_assets=False)
        assert report.ok
        assert "account.not_read" in codes(report, Severity.WARNING)
        assert "currency.unverified" in codes(report, Severity.WARNING)

    def test_wrong_account_is_an_error(self, plan) -> None:  # type: ignore[no-untyped-def]
        other = AccountContext(id="act_9999999999", currency="PLN")
        assert "account.mismatch" in codes(
            validate_plan(plan, account=other, check_assets=False), Severity.ERROR
        )

    def test_disabled_account_blocks(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        account.account_status = 2
        account.disable_reason = 1
        assert "account.not_active" in codes(
            validate_plan(plan, account=account, check_assets=False), Severity.ERROR
        )

    def test_no_payment_method_blocks_before_objects_are_created(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        # Otherwise the campaign builds fine and silently never delivers.
        account.has_payment_method = False
        assert "account.no_payment_method" in codes(
            validate_plan(plan, account=account, check_assets=False), Severity.ERROR
        )

    def test_not_queryable_blocks(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        account.is_queryable = False
        assert "account.not_queryable" in codes(
            validate_plan(plan, account=account, check_assets=False), Severity.ERROR
        )

    def test_mcp_not_enabled_warns_but_does_not_block(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        account.is_ads_mcp_enabled = False
        report = validate_plan(plan, account=account, check_assets=False)
        assert "account.mcp_not_enabled" in codes(report, Severity.WARNING)
        assert report.ok

    def test_unknown_timezone_warns(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        account.timezone_name = None
        assert "account.timezone_unknown" in codes(
            validate_plan(plan, account=account, check_assets=False), Severity.WARNING
        )


class TestCurrency:
    def test_currency_mismatch_blocks(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        # The plan says PLN, the account bills USD. Meta would spend USD.
        account.currency = "USD"
        report = validate_plan(plan, account=account, check_assets=False)
        assert "currency.mismatch" in codes(report, Severity.ERROR)

    def test_budget_is_reported_in_both_units(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        report = validate_plan(plan, account=account, check_assets=False)
        resolved = next(f for f in report.findings if f.code == "budget.resolved")
        assert "70.00 PLN" in resolved.message
        assert "7000 minor units" in resolved.message

    def test_metas_offset_is_flagged_when_it_differs_from_iso(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        account.currency_offset = 1
        report = validate_plan(plan, account=account, check_assets=False)
        assert "currency.offset_differs" in codes(report, Severity.WARNING)

    def test_metas_offset_is_used_for_conversion(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        account.currency_offset = 1
        report = validate_plan(plan, account=account, check_assets=False)
        resolved = next(f for f in report.findings if f.code == "budget.resolved")
        assert "70 minor units" in resolved.message

    def test_zero_decimal_currency_is_not_inflated(self, account) -> None:  # type: ignore[no-untyped-def]
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["budget"].update(amount="5000", currency="JPY")
            raw["campaign"]["ad_sets"][0]["targeting"]["countries"] = ["JP"]

        account.currency = "JPY"
        account.currency_offset = 1
        report = validate_plan(build(mutate), account=account, check_assets=False)
        resolved = next(f for f in report.findings if f.code == "budget.resolved")
        assert "5000 minor units" in resolved.message


class TestEuDsa:
    def test_eu_targeting_without_transparency_fields_blocks(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["dsa"] = {"beneficiary": None, "payor": None}

        report = validate_plan(build(mutate), check_assets=False)
        assert "dsa.missing_fields" in codes(report, Severity.ERROR)

    def test_partial_transparency_fields_still_block(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["dsa"] = {"beneficiary": "Acme", "payor": None}

        finding = next(
            f
            for f in validate_plan(build(mutate), check_assets=False).findings
            if f.code == "dsa.missing_fields"
        )
        assert "payor" in finding.message
        assert "beneficiary" not in finding.message.split("field(s)")[1]

    def test_brand_defaults_satisfy_the_requirement(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["dsa"] = {"beneficiary": None, "payor": None}

        brand = BrandConfig(
            name="Acme", dsa={"beneficiary": "Acme Sp. z o.o.", "payor": "Acme Sp. z o.o."}
        )
        report = validate_plan(build(mutate), brand=brand, check_assets=False)
        assert "dsa.missing_fields" not in codes(report)
        assert "dsa.present" in codes(report)

    def test_non_eu_targeting_does_not_require_them(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["dsa"] = {"beneficiary": None, "payor": None}
            raw["campaign"]["ad_sets"][0]["targeting"]["countries"] = ["US"]

        assert "dsa.missing_fields" not in codes(validate_plan(build(mutate), check_assets=False))

    @pytest.mark.parametrize("country", ["PL", "DE", "FR", "IE", "NO", "IS", "LI"])
    def test_eea_countries_are_covered_not_just_eu(self, country: str) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["dsa"] = {"beneficiary": None, "payor": None}
            raw["campaign"]["ad_sets"][0]["targeting"]["countries"] = [country]

        assert "dsa.missing_fields" in codes(
            validate_plan(build(mutate), check_assets=False), Severity.ERROR
        )


class TestSpecialAdCategories:
    def test_empty_declaration_is_noted_as_a_claim_the_user_is_making(self, plan) -> None:  # type: ignore[no-untyped-def]
        report = validate_plan(plan, check_assets=False)
        assert "special_category.none_declared" in codes(report, Severity.INFO)

    def test_brand_declaring_a_category_the_plan_omits_blocks(self, plan) -> None:  # type: ignore[no-untyped-def]
        brand = BrandConfig(name="Acme", special_ad_category=["EMPLOYMENT"])
        report = validate_plan(plan, brand=brand, check_assets=False)
        assert "special_category.not_declared" in codes(report, Severity.ERROR)

    def test_a_declared_category_is_accepted(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["special_ad_categories"] = ["EMPLOYMENT"]

        brand = BrandConfig(name="Acme", special_ad_category=["EMPLOYMENT"])
        report = validate_plan(build(mutate), brand=brand, check_assets=False)
        assert "special_category.not_declared" not in codes(report)


class TestIdentityAndTracking:
    def test_missing_page_blocks(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            del raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["page_id"]

        assert "creative.page_missing" in codes(
            validate_plan(build(mutate), check_assets=False), Severity.ERROR
        )

    def test_page_not_on_the_account_blocks(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        account.available_page_ids = ["9999999999"]
        assert "creative.page_unknown" in codes(
            validate_plan(plan, account=account, check_assets=False), Severity.ERROR
        )

    def test_instagram_identity_not_linked_blocks(self, account) -> None:  # type: ignore[no-untyped-def]
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["instagram_account_id"] = (
                "7777777777"
            )

        assert "creative.instagram_unknown" in codes(
            validate_plan(build(mutate), account=account, check_assets=False), Severity.ERROR
        )

    def test_conversion_optimisation_without_a_dataset_blocks(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["tracking"] = {}

        assert "tracking.dataset_missing" in codes(
            validate_plan(build(mutate), check_assets=False), Severity.ERROR
        )

    def test_unknown_dataset_blocks(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        account.available_dataset_ids = ["8888888888"]
        assert "tracking.dataset_unknown" in codes(
            validate_plan(plan, account=account, check_assets=False), Severity.ERROR
        )

    def test_event_with_no_recent_volume_warns(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        # Optimising for an event with no volume will not deliver, but Meta
        # accepts the configuration - so this is a warning, not an error.
        account.available_conversion_events = ["PURCHASE"]
        report = validate_plan(plan, account=account, check_assets=False)
        assert "tracking.event_not_seen" in codes(report, Severity.WARNING)
        assert report.ok

    def test_missing_optimization_goal_warns(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            del raw["campaign"]["ad_sets"][0]["optimization_goal"]
            raw["campaign"]["ad_sets"][0]["tracking"] = {"dataset_id": "1234567890"}

        assert "optimization_goal.absent" in codes(
            validate_plan(build(mutate), check_assets=False), Severity.WARNING
        )

    def test_discovered_enums_are_enforced_when_present(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        account.valid_optimization_goals = ["LINK_CLICKS"]
        assert "optimization_goal.invalid" in codes(
            validate_plan(plan, account=account, check_assets=False), Severity.ERROR
        )

    def test_empty_discovered_enums_mean_we_did_not_look(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        # An empty list must not be read as "nothing is valid" - that would
        # reject valid plans every time Meta ships a new value.
        account.valid_optimization_goals = []
        account.valid_objectives = []
        report = validate_plan(plan, account=account, check_assets=False)
        assert "optimization_goal.invalid" not in codes(report)
        assert "objective.invalid" not in codes(report)

    def test_invalid_cta_blocks_when_the_set_is_known(self, plan, account) -> None:  # type: ignore[no-untyped-def]
        account.valid_call_to_action_types = ["LEARN_MORE"]
        assert "creative.cta_invalid" in codes(
            validate_plan(plan, account=account, check_assets=False), Severity.ERROR
        )


class TestDestinations:
    @pytest.mark.parametrize(
        ("url", "code"),
        [
            ("http://acme.example.com/webinar", "destination.not_https"),
            ("https://localhost/webinar", "destination.not_public"),
            ("https://acme.example.com/{{utm}}", "destination.unresolved_template"),
        ],
    )
    def test_problem_urls_are_flagged(self, url: str, code: str) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["destination_url"] = url

        assert code in codes(validate_plan(build(mutate), check_assets=False))

    def test_http_warns_but_does_not_block(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["destination_url"] = (
                "http://acme.example.com/webinar"
            )

        report = validate_plan(build(mutate), check_assets=False)
        assert "destination.not_https" in codes(report, Severity.WARNING)
        assert report.ok

    def test_localhost_blocks(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["destination_url"] = (
                "https://localhost:3000/webinar"
            )

        assert not validate_plan(build(mutate), check_assets=False).ok


class TestCreativeHonesty:
    def test_identical_angles_across_variants_warns(self) -> None:
        # Wording changes on one idea are one test, not several.
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "multi_variant"
            creative["variants"] = [
                {"angle": "time saved", "primary_text": "Get your Fridays back."},
                {"angle": "Time Saved", "primary_text": "Reclaim your Fridays."},
            ]

        report = validate_plan(build(mutate), check_assets=False)
        assert "creative.angles_not_distinct" in codes(report, Severity.WARNING)
        assert report.ok

    def test_distinct_angles_do_not_warn(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "multi_variant"
            creative["variants"] = [
                {"angle": "time saved", "primary_text": "Get your Fridays back."},
                {"angle": "audit risk", "primary_text": "Numbers nobody has to double-check."},
            ]

        assert "creative.angles_not_distinct" not in codes(
            validate_plan(build(mutate), check_assets=False)
        )

    def test_advantage_defaults_are_always_surfaced(self, plan) -> None:  # type: ignore[no-untyped-def]
        # A user should never learn from a preview that Meta altered a creative.
        assert "creative.advantage_default" in codes(
            validate_plan(plan, check_assets=False), Severity.INFO
        )

    def test_declared_advantage_settings_are_listed(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["advantage"] = {
                "enhancements": {"standard_enhancements": False, "text_improvements": True}
            }

        finding = next(
            f
            for f in validate_plan(build(mutate), check_assets=False).findings
            if f.code == "creative.advantage_declared"
        )
        assert "text_improvements" in finding.message
        assert "standard_enhancements" in finding.message


class TestNamingAndAudiences:
    def test_duplicate_ad_set_names_warn(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"].append(dict(raw["campaign"]["ad_sets"][0]))

        assert "naming.duplicate_ad_sets" in codes(
            validate_plan(build(mutate), check_assets=False), Severity.WARNING
        )

    def test_audience_both_included_and_excluded_blocks(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["targeting"].update(
                custom_audience_ids=["555"], excluded_custom_audience_ids=["555"]
            )

        assert "targeting.audience_included_and_excluded" in codes(
            validate_plan(build(mutate), check_assets=False), Severity.ERROR
        )

    def test_unknown_audience_blocks(self, account) -> None:  # type: ignore[no-untyped-def]
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["targeting"]["custom_audience_ids"] = ["555"]

        account.available_custom_audience_ids = ["666"]
        assert "targeting.audience_unknown" in codes(
            validate_plan(build(mutate), account=account, check_assets=False), Severity.ERROR
        )

    def test_advantage_audience_left_unset_with_hard_bounds_is_noted(self, plan) -> None:  # type: ignore[no-untyped-def]
        assert "targeting.advantage_audience_unset" in codes(
            validate_plan(plan, check_assets=False), Severity.INFO
        )


class TestLifetimeBudgetSchedule:
    def test_lifetime_budget_without_an_end_blocks(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["budget"]["type"] = "lifetime"

        assert "schedule.lifetime_needs_end" in codes(
            validate_plan(build(mutate), check_assets=False), Severity.ERROR
        )

    def test_lifetime_budget_with_an_end_is_fine(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["budget"]["type"] = "lifetime"
            raw["campaign"]["ad_sets"][0]["schedule"] = {
                "start": "2026-10-01T00:00:00Z",
                "end": "2026-10-31T00:00:00Z",
            }

        assert "schedule.lifetime_needs_end" not in codes(
            validate_plan(build(mutate), check_assets=False)
        )


class TestRoutingReport:
    def test_single_image_routes_to_the_mcp(self, plan) -> None:  # type: ignore[no-untyped-def]
        report = validate_plan(plan, check_assets=False)
        assert report.providers_used["create_single_image_creative"] == "official_mcp"
        assert not report.uses_fallback

    def test_video_creative_routes_to_the_fallback_and_says_why(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "single_video"
            creative["assets"] = [{"video_id": "999"}]

        report = validate_plan(build(mutate), check_assets=False)
        assert report.providers_used["create_video_creative"] == "api_fallback"
        assert report.uses_fallback
        finding = next(f for f in report.findings if f.code == "routing.fallback")
        assert "does not currently expose" in finding.message

    def test_local_image_routes_only_image_upload(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / "a.png", 1200, 628)

        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"] = [
                {"local_path": str(image)}
            ]

        report = validate_plan(build(mutate), check_assets=False)
        assert "local_image_upload" in report.providers_used
        # An image-only plan must not claim a video upload will happen.
        assert "local_video_upload" not in report.providers_used

    def test_local_video_routes_video_upload(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "single_video"
            creative["assets"] = [{"local_path": "./clip.mp4"}]

        report = validate_plan(build(mutate), check_assets=False)
        assert "local_video_upload" in report.providers_used


class TestAssetChecks:
    def test_a_valid_image_is_reported_with_its_fingerprint(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / "ok.png", 1200, 628)

        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"] = [
                {"local_path": str(image)}
            ]

        finding = next(
            f
            for f in validate_plan(build(mutate), asset_base=tmp_path).findings
            if f.code == "asset.ok"
        )
        assert "1200x628" in finding.message
        assert "sha256:" in finding.message

    def test_a_missing_asset_blocks(self) -> None:
        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"] = [
                {"local_path": "./nope.png"}
            ]

        assert "asset.unusable" in codes(validate_plan(build(mutate)), Severity.ERROR)

    def test_a_tiny_image_warns(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / "tiny.png", 80, 80)

        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"] = [
                {"local_path": str(image)}
            ]

        report = validate_plan(build(mutate), asset_base=tmp_path)
        assert "asset.warning" in codes(report, Severity.WARNING)
        assert report.ok

    def test_relative_paths_resolve_against_the_plan_directory(self, tmp_path: Path) -> None:
        # Makes a workspace portable between machines.
        (tmp_path / "creatives").mkdir()
        write_png(tmp_path / "creatives" / "a.png", 1200, 628)

        def mutate(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"] = [
                {"local_path": "./creatives/a.png"}
            ]

        report = validate_plan(build(mutate), asset_base=tmp_path)
        assert "asset.ok" in codes(report, Severity.INFO)

    def test_an_image_used_as_a_video_is_rejected(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / "still.png", 1200, 628)

        def mutate(raw):  # type: ignore[no-untyped-def]
            creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
            creative["mode"] = "single_video"
            creative["assets"] = [{"local_path": str(image)}]

        # The plan model rejects this first: a .png cannot satisfy single_video.
        with pytest.raises(Exception, match="video asset"):
            validate_plan(build(mutate), asset_base=tmp_path)
