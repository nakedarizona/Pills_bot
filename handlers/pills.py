from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db

router = Router()


class AddPillStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_dosage = State()
    waiting_for_photo = State()
    waiting_for_frequency = State()
    waiting_for_weekday = State()
    waiting_for_monthday = State()
    waiting_for_interval = State()
    waiting_for_time = State()
    waiting_for_custom_time = State()


class EditPillStates(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_new_dosage = State()
    waiting_for_new_photo = State()


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
        "/mypills - мои таблетки (с фото)\n"
        "/editpill - редактировать таблетку\n"
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
        "   Бот спросит название, дозировку, частоту и время приёма\n\n"
        "2. <b>/mypills</b> - посмотреть все твои таблетки с фото\n\n"
        "3. <b>/editpill</b> - изменить название, дозировку или фото\n\n"
        "4. <b>/today</b> - что нужно выпить сегодня\n\n"
        "5. <b>/deletepill</b> - удалить таблетку\n\n"
        "<b>Частота приёма:</b>\n"
        "- Ежедневно\n"
        "- Через день (каждые 2, 3, N дней)\n"
        "- Раз в неделю (выбрать день)\n"
        "- Раз в месяц (выбрать число)\n\n"
        "<b>Часовой пояс:</b> Dubai (UTC+4)"
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
    await show_frequency_selection(message, state)


@router.callback_query(AddPillStates.waiting_for_photo, F.data == "skip_photo")
async def skip_photo(callback: CallbackQuery, state: FSMContext):
    """Skip photo upload."""
    await state.update_data(photo_id=None)
    await callback.answer()
    await show_frequency_selection(callback.message, state)


async def show_frequency_selection(message: Message, state: FSMContext):
    """Show frequency selection keyboard."""
    await state.set_state(AddPillStates.waiting_for_frequency)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ежедневно", callback_data="freq_daily")],
            [InlineKeyboardButton(text="Через день", callback_data="freq_interval_2")],
            [InlineKeyboardButton(text="Каждые N дней", callback_data="freq_interval_custom")],
            [InlineKeyboardButton(text="Раз в неделю", callback_data="freq_weekly")],
            [InlineKeyboardButton(text="Раз в месяц", callback_data="freq_monthly")],
        ]
    )
    await message.answer("Как часто принимать?", reply_markup=keyboard)


@router.callback_query(AddPillStates.waiting_for_frequency, F.data.startswith("freq_"))
async def process_frequency_selection(callback: CallbackQuery, state: FSMContext):
    """Process frequency selection."""
    freq_data = callback.data.replace("freq_", "")

    if freq_data == "daily":
        await state.update_data(frequency="daily", days=[1, 2, 3, 4, 5, 6, 7], interval_days=1)
        await callback.answer()
        await show_time_selection(callback.message, state)

    elif freq_data == "interval_2":
        await state.update_data(frequency="interval", days=[], interval_days=2)
        await callback.answer()
        await show_time_selection(callback.message, state)

    elif freq_data == "interval_custom":
        await state.set_state(AddPillStates.waiting_for_interval)
        await callback.message.answer("Введи количество дней между приёмами (например: 3):")
        await callback.answer()

    elif freq_data == "weekly":
        await state.set_state(AddPillStates.waiting_for_weekday)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Пн", callback_data="weekday_1"),
                    InlineKeyboardButton(text="Вт", callback_data="weekday_2"),
                    InlineKeyboardButton(text="Ср", callback_data="weekday_3"),
                    InlineKeyboardButton(text="Чт", callback_data="weekday_4"),
                ],
                [
                    InlineKeyboardButton(text="Пт", callback_data="weekday_5"),
                    InlineKeyboardButton(text="Сб", callback_data="weekday_6"),
                    InlineKeyboardButton(text="Вс", callback_data="weekday_7"),
                ],
            ]
        )
        await callback.message.answer("Выбери день недели:", reply_markup=keyboard)
        await callback.answer()

    elif freq_data == "monthly":
        await state.set_state(AddPillStates.waiting_for_monthday)
        await callback.message.answer("Введи число месяца (1-31):")
        await callback.answer()


@router.message(AddPillStates.waiting_for_interval, F.text)
async def process_interval_input(message: Message, state: FSMContext):
    """Process custom interval input."""
    try:
        interval = int(message.text.strip())
        if interval < 1 or interval > 365:
            raise ValueError()
    except ValueError:
        await message.answer("Введи число от 1 до 365:")
        return

    await state.update_data(frequency="interval", days=[], interval_days=interval)
    await show_time_selection(message, state)


@router.callback_query(AddPillStates.waiting_for_weekday, F.data.startswith("weekday_"))
async def process_weekday_selection(callback: CallbackQuery, state: FSMContext):
    """Process weekday selection."""
    weekday = int(callback.data.replace("weekday_", ""))
    await state.update_data(frequency="weekly", days=[weekday], interval_days=1)
    await callback.answer()
    await show_time_selection(callback.message, state)


@router.message(AddPillStates.waiting_for_monthday, F.text)
async def process_monthday_input(message: Message, state: FSMContext):
    """Process month day input."""
    try:
        day = int(message.text.strip())
        if day < 1 or day > 31:
            raise ValueError()
    except ValueError:
        await message.answer("Введи число от 1 до 31:")
        return

    await state.update_data(frequency="monthly", days=[day], interval_days=1)
    await show_time_selection(message, state)


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
    await message.answer("В какое время напоминать?", reply_markup=keyboard)


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

    frequency = data.get("frequency", "daily")
    days = data.get("days", [1, 2, 3, 4, 5, 6, 7])
    interval_days = data.get("interval_days", 1)

    schedule = await db.add_schedule(
        pill_id=pill.id,
        time=time_str,
        days=days,
        frequency=frequency,
        interval_days=interval_days,
    )

    freq_text = get_frequency_text(frequency, days, interval_days)

    await state.clear()
    await message.answer(
        f"Таблетка добавлена!\n\n"
        f"<b>{pill.name}</b> ({pill.dosage})\n"
        f"Время приёма: {time_str}\n"
        f"Частота: {freq_text}"
    )


def get_frequency_text(frequency: str, days: list[int], interval_days: int) -> str:
    """Get human-readable frequency text."""
    if frequency == "daily":
        return "ежедневно"
    elif frequency == "interval":
        if interval_days == 2:
            return "через день"
        return f"каждые {interval_days} дн."
    elif frequency == "weekly":
        day_names = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
        days_str = ", ".join(day_names[d] for d in days)
        return f"раз в неделю ({days_str})"
    elif frequency == "monthly":
        return f"раз в месяц ({days[0]} числа)" if days else "раз в месяц"
    return frequency


@router.message(Command("mypills"))
async def cmd_mypills(message: Message):
    """Show user's pills with photos."""
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

    for pill in pills:
        schedules = await db.get_pill_schedules(pill.id)

        if schedules:
            schedule_lines = []
            for s in schedules:
                freq_text = get_frequency_text(s.frequency, s.days, s.interval_days)
                schedule_lines.append(f"{s.time} ({freq_text})")
            schedule_text = "\n".join(schedule_lines)
        else:
            schedule_text = "не задано"

        text = (
            f"<b>{pill.name}</b>\n"
            f"Дозировка: {pill.dosage}\n"
            f"Расписание:\n{schedule_text}"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Редактировать", callback_data=f"edit_{pill.id}")]
            ]
        )

        if pill.photo_id:
            await message.answer_photo(
                photo=pill.photo_id,
                caption=text,
                reply_markup=keyboard,
            )
        else:
            await message.answer(text + "\n(без фото)", reply_markup=keyboard)


@router.message(Command("editpill"))
async def cmd_editpill(message: Message):
    """Show pills to edit."""
    user = await db.get_user(message.from_user.id, message.chat.id)
    if not user:
        await message.answer("Сначала используй /start для регистрации.")
        return

    pills = await db.get_user_pills(user.id)
    if not pills:
        await message.answer("У тебя нет таблеток для редактирования.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{p.name} ({p.dosage})", callback_data=f"edit_{p.id}")]
            for p in pills
        ]
    )
    await message.answer("Выбери таблетку для редактирования:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("edit_"))
async def show_edit_options(callback: CallbackQuery):
    """Show edit options for pill."""
    pill_id = int(callback.data.replace("edit_", ""))

    pill = await db.get_pill(pill_id)
    if not pill:
        await callback.answer("Таблетка не найдена", show_alert=True)
        return

    user = await db.get_user(callback.from_user.id, callback.message.chat.id)
    if not user or pill.user_id != user.id:
        await callback.answer("Это не твоя таблетка!", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Изменить название", callback_data=f"editname_{pill_id}")],
            [InlineKeyboardButton(text="Изменить дозировку", callback_data=f"editdosage_{pill_id}")],
            [InlineKeyboardButton(text="Изменить фото", callback_data=f"editphoto_{pill_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_mypills")],
        ]
    )

    text = f"<b>Редактирование: {pill.name}</b>\n\nЧто изменить?"

    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("editname_"))
async def start_edit_name(callback: CallbackQuery, state: FSMContext):
    """Start editing pill name."""
    pill_id = int(callback.data.replace("editname_", ""))

    pill = await db.get_pill(pill_id)
    user = await db.get_user(callback.from_user.id, callback.message.chat.id)
    if not user or not pill or pill.user_id != user.id:
        await callback.answer("Ошибка доступа", show_alert=True)
        return

    await state.update_data(edit_pill_id=pill_id)
    await state.set_state(EditPillStates.waiting_for_new_name)
    await callback.message.answer(f"Текущее название: <b>{pill.name}</b>\n\nВведи новое название:")
    await callback.answer()


@router.message(EditPillStates.waiting_for_new_name, F.text)
async def process_new_name(message: Message, state: FSMContext):
    """Process new pill name."""
    data = await state.get_data()
    pill_id = data["edit_pill_id"]

    await db.update_pill(pill_id, name=message.text)
    await state.clear()
    await message.answer(f"Название изменено на: <b>{message.text}</b>")


@router.callback_query(F.data.startswith("editdosage_"))
async def start_edit_dosage(callback: CallbackQuery, state: FSMContext):
    """Start editing pill dosage."""
    pill_id = int(callback.data.replace("editdosage_", ""))

    pill = await db.get_pill(pill_id)
    user = await db.get_user(callback.from_user.id, callback.message.chat.id)
    if not user or not pill or pill.user_id != user.id:
        await callback.answer("Ошибка доступа", show_alert=True)
        return

    await state.update_data(edit_pill_id=pill_id)
    await state.set_state(EditPillStates.waiting_for_new_dosage)
    await callback.message.answer(f"Текущая дозировка: <b>{pill.dosage}</b>\n\nВведи новую дозировку:")
    await callback.answer()


@router.message(EditPillStates.waiting_for_new_dosage, F.text)
async def process_new_dosage(message: Message, state: FSMContext):
    """Process new pill dosage."""
    data = await state.get_data()
    pill_id = data["edit_pill_id"]

    await db.update_pill(pill_id, dosage=message.text)
    await state.clear()
    await message.answer(f"Дозировка изменена на: <b>{message.text}</b>")


@router.callback_query(F.data.startswith("editphoto_"))
async def start_edit_photo(callback: CallbackQuery, state: FSMContext):
    """Start editing pill photo."""
    pill_id = int(callback.data.replace("editphoto_", ""))

    pill = await db.get_pill(pill_id)
    user = await db.get_user(callback.from_user.id, callback.message.chat.id)
    if not user or not pill or pill.user_id != user.id:
        await callback.answer("Ошибка доступа", show_alert=True)
        return

    await state.update_data(edit_pill_id=pill_id)
    await state.set_state(EditPillStates.waiting_for_new_photo)
    await callback.message.answer("Отправь новое фото таблетки:")
    await callback.answer()


@router.message(EditPillStates.waiting_for_new_photo, F.photo)
async def process_new_photo(message: Message, state: FSMContext):
    """Process new pill photo."""
    data = await state.get_data()
    pill_id = data["edit_pill_id"]

    photo_id = message.photo[-1].file_id
    await db.update_pill(pill_id, photo_id=photo_id)
    await state.clear()
    await message.answer("Фото обновлено!")


@router.callback_query(F.data == "back_to_mypills")
async def back_to_mypills(callback: CallbackQuery):
    """Return to pills list."""
    await callback.message.answer("Используй /mypills чтобы посмотреть список таблеток")
    await callback.answer()


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
