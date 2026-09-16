"""Allow ``python -m meta_ads_agent``."""

import sys

from meta_ads_agent.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
