from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select

from app.database import async_session
from app.models.user import User

router = Router()


class HRPostState(StatesGroup):
    title = State()  # Название вакансии (например: Python Backend Developer)
    skills = State()  # Скиллы (например: Python, Django, PostgreSQL)
    salary = State()  # Вилка ЗП (например: 200 000 - 300 000 руб.)
    format_type = State()  # Формат работы (Удаленка/Офис)
    description = State()  # Описание вакансии
    preview = State()  # Ожидание подтверждения и перехода к оплате


@router.message(Command("hr"))
async def cmd_hr_panel(message: types.Message, state: FSMContext):
    """Точка входа в HR-Панель."""
    async with async_session() as session:
        user = (
            await session.execute(
                select(User).where(User.telegram_id == message.from_user.id)
            )
        ).scalar_one_or_none()

    if not user:
        await message.answer("Сначала запустите бота командой /start")
        return

    text = (
        "🏢 <b>HR-Панель (Размещение вакансии)</b>\n\n"
        "Здесь вы можете опубликовать свою вакансию в нашем агрегаторе.\n"
        "Ваша вакансия получит статус 🔥 <b>Прямой работодатель</b>, "
        "будет разослана подписчикам вне очереди и закреплена в поиске!\n\n"
        "<i>Стоимость размещения: 500 Telegram Stars (или ~1000 руб.)</i>\n\n"
        "Готовы начать оформление?"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Создать вакансию", callback_data="hr_post:start"
                )
            ],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:main")],
        ]
    )

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "hr_post:cancel")
async def hr_post_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Создание вакансии отменено.")
    await callback.answer()


@router.callback_query(F.data == "hr_post:start")
async def hr_post_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HRPostState.title)
    await callback.message.edit_text(
        "📝 Шаг 1/5. <b>Должность</b>\n\n"
        "Напишите название должности (например: <i>Middle Python Developer</i>)\n\n",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="hr_post:cancel")]
            ]
        ),
    )
    await callback.answer()


@router.message(HRPostState.title)
async def process_title(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание вакансии отменено.")
        return

    await state.update_data(title=message.text)
    await state.set_state(HRPostState.skills)

    await message.answer(
        "🛠 Шаг 2/5. <b>Требуемые навыки</b>\n\n"
        "Перечислите стек через запятую (например: <i>Python, FastAPI, Docker, CI/CD</i>)\n\n",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="hr_post:start")],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="hr_post:cancel"
                    )
                ],
            ]
        ),
    )


@router.message(HRPostState.skills)
async def process_skills(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание вакансии отменено.")
        return

    await state.update_data(skills=message.text)
    await state.set_state(HRPostState.salary)

    await message.answer(
        "💰 Шаг 3/5. <b>Зарплатная вилка</b>\n\n"
        "Напишите ЗП (например: <i>от 200 000 до 350 000 руб. на руки</i>)\n"
        "Или отправьте '-', если ЗП обсуждается на собеседовании.\n\n",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад", callback_data="hr_post:back_to_skills"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="hr_post:cancel"
                    )
                ],
            ]
        ),
    )


@router.message(HRPostState.salary)
async def process_salary(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание вакансии отменено.")
        return

    await state.update_data(salary=message.text)
    await state.set_state(HRPostState.format_type)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Удаленка", callback_data="hr_fmt:Удаленка")],
            [InlineKeyboardButton(text="Офис", callback_data="hr_fmt:Офис")],
            [InlineKeyboardButton(text="Гибрид", callback_data="hr_fmt:Гибрид")],
        ]
    )

    await message.answer(
        "🏢 Шаг 4/5. <b>Формат работы</b>\n\n"
        "Выберите формат работы кнопкой или напишите свой (с городом):\n\n",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                *kb.inline_keyboard,
                [
                    InlineKeyboardButton(
                        text="◀️ Назад", callback_data="hr_post:back_to_salary"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="hr_post:cancel"
                    )
                ],
            ]
        ),
    )


@router.callback_query(F.data.startswith("hr_fmt:"))
async def process_format_cb(callback: types.CallbackQuery, state: FSMContext):
    fmt = callback.data.split(":")[1]
    await _process_format(fmt, callback.message, state)
    await callback.answer()


@router.message(HRPostState.format_type)
async def process_format_msg(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание вакансии отменено.")
        return
    await _process_format(message.text, message, state)


async def _process_format(fmt: str, message_or_cb: types.Message, state: FSMContext):
    await state.update_data(format_type=fmt)
    await state.set_state(HRPostState.description)

    await message_or_cb.answer(
        "📄 Шаг 5/5. <b>Описание вакансии</b>\n\n"
        "Отправьте подробное описание: задачи, требования, условия работы.\n"
        "Вы можете прикрепить ссылку на контакты или указать свой @username.\n\n",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад", callback_data="hr_post:back_to_format"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="hr_post:cancel"
                    )
                ],
            ]
        ),
    )


@router.message(HRPostState.description)
async def process_description(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание вакансии отменено.")
        return

    data = await state.get_data()
    data["description"] = message.text
    await state.update_data(description=message.text)
    await state.set_state(HRPostState.preview)

    # Формируем превью карточки
    salary_str = f"💰 {data['salary']}\n" if data["salary"] != "-" else ""

    preview_text = (
        f"🔥 <b>ПРЯМОЙ РАБОТОДАТЕЛЬ</b> 🔥\n\n"
        f"<b>{data['title']}</b>\n"
        f"{salary_str}"
        f"🏢 {data['format_type']}\n"
        f"🛠 <i>{data['skills']}</i>\n\n"
        f"{data['description']}\n\n"
    )

    # Сохраняем итоговый текст превью в стейт, чтобы не формировать его заново при оплате
    await state.update_data(final_text=preview_text)

    # Проверяем наличие кредитов у пользователя
    async with async_session() as session:
        user = (
            await session.execute(
                select(User).where(User.telegram_id == message.from_user.id)
            )
        ).scalar_one_or_none()
        v_credits = user.vacancy_credits if user else 0

    if v_credits > 0:
        pay_text = f"У вас есть <b>{v_credits}</b> шт. оплаченных публикаций.\nИспользовать 1 кредит?"
        pay_button = InlineKeyboardButton(
            text="✅ Опубликовать (1 кредит)", callback_data="hr_post:use_credit"
        )
        kb_rows = [[pay_button]]
    else:
        pay_text = "Стоимость размещения: 500 Stars или 650₽."
        pay_button_stars = InlineKeyboardButton(
            text="⭐ Stars (⭐500)", callback_data="hr_post:pay"
        )
        pay_button_card = InlineKeyboardButton(
            text="💳 Карта (650₽)", callback_data="select_method:hr_pack:1:650:500"
        )
        kb_rows = [[pay_button_stars, pay_button_card]]

    kb_rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Заполнить заново", callback_data="hr_post:start"
            )
        ]
    )
    kb_rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="hr_post:cancel")]
    )
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await message.answer(
        f"👀 <b>Превью вашей вакансии:</b>\n"
        f"---------------------------------\n"
        f"{preview_text}"
        f"---------------------------------\n\n"
        f"{pay_text}",
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "hr_post:pay")
async def hr_post_pay(callback: types.CallbackQuery, state: FSMContext):
    """Генерация счета в Stars для оплаты публикации."""
    await callback.message.answer_invoice(
        title="Публикация вакансии",
        description="Размещение вакансии со статусом «Прямой работодатель» и приоритетной рассылкой кандидатам.",
        payload="hr_post:500",  # Payload по которому payments.py определит покупку
        currency="XTR",  # Telegram Stars
        prices=[types.LabeledPrice(label="Публикация", amount=500)],
    )
    await callback.answer()


@router.callback_query(F.data == "hr_post:use_credit")
async def hr_post_use_credit(callback: types.CallbackQuery, state: FSMContext):
    """Списание кредита и публикация вакансии."""
    user_id = callback.from_user.id
    data = await state.get_data()
    data.get("final_text")

    async with async_session() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == user_id))
        ).scalar_one_or_none()

        if not user or user.vacancy_credits < 1:
            await callback.answer("У вас нет оплаченных публикаций", show_alert=True)
            return

        user.vacancy_credits -= 1
        await session.commit()

    # Создаем вакансию в БД (упрощенно)
    async with async_session() as session:
        from app.services.job_service import JobService

        js = JobService(session)
        # В реальном сценарии мы бы вызывали js.add_job, но тут мы эмулируем
        # для демонстрации логики оплаты продвижения.
        # Допустим вакансия создается с moderation_status='approved'
        job = await js.add_job(
            title=data["title"],
            description=data["description"],
            link="https://t.me/" + (callback.from_user.username or "bot"),
            source="HR Panel",
            category="other",
        )
        if job:
            job.employer_id = user_id
            await session.commit()
            job_id = job.id
        else:
            await callback.answer("Ошибка при создании вакансии", show_alert=True)
            return

    # Предлагаем продвижение
    text = (
        "✅ <b>Вакансия опубликована!</b>\n\n"
        "Хотите сделать её 🔥 <b>Горячей</b>?\n"
        "• Закрепится в топе на 3 дня\n"
        "• Будет выделена огнем\n"
        "• Получит приоритетную рассылку\n\n"
        "<i>Стоимость: 250 Stars или 325₽ (1 кредит вакансии)</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔥 Продвинуть (1 кредит)",
                    callback_data=f"hr_promote:credit:{job_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Stars (⭐250)", callback_data=f"hr_promote:stars:{job_id}"
                ),
                InlineKeyboardButton(
                    text="💳 Карта (325₽)",
                    callback_data="select_method:hr_pack:1:325:250",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🙅‍♂️ Нет, спасибо", callback_data="hr_post:done"
                )
            ],
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "hr_post:done")
async def hr_post_done(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "✅ Вакансия успешно размещена в общем списке!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏠 В главное меню", callback_data="menu:main"
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "hr_post:back_to_skills")
async def hr_back_to_skills(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HRPostState.skills)
    await callback.message.edit_text(
        "🛠 Шаг 2/5. <b>Требуемые навыки</b>\n\n"
        "Перечислите стек через запятую (например: <i>Python, FastAPI, Docker, CI/CD</i>)\n\n",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="hr_post:start")],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="hr_post:cancel"
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "hr_post:back_to_salary")
async def hr_back_to_salary(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HRPostState.salary)
    await callback.message.edit_text(
        "💰 Шаг 3/5. <b>Зарплатная вилка</b>\n\n"
        "Напишите ЗП (например: <i>от 200 000 до 350 000 руб. на руки</i>)\n"
        "Или отправьте '-', если ЗП обсуждается на собеседовании.\n\n",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад", callback_data="hr_post:back_to_skills"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="hr_post:cancel"
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "hr_post:back_to_format")
async def hr_back_to_format(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HRPostState.format_type)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Удаленка", callback_data="hr_fmt:Удаленка")],
            [InlineKeyboardButton(text="Офис", callback_data="hr_fmt:Офис")],
            [InlineKeyboardButton(text="Гибрид", callback_data="hr_fmt:Гибрид")],
            [
                InlineKeyboardButton(
                    text="◀️ Назад", callback_data="hr_post:back_to_salary"
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="hr_post:cancel")],
        ]
    )
    await callback.message.edit_text(
        "🏢 Шаг 4/5. <b>Формат работы</b>\n\n"
        "Выберите формат работы кнопкой или напишите свой (с городом):\n\n",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    from ..system.start import cmd_start  # UPDATED IMPORT PATH

    await cmd_start(callback.message, command=None)
    await callback.answer()


@router.callback_query(F.data.startswith("hr_promote:"))
async def hr_promote_process(callback: types.CallbackQuery):
    _, mode, job_id_str = callback.data.split(":")
    job_id = int(job_id_str)
    user_id = callback.from_user.id

    async with async_session() as session:
        from app.services.job_service import JobService
        from app.services.user_service import UserService

        js = JobService(session)
        us = UserService(session)

        if mode == "credit":
            user = await us.get_or_create_user(user_id)
            if user.vacancy_credits > 0:
                user.vacancy_credits -= 1
                await js.promote_job(job_id)
                await callback.message.edit_text(
                    "🔥 <b>Готово!</b> Вакансия продвинута и выделена огнем."
                )
                await callback.answer("Успешно!", show_alert=True)
            else:
                await callback.answer("Недостаточно кредитов", show_alert=True)
        else:
            # Оплата через Stars (Invoice)
            await callback.message.answer_invoice(
                title="Продвижение вакансии",
                description="Закрепление вакансии в ТОП-е на 3 дня и выделение огнем 🔥",
                payload=f"hr_promote:{job_id}",
                currency="XTR",
                prices=[types.LabeledPrice(label="Продвижение", amount=250)],
            )
            await callback.answer()
