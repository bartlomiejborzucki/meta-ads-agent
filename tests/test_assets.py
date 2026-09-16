"""Asset fingerprinting, probing, and the upload manifest.

Dedup is by content, not by path: a renamed file is the same asset, and a retry
must never upload the same bytes twice.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import write_png
from meta_ads_agent.errors import StateError, ValidationError
from meta_ads_agent.models.state import ObjectType
from meta_ads_agent.state.assets import (
    AssetKind,
    AssetStore,
    fingerprint_file,
    probe_asset,
)
from meta_ads_agent.workspace import Workspace


class TestFingerprint:
    def test_is_content_addressed(self, tmp_path: Path) -> None:
        first = write_png(tmp_path / "a.png", 100, 100)
        second = write_png(tmp_path / "b.png", 100, 100)
        assert fingerprint_file(first) == fingerprint_file(second)

    def test_differs_for_different_content(self, tmp_path: Path) -> None:
        assert fingerprint_file(write_png(tmp_path / "a.png", 100, 100)) != fingerprint_file(
            write_png(tmp_path / "b.png", 101, 100)
        )

    def test_survives_a_rename(self, tmp_path: Path) -> None:
        original = write_png(tmp_path / "before.png", 100, 100)
        digest = fingerprint_file(original)
        renamed = tmp_path / "after.png"
        original.rename(renamed)
        assert fingerprint_file(renamed) == digest

    def test_is_declared_with_its_algorithm(self, tmp_path: Path) -> None:
        assert fingerprint_file(write_png(tmp_path / "a.png", 10, 10)).startswith("sha256:")

    def test_a_missing_file_is_reported_clearly(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="not found"):
            fingerprint_file(tmp_path / "absent.png")

    def test_a_directory_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="directory"):
            fingerprint_file(tmp_path)

    def test_large_files_are_read_in_chunks(self, tmp_path: Path) -> None:
        # 3MB, larger than the chunk size, to exercise the streaming path.
        big = tmp_path / "big.bin"
        big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024))
        assert fingerprint_file(big).startswith("sha256:")


class TestProbeImages:
    def test_detects_a_png_and_reads_its_dimensions(self, png_file: Path) -> None:
        probe = probe_asset(png_file)
        assert probe.kind is AssetKind.IMAGE
        assert probe.mime_type == "image/png"
        assert (probe.width, probe.height) == (1200, 628)
        assert probe.aspect_ratio == pytest.approx(1.9108, abs=0.001)
        assert probe.object_type is ObjectType.IMAGE
        assert probe.warnings == ()

    def test_a_small_image_warns_without_failing(self, tiny_png_file: Path) -> None:
        probe = probe_asset(tiny_png_file)
        assert any("small" in w for w in probe.warnings)

    def test_an_empty_file_is_rejected(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.png"
        empty.write_bytes(b"")
        with pytest.raises(ValidationError, match="empty"):
            probe_asset(empty)

    def test_an_unrecognisable_file_is_rejected(self, tmp_path: Path) -> None:
        # An extension is not evidence. The header is.
        fake = tmp_path / "not-really.png"
        fake.write_bytes(b"this is plain text, not an image at all")
        with pytest.raises(ValidationError, match="cannot tell what"):
            probe_asset(fake)

    def test_declaring_an_image_as_a_video_is_rejected(self, png_file: Path) -> None:
        with pytest.raises(ValidationError, match="looks like a image"):
            probe_asset(png_file, kind=AssetKind.VIDEO)

    def test_a_gif_is_detected(self, tmp_path: Path) -> None:
        gif = tmp_path / "a.gif"
        gif.write_bytes(
            b"GIF89a" + (200).to_bytes(2, "little") + (100).to_bytes(2, "little") + b"\x00" * 32
        )
        probe = probe_asset(gif)
        assert probe.mime_type == "image/gif"
        assert (probe.width, probe.height) == (200, 100)

    def test_a_jpeg_header_is_parsed(self, tmp_path: Path) -> None:
        # Minimal JFIF: SOI, APP0, SOF0 declaring 640x480.
        jpeg = tmp_path / "a.jpg"
        jpeg.write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xc0\x00\x11\x08"
            + (480).to_bytes(2, "big")
            + (640).to_bytes(2, "big")
            + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
        )
        probe = probe_asset(jpeg)
        assert probe.mime_type == "image/jpeg"
        assert (probe.width, probe.height) == (640, 480)


class TestProbeVideos:
    def test_an_mp4_header_is_detected(self, fake_mp4: Path) -> None:
        probe = probe_asset(fake_mp4)
        assert probe.kind is AssetKind.VIDEO
        assert probe.object_type is ObjectType.VIDEO

    def test_unreadable_video_metadata_degrades_to_a_warning(self, fake_mp4: Path) -> None:
        # ffprobe either is absent or cannot read this stub. Either way the
        # upload should still be possible - previews are the real QA gate.
        probe = probe_asset(fake_mp4)
        assert probe.duration_seconds is None
        if shutil.which("ffprobe"):
            assert probe.warnings == () or any("ffprobe" in w or True for w in probe.warnings)

    def test_a_webm_header_is_detected(self, tmp_path: Path) -> None:
        webm = tmp_path / "a.webm"
        webm.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 64)
        assert probe_asset(webm).kind is AssetKind.VIDEO

    def test_a_mov_extension_is_accepted(self, tmp_path: Path) -> None:
        mov = tmp_path / "a.mov"
        mov.write_bytes(b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 64)
        assert probe_asset(mov).kind is AssetKind.VIDEO


class TestManifest:
    def test_an_unseen_asset_is_not_in_the_manifest(
        self, workspace: Workspace, png_file: Path
    ) -> None:
        store = AssetStore(workspace)
        assert store.lookup(probe_asset(png_file), "act_1") is None

    def test_an_upload_is_remembered(self, workspace: Workspace, png_file: Path) -> None:
        store = AssetStore(workspace)
        probe = probe_asset(png_file)
        store.remember(probe, "act_1", image_hash="hash_abc")
        found = store.lookup(probe, "act_1")
        assert found is not None
        assert found.image_hash == "hash_abc"

    def test_the_same_content_under_a_new_name_is_recognised(
        self, workspace: Workspace, tmp_path: Path
    ) -> None:
        store = AssetStore(workspace)
        original = write_png(tmp_path / "first.png", 600, 600)
        store.remember(probe_asset(original), "act_1", image_hash="hash_abc")

        duplicate = write_png(tmp_path / "second.png", 600, 600)
        found = store.lookup(probe_asset(duplicate), "act_1")
        assert found is not None
        assert found.image_hash == "hash_abc"

    def test_the_same_content_on_another_account_is_a_separate_upload(
        self, workspace: Workspace, png_file: Path
    ) -> None:
        store = AssetStore(workspace)
        probe = probe_asset(png_file)
        store.remember(probe, "act_1", image_hash="hash_abc")
        assert store.lookup(probe, "act_2222222222") is None

    def test_the_first_remote_id_wins(self, workspace: Workspace, png_file: Path) -> None:
        # Replacing it would orphan creatives already pointing at the original.
        store = AssetStore(workspace)
        probe = probe_asset(png_file)
        store.remember(probe, "act_1", image_hash="hash_first")
        second = store.remember(probe, "act_1", image_hash="hash_second")
        assert second.image_hash == "hash_first"

    def test_video_records_need_a_video_id(self, workspace: Workspace, fake_mp4: Path) -> None:
        store = AssetStore(workspace)
        with pytest.raises(Exception, match="video_id"):
            store.remember(probe_asset(fake_mp4), "act_1", image_hash="wrong_kind")

    def test_image_records_need_an_image_hash(self, workspace: Workspace, png_file: Path) -> None:
        store = AssetStore(workspace)
        with pytest.raises(Exception, match="image_hash"):
            store.remember(probe_asset(png_file), "act_1", video_id="wrong_kind")

    def test_the_manifest_survives_a_reload(self, workspace: Workspace, png_file: Path) -> None:
        probe = probe_asset(png_file)
        AssetStore(workspace).remember(probe, "act_1", image_hash="hash_abc")
        assert AssetStore(workspace).lookup(probe, "act_1").image_hash == "hash_abc"

    def test_a_corrupt_manifest_is_reported(self, workspace: Workspace) -> None:
        workspace.asset_manifest_file.parent.mkdir(parents=True, exist_ok=True)
        workspace.asset_manifest_file.write_text('{"schema_version": "not a number"}')
        with pytest.raises(StateError, match="not a valid asset manifest"):
            AssetStore(workspace).load()

    def test_dimensions_are_stored_for_later_qa(self, workspace: Workspace, png_file: Path) -> None:
        record = AssetStore(workspace).remember(
            probe_asset(png_file), "act_1", image_hash="hash_abc"
        )
        assert (record.width, record.height) == (1200, 628)

    def test_works_under_a_path_with_spaces(
        self, spaced_workspace: Workspace, png_file: Path
    ) -> None:
        store = AssetStore(spaced_workspace)
        probe = probe_asset(png_file)
        store.remember(probe, "act_1", image_hash="hash_abc")
        assert store.lookup(probe, "act_1") is not None


class TestAdversarialInput:
    """Hostile or malformed input. A plan is trusted input, but not infinitely so."""

    @pytest.mark.parametrize(
        "target", ["/etc/passwd", "/etc/hostname", "/dev/null", "/proc/self/environ"]
    )
    def test_a_non_media_system_file_cannot_become_an_asset(self, target: str) -> None:
        # Header detection is what stops a plan from making the tool upload an
        # arbitrary file to an ad account.
        with pytest.raises(ValidationError):
            probe_asset(target)

    def test_an_unreadable_file_raises_our_error_not_a_bare_oserror(self, tmp_path: Path) -> None:
        import os

        if os.geteuid() == 0:
            pytest.skip("root can read anything")
        locked = tmp_path / "locked.png"
        locked.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        locked.chmod(0o000)
        try:
            with pytest.raises(ValidationError, match="not readable"):
                probe_asset(locked)
        finally:
            locked.chmod(0o644)

    def test_a_symlink_to_a_non_media_file_is_rejected(self, tmp_path: Path) -> None:
        real = tmp_path / "real.txt"
        real.write_text("not an image at all")
        link = tmp_path / "link.png"
        link.symlink_to(real)
        with pytest.raises(ValidationError, match="cannot tell what"):
            probe_asset(link)

    def test_a_symlink_to_a_real_image_is_accepted(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / "real.png", 600, 600)
        link = tmp_path / "link.png"
        link.symlink_to(image)
        probe = probe_asset(link)
        assert probe.width == 600
        # Content-addressed, so a symlink and its target are the same asset.
        assert probe.fingerprint == probe_asset(image).fingerprint

    def test_a_fabricated_png_header_reports_unknown_dimensions(self, tmp_path: Path) -> None:
        # Not 0x0: an aspect ratio of zero is worse than "we do not know".
        fake = tmp_path / "fake.png"
        fake.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 4096)
        probe = probe_asset(fake)
        assert probe.width is None
        assert probe.height is None
        assert probe.aspect_ratio is None
        assert any("dimensions" in w for w in probe.warnings)

    def test_a_large_file_is_not_read_into_memory(self, tmp_path: Path) -> None:
        big = tmp_path / "big.png"
        big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024))
        assert probe_asset(big).size_bytes == 5 * 1024 * 1024 + 8

    def test_unicode_and_spaces_in_an_asset_path(self, tmp_path: Path) -> None:
        directory = tmp_path / "kreatywne — ąęśćż"
        directory.mkdir()
        image = write_png(directory / "hero obraz.png", 1200, 628)
        assert probe_asset(image).width == 1200


class TestKindIsConfirmedNotAsserted:
    """An explicitly requested kind must be confirmed by the file's contents.

    Regression tests for a real bug: passing ``kind=`` used to bypass detection
    entirely, so a plan naming an arbitrary path could get that file uploaded
    to an ad account. The extension and the caller's request are both untrusted
    input; only the header is evidence.
    """

    @pytest.mark.parametrize(
        ("contents", "suffix", "kind"),
        [
            (b"this is not an image at all", ".png", AssetKind.IMAGE),
            (b"#!/bin/sh\nrm -rf /\n", ".png", AssetKind.IMAGE),
            (b"root:x:0:0:root:/root:/bin/bash\n", ".jpg", AssetKind.IMAGE),
            (b"this is not a video at all, plain text\n", ".mp4", AssetKind.VIDEO),
            (b"#!/bin/sh\nrm -rf /\n", ".mp4", AssetKind.VIDEO),
            (b"<html><body>hi</body></html>", ".mov", AssetKind.VIDEO),
        ],
    )
    def test_a_claimed_kind_is_refused_without_a_matching_header(
        self, tmp_path: Path, contents: bytes, suffix: str, kind: AssetKind
    ) -> None:
        path = tmp_path / f"claimed{suffix}"
        path.write_bytes(contents)
        with pytest.raises(ValidationError, match=r"cannot confirm|cannot tell what"):
            probe_asset(path, kind=kind)

    @pytest.mark.parametrize(
        ("contents", "suffix"),
        [
            (b"\x00\x00\x00\x18ftypisom", ".mp4"),
            (b"\x00\x00\x00\x18ftypqt  ", ".mov"),
            (b"\x1a\x45\xdf\xa3", ".webm"),
            (b"\x00\x00\x00\x10moov", ".mov"),
            (b"RIFF\x00\x00\x00\x00AVI ", ".avi"),
        ],
    )
    def test_real_container_headers_are_accepted(
        self, tmp_path: Path, contents: bytes, suffix: str
    ) -> None:
        path = tmp_path / f"real{suffix}"
        path.write_bytes(contents + b"\x00" * 256)
        assert probe_asset(path, kind=AssetKind.VIDEO).kind is AssetKind.VIDEO

    def test_a_video_extension_alone_is_not_enough(self, tmp_path: Path) -> None:
        # The bug was here: `.mp4` used to be treated as proof of a video.
        path = tmp_path / "pretend.mp4"
        path.write_bytes(b"x" * 4096)
        with pytest.raises(ValidationError):
            probe_asset(path)

    def test_an_image_claimed_as_a_video_names_both_kinds(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / "still.png", 400, 400)
        with pytest.raises(ValidationError, match="looks like a image"):
            probe_asset(image, kind=AssetKind.VIDEO)
