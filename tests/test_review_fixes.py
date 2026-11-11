"""Regressions for the defects the 2026-11-11 review found.

Each test is the input that used to go wrong, named for what went wrong.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml
from pydantic import ValidationError as PydanticValidationError

from conftest import plan_dict, write_png
from meta_ads_agent.cli.main import main
from meta_ads_agent.errors import ValidationError
from meta_ads_agent.models.brand import BrandConfig
from meta_ads_agent.models.plan import CampaignPlanDocument
from meta_ads_agent.naming import has_placeholders, render, render_plan, with_utm
from meta_ads_agent.state.assets import AssetKind, probe_asset
from meta_ads_agent.validation import AccountContext, Severity, validate_plan
from meta_ads_agent.workspace import Workspace


def build(mutate=None, **overrides):  # type: ignore[no-untyped-def]
    raw = plan_dict(**overrides)
    if mutate:
        mutate(raw)
    return CampaignPlanDocument.model_validate(raw)


def codes(report, severity=None):  # type: ignore[no-untyped-def]
    return {f.code for f in report.findings if severity is None or f.severity is severity}


def creative(raw):  # type: ignore[no-untyped-def]
    return raw["campaign"]["ad_sets"][0]["ads"][0]["creative"]


def set_currency(raw, code: str) -> None:  # type: ignore[no-untyped-def]
    raw["campaign"]["ad_sets"][0]["budget"]["currency"] = code


class TestCurrency:
    def test_a_currency_the_table_lacks_is_fine_when_meta_gave_its_offset(self) -> None:
        plan = build(lambda raw: set_currency(raw, "XQZ"))
        account = AccountContext(id="act_1234567890", currency="XQZ", currency_offset=100)
        report = validate_plan(plan, account=account, check_assets=False)
        assert "currency.unknown_scale" not in codes(report)
        assert "currency.scale_from_account" in codes(report, Severity.INFO)

    def test_it_is_still_unknown_without_the_accounts_offset(self) -> None:
        plan = build(lambda raw: set_currency(raw, "XQZ"))
        report = validate_plan(plan, check_assets=False)
        assert "currency.unknown_scale" in codes(report, Severity.ERROR)

    def test_another_currencys_offset_is_not_compared_with_the_plans(self) -> None:
        # JPY has no minor unit, PLN has two: the mismatch is the finding,
        # and "offset differs" beside it only confused the reader.
        account = AccountContext(id="act_1234567890", currency="JPY", currency_offset=1)
        report = validate_plan(build(), account=account, check_assets=False)
        assert "currency.mismatch" in codes(report, Severity.ERROR)
        assert "currency.offset_differs" not in codes(report)


class TestSpecialCategories:
    def test_a_category_the_brand_declares_and_the_plan_omits_is_an_error(self) -> None:
        brand = BrandConfig.model_validate(
            {"name": "Acme", "special_ad_category": ["HOUSING", "CREDIT"]}
        )

        def declare(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["special_ad_categories"] = ["CREDIT"]

        report = validate_plan(build(declare), brand=brand, check_assets=False)
        finding = next(f for f in report.findings if f.code == "special_category.not_declared")
        assert finding.severity is Severity.ERROR
        assert "HOUSING" in finding.message

    def test_a_retired_category_names_its_replacement(self) -> None:
        def declare(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["special_ad_categories"] = ["CREDIT"]

        report = validate_plan(build(declare), check_assets=False)
        finding = next(f for f in report.findings if f.code == "special_category.retired")
        assert finding.severity is Severity.WARNING
        assert "FINANCIAL_PRODUCTS_SERVICES" in finding.message

    def test_declaring_everything_the_brand_does_passes(self) -> None:
        brand = BrandConfig.model_validate({"name": "Acme", "special_ad_category": ["CREDIT"]})

        def declare(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["special_ad_categories"] = ["CREDIT", "HOUSING"]

        report = validate_plan(build(declare), brand=brand, check_assets=False)
        assert "special_category.not_declared" not in codes(report)


class TestOneAssetPerSingleCreative:
    def test_a_single_image_with_two_images_does_not_validate(self) -> None:
        def two(raw):  # type: ignore[no-untyped-def]
            creative(raw)["assets"] = [{"image_hash": "aaa111"}, {"image_hash": "bbb222"}]

        # It still loads: a plan an earlier release accepted must stay readable.
        report = validate_plan(build(two), check_assets=False)
        finding = next(f for f in report.findings if f.code == "creative.one_asset")
        assert finding.severity is Severity.ERROR
        assert "lists 2" in finding.message

    def test_a_video_with_an_image_beside_it_points_at_thumbnail(self) -> None:
        def mixed(raw):  # type: ignore[no-untyped-def]
            creative(raw)["mode"] = "single_video"
            creative(raw)["assets"] = [{"video_id": "123456"}, {"image_hash": "aaa111"}]

        report = validate_plan(build(mixed), check_assets=False)
        finding = next(f for f in report.findings if f.code == "creative.one_asset")
        assert "thumbnail" in finding.message

    def test_one_asset_is_fine(self) -> None:
        assert "creative.one_asset" not in codes(validate_plan(build(), check_assets=False))

    def test_a_video_takes_a_thumbnail(self) -> None:
        def video(raw):  # type: ignore[no-untyped-def]
            creative(raw)["mode"] = "single_video"
            creative(raw)["assets"] = [{"video_id": "123456"}]
            creative(raw)["thumbnail"] = {"image_hash": "aaa111"}

        plan = build(video)
        refs = plan.campaign.ad_sets[0].ads[0].creative.asset_refs()
        assert [where for where, _ in refs] == ["assets[0]", "thumbnail"]

    @pytest.mark.parametrize(
        ("thumbnail", "message"),
        [
            ({"video_id": "999"}, "a thumbnail is an image"),
            ({"local_path": "./cover.mp4"}, "a thumbnail is an image"),
        ],
    )
    def test_a_thumbnail_is_an_image(self, thumbnail, message: str) -> None:  # type: ignore[no-untyped-def]
        def video(raw):  # type: ignore[no-untyped-def]
            creative(raw)["mode"] = "single_video"
            creative(raw)["assets"] = [{"video_id": "123456"}]
            creative(raw)["thumbnail"] = thumbnail

        with pytest.raises(PydanticValidationError, match=message):
            build(video)

    def test_a_thumbnail_on_an_image_ad_is_refused(self) -> None:
        def stray(raw):  # type: ignore[no-untyped-def]
            creative(raw)["thumbnail"] = {"image_hash": "aaa111"}

        with pytest.raises(PydanticValidationError, match="only valid with mode=single_video"):
            build(stray)


class TestFileIsWhatThePlanUsesItAs:
    def test_an_mp4_named_jpg_is_caught_for_a_single_image(
        self, tmp_path: Path, fake_mp4: Path
    ) -> None:
        disguised = tmp_path / "photo.jpg"
        disguised.write_bytes(fake_mp4.read_bytes())

        def local(raw):  # type: ignore[no-untyped-def]
            creative(raw)["assets"] = [{"local_path": "photo.jpg"}]

        report = validate_plan(build(local), asset_base=tmp_path)
        finding = next(f for f in report.findings if f.code == "asset.unusable")
        assert "looks like a video but was used as an image" in finding.message

    def test_an_image_among_a_multi_variants_videos_is_caught_by_content(
        self, tmp_path: Path, fake_mp4: Path
    ) -> None:
        write_png(tmp_path / "really-a-picture.mp4", 1080, 1080)
        (tmp_path / "clip.mp4").write_bytes(fake_mp4.read_bytes())

        def local(raw):  # type: ignore[no-untyped-def]
            creative(raw)["mode"] = "multi_variant"
            creative(raw)["assets"] = [
                {"local_path": "clip.mp4"},
                {"local_path": "really-a-picture.mp4"},
            ]

        report = validate_plan(build(local), asset_base=tmp_path)
        assert [f.path for f in report.findings if f.code == "asset.unusable"] == [
            "campaign.ad_sets[0].ads[0].creative.assets[1]"
        ]

    @pytest.mark.parametrize("brand", [b"heic", b"mif1", b"avif"])
    def test_a_heic_or_avif_still_is_not_a_video(self, tmp_path: Path, brand: bytes) -> None:
        still = tmp_path / "photo.heic"
        still.write_bytes(b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 256)
        with pytest.raises(ValidationError, match="HEIC/HEIF or AVIF image"):
            probe_asset(still)

    def test_an_mp4_is_still_a_video(self, fake_mp4: Path) -> None:
        assert probe_asset(fake_mp4).kind is AssetKind.VIDEO


class TestMetaMacrosInUrls:
    URL = "https://acme.example.com/webinar?utm_content={{ad.name}}&src={{site_source_name}}"

    def test_a_destination_with_metas_own_macros_is_finished(self) -> None:
        def macro(raw):  # type: ignore[no-untyped-def]
            creative(raw)["destination_url"] = self.URL

        report = validate_plan(build(macro), check_assets=False)
        assert "destination.unresolved_template" not in codes(report)

    @pytest.mark.parametrize(
        "url",
        [
            "https://acme.example.com/?utm_content={{variant}}",
            "https://acme.example.com/?utm_content={{ad.title}}",
            "https://acme.example.com/<landing>",
        ],
    )
    def test_anything_else_in_braces_is_still_unresolved(self, url: str) -> None:
        def unresolved(raw):  # type: ignore[no-untyped-def]
            creative(raw)["destination_url"] = url

        report = validate_plan(build(unresolved), check_assets=False)
        assert "destination.unresolved_template" in codes(report, Severity.ERROR)

    def test_a_macro_is_not_one_of_our_placeholders(self) -> None:
        assert not has_placeholders("x={{placement}}&y={{campaign.id}}")
        assert has_placeholders("x={{placement}}&y={variant}")

    def test_rendering_leaves_a_macro_exactly_as_written(self) -> None:
        out = render("{offer}_{{ad.name}}_{date}", {"offer": "webinar", "date": "2026"}, where="x")
        assert out == "webinar_{{ad.name}}_2026"

    def test_a_macro_in_a_utm_reaches_the_url_unencoded(self) -> None:
        url = with_utm("https://acme.example.com/", {"utm_content": "{{ad.name}}"})
        assert url == "https://acme.example.com/?utm_content={{ad.name}}"


class TestRenderPlan:
    def test_a_utm_the_url_already_has_is_not_rendered_at_all(self) -> None:
        # The brand's default utm_campaign is "{offer}_{date}". With no offer
        # that used to fail the whole render, for a parameter never added.
        def no_offer(raw):  # type: ignore[no-untyped-def]
            raw.pop("offer")
            creative(raw)["destination_url"] = "https://acme.example.com/?utm_campaign=spring"

        brand = BrandConfig.model_validate({"name": "Acme"})
        result = render_plan(build(no_offer), brand)
        url = result.document.campaign.ad_sets[0].ads[0].creative.destination_url
        assert "utm_campaign=spring" in url and "utm_source=meta" in url

    def test_a_missing_token_still_fails_a_parameter_that_would_be_added(self) -> None:
        brand = BrandConfig.model_validate({"name": "Acme"})
        with pytest.raises(ValidationError, match=r"\{offer\} has no value"):
            render_plan(build(lambda raw: raw.pop("offer")), brand)

    def test_the_date_is_the_accounts_calendar_day(self) -> None:
        # 22:30 UTC on the 15th is 00:30 on the 16th in Warsaw.
        def named(raw):  # type: ignore[no-untyped-def]
            raw["campaign"]["name"] = "{brand} {date}"

        plan = build(named, created_at="2026-09-15T22:30:00Z")
        assert render_plan(plan, None).document.campaign.name == "Acme 2026-09-15"
        warsaw = render_plan(plan, None, tz=ZoneInfo("Europe/Warsaw"))
        assert warsaw.document.campaign.name == "Acme 2026-09-16"

    def test_escaped_braces_around_a_token_are_refused(self) -> None:
        # "{{brand}}" came out as "{brand}" and was expanded by the next render.
        with pytest.raises(ValidationError, match="the next render would expand"):
            render("{{brand}} | {date}", {"brand": "Acme", "date": "2026"}, where="campaign.name")

    def test_other_literal_braces_are_kept(self) -> None:
        assert render("{{sale}} {date}", {"date": "2026"}, where="x") == "{sale} 2026"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    monkeypatch.chdir(tmp_path)
    workspace = Workspace.at(tmp_path / ".meta-ads")
    workspace.create()
    return workspace


def save_plan(workspace: Workspace, raw=None) -> Path:  # type: ignore[no-untyped-def]
    target = workspace.plan_file("acme-webinar")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(raw or plan_dict()), encoding="utf-8")
    return target


class TestValidatePlanCommand:
    def test_a_broken_workspace_brand_file_fails_the_plan(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # It was "ignored", the special-category and EU checks were skipped,
        # and the plan came back valid.
        project.brand_file.write_text("name: [unclosed", encoding="utf-8")
        code = main(["validate-plan", str(save_plan(project)), "--skip-assets", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert code == 1
        assert payload["ok"] is False
        assert "brand.unreadable" in {f["code"] for f in payload["findings"]}

    @pytest.mark.parametrize(
        "content",
        [
            "slug: acme\n".encode("utf-16"),
            b"- just\n- a list\n",
        ],
    )
    def test_a_plan_that_is_not_utf8_yaml_mapping_exits_2(
        self, project: Workspace, capsys: pytest.CaptureFixture[str], content: bytes
    ) -> None:
        target = project.plan_file("acme-webinar")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        assert main(["validate-plan", str(target)]) == 2
        assert "Traceback" not in capsys.readouterr().err

    def test_a_directory_given_as_the_plan_exits_2(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["validate-plan", str(project.root)]) == 2
        assert "could not be read" in capsys.readouterr().err


class TestRenderPlanCommand:
    def test_a_missing_brand_file_exits_2_like_validate_plan(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        plan = save_plan(project)
        assert main(["render-plan", str(plan), "--brand-file", "nope.yaml"]) == 2
        assert main(["validate-plan", str(plan), "--brand-file", "nope.yaml"]) == 2
        assert "does not exist" in capsys.readouterr().err

    def test_the_date_follows_the_cached_accounts_timezone(
        self, project: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        raw = plan_dict(created_at="2026-09-15T22:30:00Z")
        raw["campaign"]["name"] = "{brand} {date}"
        plan = save_plan(project, raw)
        project.account_file.write_text(
            yaml.safe_dump({"id": "act_1234567890", "timezone_name": "Europe/Warsaw"}),
            encoding="utf-8",
        )
        assert main(["render-plan", str(plan), "--json"]) == 0
        changes = json.loads(capsys.readouterr().out)["changes"]
        assert changes[0]["to"] == "Acme 2026-09-16"


def test_created_at_fixture_is_utc() -> None:
    # The timezone tests above rely on the plan storing an aware UTC moment.
    plan = build(created_at="2026-09-15T22:30:00Z")
    assert plan.created_at.utcoffset() == dt.timedelta(0)


class TestCliRobustness:
    @pytest.mark.parametrize("name", ["Acme: Shoes", "#1 Shop", 'Say "hi"', "Zażółć & Co."])
    def test_init_writes_any_brand_name_as_valid_yaml(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        # Inserted bare, "Acme: Shoes" was a mapping and "#1 Shop" a comment.
        monkeypatch.chdir(tmp_path)
        assert main(["init", "--brand", name]) == 0
        capsys.readouterr()
        brand = yaml.safe_load((tmp_path / ".meta-ads" / "brand.yaml").read_text(encoding="utf-8"))
        assert brand["name"] == name
        assert main(["init", "--check"]) == 0

    def test_doctor_survives_a_host_binary_that_prints_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        from meta_ads_agent.cli import doctor

        monkeypatch.setattr(
            doctor.subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="", stderr=""),
        )
        assert doctor._binary_version("/usr/bin/claude") == ""

    def test_doctor_reports_a_bad_graph_version_and_carries_on(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("META_GRAPH_API_VERSION", "26")
        main(["doctor", "--json"])
        checks = {c["label"]: c for c in json.loads(capsys.readouterr().out)["checks"]}
        assert checks["graph api version"]["status"] == "INVALID"
        # The checks after it still ran.
        assert "workspace" in " ".join(checks)

    def test_report_without_an_analysis_is_not_success(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["report"]) == 2
        assert "compare" in capsys.readouterr().out

    def test_fatigue_says_that_it_ignores_a_level(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # It used to accept --level and silently do nothing with it. The flag
        # stays - names are not removed within a major version - and says so.
        rows = tmp_path / "rows.json"
        rows.write_text("[]", encoding="utf-8")
        main(["report", "fatigue", str(rows), "--level", "campaign"])
        assert "--level campaign is ignored" in capsys.readouterr().err
        main(["report", "fatigue", str(rows), "--level", "ad"])
        assert "ignored" not in capsys.readouterr().err

    @pytest.mark.parametrize("command", [["compare", "--days", "7"], ["fatigue"]])
    def test_a_missing_brand_file_exits_2_for_reports_too(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], command: list[str]
    ) -> None:
        rows = tmp_path / "rows.json"
        rows.write_text("[]", encoding="utf-8")
        assert main(["report", *command, str(rows), "--brand-file", "nope.yaml"]) == 2
        assert "does not exist" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "content", ['[{"spend": "1"}]'.encode("utf-16"), b"\xff\xfe not json at all"]
    )
    def test_insights_that_are_not_utf8_exit_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes
    ) -> None:
        rows = tmp_path / "rows.json"
        rows.write_bytes(content)
        assert main(["report", "compare", str(rows), "--days", "7"]) == 2
        assert "not UTF-8" in capsys.readouterr().err

    def test_insights_given_a_directory_exit_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["report", "compare", str(tmp_path), "--days", "7"]) == 2
        assert "could not be read" in capsys.readouterr().err

    def test_a_lift_too_small_for_a_float_is_an_error_not_a_crash(self) -> None:
        from meta_ads_agent.analysis.power import PowerInputs, sample_size_per_cell

        inputs = PowerInputs(baseline_rate=0.02, units_per_day_per_cell=1000, cells=2)
        with pytest.raises(ValidationError, match="too small to tell"):
            sample_size_per_cell(inputs, 1e-20)

    def test_one_bad_byte_does_not_hide_the_rest_of_the_action_log(
        self, project: Workspace
    ) -> None:
        from meta_ads_agent.state.actionlog import ActionLog, ActionRecord

        log = ActionLog(project)
        log.append(ActionRecord(operation="first"))
        with log.path.open("ab") as stream:
            stream.write(b'{"operation": "bro\xffken"}\n')
        log.append(ActionRecord(operation="third"))
        assert [r.operation for r in log.read()] == ["first", "third"]


class TestCopyLint:
    BRAND = BrandConfig.model_validate(
        {"name": "Acme", "banned_phrases": ["risk free", "Guaranteed results", "  "]}
    )

    def test_a_banned_phrase_blocks_whatever_its_case_or_spacing(self) -> None:
        def banned(raw):  # type: ignore[no-untyped-def]
            variant = creative(raw)["variants"][0]
            variant["primary_text"] = "Try it RISK   free for a month."
            variant["headline"] = "guaranteed Results, or not"

        report = validate_plan(build(banned), brand=self.BRAND, check_assets=False)
        hits = [f for f in report.findings if f.code == "copy.banned_phrase"]
        assert not report.ok
        assert {f.path.rsplit(".", 1)[1] for f in hits} == {"primary_text", "headline"}
        assert "'risk free'" in hits[0].message

    def test_clean_copy_passes_and_a_blank_phrase_matches_nothing(self) -> None:
        report = validate_plan(build(), brand=self.BRAND, check_assets=False)
        assert "copy.banned_phrase" not in codes(report)

    def test_carousel_card_text_is_read_too(self) -> None:
        def carousel(raw):  # type: ignore[no-untyped-def]
            c = creative(raw)
            c["mode"] = "carousel"
            c.pop("assets")
            c["cards"] = [
                {"asset": {"image_hash": "aaa111"}, "headline": "Risk free trial"},
                {"asset": {"image_hash": "bbb222"}, "headline": "Fine"},
            ]

        report = validate_plan(build(carousel), brand=self.BRAND, check_assets=False)
        assert [f.path for f in report.findings if f.code == "copy.banned_phrase"] == [
            "campaign.ad_sets[0].ads[0].creative.cards[0].headline"
        ]

    def test_without_a_brand_there_is_no_rule_to_break(self) -> None:
        def banned(raw):  # type: ignore[no-untyped-def]
            creative(raw)["variants"][0]["primary_text"] = "risk free"

        assert "copy.banned_phrase" not in codes(validate_plan(build(banned), check_assets=False))


class TestMultiVariantLimits:
    @staticmethod
    def multi(assets: int, texts: int):  # type: ignore[no-untyped-def]
        def mutate(raw):  # type: ignore[no-untyped-def]
            c = creative(raw)
            c["mode"] = "multi_variant"
            c["assets"] = [{"image_hash": f"hash{i:04d}"} for i in range(assets)]
            c["variants"] = [
                {"angle": f"angle {i}", "primary_text": f"Text number {i}"} for i in range(texts)
            ]

        return build(mutate)

    def test_within_the_limits_says_nothing(self) -> None:
        report = validate_plan(self.multi(10, 5), check_assets=False)
        assert not {c for c in codes(report) if c.startswith("creative.multi_variant")}

    def test_eleven_assets_or_six_texts_are_errors(self) -> None:
        report = validate_plan(self.multi(11, 6), check_assets=False)
        limits = [f for f in report.findings if f.code == "creative.multi_variant_limits"]
        assert [f.severity for f in limits] == [Severity.ERROR, Severity.ERROR]
        assert "11 assets" in limits[0].message and "6 different primary_text" in limits[1].message

    def test_text_variants_on_one_asset_are_fine_for_a_leads_campaign(self) -> None:
        report = validate_plan(self.multi(1, 3), check_assets=False)
        assert "creative.text_variants_objective" not in codes(report)

    def test_text_variants_on_one_asset_warn_under_traffic(self) -> None:
        plan = self.multi(1, 3)
        plan.campaign.objective = "OUTCOME_TRAFFIC"
        report = validate_plan(plan, check_assets=False)
        assert report.ok
        assert "creative.text_variants_objective" in codes(report, Severity.WARNING)


class TestAspectAgainstPlacement:
    @staticmethod
    def plan(positions: list[str] | None, *, pinned: str | None = None):  # type: ignore[no-untyped-def]
        def mutate(raw):  # type: ignore[no-untyped-def]
            ad_set = raw["campaign"]["ad_sets"][0]
            if positions is not None:
                ad_set["placements"] = {"mode": "manual", "positions": positions}
            c = creative(raw)
            if pinned:
                c["mode"] = "multi_variant"
                c["assets"] = [
                    {"local_path": "picture.png", "placement": pinned},
                    {"image_hash": "fallback0001"},
                ]
            else:
                c["assets"] = [{"local_path": "picture.png"}]

        return build(mutate)

    def aspect(self, tmp_path: Path, size: tuple[int, int], plan) -> list[str]:  # type: ignore[no-untyped-def]
        write_png(tmp_path / "picture.png", *size)
        report = validate_plan(plan, asset_base=tmp_path)
        return [f.message for f in report.findings if f.code == "asset.aspect_placement"]

    def test_a_landscape_image_for_stories_only_is_flagged(self, tmp_path: Path) -> None:
        plan = self.plan(["instagram_stories", "facebook_stories"])
        (message,) = self.aspect(tmp_path, (1200, 628), plan)
        assert "1200x628" in message and "9:16" in message

    def test_a_vertical_image_for_stories_is_fine(self, tmp_path: Path) -> None:
        assert self.aspect(tmp_path, (1080, 1920), self.plan(["instagram_reels"])) == []

    def test_a_vertical_image_for_feed_only_is_flagged(self, tmp_path: Path) -> None:
        (message,) = self.aspect(tmp_path, (1080, 1920), self.plan(["facebook_feed"]))
        assert "4:5" in message

    def test_a_square_image_for_feed_is_fine(self, tmp_path: Path) -> None:
        assert self.aspect(tmp_path, (1080, 1080), self.plan(["instagram_feed"])) == []

    def test_a_pinned_asset_is_judged_by_its_own_placement(self, tmp_path: Path) -> None:
        plan = self.plan(None, pinned="instagram_stories")
        assert len(self.aspect(tmp_path, (1200, 628), plan)) == 1

    @pytest.mark.parametrize("positions", [None, ["facebook_feed", "instagram_stories"]])
    def test_automatic_or_mixed_placements_say_nothing(
        self, tmp_path: Path, positions: list[str] | None
    ) -> None:
        # Meta crops per placement there; the preview is the evidence.
        assert self.aspect(tmp_path, (1200, 628), self.plan(positions)) == []
