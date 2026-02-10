from datetime import datetime, date
import pytz
from aiogram import Router, F
from aiogram.types import CallbackQuery

import database as db
from config import TIMEZONE

router = Router()

# Get timezone object
TZ = pytz.timezone(TIMEZONE)


def get_now():
    """Get current datetime in configured timezone."""
    return datetime.now(TZ)


def get_today():
    """Get current date in configured timezone."""
    return get_now().date()


@router.callback_query(F.data.startswith("taken_"))
async def confirm_taken(callback: CallbackQuery):
    """Confirm pill was taken."""
    log_id = int(callback.data.replace("taken_", ""))

    log = await db.get_intake_log(log_id)
    if not log:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    # Verify ownership through schedule -> pill -> user chain
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

    # For interval-based schedules, update start_date to today
    # so the next reminder will be after interval_days from today
    if row["frequency"] == "interval":
        today_str = get_today().isoformat()
        await db.update_schedule_start_date(row["schedule_id"], today_str)

    await callback.answer("Отлично! Отмечено как выпито.")

    result_text = (
        f"<b>{row['name']}</b> ({row['dosage']})\n\n"
        f"✅ Выпито в {now.strftime('%H:%M')}"
    )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=result_text, parse_mode="HTML")
        else:
            await callback.message.edit_text(text=result_text, parse_mode="HTML")
    except:
        pass


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

    result_text = (
        f"<b>{row['name']}</b> ({row['dosage']})\n\n"
        f"❌ Пропущено"
    )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=result_text, parse_mode="HTML")
        else:
            await callback.message.edit_text(text=result_text, parse_mode="HTML")
    except:
        pass


@router.callback_query(F.data.startswith("not_taken_"))
async def not_taken_yet(callback: CallbackQuery):
    """User says they haven't taken the pill yet - will be reminded later."""
    log_id = int(callback.data.replace("not_taken_", ""))

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

    if log.status != "pending":
        await callback.answer("Статус уже изменён!")
        return

    # Keep status as pending, the scheduler will send follow-up reminders
    await callback.answer("Хорошо, напомню позже!")

    result_text = (
        f"<b>{row['name']}</b> ({row['dosage']})\n\n"
        f"⏳ Напомню через 3 часа (до 21:00)"
    )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=result_text, parse_mode="HTML")
        else:
            await callback.message.edit_text(text=result_text, parse_mode="HTML")
    except:
        pass


@router.callback_query(F.data.startswith("remind_later_"))
async def remind_later(callback: CallbackQuery):
    """Legacy handler - remind again later."""
    log_id = int(callback.data.replace("remind_later_", ""))

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
            SELECT u.telegram_id
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

    await callback.answer("Напомню позже!")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
