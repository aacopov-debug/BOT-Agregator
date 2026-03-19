from datetime import datetime, timezone
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from ...models.job import Job
from ...models.user import User
from ...database import async_session
from ...utils.resume_parser import extract_skills, parse_resume
from ...services.job_service import JobService
from ...services.user_service import UserService
from ...utils.subscription import is_subscribed
from ...utils.keyboards import get_subscription_keyboard
from ...config import settings
from aiogram.types import BufferedInputFile
import html

router = Router()


# Шаблоны сопроводительных писем
TEMPLATES = {
    "formal": {
        "name": "📋 Формальное",
        "greeting": "Уважаемый менеджер по подбору персонала",
        "style": "formal",
    },
    "friendly": {
        "name": "😊 Дружелюбное",
        "greeting": "Добрый день",
        "style": "friendly",
    },
    "concise": {
        "name": "⚡ Краткое",
        "greeting": "Здравствуйте",
        "style": "concise",
    },
}


@router.callback_query(F.data.startswith("cover:"))
async def cover_letter_menu(callback: types.CallbackQuery):
    """Выбор стиля сопроводительного письма."""
    job_id = int(callback.data.split(":")[1])

    # --- ПРОВЕРКА ПОДПИСКИ ---
    if settings.REQUIRED_CHANNEL_ID:
        subscribed = await is_subscribed(
            callback.bot, callback.from_user.id, settings.REQUIRED_CHANNEL_ID
        )
        if not subscribed:
            await callback.message.answer(
                "✉️ <b>AI-генератор писем доступен только подписчикам!</b>\n\n"
                "Подпишитесь на наш канал, чтобы бот писал отклики за вас.",
                parse_mode="HTML",
                reply_markup=get_subscription_keyboard(
                    settings.REQUIRED_CHANNEL_LINK, callback.data
                ),
            )
            await callback.answer()
            return
    # -------------------------

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t["name"], callback_data=f"covgen:{style}:{job_id}"
                )
            ]
            for style, t in TEMPLATES.items()
        ]
        + [[InlineKeyboardButton(text="◀️ Назад", callback_data=f"detail:{job_id}")]]
    )

    await callback.message.edit_text(
        "✉️ <b>Генератор сопроводительного письма</b>\n\n"
        "Выберите стиль:\n\n"
        "📋 <b>Формальное</b> — классическое деловое\n"
        "😊 <b>Дружелюбное</b> — тёплое и открытое\n"
        "⚡ <b>Краткое</b> — лаконичное и по делу",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("covgen:"))
async def generate_cover_letter(callback: types.CallbackQuery):
    """Генерация сопроводительного письма."""
    parts = callback.data.split(":")
    style = parts[1]
    job_id = int(parts[2])

    async with async_session() as session:
        job = (
            await session.execute(select(Job).where(Job.id == job_id))
        ).scalar_one_or_none()

        user = (
            await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
        ).scalar_one_or_none()

    if not job:
        await callback.answer("Вакансия не найдена")
        return

    # Проверка баланса кредитов
    if not user:
        await callback.answer("Ошибка пользователя")
        return

    is_prem = (user.role == "admin") or (
        user.is_premium
        and user.premium_until
        and user.premium_until > datetime.now(timezone.utc)
    )
    if user.ai_credits < 1 and not is_prem:
        await callback.answer(
            "❌ У вас закончились AI-кредиты.\nПополните баланс командой /balance",
            show_alert=True,
        )
        return

    # Списываем кредит если не премиум
    if not is_prem:
        async with async_session() as session:
            # Требуется повторный запрос для обновления в сессии если мы хотим гарантировать атомарность,
            # но здесь можно просто обновить и закоммитить в одной сессии.
            # В данном хендлере сессия уже была закрыта, откроем новую для списания.
            user_to_update = (
                await session.execute(
                    select(User).where(User.telegram_id == callback.from_user.id)
                )
            ).scalar_one_or_none()
            if user_to_update:
                user_to_update.ai_credits -= 1
                await session.commit()

    # Извлекаем навыки из вакансии
    job_text = f"{job.title} {job.description or ''}"
    job_skills = extract_skills(job_text)

    # Навыки пользователя из резюме
    user_skills = set()
    if user and user.resume_text:
        user_skills = extract_skills(user.resume_text)

    # Совпадающие навыки
    matched = job_skills & user_skills if user_skills else job_skills

    template = TEMPLATES.get(style, TEMPLATES["formal"])
    name = callback.from_user.first_name or "Кандидат"

    letter = _build_letter(
        style=template["style"],
        greeting=template["greeting"],
        name=name,
        job_title=job.title,
        company=_extract_company(job.description or ""),
        matched_skills=list(matched)[:6],
        all_skills=list(job_skills)[:8],
        source=job.source or "",
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Копировать", callback_data=f"covcopy:{job_id}"
                ),
                InlineKeyboardButton(
                    text="🔄 Другой стиль", callback_data=f"cover:{job_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📩 Откликнуться", callback_data=f"apply:{job_id}"
                ),
                InlineKeyboardButton(
                    text="◀️ Вакансия", callback_data=f"detail:{job_id}"
                ),
            ],
        ]
    )

    await callback.message.edit_text(
        letter, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("covcopy:"))
async def cover_copy_hint(callback: types.CallbackQuery):
    """Подсказка для копирования."""
    await callback.answer(
        "💡 Длительно нажмите на текст → Скопировать", show_alert=True
    )


# === 1. ОТКЛИК НА ВАКАНСИЮ (быстрое письмо) ===


@router.callback_query(F.data.startswith("apply:"))
async def callback_apply(callback: types.CallbackQuery):
    """Генерирует сопроводительное письмо для вакансии."""
    job_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.get_job_by_id(job_id)
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            callback.from_user.id, callback.from_user.username
        )

    if not job:
        await callback.answer("Вакансия не найдена")
        return

    # Парсим профиль из ключевых слов
    name = callback.from_user.first_name or "Кандидат"
    skills = user.keywords if user.keywords else "разработка"
    profile = parse_resume(skills)

    # Генерация письма
    letter = _generate_cover_letter_quick(name, profile, job)

    response = (
        f"📩 <b>Сопроводительное письмо</b>\n"
        f"Для: <i>{job.title[:60]}</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{letter}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Скопировать текст", callback_data=f"apply_copy:{job_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📄 Скачать .txt", callback_data=f"apply_file:{job_id}"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"detail:{job_id}")],
        ]
    )

    await callback.message.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("apply_file:"))
async def callback_apply_file(callback: types.CallbackQuery):
    """Скачать письмо как файл."""
    job_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.get_job_by_id(job_id)
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            callback.from_user.id, callback.from_user.username
        )

    if not job:
        await callback.answer("Не найдено")
        return

    name = callback.from_user.first_name or "Кандидат"
    profile = parse_resume(user.keywords or "разработка")
    letter = _generate_cover_letter_quick(name, profile, job)

    content = f"Сопроводительное письмо\nВакансия: {job.title}\n\n{letter}".encode(
        "utf-8"
    )
    doc = BufferedInputFile(content, filename="cover_letter.txt")
    await callback.message.answer_document(
        doc, caption="📩 Ваше сопроводительное письмо"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("apply_copy:"))
async def callback_apply_copy(callback: types.CallbackQuery):
    """Отправляет текст отдельным сообщением для копирования."""
    job_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.get_job_by_id(job_id)
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            callback.from_user.id, callback.from_user.username
        )

    if not job:
        await callback.answer("Не найдено")
        return

    name = callback.from_user.first_name or "Кандидат"
    profile = parse_resume(user.keywords or "разработка")
    letter = _generate_cover_letter_quick(name, profile, job)

    await callback.message.answer(
        f"<code>{html.escape(letter)}</code>", parse_mode="HTML"
    )
    await callback.answer("Скопируйте текст выше ☝️")


def _generate_cover_letter_quick(name: str, profile: dict, job) -> str:
    """Генерирует сопроводительное письмо на основе профиля и вакансии."""
    skills = profile.get("skills", [])
    exp = profile.get("experience", "middle")

    exp_text = {
        "intern": "начинающий специалист",
        "junior": "начинающий специалист с горящими глазами",
        "middle": "специалист с опытом коммерческой разработки",
        "senior": "опытный специалист с глубокой экспертизой",
        "lead": "опытный лидер с навыками управления командой",
    }.get(exp, "специалист")

    skills_text = ", ".join(skills[:8]) if skills else "современные технологии"

    title = job.title[:80]

    letter = (
        f"Здравствуйте!\n\n"
        f"Меня зовут {name}, я {exp_text}.\n\n"
        f"Заинтересовала ваша вакансия «{title}».\n\n"
        f"Мой стек: {skills_text}.\n\n"
        f"Готов обсудить детали и выполнить тестовое задание.\n"
        f"Буду рад возможности присоединиться к вашей команде!\n\n"
        f"С уважением,\n{name}"
    )
    return letter


def _build_letter(
    style, greeting, name, job_title, company, matched_skills, all_skills, source
):
    """Создаёт текст сопроводительного письма."""
    company_text = f" в {company}" if company else ""

    if style == "formal":
        letter = (
            f"✉️ <b>Сопроводительное письмо</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{greeting},\n\n"
            f"Меня зовут {name}, и я хотел бы выразить "
            f"заинтересованность в позиции "
            f"<b>{job_title}</b>{company_text}.\n\n"
        )
        if matched_skills:
            skills_str = ", ".join(matched_skills)
            letter += (
                f"Обладаю опытом работы с: {skills_str}. "
                f"Уверен, что мои навыки позволят мне "
                f"эффективно справляться с задачами этой роли.\n\n"
            )
        letter += (
            f"Буду рад обсудить детали на собеседовании.\n\n"
            f"С уважением,\n{name}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

    elif style == "friendly":
        letter = (
            f"✉️ <b>Сопроводительное письмо</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{greeting}! 👋\n\n"
            f"Меня зовут {name}. Увидел вакансию "
            f"<b>{job_title}</b>{company_text} и она "
            f"отлично мне подходит!\n\n"
        )
        if matched_skills:
            skills_str = ", ".join(matched_skills)
            letter += (
                f"Я активно работаю с: {skills_str}. "
                f"Люблю решать сложные задачи и "
                f"постоянно развиваюсь.\n\n"
            )
        letter += (
            f"Буду рад пообщаться и узнать больше!\n\n"
            f"С наилучшими пожеланиями,\n{name} 👋\n\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

    else:  # concise
        letter = (
            f"✉️ <b>Сопроводительное письмо</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{greeting},\n\n"
            f"{name} → <b>{job_title}</b>{company_text}.\n\n"
        )
        if matched_skills:
            letter += f"🔧 Навыки: {', '.join(matched_skills)}\n\n"
        letter += f"Готов к собеседованию.\n\n— {name}\n\n━━━━━━━━━━━━━━━━━━━━"

    if all_skills:
        letter += f"\n\n🔑 <i>Ключевые навыки вакансии: {', '.join(all_skills)}</i>"

    return letter


def _extract_company(description: str) -> str:
    """Простое извлечение названия компании."""
    import re

    patterns = [
        r'компания\s+[«"]?(\w+)',
        r"в\s+([A-Z][a-zA-Z]+)",
        r"Компания:\s*(.+?)[\n,]",
    ]
    for pat in patterns:
        match = re.search(pat, description, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:30]
    return ""
