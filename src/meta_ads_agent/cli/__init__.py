"""Command-line interface.

Deliberately small. This is not an alternative Ads Manager - it fills specific
gaps and supports the skills with deterministic checks. Commands:

    doctor         local prerequisites and connection status
    init           create the brand workspace
    capabilities   what routes where, and which gaps the fallback covers
    validate-plan  platform-constraint validation before any write
    state          inspect and resume campaign state
    api            the Marketing API fallback

Built on argparse to keep the dependency list to validation and YAML only.
"""
