import io
import logging
from openai import AsyncOpenAI
from datetime import datetime, timezone
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ...services.job_service import JobService
from ...services.user_service import UserService
from ...database import async_session
from ...utils.resume_parser import parse_resume, match_score
from ...utils.categorizer import get_category_label
from ...utils.subscription import is_subscribed
from ...utils.keyboards import get_subscription_keyboard
from ...config import settings

router = Router()
logger = logging.getLogger(__name__)

# Инициализируем клиент OpenAI
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


class ResumeState(StatesGroup):
    waiting_for_resume = State()


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Извлекает текст из PDF-файла."""
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        logger.warning(f"PDF parse error: {e}")
        return ""


@router.message(Command("resume"))
async def cmd_resume(message: types.Message, state: FSMContext):
    from ...utils.keyboards import CANCEL_KEYBOARD

    await message.answer(
        "📄 <b>Загрузка резюме</b>\n\n"
        "Отправьте мне резюме:\n\n"
        "📎 <b>PDF-файл</b> — прикрепите документ\n"
        "📝 <b>Текст</b> — просто вставьте текст\n\n"
        "Можно перечислить:\n"
        "• Навыки (Python, React, Docker...)\n"
        "• Опыт (3 года, senior...)\n"
        "• Формат (remote, офис)\n"
        "• Зарплата (от 200 000₽)\n\n"
        "💡 <i>Чем подробнее — тем точнее AI-анализ!</i>",
        parse_mode="HTML",
        reply_markup=CANCEL_KEYBOARD,
    )
    await state.set_state(ResumeState.waiting_for_resume)


@router.message(ResumeState.waiting_for_resume)
async def process_resume(message: types.Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("Отменено.")
        return

    resume_text = ""
    source_type = "текст"

    if message.document:
        try:
            file = await message.bot.get_file(message.document.file_id)
            bio = io.BytesIO()
            await message.bot.download_file(file.file_path, bio)
            file_bytes = bio.getvalue()
            file_name = (message.document.file_name or "").lower()

            if file_name.endswith(".pdf"):
                resume_text = _extract_pdf_text(file_bytes)
                source_type = "PDF"
            else:
                resume_text = file_bytes.decode("utf-8", errors="ignore")
                source_type = "файл"

            if not resume_text.strip():
                await message.answer(
                    "❌ Не удалось извлечь текст из файла.\n"
                    "💡 <i>Попробуйте скопировать текст и отправить сообщением.</i>",
                    parse_mode="HTML",
                )
                return
        except Exception as e:
            logger.error(f"Resume file error: {e}")
            await message.answer("❌ Ошибка чтения файла. Отправьте текст сообщением.")
            return
    elif message.text:
        resume_text = message.text
    else:
        await message.answer("Отправьте текст или PDF-документ.")
        return

    if len(resume_text) < 10:
        await message.answer("Слишком мало текста. Напишите подробнее.")
        return

    await state.clear()

    profile = parse_resume(resume_text)

    async with async_session() as session:
        user_service = UserService(session)
        if profile["skills_text"]:
            await user_service.update_keywords(
                message.from_user.id, profile["skills_text"]
            )

    exp_labels = {
        "intern": "🟢 Стажёр",
        "junior": "🟢 Junior",
        "middle": "🟡 Middle",
        "senior": "🔴 Senior",
        "lead": "🔴 Lead",
    }
    fmt_labels = {
        "remote": "🏠 Удалёнка",
        "office": "🏢 Офис",
        "hybrid": "🔄 Гибрид",
        "any": "📍 Любой",
    }

    skills_list = (
        ", ".join(profile["skills"][:15]) if profile["skills"] else "не определены"
    )
    exp_label = exp_labels.get(profile["experience"], "🟡 Middle")
    fmt_label = fmt_labels.get(profile["work_format"], "📍 Любой")
    salary_text = (
        f"💰 от {profile['salary_expectation']:,}₽"
        if profile["salary_expectation"]
        else "💰 не указана"
    )

    response = (
        f"✅ <b>Резюме загружено!</b> (из {source_type})\n\n"
        "━━━ <b>Ваш профиль</b> ━━━\n\n"
        f"🛠 <b>Навыки:</b> {skills_list}\n"
        f"📊 <b>Уровень:</b> {exp_label}\n"
        f"📍 <b>Формат:</b> {fmt_label}\n"
        f"{salary_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔑 Навыки сохранены для уведомлений!"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 AI-анализ резюме", callback_data="resume:ai_analyze"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔥 Прожарить резюме (Roast)", callback_data="resume:roast"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Найти вакансии", callback_data="resume:match"
                )
            ],
            [
                InlineKeyboardButton(text="📄 В HTML", callback_data="resume:html"),
                InlineKeyboardButton(text="✏️ Заново", callback_data="resume:reload"),
            ],
        ]
    )

    await state.update_data(profile=profile, resume_text=resume_text[:5000])
    await message.answer(response, parse_mode="HTML", reply_markup=keyboard)


# ===== AI-анализ резюме =====


@router.callback_query(F.data == "resume:ai_analyze")
async def callback_ai_analyze(callback: types.CallbackQuery, state: FSMContext):
    """AI оценивает сильные/слабые стороны и советует вакансии."""
    data = await state.get_data()
    resume_text = data.get("resume_text", "")
    profile = data.get("profile")

    if not resume_text and not profile:
        await callback.answer("❌ Сначала загрузите резюме (/resume)")
        return

    if not settings.OPENAI_API_KEY:
        await callback.answer("❌ AI недоступен (нет API-ключа OpenAI)")
        return

    # --- ПРОВЕРКА ПОДПИСКИ ---
    if settings.REQUIRED_CHANNEL_ID:
        subscribed = await is_subscribed(
            callback.bot, callback.from_user.id, settings.REQUIRED_CHANNEL_ID
        )
        if not subscribed:
            await callback.message.answer(
                "📢 <b>Для использования AI-анализа нужно подписаться на наш канал!</b>\n\n"
                "Там мы публикуем секретные советы по поиску работы и самые горячие вакансии.",
                parse_mode="HTML",
                reply_markup=get_subscription_keyboard(
                    settings.REQUIRED_CHANNEL_LINK, "resume:ai_analyze"
                ),
            )
            await callback.answer()
            return
    # -------------------------

    # Загружаем юзера для проверки баланса кредитов
    async with async_session() as session:
        from ...models.user import User
        from sqlalchemy import select

        user = (
            await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        is_prem = (user.role == "admin") or (
            user.is_premium and user.premium_until and user.premium_until > now
        )
        if not user or (user.ai_credits < 1 and not is_prem):
            await callback.answer(
                "❌ У вас закончились AI-кредиты.\nПополните баланс командой /balance",
                show_alert=True,
            )
            return

        now = datetime.now(timezone.utc)
        is_prem = user.is_premium and user.premium_until and user.premium_until > now
        # Списываем кредит только если НЕ Premium
        if not is_prem:
            user.ai_credits -= 1
            await session.commit()
        else:
            await session.commit()

    await callback.answer("🤖 AI анализирует резюме... (10-15 сек)", show_alert=True)

    async with async_session() as session:
        job_service = JobService(session)
        jobs = await job_service.get_latest_jobs(limit=30)

    jobs_context = (
        "\n".join([f"- {j.title} [{j.source}]" for j in jobs[:20]])
        if jobs
        else "нет данных"
    )
    skills_text = (
        ", ".join(profile["skills"])
        if profile and profile.get("skills")
        else "не указаны"
    )

    prompt = (
        f"Ты — карьерный AI-консультант. Проанализируй резюме.\n\n"
        f"РЕЗЮМЕ:\n{resume_text[:3000]}\n\n"
        f"НАВЫКИ: {skills_text}\n\n"
        f"ВАКАНСИИ НА РЫНКЕ:\n{jobs_context[:2000]}\n\n"
        f"Дай КРАТКИЙ анализ на русском:\n"
        f"1. 💪 СИЛЬНЫЕ СТОРОНЫ (3-4 пункта)\n"
        f"2. ⚠️ ЧТО УЛУЧШИТЬ (2-3 пункта)\n"
        f"3. 🎯 ТОП-3 ПОДХОДЯЩИЕ ВАКАНСИИ из списка\n"
        f"4. 📈 СОВЕТ ПО КАРЬЕРЕ (1-2 предложения)\n\n"
        f"Используй эмодзи, будь конкретен."
    )

    analysis = await _call_ai(prompt)

    if not analysis:
        # Возвращаем кредит, так как произошла ошибка ИИ
        async with async_session() as session:
            from ...models.user import User
            from sqlalchemy import select

            user = (
                await session.execute(
                    select(User).where(User.telegram_id == callback.from_user.id)
                )
            ).scalar_one_or_none()
            if user:
                user.ai_credits += 1
                await session.commit()

        await callback.message.answer("❌ AI временно недоступен. Попробуйте позже.")
        return

    text = (
        f"🤖 <b>AI-анализ вашего резюме</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{analysis}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>На основе {len(jobs)} актуальных вакансий</i>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎯 Найти вакансии", callback_data="resume:match"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Повторить", callback_data="resume:ai_analyze"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Загрузить заново", callback_data="resume:reload"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад в меню резюме", callback_data="resume:back_to_menu"
                )
            ],
        ]
    )

    if len(text) > 4000:
        text = text[:3950] + "..."

    await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ===== AI-прожарка резюме (Roast) =====


@router.callback_query(F.data == "resume:roast")
async def callback_resume_roast(callback: types.CallbackQuery, state: FSMContext):
    """AI жестко критикует и высмеивает резюме."""
    data = await state.get_data()
    resume_text = data.get("resume_text", "")

    if not resume_text:
        await callback.answer("❌ Сначала загрузите резюме (/resume)", show_alert=True)
        return

    # --- ПРОВЕРКА ПОДПИСКИ ---
    if settings.REQUIRED_CHANNEL_ID:
        subscribed = await is_subscribed(
            callback.bot, callback.from_user.id, settings.REQUIRED_CHANNEL_ID
        )
        if not subscribed:
            await callback.message.answer(
                "🔥 <b>Прожарка разрешена только подписчикам канала!</b>\n\n"
                "Подпишись, чтобы увидеть, как AI разносит твое резюме в пух и прах. 😂",
                parse_mode="HTML",
                reply_markup=get_subscription_keyboard(
                    settings.REQUIRED_CHANNEL_LINK, "resume:roast"
                ),
            )
            await callback.answer()
            return
    # -------------------------

    # Проверка баланса кредитов
    async with async_session() as session:
        from ...models.user import User
        from sqlalchemy import select

        user = (
            await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
        ).scalar_one_or_none()

        if not user:
            return

        now = datetime.now(timezone.utc)
        is_prem = (user.role == "admin") or (
            user.is_premium and user.premium_until and user.premium_until > now
        )

        if user.ai_credits < 1 and not is_prem:
            await callback.answer(
                "❌ AI-кредиты закончились!\n\n"
                "Купите пакет кредитов или Premium, чтобы зажигать дальше. "
                "Premium дает безлимит на все AI-функции!",
                show_alert=True,
            )
            return

        # Списываем 1 кредит за прожарку (если не премиум)
        if not is_prem:
            user.ai_credits -= 1
            await session.commit()

    await callback.answer("🔥 Разогреваю сковородку... (10 сек)", show_alert=True)

    from ...services.ai_roast import generate_resume_roast

    result = await generate_resume_roast(resume_text)

    roast_text = result["text"]
    score = result["score"]

    # Реферальная ссылка для шаринга
    ref_link = f"https://t.me/arbotagregator_bot?start=ref_{callback.from_user.id}"
    share_text = f"Моё резюме только что прожарили в ArBOT! 😂 Мой Roast Score: {score}%. Попробуй и ты!"
    share_url = f"https://t.me/share/url?url={ref_link}&text={share_text}"

    text = (
        f"🔥 <b>AI-ПРОЖАРКА ТВОЕГО РЕЗЮМЕ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{roast_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💀 <b>Roast Score: {score}%</b>\n\n"
        f"<i>Поделись своим позором с друзьями!</i> 👇"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📣 Поделиться позором", url=share_url)],
            [
                InlineKeyboardButton(
                    text="🎯 Найти вакансии", callback_data="resume:match"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад в меню", callback_data="resume:back_to_menu"
                )
            ],
        ]
    )

    if len(text) > 4000:
        text = text[:3950] + "..."

    await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


async def _call_ai(prompt: str) -> str:
    """Вызов OpenAI (gpt-4o-mini)."""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"AI exception: {e}")
        return ""


# ===== Matching =====


@router.callback_query(F.data == "resume:match")
async def callback_resume_match(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    profile = data.get("profile")

    if not profile:
        async with async_session() as session:
            user_service = UserService(session)
            user = await user_service.get_or_create_user(
                callback.from_user.id, callback.from_user.username
            )
            if user.keywords:
                profile = parse_resume(user.keywords)
            else:
                await callback.answer("Сначала загрузите резюме: /resume")
                return

    async with async_session() as session:
        job_service = JobService(session)
        all_jobs = await job_service.get_latest_jobs(limit=50)

    if not all_jobs:
        await callback.message.edit_text("😔 Пока нет вакансий.")
        await callback.answer()
        return

    scored = [(match_score(profile, j.title, j.description or ""), j) for j in all_jobs]
    scored = [(s, j) for s, j in scored if s > 10]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:10]

    if not top:
        await callback.message.edit_text(
            "😔 Не нашёл подходящих вакансий.\nРасширьте навыки в резюме."
        )
        await callback.answer()
        return

    response = "🎯 <b>Вакансии для вашего резюме</b>\n\n"
    for score, job in top:
        bar = "🟢" if score >= 70 else ("🟡" if score >= 40 else "🔴")
        cat = get_category_label(job.category) if job.category else ""
        link = f"<a href='{job.link}'>→</a>" if job.link else ""
        src = (
            "🏢"
            if job.source == "hh.ru"
            else ("💻" if job.source == "habr.career" else "📱")
        )
        response += (
            f"{bar} <b>{score:.0f}%</b>  {job.title[:55]}\n   {cat} {src}  {link}\n\n"
        )

    response += "━━━━━━━━━━━━━━━━━━━━\n🔹 <b>Скоринг:</b>\n🟢 70%+ идеал  •  🟡 40-70% хорошо  •  🔴 <40%"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 AI-анализ", callback_data="resume:ai_analyze"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Обновить резюме", callback_data="resume:reload"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад в меню резюме", callback_data="resume:back_to_menu"
                )
            ],
        ]
    )

    await callback.message.edit_text(
        response,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )
    await callback.answer()


# ===== HTML-экспорт =====


@router.callback_query(F.data == "resume:html")
async def callback_resume_html(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    profile = data.get("profile")
    if not profile:
        await callback.answer("❌ Сначала загрузите резюме (/resume)")
        return

    name = callback.from_user.first_name or "Кандидат"
    ", ".join(profile["skills"]) if profile["skills"] else "не указаны"
    exp = profile.get("experience", "Не указан")
    fmt = profile.get("work_format", "Любой")
    salary = (
        f"от {profile['salary_expectation']} ₽"
        if profile.get("salary_expectation")
        else "Не указана"
    )

    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>Резюме - {name}</title>
<style>
body{{font-family:'Segoe UI',sans-serif;background:#f3f4f6;color:#1f2937;margin:0;padding:40px;display:flex;justify-content:center}}
.c{{background:#fff;max-width:800px;padding:50px;border-radius:12px;box-shadow:0 10px 25px rgba(0,0,0,.05)}}
.h{{border-bottom:2px solid #e5e7eb;padding-bottom:20px;margin-bottom:30px}}
h1{{margin:0;color:#111;font-size:32px}}.sub{{color:#6b7280;margin-top:10px}}
h2{{color:#4f46e5;font-size:22px;margin-bottom:15px}}
.pills{{display:flex;flex-wrap:wrap;gap:10px}}
.pill{{background:#eef2ff;color:#4338ca;padding:8px 15px;border-radius:20px;font-size:14px;font-weight:600}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.card{{background:#f9fafb;padding:20px;border-radius:8px;border-left:4px solid #4f46e5}}
.card strong{{display:block;color:#4b5563;margin-bottom:5px;font-size:14px}}
.card span{{font-size:18px;font-weight:600;color:#111}}
</style></head><body><div class="c">
<div class="h"><h1>{name}</h1><div class="sub">Job Aggregator Bot</div></div>
<div class="grid" style="margin-bottom:35px">
<div class="card"><strong>Опыт:</strong><span>{exp.title()}</span></div>
<div class="card"><strong>ЗП:</strong><span>{salary}</span></div>
<div class="card" style="grid-column:span 2"><strong>Формат:</strong><span>{fmt.title()}</span></div>
</div>
<div style="margin-bottom:30px"><h2>Навыки</h2><div class="pills">
{"".join([f'<div class="pill">{s}</div>' for s in profile["skills"]]) if profile["skills"] else '<div class="pill">Не указаны</div>'}
</div></div>
<p style="margin-top:50px;text-align:center;color:#9ca3af;font-size:12px">Ctrl+P → Сохранить как PDF</p>
</div></body></html>"""

    from aiogram.types import BufferedInputFile

    doc = BufferedInputFile(
        html_content.encode("utf-8"), filename=f"Resume_{callback.from_user.id}.html"
    )
    await callback.message.answer_document(
        doc,
        caption="📄 <b>Резюме в HTML!</b>\nОткройте в браузере → Ctrl+P → PDF.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "resume:reload")
async def callback_resume_reload(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📄 Отправьте текст резюме или PDF-документ:")
    await state.set_state(ResumeState.waiting_for_resume)
    await callback.answer()


@router.callback_query(F.data == "resume:back_to_menu")
async def cb_resume_back(callback: types.CallbackQuery, state: FSMContext):
    # Возвращаем начальное сообщение /resume
    await cmd_resume(callback.message, state)
    await callback.message.delete()
    await callback.answer()
