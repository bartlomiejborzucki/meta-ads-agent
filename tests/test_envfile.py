"""The optional ./.env for the API fallback, as the README describes it."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import REAL_DOTENV_APPLY
from meta_ads_agent import envfile
from meta_ads_agent.envfile import parse


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [k for k in os.environ if k.startswith("META_")]:
        monkeypatch.delenv(name)


class TestParse:
    def test_the_shipped_example_parses(self) -> None:
        values = parse((Path(__file__).resolve().parents[1] / ".env.example").read_text())
        assert values["META_GRAPH_API_VERSION"] == "v26.0"
        assert values["META_ACCESS_TOKEN"] == ""

    @pytest.mark.parametrize(
        ("line", "value"),
        [
            ("META_ACCESS_TOKEN=abc", "abc"),
            ('META_ACCESS_TOKEN="abc def"', "abc def"),
            ("export META_ACCESS_TOKEN='abc'", "abc"),
            ("META_ACCESS_TOKEN=abc  # note", "abc"),
        ],
    )
    def test_the_usual_forms(self, line: str, value: str) -> None:
        assert parse(line) == {"META_ACCESS_TOKEN": value}

    def test_only_meta_keys_and_nothing_is_expanded(self) -> None:
        text = "PATH=/evil\nMETA_AD_ACCOUNT_ID=$(whoami)\nMETA_APP_ID=${HOME}\n"
        assert parse(text) == {"META_AD_ACCOUNT_ID": "$(whoami)", "META_APP_ID": "${HOME}"}


class TestApply:
    def test_a_dotenv_fills_what_the_environment_lacks(
        self, tmp_path: Path, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".env").write_text("META_ACCESS_TOKEN=from-file\nMETA_AD_ACCOUNT_ID=act_1\n")
        monkeypatch.setattr(envfile, "apply", REAL_DOTENV_APPLY)
        applied = envfile.apply(tmp_path)
        assert applied == ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID")
        assert os.environ["META_ACCESS_TOKEN"] == "from-file"

    def test_the_environment_wins_even_when_empty(
        self, tmp_path: Path, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # CI empties the token on purpose; a .env must not refill it.
        monkeypatch.setenv("META_ACCESS_TOKEN", "")
        (tmp_path / ".env").write_text("META_ACCESS_TOKEN=from-file\n")
        monkeypatch.setattr(envfile, "apply", REAL_DOTENV_APPLY)
        assert envfile.apply(tmp_path) == ()
        assert os.environ["META_ACCESS_TOKEN"] == ""

    def test_no_file_is_not_an_error(self, tmp_path: Path, clean_env: None) -> None:
        assert REAL_DOTENV_APPLY(tmp_path) == ()

    def test_doctor_names_the_file_without_the_value(
        self,
        tmp_path: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from meta_ads_agent.cli.main import main

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(envfile, "apply", REAL_DOTENV_APPLY)
        (tmp_path / ".env").write_text("META_ACCESS_TOKEN=fake-token-42\n")
        main(["doctor"])
        out = capsys.readouterr().out
        assert ".env" in out
        assert "fake-token-42" not in out
        assert "sha256:" in out
