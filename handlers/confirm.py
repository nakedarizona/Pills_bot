import re
from datetime import datetime, date
import pytz
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import database as db
from config import TIMEZONE

router = Router()

TZ = pytz.timezone(TIMEZONE)


def get_now():
    return datetime.now(TZ)


def get_today():
    return get_now().date()


def extract_log_ids_from_markup(markup) -> list[int]:
    """Extract all log IDs from inline keyboard buttons."""
    log_ids = set()
    if not markup or not markup.inline_keyboard:
        return []
    for row in markup.inline_keyboard:
        for btn in row:
            if btn.callback_data:
                match = re.search(r"(?:taken|missed)_(\d+)", btn.callback_data)
                if match:
                    log_ids.add(int(match.group(1)))
    return sorted(log_ids)


def extract_log_ids_from_text(text: str) -> list[int]:
    """Extract log IDs mentioned in the message text as a fallback."""
    # This won't work - log IDs are only in buttons
    return []


async def rebuild_message(callback: CallbackQuery, current_log_id: int):
    """Rebuild the grouped message with updated statuses."""
    # Get all log IDs from the keyboard of the original message
    log_ids = extract_log_ids_from_markup(callback.message.reply_markup)

    # Also include the current log_id (might already be in list, but ensure it)
    if current_log_id not in log_ids:
        log_ids.append(current_log_id)
        log_ids.sort()

    # Fetch fresh data for all logs
    logs = await db.get_intake_logs_by_ids(log_ids)
    if not logs:
        return

    # Extract the header from original message (first line before the pill list)
    original_text = callback.message.text or callback.message.caption or ""
    first_line = original_text.split("\n")[0] if original_text else ""

    # Build updated text
    lines = [first_line, ""]
    for log in logs:
        status = log.get("status", "pending")
        if status == "taken":
            taken_at = log.get("taken_at", "")
            time_str = ""
            if taken_at:
                try:
                    t = datetime.fromisoformat(taken_at)
                    time_str = t.strftime("%H:%M")
                except:
                    pass
            suffix = f" — выпито в {time_str}" if time_str else ""
            lines.append(f"✅ {log['pill_name']} ({log['dosage']}){suffix}")
        elif status == "missed":
            lines.append(f"❌ {log['pill_name']} ({log['dosage']}) — пропущено")
        else:
            lines.append(f"⏳ {log['pill_name']} ({log['dosage']})")

    text = "\n".join(lines)

    # Build keyboard only for still-pending pills
    buttons = []
    for log in logs:
        if log.get("status", "pending") == "pending":
            buttons.append([
                InlineKeyboardButton(text=f"✅ {log['pill_name']}", callback_data=f"taken_{log['id']}"),
                InlineKeyboardButton(text=f"❌ {log['pill_name']}", callback_data=f"missed_{log['id']}"),
            ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    try:
        await callback.message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")
    except:
        pass


@router.callback_query(F.data.startswith("taken_"))
async def confirm_taken(callback: CallbackQuery):
    """Confirm pill was taken."""
    log_id = int(callback.data.replace("taken_", ""))

    log = await db.get_intake_log(log_id)
    if not log:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    import aiosqlite
    from config import DB_PATH

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT u.telegram_id, p.name, p.dosage, s.frequency, s.id as schedule_id
            FROM schedules s
            JOIN pills p ON s.pill_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE s.id = ?
            """,
            (log.schedule_id,),
        )
        row = await cursor.fetchone()

    if not row or row["telegram_id"] != callback.from_user.id:
        await callback.answer("Это не твоя таблетка!", show_alert=True)
        return

    if log.status == "taken":
        await callback.answer("Уже отмечено как выпито!")
        return

    now = get_now()
    await db.update_intake_status(log_id, "taken", now)

    if row["frequency"] == "interval":
        today_str = get_today().isoformat()
        await db.update_schedule_start_date(row["schedule_id"], today_str)

    await callback.answer("Отлично! Отмечено как выпито.")
    await rebuild_message(callback, log_id)


@router.callback_query(F.data.startswith("missed_"))
async def confirm_missed(callback: CallbackQuery):
    """Confirm pill was missed."""
    log_id = int(callback.data.replace("missed_", ""))

    log = await db.get_intake_log(log_id)
    if not log:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    import aiosqlite
    from config import DB_PATH

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT u.telegram_id, p.name, p.dosage
            FROM schedules s
            JOIN pills p ON s.pill_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE s.id = ?
            """,
            (log.schedule_id,),
        )
        row = await cursor.fetchone()

    if not row or row["telegram_id"] != callback.from_user.id:
        await callback.answer("Это не твоя таблетка!", show_alert=True)
        return

    if log.status == "missed":
        await callback.answer("Уже отмечено как пропущено!")
        return

    await db.update_intake_status(log_id, "missed")
    await callback.answer("Отмечено как пропущено.")
    await rebuild_message(callback, log_id)
