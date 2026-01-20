from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db

router = Router()


class AddPillStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_dosage = State()
    waiting_for_photo = State()
    waiting_for_time = State()
    waiting_for_custom_time = State()


def get_user_mention(username: str | None, first_name: str | None) -> str:
    """Get user mention string."""
    if username:
        return f"@{username}"
    return first_name or "Пользователь"


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle /start command - register user."""
    user = await db.get_or_create_user(
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    await message.answer(
        f"Привет, {get_user_mention(user.username, user.first_name)}!\n\n"
        "Я помогу тебе не забывать принимать таблетки.\n\n"
        "<b>Команды:</b>\n"
        "/addpill - добавить таблетку\n"
        "/mypills - мои таблетки\n"
        "/today - расписание на сегодня\n"
        "/deletepill - удалить таблетку\n"
        "/help - помощь"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command."""
    await message.answer(
        "<b>Как пользоваться ботом:</b>\n\n"
        "1. <b>/addpill</b> - добавить новую таблетку\n"
        "   Бот спросит название, дозировку и время приёма\n\n"
        "2. <b>/mypills</b> - посмотреть все твои таблетки\n\n"
        "3. <b>/today</b> - что нужно выпить сегодня\n\n"
        "4. <b>/deletepill</b> - удалить таблетку\n\n"
        "<b>Как работают напоминания:</b>\n"
        "- Бот напомнит в указанное время\n"
        "- Нажми кнопку когда выпьешь таблетку\n"
        "- Если забудешь - вечером напомню ещё раз"
    )


@router.message(Command("addpill"))
async def cmd_addpill(message: Message, state: FSMContext):
    """Start adding a new pill."""
    user = await db.get_or_create_user(
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    await state.update_data(user_id=user.id)
    await state.set_state(AddPillStates.waiting_for_name)
    await message.answer("Введи название таблетки:")


@router.message(AddPillStates.waiting_for_name, F.text)
async def process_pill_name(message: Message, state: FSMContext):
    """Process pill name."""
    await state.update_data(pill_name=message.text)
    await state.set_state(AddPillStates.waiting_for_dosage)
    await message.answer("Введи дозировку (например: 500мг, 1 капсула, 2 таблетки):")


@router.message(AddPillStates.waiting_for_dosage, F.text)
async def process_pill_dosage(message: Message, state: FSMContext):
    """Process pill dosage."""
    await state.update_data(dosage=message.text)
    await state.set_state(AddPillStates.waiting_for_photo)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить", callback_data="skip_photo")]
        ]
    )
    await message.answer(
        "Отправь фото таблетки или нажми 'Пропустить':",
        reply_markup=keyboard,
    )


@router.message(AddPillStates.waiting_for_photo, F.photo)
async def process_pill_photo(message: Message, state: FSMContext):
    """Process pill photo."""
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await show_time_selection(message, state)


@router.callback_query(AddPillStates.waiting_for_photo, F.data == "skip_photo")
async def skip_photo(callback: CallbackQuery, state: FSMContext):
    """Skip photo upload."""
    await state.update_data(photo_id=None)
    await callback.answer()
    await show_time_selection(callback.message, state)


async def show_time_selection(message: Message, state: FSMContext):
    """Show time selection keyboard."""
    await state.set_state(AddPillStates.waiting_for_time)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Утро 08:00", callback_data="time_08:00"),
                InlineKeyboardButton(text="День 14:00", callback_data="time_14:00"),
            ],
            [
                InlineKeyboardButton(text="Вечер 20:00", callback_data="time_20:00"),
                InlineKeyboardButton(text="Своё время", callback_data="time_custom"),
            ],
        ]
    )
    await message.answer("Когда принимать таблетку?", reply_markup=keyboard)


@router.callback_query(AddPillStates.waiting_for_time, F.data.startswith("time_"))
async def process_time_selection(callback: CallbackQuery, state: FSMContext):
    """Process time selection."""
    time_data = callback.data.replace("time_", "")

    if time_data == "custom":
        await state.set_state(AddPillStates.waiting_for_custom_time)
        await callback.message.answer("Введи время в формате ЧЧ:ММ (например: 09:30):")
        await callback.answer()
        return

    await save_pill(callback.message, state, time_data)
    await callback.answer()


@router.message(AddPillStates.waiting_for_custom_time, F.text)
async def process_custom_time(message: Message, state: FSMContext):
    """Process custom time input."""
    time_str = message.text.strip()

    # Validate time format
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError()
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError()
        time_str = f"{hour:02d}:{minute:02d}"
    except ValueError:
        await message.answer("Неверный формат. Введи время в формате ЧЧ:ММ (например: 09:30):")
        return

    await save_pill(message, state, time_str)


async def save_pill(message: Message, state: FSMContext, time_str: str):
    """Save pill to database."""
    data = await state.get_data()

    pill = await db.add_pill(
        user_id=data["user_id"],
        name=data["pill_name"],
        dosage=data["dosage"],
        photo_id=data.get("photo_id"),
    )

    # Add schedule for all days of the week
    await db.add_schedule(pill_id=pill.id, time=time_str, days=[1, 2, 3, 4, 5, 6, 7])

    await state.clear()
    await message.answer(
        f"Таблетка добавлена!\n\n"
        f"<b>{pill.name}</b> ({pill.dosage})\n"
        f"Время приёма: {time_str}\n"
        f"Дни: ежедневно"
    )


@router.message(Command("mypills"))
async def cmd_mypills(message: Message):
    """Show user's pills."""
    user = await db.get_user(message.from_user.id, message.chat.id)
    if not user:
        await message.answer("Сначала используй /start для регистрации.")
        return

    pills = await db.get_user_pills(user.id)
    if not pills:
        await message.answer(
            "У тебя пока нет добавленных таблеток.\n"
            "Используй /addpill чтобы добавить."
        )
        return

    text = "<b>Твои таблетки:</b>\n\n"
    for pill in pills:
        schedules = await db.get_pill_schedules(pill.id)
        times = ", ".join(s.time for s in schedules) if schedules else "не задано"
        text += f"• <b>{pill.name}</b> ({pill.dosage})\n  Время: {times}\n\n"

    await message.answer(text)


@router.message(Command("deletepill"))
async def cmd_deletepill(message: Message):
    """Show pills to delete."""
    user = await db.get_user(message.from_user.id, message.chat.id)
    if not user:
        await message.answer("Сначала используй /start для регистрации.")
        return

    pills = await db.get_user_pills(user.id)
    if not pills:
        await message.answer("У тебя нет таблеток для удаления.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{p.name} ({p.dosage})", callback_data=f"delete_{p.id}")]
            for p in pills
        ]
    )
    await message.answer("Выбери таблетку для удаления:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("delete_"))
async def process_delete_pill(callback: CallbackQuery):
    """Delete selected pill."""
    pill_id = int(callback.data.replace("delete_", ""))

    pill = await db.get_pill(pill_id)
    if not pill:
        await callback.answer("Таблетка не найдена", show_alert=True)
        return

    # Check ownership
    user = await db.get_user(callback.from_user.id, callback.message.chat.id)
    if not user or pill.user_id != user.id:
        await callback.answer("Это не твоя таблетка!", show_alert=True)
        return

    await db.delete_pill(pill_id)
    await callback.answer("Удалено!")
    await callback.message.edit_text(f"Таблетка <b>{pill.name}</b> удалена.")


@router.message(Command("today"))
async def cmd_today(message: Message):
    """Show today's schedule."""
    user = await db.get_user(message.from_user.id, message.chat.id)
    if not user:
        await message.answer("Сначала используй /start для регистрации.")
        return

    schedule = await db.get_user_today_schedule(user.id)
    if not schedule:
        await message.answer("На сегодня ничего не запланировано.")
        return

    text = "<b>Расписание на сегодня:</b>\n\n"
    for item in schedule:
        status_emoji = {
            "taken": "✅",
            "missed": "❌",
            "pending": "⏳",
            "reminded": "🔔",
            None: "⏳",
        }.get(item.get("intake_status"), "⏳")

        text += f"{status_emoji} {item['time']} - <b>{item['pill_name']}</b> ({item['dosage']})\n"

    await message.answer(text)
