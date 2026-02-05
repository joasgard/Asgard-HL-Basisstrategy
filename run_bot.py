#!/usr/bin/env python3
"""
Backward-compatible entry point for the Delta Neutral Bot.

This script delegates to scripts/run_bot.py for the actual implementation.
Please use `python -m scripts.run_bot` or `python scripts/run_bot.py` in new code.
"""

import warnings

# Show deprecation warning
warnings.warn(
    "run_bot.py in root is deprecated. Use 'python scripts/run_bot.py' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Import and run from scripts directory
from scripts.run_bot import main

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
