"""The release manifest: the explicit list of what a version consists of.

An update that copies "the files that were already there" is the bug this
exists to prevent. A manifest enumerates the payload instead, so a new file, a
new directory, a new script and a deleted file are all just differences
between two lists - no special case, and nothing that only works for files
that happened to exist before.

Each entry carries a SHA-256, which makes two further things possible: an
installed tree can be checked for completeness without the repository, and a
migration script can be run only when its bytes are the bytes the release
declared.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from meta_ads_agent.errors import ConfigError

SCHEMA_VERSION = 1

# The payload is the set of skill directories. Everything else in the
# repository - docs, tests, the CLI - is either separately installed or not
# installed at all, and including it here would make the manifest a lie.
PAYLOAD_ROOT = "skills"
SKILL_PREFIX = "meta-ads-"

# Never shipped, whatever a working tree happens to contain.
_EXCLUDED_NAMES = frozenset({".DS_Store", "Thumbs.db", ".gitkeep"})
_EXCLUDED_DIRS = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """One shipped file, addressed relative to the payload root."""

    path: str
    sha256: str
    size: int
    executable: bool = False

    @property
    def skill(self) -> str:
        return self.path.split("/", 1)[0]

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {"path": self.path, "sha256": self.sha256, "size": self.size}
        if self.executable:
            record["executable"] = True
        return record


@dataclass(frozen=True, slots=True)
class MigrationRef:
    """A migration this release expects to have run.

    ``script`` names a file inside the payload when the migration is carried
    out by code rather than by the built-in registry. Running it is gated on
    the file's hash matching ``script_sha256`` - a release can only ask us to
    execute bytes it declared.
    """

    id: str
    description: str
    introduced_in: str
    script: str | None = None
    script_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": self.id,
            "description": self.description,
            "introduced_in": self.introduced_in,
        }
        if self.script:
            record["script"] = self.script
            record["script_sha256"] = self.script_sha256
        return record


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    """Everything one version of the payload consists of."""

    version: str
    entries: tuple[ManifestEntry, ...]
    migrations: tuple[MigrationRef, ...] = ()
    schema_version: int = SCHEMA_VERSION
    payload_root: str = PAYLOAD_ROOT

    @property
    def digest(self) -> str:
        """One hash identifying this payload, independent of file order.

        Derived rather than stored, so a hand-edited manifest cannot claim a
        digest it does not have.
        """
        joined = "\n".join(f"{e.path}\0{e.sha256}\0{e.size}" for e in self.sorted_entries())
        return sha256_bytes(joined.encode("utf-8"))

    def sorted_entries(self) -> list[ManifestEntry]:
        return sorted(self.entries, key=lambda e: e.path)

    @property
    def skills(self) -> list[str]:
        return sorted({entry.skill for entry in self.entries})

    def by_path(self) -> dict[str, ManifestEntry]:
        return {entry.path: entry for entry in self.entries}

    def entry(self, path: str) -> ManifestEntry | None:
        return self.by_path().get(path)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "payload_root": self.payload_root,
            "digest": self.digest,
            "skills": self.skills,
            "migrations": [m.as_dict() for m in self.migrations],
            "files": [entry.as_dict() for entry in self.sorted_entries()],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n"


def _walk_payload(root: Path) -> Iterator[Path]:
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if not skill_dir.name.startswith(SKILL_PREFIX):
            continue
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            parts = set(path.relative_to(root).parts)
            if parts & _EXCLUDED_DIRS or path.name in _EXCLUDED_NAMES:
                continue
            yield path


def build_manifest(
    repo_root: Path,
    version: str,
    *,
    migrations: Iterable[MigrationRef] = (),
) -> ReleaseManifest:
    """Read the working tree and describe it."""
    payload = repo_root / PAYLOAD_ROOT
    if not payload.is_dir():
        raise ConfigError(f"no payload directory at {payload}")

    entries = [
        ManifestEntry(
            path=path.relative_to(payload).as_posix(),
            sha256=sha256_file(path),
            size=path.stat().st_size,
            executable=bool(path.stat().st_mode & 0o111),
        )
        for path in _walk_payload(payload)
    ]
    if not entries:
        raise ConfigError(f"{payload} contains no {SKILL_PREFIX}* files")

    resolved = list(migrations)
    for index, migration in enumerate(resolved):
        if not migration.script:
            continue
        script = payload / migration.script
        if not script.is_file():
            raise ConfigError(
                f"migration {migration.id} names {migration.script}, which is not in the payload"
            )
        resolved[index] = MigrationRef(
            id=migration.id,
            description=migration.description,
            introduced_in=migration.introduced_in,
            script=migration.script,
            script_sha256=sha256_file(script),
        )

    return ReleaseManifest(version=version, entries=tuple(entries), migrations=tuple(resolved))


def manifest_from_dict(raw: dict[str, Any]) -> ReleaseManifest:
    schema = raw.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise ConfigError(
            f"release manifest schema {schema!r} is not supported by this version "
            f"(expected {SCHEMA_VERSION}). Upgrade the CLI before upgrading the skills."
        )
    try:
        entries = tuple(
            ManifestEntry(
                path=item["path"],
                sha256=item["sha256"],
                size=int(item["size"]),
                executable=bool(item.get("executable", False)),
            )
            for item in raw["files"]
        )
        migrations = tuple(
            MigrationRef(
                id=item["id"],
                description=item["description"],
                introduced_in=item["introduced_in"],
                script=item.get("script"),
                script_sha256=item.get("script_sha256"),
            )
            for item in raw.get("migrations", [])
        )
        manifest = ReleaseManifest(
            version=raw["version"],
            entries=entries,
            migrations=migrations,
            payload_root=raw.get("payload_root", PAYLOAD_ROOT),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"release manifest is malformed: {exc}") from exc

    declared = raw.get("digest")
    if declared and declared != manifest.digest:
        raise ConfigError(
            "release manifest digest does not match its own file list - "
            "it has been edited by hand or truncated"
        )
    return manifest


def load_manifest(path: Path) -> ReleaseManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"no release manifest at {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    return manifest_from_dict(raw)


@dataclass(slots=True)
class VerificationReport:
    """What is wrong with an installed tree, in the terms the user needs."""

    missing: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not (self.missing or self.modified or self.orphaned)

    def as_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "missing": sorted(self.missing),
            "modified": sorted(self.modified),
            "orphaned": sorted(self.orphaned),
        }


def verify_tree(manifest: ReleaseManifest, installed_root: Path) -> VerificationReport:
    """Compare an installed payload against the manifest, both ways.

    Both directions matter. Missing files are the obvious failure; leftovers
    from an older version are the quiet one, because the install looks right
    and the agent reads a file the current release deleted.
    """
    report = VerificationReport()
    expected = manifest.by_path()

    for path, entry in expected.items():
        target = installed_root / path
        if not target.is_file():
            report.missing.append(path)
        elif sha256_file(target) != entry.sha256:
            report.modified.append(path)

    for skill in manifest.skills:
        skill_dir = installed_root / skill
        if not skill_dir.is_dir():
            continue
        for found in skill_dir.rglob("*"):
            if not found.is_file():
                continue
            relative = found.relative_to(installed_root).as_posix()
            if relative not in expected:
                report.orphaned.append(relative)

    return report
