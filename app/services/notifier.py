import logging
import asyncio
import html
from datetime import datetime, timezone
from collections import defaultdict
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..models.job import Job
from ..models.user import User
from ..utils.categorizer import get_category_label
from ..utils.resume_parser import match_score

logger = logging.getLogger(__name__)


class NotifierService:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._sent: set = set()
        # Буферы для отложенных уведомлений: {user_telegram_id: [(job, matched_kw, score), ...]}
        self._hourly_buffer: dict = defaultdict(list)
        self._daily_buffer: dict = defaultdict(list)
        # Лимит Telegram: ~30 сообщений в секунду суммарно. Ставим 25 для надежности.
        self._rate_limiter = asyncio.Semaphore(25)

    async def _sent_cleanup(self):
        """Очистка кэша отправленных (чтобы не рос бесконечно)."""
        if len(self._sent) > 50000:
            self._sent.clear()
            logger.info("🧹 Sent cache cleared")

    async def notify_user_about_job(
        self, user: User, job: Job, pre_loaded_subs: list = None
    ):
        """Smart-уведомление с учётом режима частоты."""
        # Дедупликация
        key = (user.telegram_id, job.id)
        if key in self._sent:
            return

        text = f"{job.title} {job.description or ''}".lower()

        # 0. Проверяем стоп-слова (черный список) — Кэшируем список
        sw_attr = getattr(user, "stop_words", "")
        if sw_attr and sw_attr.strip():
            stop_words = [sw.strip().lower() for sw in sw_attr.split(",") if sw.strip()]
            for sw in stop_words:
                if sw in text:
                    self._sent.add(key)
                    return

        matched_kw = []

        # 1. Проверяем обычные ключевые слова
        if user.keywords and user.keywords.strip():
            keywords = [
                k.strip().lower() for k in user.keywords.split(",") if k.strip()
            ]
            matched_kw.extend([kw for kw in keywords if kw in text])

        # 2. Проверяем умные подписки (БЕЗ ЗАПРОСА К БД В ЦИКЛЕ)
        if pre_loaded_subs:
            for sub_query in pre_loaded_subs:
                sq = sub_query.lower()
                if sq in text and sq not in matched_kw:
                    matched_kw.append(sq)

        if not matched_kw:
            return

        # Smart matching score
        profile = {
            "skills": matched_kw,
            "experience": None,
            "work_format": None,
            "salary_expectation": None,
        }
        score = match_score(profile, job.title, job.description or "")
        # Накидываем баллы промотированным вакансиям для приоритета
        if getattr(job, "is_promoted", False):
            score += 100

        self._sent.add(key)

        # Определяем режим пользователя
        mode = getattr(user, "notify_mode", "instant") or "instant"
        now = datetime.now(timezone.utc)
        is_premium = (
            getattr(user, "is_premium", False)
            and user.premium_until
            and user.premium_until > now
        )

        if mode == "off":
            return

        # Ограничение мгновенных уведомлений для не-Premium
        if mode == "instant" and not is_premium:
            mode = "hourly"
            # Можно было бы отправить уведомление, но лучше просто тихо положить в буфер,
            # а в самом буфере (flush_hourly) добавить приписку про Premium.

        if mode == "hourly":
            self._hourly_buffer[user.telegram_id].append((job, matched_kw, score))
            return
        elif mode == "daily":
            self._daily_buffer[user.telegram_id].append((job, matched_kw, score))
            return

        # mode == "instant" — отправляем сразу (только для Premium)
        await self._send_single_notification(user.telegram_id, job, matched_kw, score)

    async def _send_single_notification(
        self, chat_id: int, job: Job, matched_kw: list, score: int
    ):
        """Отправка одного мгновенного уведомления."""
        # Убираем бонус промо для отображения реального score, если нужно.
        # Но для простоты оставим как есть — пользователь увидит высокое совпадение.
        if score >= 100:  # Промо-вакансия
            match_icon, match_label = "🔥", "Прямой работодатель (Рекомендуем)"
        elif score >= 80:
            match_icon, match_label = "🟢", "Отличное совпадение"
        elif score >= 50:
            match_icon, match_label = "🟡", "Хорошее совпадение"
        else:
            match_icon, match_label = "🔵", "Частичное совпадение"

        cat_label = get_category_label(job.category) if job.category else ""

        if getattr(job, "is_promoted", False):
            src = "🏢"  # У промо всегда 🏢, так как напрямую
            promoted_badge = "⭐️ <b>ПРОМО</b>\n\n"
        else:
            src = {"hh.ru": "🏢", "habr.career": "💻", "kwork.ru": "🟠"}.get(
                job.source, "📱"
            )
            promoted_badge = ""

        desc_preview = (job.description or "")[:250]
        matched_str = ", ".join(matched_kw[:3])

        safe_title = html.escape(job.title)
        safe_source = html.escape(job.source or "Unknown")
        safe_desc = html.escape(desc_preview)
        safe_match_label = html.escape(match_label)
        safe_matched_str = html.escape(matched_str)

        message = (
            f"🎯 <b>Новая вакансия для вас!</b>\n\n"
            f"{promoted_badge}"
            f"<b>{safe_title}</b>\n"
            f"{src} {safe_source} • {cat_label}\n\n"
            f"{safe_desc}...\n\n"
            f"{match_icon} <b>{safe_match_label}</b>\n"
            f"🔑 Совпало: {safe_matched_str}"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📄 Подробнее", callback_data=f"detail:{job.id}"
                    ),
                    InlineKeyboardButton(
                        text="⭐ В избранное", callback_data=f"fav:add:{job.id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="📤 Быстрый отклик", callback_data=f"quickapply:{job.id}"
                    ),
                ],
            ]
        )

        async with self._rate_limiter:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=keyboard,
                )
                logger.info(f"✅ Notified {chat_id} job#{job.id} ({score}%)")
                await asyncio.sleep(0.04)  # 1/25 sec
            except Exception as e:
                from aiogram.exceptions import TelegramRetryAfter

                if isinstance(e, TelegramRetryAfter):
                    logger.warning(
                        f"⚠️ Flood limit reached. Retrying in {e.retry_after}s"
                    )
                    await asyncio.sleep(e.retry_after)
                    await self._send_single_notification(
                        chat_id, job, matched_kw, score
                    )
                else:
                    logger.error(f"❌ Failed notify {chat_id}: {e}")

    async def flush_hourly(self):
        """Отправка сводки за последний час для пользователей с режимом 'hourly'."""
        await self._sent_cleanup()
        if not self._hourly_buffer:
            return

        sent = 0
        for chat_id, items in list(self._hourly_buffer.items()):
            if not items:
                continue

            # Сортируем по score
            items.sort(key=lambda x: x[2], reverse=True)
            top = items[:10]

            text = f"🕐 <b>Сводка за последний час</b> (+{len(items)} вакансий)\n\n"
            for i, (job, matched_kw, score) in enumerate(top, 1):
                src = {"hh.ru": "🏢", "habr.career": "💻", "kwork.ru": "🟠"}.get(
                    job.source, "📱"
                )
                link = f" <a href='{job.link}'>→</a>" if job.link else ""
                text += f"{i}. {src} <b>{html.escape(job.title[:60])}</b> ({score}%){link}\n"

            if len(items) > 10:
                text += f"\n... и ещё {len(items) - 10}\n"

            text += "\n👉 /jobs — все вакансии"
            text += (
                "\n\n👑 <b>Хотите получать вакансии мгновенно?</b> Подключите /premium!"
            )

            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                sent += 1
            except Exception as e:
                logger.debug(f"Hourly flush error {chat_id}: {e}")

        self._hourly_buffer.clear()
        if sent:
            logger.info(f"🕐 Hourly digest sent to {sent} users")

    async def flush_daily(self):
        """Отправка ежедневной сводки (daily-буфер) для пользователей с режимом 'daily'."""
        if not self._daily_buffer:
            return

        sent = 0
        for chat_id, items in list(self._daily_buffer.items()):
            if not items:
                continue

            items.sort(key=lambda x: x[2], reverse=True)
            top = items[:15]

            text = f"📅 <b>Ежедневная сводка</b> (+{len(items)} вакансий за день)\n\n"
            for i, (job, matched_kw, score) in enumerate(top, 1):
                src = {"hh.ru": "🏢", "habr.career": "💻", "kwork.ru": "🟠"}.get(
                    job.source, "📱"
                )
                link = f" <a href='{job.link}'>→</a>" if job.link else ""
                text += f"{i}. {src} <b>{html.escape(job.title[:60])}</b> ({score}%){link}\n"

            if len(items) > 15:
                text += f"\n... и ещё {len(items) - 15}\n"

            text += "\n👉 /jobs — все вакансии"

            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                sent += 1
            except Exception as e:
                logger.debug(f"Daily flush error {chat_id}: {e}")

        self._daily_buffer.clear()
        if sent:
            logger.info(f"📅 Daily digest sent to {sent} users")
