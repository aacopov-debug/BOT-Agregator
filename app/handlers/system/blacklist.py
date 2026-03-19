from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from ...services.user_service import UserService
from ...database import async_session

router = Router()


class BlacklistState(StatesGroup):
    waiting_for_stopwords = State()


@router.message(Command("blacklist"))
async def cmd_blacklist(message: types.Message):
    """Меню управления черным списком слов."""
    await send_blacklist_menu(message)


async def send_blacklist_menu(message: types.Message):
    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(message.from_user.id)

    stop_words = user.stop_words if user.stop_words else "Пусто"

    text = (
        f"🚫 <b>Черный список (Анти-спам)</b>\n\n"
        f"Бот будет автоматически <b>игнорировать</b> вакансии, если в их заголовке, описании или названии компании будут найдены эти слова.\n\n"
        f"<b>Текущие стоп-слова:</b>\n"
        f"<code>{stop_words}</code>\n\n"
        f"<i>Пример: 1С, офис, стажер, php</i>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить список", callback_data="blacklist:edit"
                )
            ],
            [InlineKeyboardButton(text="🗑 Очистить", callback_data="blacklist:clear")],
        ]
    )

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "blacklist:edit")
async def cb_blacklist_edit(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🚫 Пожалуйста, отправьте мне новые стоп-слова через запятую.\n\n"
        "Например: <code>битрикс, офис, junior</code>\n\n"
        "<i>Для отмены введите /cancel</i>",
        parse_mode="HTML",
    )
    await state.set_state(BlacklistState.waiting_for_stopwords)
    await callback.answer()


@router.callback_query(F.data == "blacklist:clear")
async def cb_blacklist_clear(callback: types.CallbackQuery):
    async with async_session() as session:
        user_service = UserService(session)
        await user_service.update_stop_words(callback.from_user.id, "")

    await callback.message.edit_text(
        "✅ Черный список очищен! Теперь вы будете получать <b>все</b> вакансии по ключевым словам.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(BlacklistState.waiting_for_stopwords)
async def process_new_stopwords(message: types.Message, state: FSMContext):
    text = message.text.strip()

    if text == "/cancel":
        await message.answer("❌ Изменение черного списка отменено.")
        await state.clear()
        return

    # Чистим строку (убираем лишние пробелы вокруг слов)
    words = [w.strip().lower() for w in text.split(",") if w.strip()]
    cleaned_stopwords = ", ".join(words)

    async with async_session() as session:
        user_service = UserService(session)
        await user_service.update_stop_words(message.from_user.id, cleaned_stopwords)

    await message.answer(
        f"✅ <b>Черный список обновлен!</b>\n\n"
        f"Бот больше не будет присылать вам вакансии со словами:\n"
        f"<code>{cleaned_stopwords}</code>",
        parse_mode="HTML",
    )
    await state.clear()
