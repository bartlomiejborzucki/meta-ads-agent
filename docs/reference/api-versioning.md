# Graph API versioning

## Where the version lives

One place: `src/meta_ads_agent/api/version.py`.

```python
DEFAULT_GRAPH_API_VERSION = "v26.0"   # tested against this release
OLDEST_SUPPORTED_VERSION  = "v24.0"   # Meta's window as of 2026-09-16
```

Every fallback request reads it from there. Scattering a version string across
call sites is how a project ends up pinned to three versions at once.

Only the **fallback** uses it. Meta's MCP manages its own versioning, which is
one of the reasons MCP-first is the default.

## Overriding

```bash
export META_GRAPH_API_VERSION=v27.0
```

Resolution order: explicit argument, then the environment variable, then the
default. Malformed values are rejected rather than passed through -
`graph_api_version()` requires the `v<major>.<minor>` form. A version older than
`OLDEST_SUPPORTED_VERSION` refuses to connect, with a message saying why.

## The SDK major has to agree

`facebook-business` majors track Graph API versions. `26.0.1` corresponds to
`v26.0`. Setting `META_GRAPH_API_VERSION=v27.0` while running the 26.x SDK will
mostly work and will fail in whichever specific place the shapes diverged -
which is a worse failure than a clean one, because it surfaces late.

`pyproject.toml` pins one major:

```toml
api = ["facebook-business>=26.0,<27"]
```

## Upgrading

1. Read Meta's Marketing API changelog for the target version. Breaking changes
   and field removals are listed there.
2. Bump the pin in `pyproject.toml` to the matching SDK major.
3. Bump `DEFAULT_GRAPH_API_VERSION`.
4. Update `graph_api_version` in `config/capabilities.yaml` - a test asserts the
   two agree, so a partial upgrade fails CI.
5. Run the tests. They use a faked SDK, so they check *our* logic, not Meta's -
   a green suite is necessary and not sufficient.
6. Exercise the fallback against a designated test ad account. See
   `tests/live/README.md`.
7. Update `OLDEST_SUPPORTED_VERSION` if Meta's support window moved.
8. Note it in `CHANGELOG.md`.

Dependabot is configured **not** to auto-merge `facebook-business`, because a
major there is an API migration wearing a dependency bump.

## Version expiry

Meta expires versions on a schedule. As of 2026-09-16, `v23.0` had expired and
`v24.0` was the oldest supported.

An expired version stops working, so the practical guidance is: stay within one
or two versions of current, and upgrade before the window closes rather than
after something breaks.

## Raw Graph requests

The fallback uses the SDK's resource objects. Where a raw request is genuinely
necessary it must:

- be encapsulated in one module
- carry a comment saying why the SDK was insufficient
- use the configured version explicitly - never a hardcoded path segment
- be covered by a test

As of 1.0 there are none. The SDK covers every fallback capability, including
chunked video upload and processing-status polling, which is precisely why we
use it - see [ADR-002](../architecture/adr/ADR-002-api-fallback.md).
