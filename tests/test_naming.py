"""Brand naming and UTM templates, applied deterministically.

Before this module the templates were documented as "substituted at plan
time" and substituted by nothing: the agent expanded them in prose, so two
builds could disagree about what a token meant.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
import yaml

from conftest import plan_dict
from meta_ads_agent.cli.main import main
from meta_ads_agent.errors import ValidationError
from meta_ads_agent.models.brand import BrandConfig
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.naming import audience_label, has_placeholders, render, render_plan, with_utm
from meta_ads_agent.validation import Severity, validate_plan

CREATED = "2026-09-16T08:00:00Z"


def templated(**overrides):  # type: ignore[no-untyped-def]
    raw = plan_dict(created_at=CREATED, **overrides)
    raw["campaign"]["name"] = "{brand} | {objective} | {date}"
    raw["campaign"]["ad_sets"][0]["name"] = "{audience}"
    raw["campaign"]["ad_sets"][0]["ads"][0]["name"] = "{audience} | {variant}"
    return CampaignPlanDocument.model_validate(raw)


def brand(**utm: str | None) -> BrandConfig:
    return BrandConfig.model_validate({"name": "Acme", "utm": utm} if utm else {"name": "Acme"})


class TestRender:
    def test_known_tokens_are_substituted(self) -> None:
        assert render("{brand}-{date}", {"brand": "Acme", "date": "2026"}, where="x") == "Acme-2026"

    def test_an_unknown_token_is_an_error_naming_it(self) -> None:
        with pytest.raises(ValidationError, match=r"unknown token\(s\) \{colour\}"):
            render("{colour}", {}, where="campaign.name")

    def test_a_token_with_no_value_is_an_error_not_an_empty_string(self) -> None:
        with pytest.raises(ValidationError, match=r"\{offer\} has no value"):
            render("{offer}_{date}", {"offer": None, "date": "2026"}, where="utm")

    @pytest.mark.parametrize(
        ("targeting", "label"),
        [
            ({"countries": ["PL"], "age_min": 25, "age_max": 55}, "PL 25-55"),
            ({"countries": ["DE", "AT"], "age_min": 18}, "DE AT 18+"),
            ({"countries": ["PL"]}, "PL"),
        ],
    )
    def test_audience_label(self, targeting: dict[str, object], label: str) -> None:
        from meta_ads_agent.models.plan import TargetingPlan

        assert audience_label(TargetingPlan.model_validate(targeting)) == label

    def test_literal_braces_that_are_not_tokens_are_not_placeholders(self) -> None:
        assert not has_placeholders("Summer {2026} Sale")
        assert has_placeholders("{brand} sale")


class TestBadTemplates:
    @pytest.mark.parametrize("template", ["{date} {", "{brand} 50%}", "{brand} {date:%Y}"])
    def test_a_malformed_template_is_a_validation_error_not_a_crash(self, template: str) -> None:
        with pytest.raises(ValidationError, match=r"campaign\.name"):
            render(template, {"brand": "Acme", "date": "2026"}, where="campaign.name")

    def test_a_literal_brace_can_still_be_written(self) -> None:
        assert render("{brand} {{sale}}", {"brand": "Acme"}, where="x") == "Acme {sale}"

    def test_render_plan_reports_it_through_the_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        raw = plan_dict(created_at=CREATED)
        raw["campaign"]["name"] = "{date} {"
        path = tmp_path / "plan.yaml"
        path.write_text(yaml.safe_dump(raw))
        assert main(["render-plan", str(path)]) == 1
        assert "not a valid template" in capsys.readouterr().err


class TestUtm:
    def test_parameters_are_appended(self) -> None:
        assert with_utm("https://a.example/p", {"utm_source": "meta"}) == (
            "https://a.example/p?utm_source=meta"
        )

    def test_an_existing_parameter_is_never_overwritten(self) -> None:
        url = "https://a.example/p?utm_source=newsletter&x=1"
        assert with_utm(url, {"utm_source": "meta", "utm_medium": "paid"}) == (
            "https://a.example/p?utm_source=newsletter&x=1&utm_medium=paid"
        )

    def test_the_fragment_survives(self) -> None:
        assert with_utm("https://a.example/p#form", {"utm_source": "meta"}).endswith("#form")


class TestRenderPlan:
    def test_names_are_rendered_from_the_plan_and_brand(self) -> None:
        result = render_plan(templated(), brand())
        campaign = result.document.campaign
        assert campaign.name == "Acme | OUTCOME_LEADS | 2026-09-16"
        assert campaign.ad_sets[0].name == "PL 25-55"
        assert campaign.ad_sets[0].ads[0].name == "PL 25-55 | time saved"

    def test_brand_utms_and_ad_set_overrides_reach_the_url(self) -> None:
        doc = templated()
        doc.campaign.ad_sets[0].tracking.utm = {"medium": "cpc"}
        url = render_plan(doc, brand()).document.campaign.ad_sets[0].ads[0].creative
        assert url.destination_url == (
            "https://acme.example.com/webinar?utm_source=meta&utm_medium=cpc"
            "&utm_campaign=webinar_2026-09-16&utm_content=time+saved"
        )

    def test_without_brand_config_only_the_ad_sets_own_utms_apply(self) -> None:
        doc = templated()
        doc.campaign.ad_sets[0].tracking.utm = {"utm_source": "meta"}
        creative = render_plan(doc, None).document.campaign.ad_sets[0].ads[0].creative
        assert creative.destination_url == "https://acme.example.com/webinar?utm_source=meta"

    def test_rendering_twice_changes_nothing_the_second_time(self) -> None:
        once = render_plan(templated(), brand()).document
        again = render_plan(once, brand())
        assert not again.changed
        assert again.document == once

    def test_a_plan_without_tokens_is_left_exactly_as_written(self) -> None:
        doc = CampaignPlanDocument.model_validate(plan_dict(created_at=CREATED))
        result = render_plan(doc, None)
        assert not result.changed
        assert result.document == doc

    def test_a_brand_template_needing_a_missing_offer_is_refused(self) -> None:
        doc = templated(offer=None)
        with pytest.raises(ValidationError, match=r"\{offer\} has no value"):
            render_plan(doc, brand())

    def test_the_date_is_the_plans_not_todays(self) -> None:
        doc = templated()
        assert doc.created_at.date() == dt.date(2026, 9, 16)
        assert "2026-09-16" in render_plan(doc, brand()).document.campaign.name


class TestCarouselCardLinks:
    @staticmethod
    def _carousel() -> CampaignPlanDocument:
        raw = plan_dict(created_at=CREATED)
        creative = raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]
        creative["mode"] = "carousel"
        creative["assets"] = []
        creative["cards"] = [
            {"asset": {"image_hash": "a"}, "link": "https://acme.example.com/a"},
            {"asset": {"image_hash": "b"}},
        ]
        return CampaignPlanDocument.model_validate(raw)

    def test_a_cards_own_link_gets_the_utms_too(self) -> None:
        creative = (
            render_plan(self._carousel(), brand()).document.campaign.ad_sets[0].ads[0].creative
        )
        assert creative.cards[0].link is not None
        assert "utm_source=meta" in creative.cards[0].link
        assert creative.cards[1].link is None  # it uses the destination, which has them

    def test_the_validator_notices_a_card_link_without_them(self) -> None:
        doc = self._carousel()
        doc.campaign.ad_sets[0].tracking.utm = {"utm_source": "meta"}
        doc.campaign.ad_sets[0].ads[
            0
        ].creative.destination_url = "https://acme.example.com/webinar?utm_source=meta"
        paths = {
            f.path
            for f in validate_plan(doc, check_assets=False).findings
            if f.code == "tracking.utm_not_applied"
        }
        assert paths == {"campaign.ad_sets[0].ads[0].creative.cards[0].link"}


class TestValidatorRefusesWhatWasNotRendered:
    def test_an_unrendered_name_blocks(self) -> None:
        report = validate_plan(templated(), check_assets=False)
        assert "naming.unrendered" in {f.code for f in report.errors}

    def test_a_rendered_plan_passes_that_check(self) -> None:
        report = validate_plan(render_plan(templated(), brand()).document, check_assets=False)
        assert "naming.unrendered" not in {f.code for f in report.findings}

    def test_utms_named_but_not_in_the_url_warn(self) -> None:
        doc = CampaignPlanDocument.model_validate(plan_dict())
        doc.campaign.ad_sets[0].tracking.utm = {"utm_source": "meta"}
        report = validate_plan(doc, check_assets=False)
        assert "tracking.utm_not_applied" in {
            f.code for f in report.findings if f.severity is Severity.WARNING
        }

    def test_an_asset_pinned_to_a_placement_outside_multi_variant_is_refused(self) -> None:
        # Only asset customisation rules - mode=multi_variant - can honour it.
        from pydantic import ValidationError as PydanticValidationError

        raw = plan_dict()
        raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]["assets"][0]["placement"] = (
            "instagram_stories"
        )
        with pytest.raises(PydanticValidationError, match="needs mode=multi_variant"):
            CampaignPlanDocument.model_validate(raw)


class TestRenderPlanCommand:
    @pytest.fixture
    def plan_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("META_ADS_WORKSPACE", raising=False)
        (tmp_path / "brand.yaml").write_text(yaml.safe_dump({"name": "Acme"}))
        path = tmp_path / "plan.yaml"
        path.write_text(yaml.safe_dump(templated().model_dump(mode="json", exclude_none=True)))
        return path

    def test_without_write_nothing_changes_on_disk(
        self, plan_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        before = plan_file.read_text()
        assert main(["render-plan", str(plan_file), "--brand-file", "brand.yaml"]) == 0
        assert "Acme | OUTCOME_LEADS | 2026-09-16" in capsys.readouterr().out
        assert plan_file.read_text() == before

    def test_write_saves_a_plan_that_then_validates_its_names(
        self, plan_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = ["render-plan", str(plan_file), "--brand-file", "brand.yaml", "--write", "--json"]
        assert main(argv) == 0
        assert json.loads(capsys.readouterr().out)["written"] is True
        saved = CampaignPlanDocument.model_validate(yaml.safe_load(plan_file.read_text()))
        assert saved.campaign.name == "Acme | OUTCOME_LEADS | 2026-09-16"
        assert "naming.unrendered" not in {
            f.code for f in validate_plan(saved, check_assets=False).findings
        }

    def test_an_unrenderable_template_exits_1(
        self, plan_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        raw = yaml.safe_load(plan_file.read_text())
        raw["campaign"]["name"] = "{colour}"
        plan_file.write_text(yaml.safe_dump(raw))
        assert main(["render-plan", str(plan_file)]) == 1
        assert "{colour}" in capsys.readouterr().err
