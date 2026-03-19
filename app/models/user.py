from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, Date
from sqlalchemy.sql import func
from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    role = Column(String(20), default="user")  # Роль юзера: user, hr, admin
    keywords = Column(String(1000), default="")
    stop_words = Column(String(1000), default="")  # Черный список слов (через запятую)
    notify_mode = Column(
        String(20), default="instant"
    )  # instant / hourly / daily / off
    ai_credits = Column(
        Integer, default=3
    )  # 3 бесплатных генерации при старте (было 10)
    vacancy_credits = Column(
        Integer, default=0
    )  # Кредиты на публикацию вакансий (для HR)
    referred_by = Column(
        BigInteger, nullable=True
    )  # Telegram ID пользователя, который пригласил
    is_premium = Column(Boolean, default=False)  # Активна ли Premium-подписка
    premium_until = Column(
        DateTime(timezone=True), nullable=True
    )  # Дата окончания подписки
    streak_count = Column(Integer, default=0)  # Количество дней подряд в боте
    last_streak_date = Column(Date, nullable=True)  # Дата последнего обновления стрика
    daily_views = Column(Integer, default=0)  # Количество просмотров вакансий сегодня
    last_view_date = Column(Date, nullable=True)  # Дата последних просмотров
    voice = Column(
        String(100), default="alloy"
    )  # Голос для TTS: alloy, echo, fable, onyx, nova, shimmer, eleven_...
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<User(id={self.id}, tg={self.telegram_id})>"
