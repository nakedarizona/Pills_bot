import logging
from datetime import datetime, date
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import database as db
from config import TIMEZONE

logger = logging.getLogger(__name__)

TZ = pytz.timezone(TIMEZONE)

# Morning reminder at 8:00 for pills scheduled 00:00-19:59
MORNING_HOUR = 8
# Evening reminder at 20:00 for pills scheduled 20:00-23:59
EVENING_HOUR = 20


def get_now():
    return datetime.now(TZ)


def get_today():
    return get_now().date()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Setup scheduler with 2 daily reminders."""
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Morning reminder at 8:00 Dubai time
    scheduler.add_job(
        send_morning_reminder,
        CronTrigger(hour=MORNING_HOUR, minute=0, timezone=TZ),
        args=[bot],
        id="morning_reminder",
        replace_existing=True,
    )

    # Evening reminder at 20:00 Dubai time
    scheduler.add_job(
        send_evening_reminder,
        CronTrigger(hour=EVENING_HOUR, minute=0, timezone=TZ),
        args=[bot],
        id="evening_reminder",
        replace_existing=True,
    )

    return scheduler


def build_pills_text_and_keyboard(mention: str, pills: list[dict], header: str) -> tuple[str, InlineKeyboardMarkup]:
    """Build grouped message text and keyboard for a list of pills."""
    lines = [f"{mention}, {header}\n"]

    for p in pills:
        status = p.get("status", "pending")
        if status == "taken":
            taken_at = p.get("taken_at", "")
            time_str = ""
            if taken_at and isinstance(taken_at, str):
                try:
                    t = datetime.fromisoformat(taken_at)
                    time_str = t.strftime("%H:%M")
                except:
                    pass
            suffix = f" — выпито в {time_str}" if time_str else ""
            lines.append(f"✅ {p['pill_name']} ({p['dosage']}){suffix}")
        elif status == "missed":
            lines.append(f"❌ {p['pill_name']} ({p['dosage']}) — пропущено")
        else:
            schedule_time = p.get("time", "")
            time_suffix = f" [{schedule_time}]" if schedule_time else ""
            lines.append(f"⏳ {p['pill_name']} ({p['dosage']}){time_suffix}")

    text = "\n".join(lines)

    buttons = []
    for p in pills:
        if p.get("status", "pending") == "pending":
            buttons.append([
                InlineKeyboardButton(text=f"✅ {p['pill_name']}", callback_data=f"taken_{p['id']}"),
                InlineKeyboardButton(text=f"❌ {p['pill_name']}", callback_data=f"missed_{p['id']}"),
            ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    return text, keyboard


async def send_grouped_reminder(bot: Bot, time_from: str, time_to: str, header: str):
    """Send one grouped reminder per user for pills in the given time range."""
    now = get_now()
    current_date = get_today()

    schedules = await db.get_schedules_for_time_range(time_from, time_to, current_date)

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
            "time": schedule["time"],
            "status": "pending",
        })

    for key, data in user_pills.items():
        if data["username"]:
            mention = f"@{data['username']}"
        else:
            mention = data["first_name"] or "Друг"

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


async def send_morning_reminder(bot: Bot):
    """Morning reminder at 8:00 for all pills scheduled 00:00-19:59."""
    logger.info("Sending morning reminders")
    await send_grouped_reminder(bot, "00:00", "19:59", "пора выпить таблетки!")


async def send_evening_reminder(bot: Bot):
    """Evening reminder at 20:00 for all pills scheduled 20:00-23:59."""
    logger.info("Sending evening reminders")
    await send_grouped_reminder(bot, "20:00", "23:59", "вечерние таблетки!")
