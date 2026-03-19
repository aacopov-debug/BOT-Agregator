import asyncio
import logging
from logging.handlers import RotatingFileHandler
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database import engine, Base
from app.handlers import register_handlers
from app.middlewares.throttling import ThrottlingMiddleware
from app import models

# === Логирование ===
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler = logging.StreamHandler()
console_handler.setFormatter(fmt)
logger.addHandler(console_handler)
file_handler = RotatingFileHandler("bot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
file_handler.setFormatter(fmt)
logger.addHandler(file_handler)
log = logging.getLogger(__name__)

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    log.info("✅ Database ready")

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Подключаем анти-спам (отключаем для ускорения на текущем сервере)
    # dp.message.middleware(ThrottlingMiddleware(rate_limit=2))
    
    register_handlers(dp)

    # Команды в меню Telegram
    from aiogram.types import BotCommand
    commands = [
        BotCommand(command="jobs", description="📋 Вакансии"),
        BotCommand(command="search", description="🔍 Поиск"),
        BotCommand(command="resume", description="📄 Резюме"),
        BotCommand(command="interview", description="🎤 AI-Интервью (NEW!)"),
        BotCommand(command="hr", description="🏢 Для HR / Вакансия"),
        BotCommand(command="balance", description="💳 Баланс ИИ-Кредитов"),
        BotCommand(command="premium", description="💎 Тарифы"),
        BotCommand(command="referral", description="🎁 Пригласить друга"),
        BotCommand(command="hot", description="🔥 Горячие за 24ч"),
        BotCommand(command="recommend", description="🤖 Совет ИИ"),
        BotCommand(command="applications", description="📩 Трекер откликов"),
        BotCommand(command="favorites", description="⭐ Избранное"),
        BotCommand(command="random", description="🎲 Случайная"),
        BotCommand(command="profile", description="👤 Профиль"),
        BotCommand(command="filter", description="📂 Категории"),
        BotCommand(command="city", description="🌍 По городу"),
        BotCommand(command="salary_filter", description="💰 По зарплате"),
        BotCommand(command="top_skills", description="🏆 Топ навыков"),
        BotCommand(command="salary_analytics", description="💰 Аналитика зарплат"),
        BotCommand(command="compare", description="📊 Сравнить"),
        BotCommand(command="export", description="📄 Экспорт"),
        BotCommand(command="subscribe", description="📬 Подписка"),
        BotCommand(command="trends", description="📈 Тренды"),
        BotCommand(command="blacklist", description="🚫 Blacklist"),
        BotCommand(command="stats", description="📊 Статистика"),
        BotCommand(command="admin", description="🔐 Админ-панель"),
        BotCommand(command="help", description="❓ Справка"),
    ]
    await bot.set_my_commands(commands)

    log.info("🚀 Bot service started (Polling mode)")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped")
