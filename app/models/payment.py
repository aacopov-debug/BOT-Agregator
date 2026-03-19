from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, DECIMAL
from sqlalchemy.sql import func
from ..database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id = Column(BigInteger, nullable=False, index=True)

    # Идентификатор операции в нашей системе (label для YooMoney)
    label = Column(String(100), unique=True, nullable=False, index=True)

    # Тип продукта: credits, premium, hr_pack
    product_type = Column(String(20), default="credits")
    # Значение (кол-во кредитов, дней или вакансий)
    product_val = Column(Integer, default=0)

    # Оставлено для совместимости: сколько кредитов покупает
    credits_amount = Column(Integer, nullable=True)

    # Сумма к оплате (в рублях)
    price = Column(DECIMAL(10, 2), nullable=False)

    # Статус успешности
    is_paid = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    paid_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Payment(id={self.id}, user={self.user_telegram_id}, amount={self.price}, paid={self.is_paid})>"
