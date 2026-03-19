import asyncio
import logging
from collections import defaultdict
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta, timezone
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select, func

from app.config import settings
from app.database import async_session
from app.services.parsers import registry
from app.services.notifier import NotifierService
from app.services.user_service import UserService
from app.services.job_service import JobService
from app.services.digest import send_morning_digest
from app.services.ai_digest import send_ai_digest
from app.models.job import Job
from app.models.user import User

# === Логирование ===
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler = logging.StreamHandler()
console_handler.setFormatter(fmt)
logger.addHandler(console_handler)
file_handler = RotatingFileHandler(
    "worker.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(fmt)
logger.addHandler(file_handler)
log = logging.getLogger(__name__)

# Глобальные для воркера
bot: Bot = None
notifier: NotifierService = None


async def scraper_task():
    global bot, notifier
    log.info("🔄 Worker: Запуск динамического скрапинга...")

    parsers = registry.get_all_parsers()

    async def safe_run(parser):
        async with async_session() as session:
            from app.services.stats_service import StatsService

            stats_service = StatsService(session)
            parser_name = parser.get_name()
            try:
                job_service = JobService(session)
                count = await parser.parse(job_service)
                log.info(f"✅ {parser_name}: +{count}")
                await stats_service.update_parser_stats(parser_name, count, status="OK")
                return count, "OK"
            except Exception as e:
                log.error(f"❌ Error in {parser_name}: {e}")
                err_str = str(e)
                status = "BAN" if "403" in err_str or "429" in err_str else "ERROR"
                await stats_service.update_parser_stats(
                    parser_name, 0, status=status, error=err_str
                )
                return 0, status

    results = []
    for p in parsers:
        res = await safe_run(p)
        results.append(res)

    total = sum(r[0] for r in results)
    failed_count = sum(1 for r in results if r[1] != "OK")

    log.info(
        f"🚀 Worker: Скрапинг завершен! Всего новых: {total}, Ошибок: {failed_count}/{len(parsers)}"
    )

    # Уведомление админа о массовом сбое (>50% ошибок)
    if len(parsers) > 0 and failed_count / len(parsers) >= 0.5:
        log.warning("⚠️ Mass parser failure detected! Notifying admin...")
        try:
            msg = (
                f"🚨 <b>Внимание: Массовый сбой парсеров!</b>\n\n"
                f"❌ Ошибок: <b>{failed_count}</b> из <b>{len(parsers)}</b>\n"
                f"🔧 Рекомендуется проверить прокси-серверы и логи воркера."
            )
            await bot.send_message(settings.ADMIN_ID, msg, parse_mode="HTML")
        except Exception as e:
            log.error(f"Failed to send admin alert: {e}")

    if total > 0 and bot and notifier:
        await notify_users(total)


async def notify_users(new_count: int):
    global bot, notifier
    start_time = datetime.now(timezone.utc)
    async with async_session() as session:
        user_service = UserService(session)
        job_service = JobService(session)

        users = await user_service.get_users_to_notify()
        if not users:
            return

        new_jobs = await job_service.get_latest_jobs(limit=new_count)
        if not new_jobs:
            return

        from app.models.subscription import Subscription

        user_tg_ids = [u.telegram_id for u in users]

        subs_map = defaultdict(list)
        for i in range(0, len(user_tg_ids), 900):
            chunk = user_tg_ids[i : i + 900]
            stmt_subs = select(Subscription.user_telegram_id, Subscription.query).where(
                Subscription.user_telegram_id.in_(chunk)
            )
            res_subs = await session.execute(stmt_subs)
            for tg_id, query in res_subs.all():
                subs_map[tg_id].append(query)

        log.info(f"📤 Worker: Рассылка для {len(users)} чел. на {len(new_jobs)} вак.")

        count = 0
        for user in users:
            user_subs = subs_map.get(user.telegram_id, [])
            for job in new_jobs:
                await notifier.notify_user_about_job(
                    user, job, pre_loaded_subs=user_subs
                )
            count += 1
            if count % 20 == 0:
                await asyncio.sleep(0.1)

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    log.info(f"✅ Worker: Рассылка завершена за {duration:.2f} сек.")


async def cleanup_old_jobs():
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with async_session() as session:
        stmt = delete(Job).where(Job.created_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()
        if result.rowcount > 0:
            log.info(f"🗑 Worker: Удалено {result.rowcount} старых вакансий")


async def morning_digest_task():
    global bot
    if bot:
        await send_morning_digest(bot)


async def ai_digest_task():
    global bot
    if bot:
        try:
            await send_ai_digest(bot)
        except Exception as e:
            log.warning(f"Worker: AI Digest error: {e}")


async def weekly_report_task():
    global bot
    if not bot:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    async with async_session() as session:
        users = (await session.execute(select(User))).scalars().all()
        new_jobs = (
            await session.execute(
                select(func.count(Job.id)).where(Job.created_at >= cutoff)
            )
        ).scalar_one()
        for user in users:
            from app.models.application import Application

            apps = (
                await session.execute(
                    select(Application.status, func.count(Application.id))
                    .where(
                        Application.user_telegram_id == user.telegram_id,
                        Application.created_at >= cutoff,
                    )
                    .group_by(Application.status)
                )
            ).all()
            apps_dict = dict(apps)
            total_apps = sum(apps_dict.values())
            if total_apps == 0:
                continue
            text = (
                f"📊 <b>Еженедельный отчёт</b>\n\n"
                f"📋 Новых вакансий: <b>{new_jobs}</b>\n"
                f"📤 Откликов за неделю: <b>{total_apps}</b>\n"
            )
            for status, label in [
                ("applied", "📤 Отправлено"),
                ("interview", "🗓 Собеседование"),
                ("offer", "🎉 Оффер"),
                ("rejected", "❌ Отказ"),
            ]:
                cnt = apps_dict.get(status, 0)
                if cnt:
                    text += f"  {label}: {cnt}\n"
            text += "\n💪 Удачи на этой неделе!"
            try:
                await bot.send_message(user.telegram_id, text, parse_mode="HTML")
            except Exception:
                pass


async def reminder_check_task():
    global bot
    if bot:
        from app.handlers.system.reminders import send_reminders

        await send_reminders(bot)


async def hourly_flush_task():
    global notifier
    if notifier:
        try:
            await notifier.flush_hourly()
        except Exception as e:
            log.warning(f"Worker: Hourly flush error: {e}")


async def daily_flush_task():
    global notifier
    if notifier:
        try:
            await notifier.flush_daily()
        except Exception as e:
            log.warning(f"Worker: Daily flush error: {e}")


async def main():
    global bot, notifier
    log.info("🚀 Worker started")

    bot = Bot(token=settings.BOT_TOKEN)
    notifier = NotifierService(bot)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(scraper_task, "interval", seconds=settings.PARSE_INTERVAL_SECONDS)
    scheduler.add_job(cleanup_old_jobs, "cron", hour=4, minute=0)
    scheduler.add_job(morning_digest_task, "cron", hour=9, minute=0)
    scheduler.add_job(weekly_report_task, "cron", day_of_week="sun", hour=10, minute=0)
    scheduler.add_job(reminder_check_task, "interval", seconds=60)
    scheduler.add_job(ai_digest_task, "cron", hour=9, minute=5)
    scheduler.add_job(hourly_flush_task, "interval", hours=1)
    scheduler.add_job(daily_flush_task, "cron", hour=8, minute=55)

    scheduler.start()

    # Первый скрапинг — отложенный на 5 секунд
    async def _delayed_first_scrape():
        await asyncio.sleep(5)
        await scraper_task()

    asyncio.create_task(_delayed_first_scrape())

    # Бесконечный цикл для воркера
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Worker stopped")
