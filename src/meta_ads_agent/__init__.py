"""Agent-native toolkit for operating Meta Ads.

The primary execution layer is Meta's official Ads MCP server. This package is
the deterministic half of the project: money arithmetic, schema validation,
state persistence, asset fingerprinting, capability routing, and a narrow
Marketing API fallback for the few things the official MCP cannot do.

Judgement lives in ``skills/``. See docs/architecture/overview.md.
"""

__version__ = "0.9.0"

__all__ = ["__version__"]
