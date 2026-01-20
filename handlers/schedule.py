from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

import database as db

router = Router()


@router.message(Command("schedule"))
async def cmd_schedule(message: Message):
    """Show schedule management options."""
    user = await db.get_user(message.from_user.id, message.chat.id)
    if not user:
        await message.answer("Сначала используй /start для регистрации.")
        return

    pills = await db.get_user_pills(user.id)
    if not pills:
        await message.answer(
            "У тебя пока нет таблеток.\n"
            "Используй /addpill чтобы добавить."
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{p.name} ({p.dosage})",
                callback_data=f"schedule_pill_{p.id}"
            )]
            for p in pills
        ]
    )
    await message.answer(
        "Выбери таблетку для управления расписанием:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("schedule_pill_"))
async def show_pill_schedule(callback: CallbackQuery):
    """Show schedule for selected pill."""
    pill_id = int(callback.data.replace("schedule_pill_", ""))

    pill = await db.get_pill(pill_id)
    if not pill:
        await callback.answer("Таблетка не найдена", show_alert=True)
        return

    user = await db.get_user(callback.from_user.id, callback.message.chat.id)
    if not user or pill.user_id != user.id:
        await callback.answer("Это не твоя таблетка!", show_alert=True)
        return

    schedules = await db.get_pill_schedules(pill_id)

    text = f"<b>{pill.name}</b> ({pill.dosage})\n\n"

    if schedules:
        text += "<b>Текущее расписание:</b>\n"
        for s in schedules:
            days_names = get_days_names(s.days)
            text += f"• {s.time} - {days_names}\n"
    else:
        text += "Расписание не задано.\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Добавить время",
                callback_data=f"add_schedule_{pill_id}"
            )],
            [InlineKeyboardButton(
                text="Удалить расписание",
                callback_data=f"del_schedule_{pill_id}"
            )] if schedules else [],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_pills")],
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


def get_days_names(days: list[int]) -> str:
    """Convert day numbers to names."""
    day_names = {
        1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт",
        5: "Пт", 6: "Сб", 7: "Вс"
    }

    if days == [1, 2, 3, 4, 5, 6, 7]:
        return "ежедневно"
    if days == [1, 2, 3, 4, 5]:
        return "будни"
    if days == [6, 7]:
        return "выходные"

    return ", ".join(day_names[d] for d in sorted(days))


@router.callback_query(F.data.startswith("add_schedule_"))
async def add_schedule_time(callback: CallbackQuery):
    """Show time options for adding schedule."""
    pill_id = callback.data.replace("add_schedule_", "")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="06:00", callback_data=f"newtime_{pill_id}_06:00"),
                InlineKeyboardButton(text="08:00", callback_data=f"newtime_{pill_id}_08:00"),
                InlineKeyboardButton(text="10:00", callback_data=f"newtime_{pill_id}_10:00"),
            ],
            [
                InlineKeyboardButton(text="12:00", callback_data=f"newtime_{pill_id}_12:00"),
                InlineKeyboardButton(text="14:00", callback_data=f"newtime_{pill_id}_14:00"),
                InlineKeyboardButton(text="18:00", callback_data=f"newtime_{pill_id}_18:00"),
            ],
            [
                InlineKeyboardButton(text="20:00", callback_data=f"newtime_{pill_id}_20:00"),
                InlineKeyboardButton(text="22:00", callback_data=f"newtime_{pill_id}_22:00"),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data=f"schedule_pill_{pill_id}")],
        ]
    )

    await callback.message.edit_text(
        "Выбери время для приёма:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("newtime_"))
async def save_new_schedule_time(callback: CallbackQuery):
    """Save new schedule time."""
    _, pill_id, time_str = callback.data.split("_")
    pill_id = int(pill_id)

    pill = await db.get_pill(pill_id)
    if not pill:
        await callback.answer("Таблетка не найдена", show_alert=True)
        return

    user = await db.get_user(callback.from_user.id, callback.message.chat.id)
    if not user or pill.user_id != user.id:
        await callback.answer("Это не твоя таблетка!", show_alert=True)
        return

    await db.add_schedule(pill_id=pill_id, time=time_str, days=[1, 2, 3, 4, 5, 6, 7])
    await callback.answer("Время добавлено!")

    # Show updated schedule
    schedules = await db.get_pill_schedules(pill_id)
    text = f"<b>{pill.name}</b> ({pill.dosage})\n\n<b>Текущее расписание:</b>\n"
    for s in schedules:
        days_names = get_days_names(s.days)
        text += f"• {s.time} - {days_names}\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить время", callback_data=f"add_schedule_{pill_id}")],
            [InlineKeyboardButton(text="Удалить расписание", callback_data=f"del_schedule_{pill_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_pills")],
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("del_schedule_"))
async def show_schedules_to_delete(callback: CallbackQuery):
    """Show schedules to delete."""
    pill_id = int(callback.data.replace("del_schedule_", ""))

    schedules = await db.get_pill_schedules(pill_id)
    if not schedules:
        await callback.answer("Нет расписаний для удаления", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{s.time} - {get_days_names(s.days)}",
                callback_data=f"rmschedule_{s.id}_{pill_id}"
            )]
            for s in schedules
        ] + [[InlineKeyboardButton(text="Отмена", callback_data=f"schedule_pill_{pill_id}")]]
    )

    await callback.message.edit_text(
        "Выбери расписание для удаления:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rmschedule_"))
async def delete_schedule(callback: CallbackQuery):
    """Delete selected schedule."""
    _, schedule_id, pill_id = callback.data.split("_")
    schedule_id = int(schedule_id)
    pill_id = int(pill_id)

    pill = await db.get_pill(pill_id)
    user = await db.get_user(callback.from_user.id, callback.message.chat.id)
    if not user or not pill or pill.user_id != user.id:
        await callback.answer("Ошибка доступа", show_alert=True)
        return

    await db.delete_schedule(schedule_id)
    await callback.answer("Расписание удалено!")

    # Show updated pill schedule
    schedules = await db.get_pill_schedules(pill_id)
    text = f"<b>{pill.name}</b> ({pill.dosage})\n\n"

    if schedules:
        text += "<b>Текущее расписание:</b>\n"
        for s in schedules:
            text += f"• {s.time} - {get_days_names(s.days)}\n"
    else:
        text += "Расписание не задано.\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить время", callback_data=f"add_schedule_{pill_id}")],
            [InlineKeyboardButton(text="Удалить расписание", callback_data=f"del_schedule_{pill_id}")] if schedules else [],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_pills")],
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "back_to_pills")
async def back_to_pills(callback: CallbackQuery):
    """Go back to pills list."""
    user = await db.get_user(callback.from_user.id, callback.message.chat.id)
    if not user:
        await callback.answer("Ошибка", show_alert=True)
        return

    pills = await db.get_user_pills(user.id)
    if not pills:
        await callback.message.edit_text("У тебя нет добавленных таблеток.")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{p.name} ({p.dosage})",
                callback_data=f"schedule_pill_{p.id}"
            )]
            for p in pills
        ]
    )

    await callback.message.edit_text(
        "Выбери таблетку для управления расписанием:",
        reply_markup=keyboard
    )
    await callback.answer()
