"""Advisory locks for files more than one process may update.

Two agent sessions, or an agent and a terminal, can run the CLI against the
same workspace at once. Every file here is written atomically, which stops a
crash from truncating it but not two writers from each reading the old
version, adding their own entry, and saving - the second save silently drops
the first entry. For the asset manifest that means a second upload of bytes
already on Meta; for the action log, an interleaved line.

A lock is a sidecar file (``.<name>.lock``) held with ``flock`` on POSIX and
``msvcrt.locking`` on Windows. No dependency, and the lock is released by the
operating system when the process dies, so a crash never leaves a workspace
locked. The sidecar file itself is left in place; it is empty and harmless.

Locks are not re-entrant: taking the same lock twice in one process waits on
itself. Callers hold one lock at a time.
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from meta_ads_agent.errors import StateError

DEFAULT_TIMEOUT_SECONDS = 30.0
_POLL_SECONDS = 0.05


def lock_path_for(path: Path) -> Path:
    return path.with_name(f".{path.name}.lock")


@contextmanager
def file_lock(
    path: Path, *, timeout: float = DEFAULT_TIMEOUT_SECONDS, what: str | None = None
) -> Iterator[None]:
    """Hold an exclusive lock on *path* for the duration of the block.

    Waits up to *timeout* seconds, then raises :class:`StateError` naming the
    file, rather than proceeding without the lock - proceeding is the bug.
    """
    lock = lock_path_for(path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise StateError(
                    f"{what or path} is being updated by another meta-ads-agent process "
                    f"(waited {timeout:.0f}s for {lock}). Let it finish, then retry."
                )
            time.sleep(_POLL_SECONDS)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


if sys.platform == "win32":  # pragma: no cover - exercised by the Windows CI job
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import errno
    import fcntl

    _UNSUPPORTED = frozenset(
        {errno.ENOLCK, errno.EOPNOTSUPP, errno.ENOTSUP, errno.EINVAL, errno.ENOSYS}
    )

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        except OSError as exc:
            if exc.errno in _UNSUPPORTED:
                # Some filesystems refuse flock outright - notably drvfs, the
                # Windows drive seen from WSL, where --target windows-codex
                # writes. Refusing to install there would be worse than the
                # race this lock guards against, so proceed unlocked.
                return True
            raise
        return True

    def _unlock(fd: int) -> None:
        with contextlib.suppress(OSError):  # never taken, on an unsupported filesystem
            fcntl.flock(fd, fcntl.LOCK_UN)
