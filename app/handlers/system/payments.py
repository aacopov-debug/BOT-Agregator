"""Обработчик монетизации (баланс, тарифы, Telegram Stars, Premium, YooMoney)."""

import uuid
from datetime import datetime, timedelta, timezone
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

from ...services.pay_service import PayService
from ...services.user_service import UserService
from ...database import async_session
from ...models.payment import Payment
from ...config import settings

router = Router()
pay_service = PayService()

# ===== ТАРИФЫ =====
CREDIT_PACKS = [
    {"credits": 20, "stars": 75, "rub": 99, "name": "⚡ Стартовый", "emoji": "🟢"},
    {"credits": 50, "stars": 150, "rub": 199, "name": "🚀 Продвинутый", "emoji": "🟡"},
    {"credits": 150, "stars": 375, "rub": 499, "name": "💎 Про", "emoji": "🔵"},
]

PREMIUM_PLANS = [
    {"days": 3, "stars": 75, "rub": 99, "name": "3 дня Premium (Trial)", "emoji": "⏳"},
    {"months": 1, "stars": 375, "rub": 490, "name": "1 мес Premium", "emoji": "💎"},
    {
        "months": 3,
        "stars": 999,
        "rub": 1290,
        "name": "3 мес Premium (-12%)",
        "emoji": "💎💎",
    },
    {
        "months": 12,
        "stars": 2999,
        "rub": 3990,
        "name": "12 мес Premium (-32%)",
        "emoji": "💎💎💎",
    },
]

HR_PACKS = [
    {"count": 1, "stars": 500, "name": "1 Вакансия", "emoji": "🎯"},
    {"count": 3, "stars": 1200, "name": "3 Вакансии (-20%)", "emoji": "🚀"},
    {"count": 10, "stars": 3500, "name": "10 Вакансий (-30%)", "emoji": "🔥"},
]


# ===== БАЛАНС =====
@router.message(Command("balance"))
async def cmd_balance(message: types.Message):
    """Показывает баланс AI-кредитов."""
    user_id = message.from_user.id
    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            user_id, message.from_user.username
        )
        credits = user.ai_credits
        is_prem = (
            user.is_premium
            and user.premium_until
            and user.premium_until > datetime.now(timezone.utc)
        )

    if is_prem:
        status_label = "👑 Admin" if user.role == "admin" else "👑 Premium"
        premium_str = (
            f"\n{status_label} до {user.premium_until.strftime('%d.%m.%Y')}"
            if user.role != "admin"
            else f"\n{status_label} (Безлимит)"
        )
        credits_str = "♾ Безлимит"
    else:
        premium_str = ""
        credits_str = str(credits)

    text = (
        f"💎 <b>Баланс: {credits_str} AI-кредитов</b>{premium_str}\n\n"
        f"1 кредит = 1 AI-генерация:\n"
        f"• ✉️ Сопроводительное письмо\n"
        f"• 🎯 Глубокий AI-анализ\n"
        f"• 🎤 Тренировка собеседования\n\n"
        f"🆓 <b>Для бесплатных пользователей:</b>\n"
        f"👀 Просмотр вакансий: 2 в день (у вас {user.daily_views}/2)\n\n"
        f"💳 <b>Оплата картами банков РФ или ⭐ Stars</b>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💎 Купить кредиты", callback_data="shop:credits"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👑 Premium подписка", callback_data="shop:premium"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💼 Для HR (Вакансии)", callback_data="shop:hr"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Оплата картой / ЮMoney", callback_data="shop:yoomoney"
                )
            ],
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("premium"))
async def cmd_premium(message: types.Message):
    """Показывает информацию о Premium."""
    await show_premium_menu(message)


# ===== ВИТРИНА КРЕДИТОВ =====
@router.callback_query(F.data.in_(["shop:credits", "shop:yoomoney"]))
async def shop_credits(callback: types.CallbackQuery):
    text = (
        "💎 <b>Пакеты AI-кредитов</b>\n\n"
        "Оплата картой 🇷🇺 РФ или Telegram Stars.\n"
        "Выберите пакет:"
    )
    buttons = []
    for p in CREDIT_PACKS:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{p['emoji']} {p['name']} ({p['credits']} шт) — {p['rub']}₽ / ⭐{p['stars']}",
                    callback_data=f"select_method:credits:{p['credits']}:{p['rub']}:{p['stars']}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_balance")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== ВИТРИНА PREMIUM =====
@router.callback_query(F.data == "shop:premium")
async def shop_premium(callback: types.CallbackQuery):
    await show_premium_menu(callback.message, edit=True)
    await callback.answer()


async def show_premium_menu(message: types.Message, edit: bool = False):
    text = (
        "👑 <b>Premium-подписка</b>\n\n"
        "<b>Что входит:</b>\n"
        "• ♾ <b>Безлимитный</b> просмотр всех вакансий\n"
        "• ♾ Безлимитные AI-генерации (писем, анализов)\n"
        "• ⚡ Мгновенные уведомления о новых вакансиях\n"
        "• 📊 Расширенная аналитика рынка\n"
        "• 🚫 Без рекламы и лимитов\n\n"
        "Выберите план:"
    )

    buttons = []
    for p in PREMIUM_PLANS:
        val = p.get("months", p.get("days"))
        p_type = "premium_m" if "months" in p else "premium_d"

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{p['emoji']} {p['name']} — {p['rub']}₽ / ⭐{p['stars']}",
                    callback_data=f"select_method:{p_type}:{val}:{p['rub']}:{p['stars']}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_balance")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ===== ВИТРИНА HR (ВАКАНСИИ) =====
@router.callback_query(F.data == "shop:hr")
async def shop_hr(callback: types.CallbackQuery):
    text = (
        "💼 <b>Пакеты размещений для HR</b>\n\n"
        "Размещайте вакансии со статусом 🔥 <b>Прямой работодатель</b>.\n"
        "Купите пакет сейчас и публикуйте когда удобно!\n"
    )
    buttons = []
    for p in HR_PACKS:
        rub_price = int(p["stars"] * 1.3)
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{p['emoji']} {p['name']} — {rub_price}₽ / ⭐{p['stars']}",
                    callback_data=f"select_method:hr_pack:{p['count']}:{rub_price}:{p['stars']}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_balance")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== ВЫБОР МЕТОДА ОПЛАТЫ =====
@router.callback_query(F.data.startswith("select_method:"))
async def select_payment_method(callback: types.CallbackQuery):
    """Экран выбора: Stars или YooMoney."""
    parts = callback.data.split(":")
    p_type = parts[1]
    p_val = parts[2]
    p_rub = parts[3]
    p_stars = parts[4]

    name_map = {
        "credits": f"{p_val} AI-кредитов",
        "premium_m": f"Premium на {p_val} мес.",
        "premium_d": f"Premium на {p_val} дн.",
        "hr_pack": f"Пакет: {p_val} вакансий",
    }
    prod_name = name_map.get(p_type, "Услуга")

    text = f"💳 <b>Оплата: {prod_name}</b>\n\nВыберите удобный способ оплаты:"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⭐ Telegram Stars (⭐{p_stars})",
                    callback_data=f"stars_go:{p_type}:{p_val}:{p_stars}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"💳 Банковская карта РФ ({p_rub}₽)",
                    callback_data=f"yoomoney_go:{p_type}:{p_val}:{p_rub}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data=f"shop:{'premium' if 'premium' in p_type else ('hr' if 'hr' in p_type else 'credits')}",
                )
            ],
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== ЗАПУСК ОПЛАТЫ STARS =====
@router.callback_query(F.data.startswith("stars_go:"))
async def stars_go_unified(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    p_type = parts[1]
    p_val = parts[2]
    p_stars = int(parts[3])

    name_map = {
        "credits": f"{p_val} AI-кредитов",
        "premium_m": f"Premium на {p_val} мес.",
        "premium_d": f"Premium на {p_val} дн.",
        "hr_pack": f"Пакет: {p_val} вакансий",
    }
    prod_name = name_map.get(p_type, "Услуга")
    payload = f"{p_type}:{p_val}"

    await callback.message.answer_invoice(
        title=prod_name,
        description=f"Оплата {prod_name} для бота ArBOT.",
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label=prod_name, amount=p_stars)],
    )
    await callback.answer()


# ===== ЗАПУСК ОПЛАТЫ YOOMONEY =====
@router.callback_query(F.data.startswith("yoomoney_go:"))
async def yoomoney_go_unified(callback: types.CallbackQuery):
    await callback.answer("⏳ Генерируем ссылку...")

    parts = callback.data.split(":")
    p_type = parts[1]
    p_val = int(parts[2])
    p_rub = float(parts[3])

    if not pay_service.is_configured():
        await callback.answer("❌ Оплата временно недоступна", show_alert=True)
        return

    user_id = callback.from_user.id
    db_type = "premium" if "premium" in p_type else p_type
    db_val = p_val * 30 if p_type == "premium_m" else p_val

    unique_label = f"u{user_id}_{p_type[:3]}{p_val}_{uuid.uuid4().hex[:6]}"

    async with async_session() as session:
        payment = Payment(
            user_telegram_id=user_id,
            label=unique_label,
            product_type=db_type,
            product_val=db_val,
            price=p_rub,
            credits_amount=db_val if db_type == "credits" else 0,
        )
        session.add(payment)
        await session.commit()
        payment_id = payment.id

    payment_link = await pay_service.generate_payment_link(
        label=unique_label,
        amount=p_rub,
        description=f"Оплата JobBot: {p_type} ({p_val})",
    )

    if not payment_link:
        try:
            await callback.message.answer(
                "⚠️ Ошибка генерации ссылки. Попробуйте ещё раз через минуту."
            )
        except Exception:
            pass
        return

    text = (
        f"💳 <b>Оплата картой / ЮMoney</b>\n"
        f"Сумма: <b>{p_rub} ₽</b>\n\n"
        f"После оплаты нажмите кнопку «Проверить», чтобы активировать услугу."
    )

    stars_price = int(p_rub / 1.3) if p_rub > 0 else 0

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_link)],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить оплату", callback_data=f"check_pay:{payment_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data=f"select_method:{p_type}:{p_val}:{p_rub}:{stars_price}",
                )
            ],
        ]
    )

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("check_pay:"))
async def check_payment(callback: types.CallbackQuery):
    payment_id = int(callback.data.split(":")[1])
    await callback.answer("⏳ Проверяем...")

    is_success = await pay_service.process_successful_payment(payment_id)

    if is_success:
        async with async_session() as session:
            from sqlalchemy import select

            stmt = select(Payment).where(Payment.id == payment_id)
            res = await session.execute(stmt)
            p = res.scalar_one_or_none()
            if p:
                admin_msg = (
                    f"💰 <b>Успешная оплата (YooMoney)!</b>\n\n"
                    f"👤 Юзер: ID {p.user_telegram_id}\n"
                    f"📦 Товар: {p.product_type} ({p.product_val})\n"
                    f"💵 Сумма: <b>{p.price} ₽</b>"
                )
                try:
                    await callback.bot.send_message(
                        settings.ADMIN_ID, admin_msg, parse_mode="HTML"
                    )
                except Exception:
                    pass

        await callback.message.edit_text(
            "✅ <b>Оплата успешно получена!</b>\n\n"
            "Услуга активирована. Проверьте ваш профиль или /balance.",
            parse_mode="HTML",
        )
    else:
        await callback.answer(
            "⏳ Платеж пока не найден. Попробуйте через 1-2 минуты.", show_alert=True
        )


# ===== ОБРАБОТКА УСПЕШНОЙ ОПЛАТЫ STARS =====
@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    user_id = message.from_user.id

    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            user_id, message.from_user.username
        )

        if payload.startswith("credits:"):
            val = int(payload.split(":")[1])
            user.ai_credits += val
            msg = f"✅ Начислено <b>{val} AI-кредитов</b>."
        elif payload.startswith("premium_m:"):
            val = int(payload.split(":")[1])
            now = datetime.now(timezone.utc)
            base = (
                user.premium_until
                if user.premium_until and user.premium_until > now
                else now
            )
            user.is_premium = True
            user.premium_until = base + timedelta(days=val * 30)
            msg = f"👑 Premium активен до <b>{user.premium_until.strftime('%d.%m.%Y')}</b>."
        elif payload.startswith("premium_d:"):
            val = int(payload.split(":")[1])
            now = datetime.now(timezone.utc)
            base = (
                user.premium_until
                if user.premium_until and user.premium_until > now
                else now
            )
            user.is_premium = True
            user.premium_until = base + timedelta(days=val)
            msg = f"👑 Premium активен до <b>{user.premium_until.strftime('%d.%m.%Y')}</b>."
        elif payload.startswith("hr_pack:"):
            val = int(payload.split(":")[1])
            user.vacancy_credits += val
            msg = f"💼 Начислено <b>{val} кредитов</b> на вакансии."
        else:
            msg = "✅ Оплата принята!"

        await session.commit()

    # Уведомление админу
    admin_msg = (
        f"⭐ <b>Успешная оплата (Stars)!</b>\n\n"
        f"👤 Юзер: ID {user_id}\n"
        f"📦 Payload: <code>{payload}</code>\n"
        f"💎 Stars: {payment.total_amount}"
    )
    try:
        await message.bot.send_message(settings.ADMIN_ID, admin_msg, parse_mode="HTML")
    except Exception:
        pass

    await message.answer(msg, parse_mode="HTML")


# ===== /promo_gen — Генератор рекламного поста (Admin Only) =====


@router.message(Command("promo_gen"))
async def cmd_promo_gen(message: types.Message):
    """Генерирует рекламный пост для админа."""
    if message.from_user.id != settings.ADMIN_ID:
        return

    bot_info = await message.bot.get_me()
    bot_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"

    promo_text = (
        "🚀 <b>Устали искать работу в IT вручную?</b>\n\n"
        "Встречайте <b>Job Aggregator Bot</b> — ваш персональный AI-ассистент! 🤖\n\n"
        "✅ <b>Что умеет бот:</b>\n"
        "• Собирает вакансии из <b>9 источников</b> (HH, Habr, TG и др.) в одну ленту.\n"
        "• 🎯 <b>AI-Анализ</b>: Проверяет вакансию на соответствие вашему резюме за секунды.\n"
        "• ✉️ <b>AI-Письма</b>: Генерирует идеальное сопроводительное письмо под вакансию.\n"
        "• 🔊 <b>Озвучка</b>: Слушайте описание вакансий профессиональными голосами.\n"
        "• 🎤 <b>Интервью</b>: Готовьтесь к собеседованию с ИИ-тренером.\n\n"
        "🎁 Забирайте <b>+3 бонусных AI-кредита</b> по ссылке ниже!\n\n"
        f"👇 <b>Начать поиск:</b>\n"
        f"{bot_link}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🚀 Запустить бота", url=bot_link)]]
    )

    await message.answer(
        "📝 <b>Ваш рекламный пост готов:</b>\n\n" + "-" * 20, parse_mode="HTML"
    )
    await message.answer(promo_text, parse_mode="HTML", reply_markup=keyboard)


# ===== НАЗАД =====
@router.callback_query(F.data == "back_balance", StateFilter("*"))
async def back_to_balance(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    user_id = callback.from_user.id
    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            user_id, callback.from_user.username
        )
        credits = user.ai_credits
        is_prem = (
            user.is_premium
            and user.premium_until
            and user.premium_until > datetime.now(timezone.utc)
        )

    credits_str = "♾ Безлимит" if is_prem else str(credits)
    text = (
        f"💎 <b>Баланс: {credits_str} AI-кредитов</b>\n\n"
        f"Выберите раздел для пополнения:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 AI-Кредиты", callback_data="shop:credits")],
            [
                InlineKeyboardButton(
                    text="👑 Premium-подписка", callback_data="shop:premium"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💼 Для HR (Вакансии)", callback_data="shop:hr"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Оплата картой / ЮMoney", callback_data="shop:yoomoney"
                )
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
