"""``new-plan``: a plan drafted from the offer, brand.yaml and the cached account.

brand.yaml's ``account:`` block was documented as "defaults used to pre-fill a
campaign plan" and read by nothing. These tests hold the scaffold to two
promises: it uses what the workspace knows, and it invents nothing.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml

from conftest import write_png
from meta_ads_agent.cli.main import main
from meta_ads_agent.errors import ValidationError
from meta_ads_agent.models.brand import BrandConfig, Offer
from meta_ads_agent.models.plan import CopyVariant
from meta_ads_agent.scaffold import Asset, load_variants, relative_asset, scaffold_plan
from meta_ads_agent.validation import AccountContext, validate_plan
from meta_ads_agent.workspace import Workspace

BRAND: dict[str, Any] = {
    "name": "Acme",
    "account": {
        "ad_account_id": "act_1234567890",
        "page_id": "1111111111",
        "instagram_account_id": "2222222222",
        "dataset_id": "3333333333",
        "conversion_event": "LEAD",
        "countries": ["PL"],
        "objective": "OUTCOME_LEADS",
        "cta_type": "LEARN_MORE",
    },
    "dsa": {"beneficiary": "Acme Sp. z o.o.", "payor": "Acme Sp. z o.o."},
    "advantage_defaults": {"image_touchups": False},
}
OFFER: dict[str, Any] = {
    "name": "Webinar",
    "landing_page": "https://acme.example.com/webinar",
    "audience": "Marketing leads",
    "problem": "Fridays disappear",
    "outcome": "Fridays return",
    "cta": "SIGN_UP",
}
CREATED = dt.datetime(2026, 9, 16, 8, 0, tzinfo=dt.UTC)


def variant(angle: str = "time saved", **extra: str) -> CopyVariant:
    return CopyVariant(angle=angle, primary_text=f"Text about {angle}.", **extra)


def draft(**overrides: Any):  # type: ignore[no-untyped-def]
    args: dict[str, Any] = {
        "slug": "acme-webinar",
        "budget": Decimal("70"),
        "assets": [Asset(image_hash="abc123def456")],
        "variants": [variant()],
        "brand": BrandConfig.model_validate(BRAND),
        "offer": Offer.model_validate(OFFER),
        "offer_slug": "webinar",
        "account": AccountContext(id="act_1234567890", currency="PLN"),
        "created_at": CREATED,
    }
    args.update(overrides)
    return scaffold_plan(**args)


def creatives(result):  # type: ignore[no-untyped-def]
    return [ad.creative for ad in result.document.campaign.ad_sets[0].ads]


class TestFilledFromTheWorkspace:
    def test_the_brand_offer_and_account_fill_the_plan(self) -> None:
        result = draft()
        doc = result.document
        ad_set = doc.campaign.ad_sets[0]
        creative = ad_set.ads[0].creative
        assert doc.ad_account_id == "act_1234567890"
        assert (doc.brand, doc.offer) == ("Acme", "webinar")
        assert doc.campaign.objective == "OUTCOME_LEADS"
        assert doc.campaign.currency == "PLN"
        assert doc.campaign.dsa.beneficiary == "Acme Sp. z o.o."
        assert ad_set.targeting.countries == ["PL"]
        assert (ad_set.tracking.dataset_id, ad_set.tracking.conversion_event) == (
            "3333333333",
            "LEAD",
        )
        assert (creative.page_id, creative.instagram_account_id) == ("1111111111", "2222222222")
        assert creative.destination_url.startswith("https://acme.example.com/webinar")
        assert creative.advantage.enhancements == {"image_touchups": False}

    def test_it_says_where_each_value_came_from(self) -> None:
        sources = draft().sources
        assert sources["currency"] == "cached account"
        assert sources["creative.page_id"] == "brand.yaml account.page_id"
        assert sources["creative.destination_url"] == "offer landing_page"

    def test_a_flag_beats_the_offer_which_beats_the_brand(self) -> None:
        # The offer's CTA over the brand's default; a variant's own over both.
        result = draft(variants=[variant(), variant("proof", cta_type="DOWNLOAD")])
        assert [c.variants[0].cta_type for c in creatives(result)] == ["SIGN_UP", "DOWNLOAD"]
        overridden = draft(destination_url="https://acme.example.com/other", countries=["de"])
        assert overridden.sources["creative.destination_url"] == "--url"
        assert overridden.document.campaign.ad_sets[0].targeting.countries == ["DE"]

    def test_names_and_utms_are_rendered_already(self) -> None:
        doc = draft().document
        assert doc.campaign.name == "Acme | OUTCOME_LEADS | 2026-09-16"
        assert doc.campaign.ad_sets[0].name == "PL"
        url = doc.campaign.ad_sets[0].ads[0].creative.destination_url
        assert "utm_source=meta" in url and "utm_campaign=webinar_2026-09-16" in url

    def test_the_date_in_a_name_is_the_accounts_day(self) -> None:
        late = dt.datetime(2026, 9, 15, 22, 30, tzinfo=dt.UTC)
        doc = draft(created_at=late, tz=ZoneInfo("Europe/Warsaw")).document
        assert doc.campaign.name.endswith("2026-09-16")

    def test_the_accounts_only_page_is_used_and_one_of_two_is_not(self) -> None:
        bare = BrandConfig.model_validate({**BRAND, "account": {"countries": ["PL"]}})
        one = AccountContext(id="act_1234567890", currency="PLN", available_page_ids=["777"])
        result = draft(brand=bare, account=one, objective="OUTCOME_LEADS")
        assert result.sources["creative.page_id"] == "the account's only Page"
        two = AccountContext(id="act_1234567890", currency="PLN", available_page_ids=["7", "8"])
        with pytest.raises(ValidationError, match=r"creative\.page_id"):
            draft(brand=bare, account=two, objective="OUTCOME_LEADS")

    def test_with_no_brand_the_name_starts_at_the_objective(self) -> None:
        # The default template opens with {brand}, which nothing could fill.
        doc = draft(
            brand=None,
            objective="OUTCOME_LEADS",
            countries=["PL"],
            page_id="1111111111",
        ).document
        assert doc.campaign.name == "OUTCOME_LEADS | 2026-09-16"
        assert doc.brand is None

    def test_a_name_given_is_the_name(self) -> None:
        assert draft(campaign_name="Spring launch").document.campaign.name == "Spring launch"

    def test_the_draft_passes_validation(self) -> None:
        account = AccountContext(id="act_1234567890", currency="PLN")
        report = validate_plan(draft().document, account=account, check_assets=False)
        assert report.ok, report.render()

    def test_a_budget_on_the_ad_set_when_asked(self) -> None:
        doc = draft(budget_level="ad_set").document
        assert doc.campaign.budget is None
        assert str(doc.campaign.ad_sets[0].budget.amount) == "70"


class TestNothingIsInvented:
    def test_everything_missing_is_listed_at_once(self) -> None:
        with pytest.raises(ValidationError) as error:
            scaffold_plan(slug="x", budget=Decimal("70"), assets=[], variants=[])
        message = str(error.value)
        for name in (
            "ad_account_id",
            "currency",
            "campaign.objective",
            "targeting.countries",
            "creative.page_id",
            "creative.destination_url",
            "assets",
            "copy",
        ):
            assert f"- {name}:" in message, name

    def test_a_lifetime_budget_needs_its_end_date(self) -> None:
        with pytest.raises(ValidationError, match="lifetime budget needs an end date"):
            draft(budget_type="lifetime")
        end = dt.datetime(2026, 10, 31, 23, 59, tzinfo=dt.UTC)
        doc = draft(budget_type="lifetime", end=end).document
        assert doc.campaign.ad_sets[0].schedule.end == end

    def test_no_optimisation_goal_is_guessed(self) -> None:
        result = draft()
        assert result.document.campaign.ad_sets[0].optimization_goal is None
        assert any("optimisation goal" in note for note in result.notes)
        chosen = draft(optimization_goal="LEAD_GENERATION")
        assert chosen.document.campaign.ad_sets[0].optimization_goal == "LEAD_GENERATION"


class TestSplit:
    IMAGES = [Asset(local_path="creatives/square.png"), Asset(local_path="creatives/tall.png")]
    COPY = [variant("time saved"), variant("proof")]

    def test_one_ad_per_asset_named_apart(self) -> None:
        result = draft(assets=self.IMAGES)
        ads = result.document.campaign.ad_sets[0].ads
        assert [a.name for a in ads] == ["time saved | square", "time saved | tall"]
        assert [c.mode for c in creatives(result)] == ["single_image", "single_image"]

    def test_one_ad_per_variant(self) -> None:
        ads = draft(variants=self.COPY).document.campaign.ad_sets[0].ads
        assert [a.name for a in ads] == ["time saved", "proof"]

    def test_several_of_both_is_a_choice_it_will_not_make(self) -> None:
        with pytest.raises(ValidationError, match=r"--split matrix.*--split multi-variant"):
            draft(assets=self.IMAGES, variants=self.COPY)

    def test_matrix_is_every_pairing(self) -> None:
        result = draft(assets=self.IMAGES, variants=self.COPY, split="matrix")
        names = [a.name for a in result.document.campaign.ad_sets[0].ads]
        assert names == [
            "time saved | square",
            "time saved | tall",
            "proof | square",
            "proof | tall",
        ]
        assert any("= 4 ads" in note for note in result.notes)

    def test_multi_variant_is_one_ad_meta_mixes(self) -> None:
        result = draft(assets=self.IMAGES, variants=self.COPY, split="multi-variant")
        (creative,) = creatives(result)
        assert creative.mode == "multi_variant"
        assert (len(creative.assets), len(creative.variants)) == (2, 2)

    def test_a_video_becomes_a_video_ad(self) -> None:
        result = draft(assets=[Asset(video_id="700000000000031")])
        assert creatives(result)[0].mode == "single_video"

    @pytest.mark.parametrize(
        ("split", "extra", "message"),
        [
            ("per-asset", {"variants": COPY}, "takes one copy variant"),
            ("per-variant", {"assets": IMAGES}, "takes one asset"),
            (
                "multi-variant",
                {"assets": [Asset(image_hash="aaa111"), Asset(video_id="123")]},
                "images or videos, not both",
            ),
            ("sideways", {}, "split must be one of"),
        ],
    )
    def test_a_split_that_does_not_fit_is_refused(
        self, split: str, extra: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(ValidationError, match=message):
            draft(split=split, **extra)


class TestInputs:
    def test_copy_is_a_list_or_a_variants_key(self) -> None:
        items = [{"angle": "a", "primary_text": "A."}]
        assert load_variants(items, "copy.yaml")[0].angle == "a"
        assert load_variants({"variants": items}, "copy.yaml")[0].primary_text == "A."

    @pytest.mark.parametrize("raw", [None, [], {"variants": []}, "just text"])
    def test_copy_with_no_variants_says_what_is_expected(self, raw: Any) -> None:
        with pytest.raises(ValidationError, match="has no copy variants"):
            load_variants(raw, "copy.yaml")

    def test_copy_missing_its_text_names_the_file(self) -> None:
        with pytest.raises(ValidationError, match=r"copy\.yaml is not valid copy"):
            load_variants([{"angle": "a"}], "copy.yaml")

    def test_an_asset_path_is_written_relative_to_the_plan(self, tmp_path: Path) -> None:
        plan_dir = tmp_path / ".meta-ads" / "campaigns" / "spring"
        asset = tmp_path / "creatives" / "square.png"
        assert relative_asset(str(asset), plan_dir) == "../../../creatives/square.png"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("META_ADS_WORKSPACE", raising=False)
    workspace = Workspace.at(tmp_path / ".meta-ads")
    workspace.create()
    workspace.brand_file.write_text(yaml.safe_dump(BRAND), encoding="utf-8")
    workspace.offers_dir.mkdir(exist_ok=True)
    (workspace.offers_dir / "webinar.yaml").write_text(yaml.safe_dump(OFFER), encoding="utf-8")
    workspace.account_file.write_text(
        yaml.safe_dump({"id": "act_1234567890", "currency": "PLN"}), encoding="utf-8"
    )
    write_png(tmp_path / "square.png", 1080, 1080)
    (tmp_path / "copy.yaml").write_text(
        yaml.safe_dump([{"angle": "time saved", "primary_text": "Fridays, returned."}]),
        encoding="utf-8",
    )
    return workspace


ARGS = ["new-plan", "--slug", "spring", "--budget", "70", "--offer", "webinar"]
MEDIA = ["--assets", "square.png", "--copy", "copy.yaml"]


class TestCommand:
    def test_without_write_nothing_is_saved(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main([*ARGS, *MEDIA]) == 0
        out = capsys.readouterr().out
        assert "nothing written" in out and "single_image" in out
        assert not project.plan_file("spring").exists()

    def test_a_written_plan_validates_with_its_local_asset(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main([*ARGS, *MEDIA, "--write", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["written"] is True and payload["ads"] == 1
        assert payload["sources"]["creative.destination_url"] == "offer landing_page"
        plan = project.plan_file("spring")
        assert main(["validate-plan", str(plan), "--json"]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["ok"] is True
        assert "asset.ok" in {f["code"] for f in report["findings"]}

    def test_an_existing_plan_is_not_overwritten(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main([*ARGS, *MEDIA, "--write"]) == 0
        assert main([*ARGS, *MEDIA, "--write"]) == 1
        assert "already exists" in capsys.readouterr().err

    def test_copy_saved_by_the_creative_skill_is_found(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        saved = project.copy_file("spring")
        saved.parent.mkdir(parents=True)
        saved.write_text(
            yaml.safe_dump({"variants": [{"angle": "proof", "primary_text": "340 came."}]}),
            encoding="utf-8",
        )
        assert main([*ARGS, "--assets", "square.png", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["ads"] == 1

    def test_what_is_missing_exits_2_with_the_list(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(ARGS) == 2
        err = capsys.readouterr().err
        assert "- assets:" in err and "- copy:" in err

    def test_an_unknown_offer_names_the_ones_there_are(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["new-plan", "--slug", "x", "--budget", "70", "--offer", "nope", *MEDIA]) == 2
        assert "Offers here:" in capsys.readouterr().err

    def test_write_without_a_workspace_exits_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("META_ADS_WORKSPACE", raising=False)
        assert main(["new-plan", "--slug", "x", "--budget", "70", "--write"]) == 2
        assert "meta-ads-agent init" in capsys.readouterr().err
