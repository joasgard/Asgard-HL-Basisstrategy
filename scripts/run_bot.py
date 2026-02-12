#!/usr/bin/env python3
"""Simple script to run the Asgard Basis bot."""

import asyncio
import signal
from bot.core.bot import DeltaNeutralBot, BotConfig
from bot.core.internal_api import internal_app, set_bot_instance
from shared.config.settings import get_settings


async def main():
    """Run the bot and internal API server."""
    # Load config from settings
    settings = get_settings()

    config = BotConfig(
        admin_api_key=settings.admin_api_key,
        max_concurrent_positions=5,
        min_opportunity_apy=0.01,  # 1%
        enable_auto_exit=True,
        enable_circuit_breakers=True,
    )

    # Create bot
    bot = DeltaNeutralBot(config)

    # Setup signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        print("\nShutdown signal received, stopping bot...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run bot with setup
    async with bot:
        # Register bot instance with internal API
        set_bot_instance(bot)

        # Start internal API server (for dashboard communication)
        import uvicorn
        api_config = uvicorn.Config(
            internal_app,
            host="127.0.0.1",
            port=8000,
            log_level="info",
        )
        api_server = uvicorn.Server(api_config)

        print("Internal API serving on http://127.0.0.1:8000")

        # Run bot and API server concurrently
        await asyncio.gather(
            bot.run(),
            api_server.serve(),
        )


if __name__ == "__main__":
    print("Starting Asgard Basis bot...")
    print("Press Ctrl+C to stop gracefully")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Bot crashed: {e}")
        raise
