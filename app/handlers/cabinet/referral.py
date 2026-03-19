from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func

from ...database import async_session
from ...models.user import User

router = Router()


@router.message(Command("referral"))
@router.message(F.text == "🎁 Друзья")
async def cmd_referral(message: types.Message):
    await send_referral_info(message)


@router.callback_query(F.data == "menu:referral", StateFilter("*"))
async def cb_referral(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    await send_referral_info(callback.message, user_id=callback.from_user.id)


async def send_referral_info(message: types.Message, user_id: int = None):
    uid = user_id or message.from_user.id

    # Считаем количество приглашенных
    async with async_session() as session:
        stmt = select(func.count(User.id)).where(User.referred_by == uid)
        result = await session.execute(stmt)
        referred_count = result.scalar() or 0

    bot_info = await message.bot.get_me()
    bot_username = bot_info.username

    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"

    text = (
        f"🎁 <b>Реферальная программа</b>\n\n"
        f"Приглашайте друзей и получайте бесплатные AI-кредиты для работы с умными функциями платформы!\n\n"
        f"<b>Условия:</b>\n"
        f"• Вы получаете <b>+3 кредита</b> за каждого нового пользователя.\n"
        f"• За каждых <b>3 приглашенных</b> вы получаете <b>1 день Premium</b>! 👑\n"
        f"• Ваш друг получает <b>+3 кредита</b> к стандартным стартовым.\n\n"
        f"👥 <b>Вы пригласили:</b> {referred_count} чел.\n\n"
        f"👇 <b>Ваша уникальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"Отправьте её друзьям, чтобы они могли начать поиск работы с интеллектом!"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 Поделиться ссылкой",
                    url=f"https://t.me/share/url?url={ref_link}&text=Крутой AI-бот для поиска вакансий!",
                )
            ],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:main")],
        ]
    )

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
