import asyncio
import logging
from datetime import datetime, date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import database as db
from config import TIMEZONE, EVENING_REMINDER_TIME

logger = logging.getLogger(__name__)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Setup and configure the scheduler."""
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Check for reminders every minute
    scheduler.add_job(
        send_reminders,
        CronTrigger(minute="*"),
        args=[bot],
        id="send_reminders",
        replace_existing=True,
    )

    # Evening reminder for missed pills
    hour, minute = EVENING_REMINDER_TIME.split(":")
    scheduler.add_job(
        send_evening_reminders,
        CronTrigger(hour=int(hour), minute=int(minute)),
        args=[bot],
        id="evening_reminders",
        replace_existing=True,
    )

    return scheduler


async def send_reminders(bot: Bot):
    """Send reminders for current time."""
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    day_of_week = now.isoweekday()

    logger.debug(f"Checking reminders for {current_time}, day {day_of_week}")

    schedules = await db.get_schedules_for_time(current_time, day_of_week)

    for schedule in schedules:
        # Check if log already exists for today
        if await db.check_existing_log(schedule["id"], date.today()):
            continue

        # Create intake log
        log = await db.create_intake_log(
            schedule_id=schedule["id"],
            scheduled_time=now,
        )

        # Build mention
        if schedule["username"]:
            mention = f"@{schedule['username']}"
        else:
            mention = schedule["first_name"] or "Друг"

        # Build message
        text = (
            f"{mention}, пора выпить таблетку!\n\n"
            f"<b>{schedule['pill_name']}</b> ({schedule['dosage']})"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Выпил", callback_data=f"taken_{log.id}"),
                    InlineKeyboardButton(text="Позже", callback_data=f"remind_later_{log.id}"),
                ]
            ]
        )

        try:
            # Send photo if available
            if schedule.get("photo_id"):
                await bot.send_photo(
                    chat_id=schedule["chat_id"],
                    photo=schedule["photo_id"],
                    caption=text,
                    reply_markup=keyboard,
                )
            else:
                await bot.send_message(
                    chat_id=schedule["chat_id"],
                    text=text,
                    reply_markup=keyboard,
                )
            logger.info(f"Sent reminder to chat {schedule['chat_id']} for {schedule['pill_name']}")
        except Exception as e:
            logger.error(f"Failed to send reminder: {e}")


async def send_evening_reminders(bot: Bot):
    """Send reminders for pills not taken today."""
    logger.info("Running evening reminders check")

    # Get all unique chat_ids that have pending logs
    import aiosqlite
    from config import DB_PATH

    today = date.today().isoformat()

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT DISTINCT u.chat_id
            FROM intake_logs il
            JOIN schedules s ON il.schedule_id = s.id
            JOIN pills p ON s.pill_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE il.status = 'pending'
              AND date(il.scheduled_time) = ?
            """,
            (today,),
        )
        chat_ids = [row["chat_id"] for row in await cursor.fetchall()]

    for chat_id in chat_ids:
        pending_logs = await db.get_pending_logs_for_today(chat_id)

        # Group by user
        user_logs = {}
        for log in pending_logs:
            user_key = log["telegram_id"]
            if user_key not in user_logs:
                user_logs[user_key] = {
                    "username": log["username"],
                    "first_name": log["first_name"],
                    "pills": [],
                }
            user_logs[user_key]["pills"].append(log)

        for telegram_id, data in user_logs.items():
            if data["username"]:
                mention = f"@{data['username']}"
            else:
                mention = data["first_name"] or "Друг"

            pills_text = "\n".join(
                f"• {p['pill_name']} ({p['dosage']}) - {p['time']}"
                for p in data["pills"]
            )

            text = (
                f"{mention}, ты не отметил приём таблеток сегодня:\n\n"
                f"{pills_text}\n\n"
                "Выпил?"
            )

            # Create buttons for each pill
            buttons = []
            for pill_log in data["pills"]:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"Выпил {pill_log['pill_name']}",
                        callback_data=f"taken_{pill_log['id']}"
                    ),
                    InlineKeyboardButton(
                        text="Пропустил",
                        callback_data=f"missed_{pill_log['id']}"
                    ),
                ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                )
                logger.info(f"Sent evening reminder to chat {chat_id} for user {telegram_id}")

                # Update status to reminded
                for pill_log in data["pills"]:
                    await db.update_intake_status(pill_log["id"], "reminded")
            except Exception as e:
                logger.error(f"Failed to send evening reminder: {e}")
