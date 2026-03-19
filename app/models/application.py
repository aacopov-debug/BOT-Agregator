"""Модель отклика — трекер статуса заявок."""

from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from ..database import Base


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id = Column(BigInteger, nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    status = Column(
        String(20), default="applied"
    )  # applied / viewed / interview / offer / rejected
    note = Column(String(500), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    status_changed_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Application(user={self.user_telegram_id}, job={self.job_id}, status={self.status})>"
