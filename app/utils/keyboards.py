from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


def get_back_button(callback_data: str) -> InlineKeyboardButton:
    """Возвращает стандартную кнопку 'Назад'."""
    return InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data)


def get_main_menu_button() -> InlineKeyboardButton:
    """Возвращает стандартную кнопку 'В главное меню'."""
    return InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:main")


def get_close_button() -> InlineKeyboardButton:
    """Возвращает кнопку закрытия/отмены."""
    return InlineKeyboardButton(text="❌ Закрыть", callback_data="menu:close")


# Новое компактное главное меню
MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🔍 Поиск и Вакансии"),
            KeyboardButton(text="👤 Мой Кабинет"),
        ],
        [KeyboardButton(text="🤖 AI Помощник"), KeyboardButton(text="📊 Аналитика")],
        [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="❓ Помощь")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите раздел...",
)

# Универсальная кнопка отмены для Reply-клавиатур
CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
)

# Текст для кнопок возврата
BACK_BTN_TEXT = "◀️ Назад"
CANCEL_BTN_TEXT = "❌ Отмена"


def get_subscription_keyboard(
    channel_link: str, callback_data: str
) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для обязательной подписки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=channel_link)],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data=callback_data)],
        ]
    )
