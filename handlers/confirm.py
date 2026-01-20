from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery

import database as db

router = Router()


@router.callback_query(F.data.startswith("taken_"))
async def confirm_taken(callback: CallbackQuery):
    """Confirm pill was taken."""
    log_id = int(callback.data.replace("taken_", ""))

    log = await db.get_intake_log(log_id)
    if not log:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    # Verify ownership through schedule -> pill -> user chain
    from database import get_pill, get_user
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

    if log.status == "taken":
        await callback.answer("Уже отмечено как выпито!")
        return

    await db.update_intake_status(log_id, "taken", datetime.now())
    await callback.answer("Отлично! Отмечено как выпито.")

    await callback.message.edit_text(
        f"<b>{row['name']}</b> ({row['dosage']})\n\n"
        f"Выпито в {datetime.now().strftime('%H:%M')}"
    )


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

    await callback.message.edit_text(
        f"<b>{row['name']}</b> ({row['dosage']})\n\n"
        f"Пропущено"
    )


@router.callback_query(F.data.startswith("remind_later_"))
async def remind_later(callback: CallbackQuery):
    """Remind again in 30 minutes."""
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

    await callback.answer("Напомню через 30 минут!")
    await callback.message.edit_reply_markup(reply_markup=None)
