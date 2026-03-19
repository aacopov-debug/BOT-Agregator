from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from ..database import Base


class ParserStats(Base):
    """
    Модель для хранения статистики работы парсеров.
    """

    __tablename__ = "parser_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parser_name = Column(String(100), unique=True, nullable=False, index=True)

    status = Column(String(20), default="OK")  # OK, ERROR, BAN
    vacancies_found = Column(Integer, default=0)  # За последний запуск
    total_today = Column(Integer, default=0)  # За последние 24 часа (или до сброса)

    last_error = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<ParserStats(name='{self.parser_name}', status='{self.status}', today={self.total_today})>"
