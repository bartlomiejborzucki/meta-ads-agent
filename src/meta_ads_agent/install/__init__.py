"""Installing, updating and verifying the skill payload.

The skills are the thing that gets distributed, and the host that installs
them runs nothing on our behalf afterwards. Codex caches a plugin under
``~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`` and offers only a
``SessionStart`` hook, which it skips until the user has reviewed and trusted
it - so there is no post-install or post-update event to hang an upgrade off.

Everything here is therefore explicit and user-invoked: ``meta-ads-agent
install``, ``upgrade``, ``migrate``, and the installation section of
``doctor``. The alternative - assuming the host re-runs something for us - is
how an install ends up reporting a new version while running on a partial set
of files.
"""

from __future__ import annotations

from meta_ads_agent.install.manifest import ReleaseManifest, build_manifest, load_manifest
from meta_ads_agent.install.state import InstallState, UpdateInProgress
from meta_ads_agent.install.targets import InstallTarget, resolve_target

__all__ = [
    "InstallState",
    "InstallTarget",
    "ReleaseManifest",
    "UpdateInProgress",
    "build_manifest",
    "load_manifest",
    "resolve_target",
]
