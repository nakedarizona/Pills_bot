import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from config import BOT_TOKEN
from database import init_db
from handlers import pills, schedule, confirm
from scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot):
    """Set bot commands for the menu."""
    commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        BotCommand(command="help", description="Справка по командам"),
        BotCommand(command="addpill", description="Добавить таблетку"),
        BotCommand(command="mypills", description="Мои таблетки"),
        BotCommand(command="editpill", description="Редактировать таблетку"),
        BotCommand(command="deletepill", description="Удалить таблетку"),
        BotCommand(command="today", description="Расписание на сегодня"),
        BotCommand(command="status", description="Статус приёма таблеток"),
    ]
    await bot.set_my_commands(commands)
    logger.info("Bot commands registered")


async def main():
    await init_db()
    logger.info("Database initialized")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Register bot commands for menu
    await set_bot_commands(bot)

    dp.include_router(pills.router)
    dp.include_router(schedule.router)
    dp.include_router(confirm.router)

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started")

    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
