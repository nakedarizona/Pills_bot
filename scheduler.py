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


def build_pills_text_and_keyboard(mention: str, pills: list[dict], header: str) -> tuple[str, InlineKeyboardMarkup]:
    """Build grouped message text and keyboard for a list of pills.

    Each pill dict must have: id (log_id), pill_name, dosage, status.
    Optional: taken_at.
    """
    lines = [f"{mention}, {header}\n"]

    for p in pills:
        status = p.get("status", "pending")
        if status == "taken":
            taken_at = p.get("taken_at", "")
            if taken_at and isinstance(taken_at, str) and len(taken_at) >= 16:
                try:
                    t = datetime.fromisoformat(taken_at)
                    time_str = t.strftime("%H:%M")
                except:
                    time_str = ""
            else:
                time_str = ""
            suffix = f" — выпито в {time_str}" if time_str else ""
            lines.append(f"✅ {p['pill_name']} ({p['dosage']}){suffix}")
        elif status == "missed":
            lines.append(f"❌ {p['pill_name']} ({p['dosage']}) — пропущено")
        else:
            lines.append(f"⏳ {p['pill_name']} ({p['dosage']})")

    text = "\n".join(lines)

    # Build keyboard only for pending pills
    buttons = []
    for p in pills:
        if p.get("status", "pending") == "pending":
            buttons.append([
                InlineKeyboardButton(text=f"✅ {p['pill_name']}", callback_data=f"taken_{p['id']}"),
                InlineKeyboardButton(text=f"❌ {p['pill_name']}", callback_data=f"missed_{p['id']}"),
            ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    return text, keyboard


async def send_reminders(bot: Bot):
    """Send reminders for current time, grouped by user."""
    now = get_now()
    current_time = now.strftime("%H:%M")
    current_date = get_today()

    logger.debug(f"Checking reminders for {current_time}, date {current_date}")

    schedules = await db.get_schedules_for_time(current_time, current_date)

    # Create logs and group by (chat_id, telegram_id)
    user_pills = {}
    for schedule in schedules:
        if await db.check_existing_log(schedule["id"], current_date):
            continue

        log = await db.create_intake_log(
            schedule_id=schedule["id"],
            scheduled_time=now,
        )

        key = (schedule["chat_id"], schedule["telegram_id"])
        if key not in user_pills:
            user_pills[key] = {
                "chat_id": schedule["chat_id"],
                "username": schedule["username"],
                "first_name": schedule["first_name"],
                "pills": [],
            }
        user_pills[key]["pills"].append({
            "id": log.id,
            "pill_name": schedule["pill_name"],
            "dosage": schedule["dosage"],
            "status": "pending",
        })

    # Send one message per user
    for key, data in user_pills.items():
        if data["username"]:
            mention = f"@{data['username']}"
        else:
            mention = data["first_name"] or "Друг"

        header = "пора выпить таблетки!" if len(data["pills"]) > 1 else "пора выпить таблетку!"
        text, keyboard = build_pills_text_and_keyboard(mention, data["pills"], header)

        try:
            await bot.send_message(
                chat_id=data["chat_id"],
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            pill_names = ", ".join(p["pill_name"] for p in data["pills"])
            logger.info(f"Sent reminder to chat {data['chat_id']} for {pill_names}")
        except Exception as e:
            logger.error(f"Failed to send reminder: {e}")


async def send_followup_reminders(bot: Bot):
    """Send one follow-up reminder 1 hour after initial if no response, grouped by user."""
    if not is_within_reminder_hours():
        logger.debug("Outside reminder hours, skipping follow-up reminders")
        return

    now = get_now()
    logger.debug("Checking follow-up reminders")

    logs = await db.get_logs_for_followup_reminder(1)

    # Group by (chat_id, telegram_id)
    user_logs = {}
    for log in logs:
        key = (log["chat_id"], log["telegram_id"])
        if key not in user_logs:
            user_logs[key] = {
                "chat_id": log["chat_id"],
                "username": log["username"],
                "first_name": log["first_name"],
                "pills": [],
                "log_ids": [],
            }
        user_logs[key]["pills"].append({
            "id": log["id"],
            "pill_name": log["pill_name"],
            "dosage": log["dosage"],
            "status": "pending",
        })
        user_logs[key]["log_ids"].append(log["id"])

    for key, data in user_logs.items():
        if data["username"]:
            mention = f"@{data['username']}"
        else:
            mention = data["first_name"] or "Друг"

        text, keyboard = build_pills_text_and_keyboard(mention, data["pills"], "напоминаю! Ты ещё не отметил приём:")

        try:
            await bot.send_message(
                chat_id=data["chat_id"],
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            for log_id in data["log_ids"]:
                await db.update_reminder_count(log_id, now)
            logger.info(f"Sent follow-up reminder to chat {data['chat_id']}")
        except Exception as e:
            logger.error(f"Failed to send follow-up reminder: {e}")


async def send_evening_reminders(bot: Bot):
    """Send reminders for pills not taken today, grouped by user."""
    logger.info("Running evening reminders check")

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
            user_logs[user_key]["pills"].append({
                "id": log["id"],
                "pill_name": log["pill_name"],
                "dosage": log["dosage"],
                "status": "pending",
            })

        for telegram_id, data in user_logs.items():
            if data["username"]:
                mention = f"@{data['username']}"
            else:
                mention = data["first_name"] or "Друг"

            text, keyboard = build_pills_text_and_keyboard(
                mention, data["pills"], "ты не отметил приём таблеток сегодня:"
            )

            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                logger.info(f"Sent evening reminder to chat {chat_id} for user {telegram_id}")

                for pill in data["pills"]:
                    await db.update_intake_status(pill["id"], "reminded")
            except Exception as e:
                logger.error(f"Failed to send evening reminder: {e}")
