import asyncio
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat, BotCommandScopeDefault

from bot.config import BOT_TOKEN, ADMIN_IDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="start", description="Ping the bot"),
    BotCommand(command="help", description="Show help message"),
    BotCommand(command="clear", description="Clear conversation history"),
    BotCommand(command="settings", description="Bot settings"),
    BotCommand(command="privacy", description="Privacy policy")
]

ADMIN_COMMANDS = [
    BotCommand(command="approve", description="Approve a user/group"),
    BotCommand(command="disapprove", description="Disapprove a user/group"),
    BotCommand(command="approveonly", description="Toggle approve-only mode"),
    BotCommand(command="clearcache", description="Clear and reload the cache")
]

async def main():
    parser = argparse.ArgumentParser(description="Set Telegram bot commands")
    parser.add_argument("--clear", action="store_true", help="Clear all custom commands and reset to default")
    parser.add_argument("--users-only", action="store_true", help="Only set commands for regular users")
    parser.add_argument("--admins-only", action="store_true", help="Only set commands for admins")
    args = parser.parse_args()

    bot = Bot(token=BOT_TOKEN)

    try:
        if args.clear:
            logger.info("Clearing all commands...")
            await bot.delete_my_commands()
            for admin_id in ADMIN_IDS:
                await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=admin_id))
                await asyncio.sleep(1.0)
            logger.info("Commands cleared successfully.")
            return

        set_users = not args.admins_only
        set_admins = not args.users_only

        if set_users:
            logger.info("Setting commands for all private chats (regular users)...")
            await bot.set_my_commands(
                commands=USER_COMMANDS,
                scope=BotCommandScopeAllPrivateChats()
            )
            logger.info("User commands set successfully.")

        if set_admins:
            if not ADMIN_IDS:
                logger.warning("No ADMIN_IDS configured. Skipping admin commands.")
            else:
                logger.info(f"Setting commands for {len(ADMIN_IDS)} admin(s)...")
                
                combined_commands = USER_COMMANDS + ADMIN_COMMANDS
                
                for admin_id in ADMIN_IDS:
                    try:
                        await bot.set_my_commands(
                            commands=combined_commands,
                            scope=BotCommandScopeChat(chat_id=admin_id)
                        )
                        await asyncio.sleep(1.0)
                        logger.info(f"Commands set for admin {admin_id}")
                    except Exception as e:
                        logger.error(f"Failed to set commands for admin {admin_id}: {e}")
                
                logger.info("Admin commands set successfully.")

    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
