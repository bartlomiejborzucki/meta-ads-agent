"""The Marketing API fallback.

Exists only for capabilities Meta's official Ads MCP does not expose. It is a
liability, not an asset: every module here is a bet that Meta will not ship the
feature, and we expect to lose those bets. See
docs/architecture/adr/ADR-002-api-fallback.md for the shrinking-fallback rule.

Nothing in this package is imported unless a fallback command actually runs, so
a default MCP-only installation never needs ``facebook-business``.
"""

from meta_ads_agent.api.version import DEFAULT_GRAPH_API_VERSION, graph_api_version

__all__ = ["DEFAULT_GRAPH_API_VERSION", "graph_api_version"]
