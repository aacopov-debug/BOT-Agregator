from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Index,
    BigInteger,
    Boolean,
)
from sqlalchemy.sql import func
from ..database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    link = Column(String(512), nullable=True)
    source = Column(String(100), nullable=True, index=True)
    category = Column(String(50), default="other", index=True)
    job_hash = Column(String(64), unique=True, nullable=False)

    # B2B Поля (HR-Панель)
    employer_id = Column(
        BigInteger, nullable=True, index=True
    )  # Telegram ID пользователя (HR), разместившего вакансию
    is_promoted = Column(
        Boolean, default=False, index=True
    )  # Платное размещение (выше в поиске, быстрее рассылка)
    moderation_status = Column(
        String(20), default="approved"
    )  # approved (для парсеров), pending (ожидает модерации), rejected

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Составной индекс для частых запросов
    __table_args__ = (Index("ix_job_category_created", "category", "created_at"),)

    def __repr__(self):
        return f"<Job(id={self.id}, title='{self.title[:30]}', cat='{self.category}')>"
