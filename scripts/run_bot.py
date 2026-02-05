#!/usr/bin/env python3
"""Simple script to run the Delta Neutral Bot."""

import asyncio
import signal
from src.core.bot import DeltaNeutralBot, BotConfig
from src.config.settings import get_settings


async def main():
    """Run the bot."""
    # Load config from settings
    settings = get_settings()
    
    config = BotConfig(
        admin_api_key=settings.admin_api_key,
        max_concurrent_positions=5,
        min_opportunity_apy=0.01,  # 1%
        enable_auto_exit=True,
        enable_circuit_breakers=True,
    )
    
    # Create and run bot
    bot = DeltaNeutralBot(config)
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutdown signal received, stopping bot...")
        asyncio.create_task(bot.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run bot with setup
    async with bot:
        await bot.run()


if __name__ == "__main__":
    print("Starting Delta Neutral Bot...")
    print("Press Ctrl+C to stop gracefully")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Bot crashed: {e}")
        raise
