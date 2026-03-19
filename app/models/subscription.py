from sqlalchemy import Column, Integer, String, BigInteger, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_telegram_id = Column(BigInteger, nullable=False, index=True)
    query = Column(String, nullable=False)  # Поисковый запрос
    created_at = Column(DateTime(timezone=True), server_default=func.now())
