from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ...services.user_service import UserService
from ...database import async_session

router = Router()


class SettingsState(StatesGroup):
    waiting_for_keywords = State()


NOTIFY_MODES = {
    "instant": {"label": "⚡ Мгновенно", "desc": "Каждая новая вакансия сразу"},
    "hourly": {"label": "🕐 Раз в час", "desc": "Сводка за последний час"},
    "daily": {"label": "📅 Раз в день", "desc": "Дайджест в 9:00 утра"},
    "off": {"label": "🔕 Выключены", "desc": "Без уведомлений"},
}

TTS_VOICES = {
    "alloy": {"label": "Alloy (Сбалансированный)", "desc": "Универсальный"},
    "echo": {"label": "Echo (Спокойный)", "desc": "Мужской"},
    "fable": {"label": "Fable (Рассказчик)", "desc": "Повествовательный"},
    "onyx": {"label": "Onyx (Глубокий)", "desc": "Мужской"},
    "nova": {"label": "Nova (Энергичный)", "desc": "Женский"},
    "shimmer": {"label": "Shimmer (Мягкий)", "desc": "Женский"},
    "eleven_EXAVITQu4vr4xnSDxMaL": {
        "label": "💎 Bella (Premium)",
        "desc": "ElevenLabs",
    },
    "eleven_pNInz6obpgDQGcFmaJgB": {"label": "💎 Adam (Premium)", "desc": "ElevenLabs"},
}


@router.message(Command("settings"))
async def cmd_settings(message: types.Message, state: FSMContext):
    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(message.from_user.id)

    current_keywords = user.keywords if user.keywords else "Не настроены"
    mode = user.notify_mode or "instant"
    mode_info = NOTIFY_MODES.get(mode, NOTIFY_MODES["instant"])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить ключевые слова", callback_data="set:keywords"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Настроить уведомления", callback_data="set:notify"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔊 Выбрать голос озвучки", callback_data="set:voice"
                )
            ],
        ]
    )

    await message.answer(
        f"⚙️ <b>Ваши настройки</b>\n\n"
        f"🔑 Ключевые слова:\n<code>{current_keywords}</code>\n\n"
        f"🔔 Уведомления: {mode_info['label']}\n"
        f"<i>{mode_info['desc']}</i>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "set:voice")
async def cb_set_voice(callback: types.CallbackQuery):
    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(callback.from_user.id)

    current = user.voice or "alloy"
    buttons = []
    for v_key, v_info in TTS_VOICES.items():
        check = " ✅" if v_key == current else ""
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{v_info['label']}{check}", callback_data=f"setvoice:{v_key}"
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="set:back")])

    await callback.message.edit_text(
        "🔊 <b>Выбор голоса озвучки (TTS)</b>\n\nВыберите голос:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("setvoice:"))
async def cb_set_voice_apply(callback: types.CallbackQuery):
    voice = callback.data.split(":")[1]
    async with async_session() as session:
        user_service = UserService(session)
        await user_service.update_voice(callback.from_user.id, voice)
    await callback.answer("✅ Голос изменен!", show_alert=True)
    await cb_set_voice(callback)


@router.callback_query(F.data == "set:notify")
async def cb_set_notify(callback: types.CallbackQuery):
    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(callback.from_user.id)
    current = user.notify_mode or "instant"
    buttons = []
    for mode_key, mode_info in NOTIFY_MODES.items():
        check = " ✅" if mode_key == current else ""
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{mode_info['label']}{check}",
                    callback_data=f"setnotify:{mode_key}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="set:back")])
    await callback.message.edit_text(
        "🔔 <b>Настройка уведомлений</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("setnotify:"))
async def cb_set_notify_mode(callback: types.CallbackQuery):
    mode = callback.data.split(":")[1]
    async with async_session() as session:
        user_service = UserService(session)
        await user_service.update_notify_mode(callback.from_user.id, mode)
    await callback.answer("✅ Режим обновлен")
    await cb_set_notify(callback)


@router.callback_query(F.data == "set:back")
async def cb_set_back(callback: types.CallbackQuery, state: FSMContext):
    await cmd_settings(callback.message, state)
    await callback.message.delete()


@router.callback_query(F.data == "set:keywords")
async def cb_set_keywords(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✏️ <b>Настройка ключевых слов</b>\n\n"
        "Введите ключевые слова через запятую:\n"
        "<code>python, remote, junior</code>\n\n"
        "или /cancel для отмены.",
        parse_mode="HTML",
    )
    await state.set_state(SettingsState.waiting_for_keywords)
    await callback.answer()


@router.message(SettingsState.waiting_for_keywords)
async def process_keywords(message: types.Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("Действие отменено.")
        return

    keywords = message.text
    async with async_session() as session:
        user_service = UserService(session)
        await user_service.update_keywords(message.from_user.id, keywords)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Назад в настройки", callback_data="menu:settings_btn"
                )
            ]
        ]
    )
    await message.answer(
        f"✅ Ключевые слова обновлены: <code>{keywords}</code>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await state.clear()
