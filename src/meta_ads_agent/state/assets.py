"""Asset fingerprinting, validation, and the upload manifest.

One reason the API fallback exists is local files: Meta's official MCP lists
uploaded media but has no local-file ingestion path. That makes deduplication
our problem, because a retried campaign build must not upload a 200MB video
twice - and must not create two Meta video objects for one file, which would
make later reporting ambiguous.

Dedup is by **content**, not by path: a renamed file is the same asset, and two
copies of the same bytes are one upload. The key includes the ad account,
because the same file uploaded to two accounts really is two remote objects.

Probing is intentionally shallow. Headers are parsed with the standard library
to confirm a file is what its extension claims and to read dimensions where
that is cheap. ``ffprobe`` is used for video when available, because video
dimensions and duration cannot be read reliably from a header, and its absence
is a warning rather than an error.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from meta_ads_agent.errors import StateError, ValidationError
from meta_ads_agent.models.state import AssetManifest, AssetRecord, ObjectType
from meta_ads_agent.workspace import Workspace

# Chunked so a large video does not have to fit in memory.
_HASH_CHUNK = 1024 * 1024

# Meta's documented limits move; these are sanity bounds, not platform rules.
# They exist to catch "you passed the wrong file", not to enforce policy.
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024
MIN_IMAGE_DIMENSION = 200


class AssetKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


# Magic-number prefixes. Extensions lie; headers usually do not.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)
_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"})


@dataclass(frozen=True, slots=True)
class AssetProbe:
    """What we could determine about a local file."""

    path: Path
    kind: AssetKind
    fingerprint: str
    size_bytes: int
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    warnings: tuple[str, ...] = ()

    @property
    def aspect_ratio(self) -> float | None:
        if not self.width or not self.height:
            return None
        return round(self.width / self.height, 4)

    @property
    def object_type(self) -> ObjectType:
        return ObjectType.IMAGE if self.kind is AssetKind.IMAGE else ObjectType.VIDEO


def fingerprint_file(path: Path | str) -> str:
    """``sha256:<hex>`` of the file's bytes, read in chunks."""
    target = Path(path)
    digest = hashlib.sha256()
    try:
        with target.open("rb") as stream:
            while chunk := stream.read(_HASH_CHUNK):
                digest.update(chunk)
    except FileNotFoundError as exc:
        raise ValidationError(f"asset not found: {target}") from exc
    except IsADirectoryError as exc:
        raise ValidationError(f"asset path is a directory: {target}") from exc
    except PermissionError as exc:
        raise ValidationError(f"asset is not readable: {target}") from exc
    return f"sha256:{digest.hexdigest()}"


def probe_asset(path: Path | str, *, kind: AssetKind | None = None) -> AssetProbe:
    """Inspect a local asset before uploading it.

    Validates that the file exists, is non-empty, and is the type it claims to
    be. Raises for problems that make the upload pointless; collects warnings
    for things a human should look at but which Meta may well accept.
    """
    target = Path(path).expanduser()
    if not target.exists():
        raise ValidationError(f"asset not found: {target}")
    if target.is_dir():
        raise ValidationError(f"asset path is a directory: {target}")

    size = target.stat().st_size
    if size == 0:
        raise ValidationError(f"asset is empty: {target}")

    header = b""
    if size >= 4:
        try:
            with target.open("rb") as stream:
                header = stream.read(64)
        except PermissionError as exc:
            raise ValidationError(f"asset is not readable: {target}") from exc
        except OSError as exc:
            raise ValidationError(f"asset could not be read: {target}: {exc}") from exc
    detected = _detect_kind(target, header)

    # Unrecognised container with a video extension: ask ffprobe rather than
    # trusting the filename. An unusual-but-real container should work, and a
    # text file named .mp4 should not.
    if (
        detected is None
        and target.suffix.lower() in _VIDEO_EXTENSIONS
        and _ffprobe(target) is not None
    ):
        detected = AssetKind.VIDEO

    if kind is not None and detected is not kind:
        # An explicitly requested kind must be CONFIRMED by the file's own
        # header, never merely asserted by the caller. Trusting the caller here
        # would let a plan naming an arbitrary path get that file uploaded to an
        # ad account - the extension and the request are both untrusted, only
        # the header is evidence.
        if detected is None:
            raise ValidationError(
                f"cannot confirm {target} is {_article(kind.value)}: its contents do not "
                "match any supported format. Supported: JPEG, PNG, GIF, BMP, "
                f"WebP images and {sorted(_VIDEO_EXTENSIONS)} video."
            )
        raise ValidationError(
            f"{target} looks like a {detected.value} but was used as a "
            f"{kind.value}. Check the plan's creative mode."
        )

    resolved = kind or detected
    if resolved is None:
        raise ValidationError(
            f"cannot tell what {target} is. Supported: JPEG, PNG, GIF, BMP, WebP "
            f"images and {sorted(_VIDEO_EXTENSIONS)} video."
        )

    warnings: list[str] = []
    mime = _image_mime(header) if resolved is AssetKind.IMAGE else None
    width = height = None
    duration = None

    if resolved is AssetKind.IMAGE:
        if size > MAX_IMAGE_BYTES:
            warnings.append(
                f"image is {size / 1_048_576:.1f}MB, which is large enough that "
                "Meta may reject or recompress it"
            )
        width, height = _image_dimensions(target, mime)
        if width and height:
            if min(width, height) < MIN_IMAGE_DIMENSION:
                warnings.append(
                    f"{width}x{height} is small; expect visible quality loss in Feed and Stories"
                )
        else:
            warnings.append("could not read image dimensions; skipping crop checks")
    else:
        if size > MAX_VIDEO_BYTES:
            warnings.append(f"video is {size / 1_073_741_824:.2f}GB and may be rejected")
        probe = _ffprobe(target)
        if probe is None:
            warnings.append(
                "ffprobe is not available, so video dimensions, duration, and "
                "aspect ratio were not checked. Install ffmpeg for pre-upload QA, "
                "or rely on the placement previews after the ad is built."
            )
        else:
            width, height, duration = probe

    return AssetProbe(
        path=target,
        kind=resolved,
        fingerprint=fingerprint_file(target),
        size_bytes=size,
        mime_type=mime,
        width=width,
        height=height,
        duration_seconds=duration,
        warnings=tuple(warnings),
    )


def _detect_kind(path: Path, header: bytes) -> AssetKind | None:
    """Identify a file from its contents.

    **An extension is never sufficient.** A file named ``.mp4`` containing a
    shell script is not a video, and uploading it to an ad account because of
    its name would be exactly the arbitrary-file-upload problem. Only the
    header counts here; :func:`probe_asset` gives a video-extensioned file one
    second chance via ffprobe, which is evidence rather than a filename.
    """
    if _image_mime(header):
        return AssetKind.IMAGE
    if _video_container(header):
        return AssetKind.VIDEO
    return None


def _article(word: str) -> str:
    return f"an {word}" if word[0] in "aeiou" else f"a {word}"


def _video_container(header: bytes) -> bool:
    """Recognise the common video container headers."""
    # ISO base media (mp4, m4v, mov) carries 'ftyp' at offset 4.
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return True
    # Matroska and WebM share the EBML magic.
    if header[:4] == b"\x1a\x45\xdf\xa3":
        return True
    # RIFF/AVI.
    if header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return True
    # Legacy QuickTime atoms that appear before any ftyp.
    return len(header) >= 8 and header[4:8] in {b"moov", b"mdat", b"free", b"wide"}


def _image_mime(header: bytes) -> str | None:
    for signature, mime in _IMAGE_SIGNATURES:
        if header.startswith(signature):
            return mime
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def _image_dimensions(path: Path, mime: str | None) -> tuple[int | None, int | None]:
    """Read width and height from an image header.

    Only PNG, GIF, and JPEG are parsed - they cover essentially all ad
    creative, and each is a few lines. Anything else returns None and the
    caller records a warning instead of guessing.
    """
    try:
        with path.open("rb") as stream:
            if mime == "image/png":
                stream.seek(16)
                data = stream.read(8)
                if len(data) == 8:
                    width, height = struct.unpack(">II", data)
                    # A truncated or fabricated header yields zeros. Report
                    # "unknown" rather than a nonsense 0x0, so the caller warns
                    # instead of reasoning about an aspect ratio of 0.
                    if width and height:
                        return int(width), int(height)
                    return None, None
            elif mime == "image/gif":
                stream.seek(6)
                data = stream.read(4)
                if len(data) == 4:
                    width, height = struct.unpack("<HH", data)
                    if width and height:
                        return int(width), int(height)
                    return None, None
            elif mime == "image/jpeg":
                return _jpeg_dimensions(stream)
    except OSError:
        return None, None
    return None, None


def _jpeg_dimensions(stream) -> tuple[int | None, int | None]:  # type: ignore[no-untyped-def]
    """Walk JPEG segments to the first start-of-frame marker."""
    stream.seek(2)
    while True:
        marker = stream.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None, None
        length_bytes = stream.read(2)
        if len(length_bytes) < 2:
            return None, None
        (length,) = struct.unpack(">H", length_bytes)
        # SOF0..SOF15, excluding the DHT/JPG/DAC markers interleaved in range.
        if marker[1] in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            payload = stream.read(5)
            if len(payload) < 5:
                return None, None
            height, width = struct.unpack(">HH", payload[1:5])
            if width and height:
                return int(width), int(height)
            return None, None
        stream.seek(length - 2, 1)


def _ffprobe(path: Path) -> tuple[int | None, int | None, float | None] | None:
    """Read video dimensions and duration via ffprobe, if it is installed.

    ``shutil.which`` first and a fixed argument list keep this off the shell:
    the path is user-controlled, so no string interpolation and no
    ``shell=True``.
    """
    binary = shutil.which("ffprobe")
    if not binary:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, absolute binary, no shell
            [
                binary,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    streams = payload.get("streams") or [{}]
    stream = streams[0] if isinstance(streams, list) and streams else {}
    duration_raw = (payload.get("format") or {}).get("duration")
    try:
        duration = float(duration_raw) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration = None
    return (
        int(stream["width"]) if stream.get("width") else None,
        int(stream["height"]) if stream.get("height") else None,
        duration,
    )


class AssetStore:
    """The asset manifest, loaded from and saved to the workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def load(self) -> AssetManifest:
        path = self.workspace.asset_manifest_file
        if not path.is_file():
            return AssetManifest()
        raw = self.workspace.read_json(path)
        try:
            return AssetManifest.model_validate(raw)
        except PydanticValidationError as exc:
            raise StateError(f"{path} is not a valid asset manifest:\n{exc}") from exc

    def save(self, manifest: AssetManifest) -> None:
        self.workspace.write_json(
            self.workspace.asset_manifest_file,
            manifest.model_dump(mode="json", exclude_none=True),
        )

    def lookup(self, probe: AssetProbe, ad_account_id: str) -> AssetRecord | None:
        """Existing remote identity for this content, if we have uploaded it."""
        return self.load().lookup(probe.fingerprint, ad_account_id)

    def remember(
        self,
        probe: AssetProbe,
        ad_account_id: str,
        *,
        image_hash: str | None = None,
        video_id: str | None = None,
    ) -> AssetRecord:
        """Record a successful upload and flush.

        Flushed immediately for the same reason campaign state is: an upload
        that succeeded on Meta but is not on disk gets repeated.
        """
        manifest = self.load()
        record = AssetRecord(
            fingerprint=probe.fingerprint,
            ad_account_id=ad_account_id,
            local_path=str(probe.path),
            size_bytes=probe.size_bytes,
            kind=probe.object_type,
            image_hash=image_hash,
            video_id=video_id,
            width=probe.width,
            height=probe.height,
            duration_seconds=probe.duration_seconds,
        )
        stored = manifest.put(record)
        self.save(manifest)
        return stored
