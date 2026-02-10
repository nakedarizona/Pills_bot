import asyncio
import logging
from datetime import datetime, date, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import database as db
from config import TIMEZONE, EVENING_REMINDER_TIME

logger = logging.getLogger(__name__)

# Cutoff time for reminders (no reminders after this hour)
REMINDER_CUTOFF_HOUR = 21

# Get timezone object
TZ = pytz.timezone(TIMEZONE)


def get_now():
    """Get current datetime in configured timezone."""
    return datetime.now(TZ)


def get_today():
    """Get current date in configured timezone."""
    return get_now().date()


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

    # Check for follow-up reminders every 5 minutes
    scheduler.add_job(
        send_followup_reminders,
        CronTrigger(minute="*/5"),
        args=[bot],
        id="followup_reminders",
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


def is_within_reminder_hours() -> bool:
    """Check if current time is within allowed reminder hours (before 21:00)."""
    now = get_now()
    return now.hour < REMINDER_CUTOFF_HOUR


async def send_reminders(bot: Bot):
    """Send reminders for current time."""
    now = get_now()
    current_time = now.strftime("%H:%M")
    current_date = get_today()

    logger.debug(f"Checking reminders for {current_time}, date {current_date}")

    # Pass current_date instead of day_of_week
    schedules = await db.get_schedules_for_time(current_time, current_date)

    for schedule in schedules:
        # Check if log already exists for today
        if await db.check_existing_log(schedule["id"], current_date):
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
                    InlineKeyboardButton(text="✅ Выпил", callback_data=f"taken_{log.id}"),
                    InlineKeyboardButton(text="❌ Пропустил", callback_data=f"missed_{log.id}"),
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
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    chat_id=schedule["chat_id"],
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            logger.info(f"Sent reminder to chat {schedule['chat_id']} for {schedule['pill_name']}")
        except Exception as e:
            logger.error(f"Failed to send reminder: {e}")


async def send_followup_reminders(bot: Bot):
    """Send one follow-up reminder 1 hour after initial if no response."""
    if not is_within_reminder_hours():
        logger.debug("Outside reminder hours, skipping follow-up reminders")
        return

    now = get_now()
    logger.debug("Checking follow-up reminders")

    # Get logs that need 1-hour follow-up (reminder_count = 0, no response)
    logs = await db.get_logs_for_followup_reminder(1)

    for log in logs:
        if log["username"]:
            mention = f"@{log['username']}"
        else:
            mention = log["first_name"] or "Друг"

        text = (
            f"{mention}, напоминаю! Ты ещё не отметил приём:\n\n"
            f"<b>{log['pill_name']}</b> ({log['dosage']})"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Выпил", callback_data=f"taken_{log['id']}"),
                    InlineKeyboardButton(text="❌ Пропустил", callback_data=f"missed_{log['id']}"),
                ]
            ]
        )

        try:
            if log.get("photo_id"):
                await bot.send_photo(
                    chat_id=log["chat_id"],
                    photo=log["photo_id"],
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    chat_id=log["chat_id"],
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )

            await db.update_reminder_count(log["id"], now)
            logger.info(f"Sent follow-up reminder to chat {log['chat_id']} for {log['pill_name']}")
        except Exception as e:
            logger.error(f"Failed to send follow-up reminder: {e}")


async def send_evening_reminders(bot: Bot):
    """Send reminders for pills not taken today."""
    logger.info("Running evening reminders check")

    # Get all unique chat_ids that have pending logs
    import aiosqlite
    from config import DB_PATH

    today = get_today().isoformat()

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
                        text=f"✅ Выпил {pill_log['pill_name']}",
                        callback_data=f"taken_{pill_log['id']}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Пропустил",
                        callback_data=f"missed_{pill_log['id']}"
                    ),
                ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                logger.info(f"Sent evening reminder to chat {chat_id} for user {telegram_id}")

                # Update status to reminded
                for pill_log in data["pills"]:
                    await db.update_intake_status(pill_log["id"], "reminded")
            except Exception as e:
                logger.error(f"Failed to send evening reminder: {e}")
