import logging
import threading
import asyncio
import urllib.parse
from yoomoney import Client
from ..config import settings
from ..database import async_session
from ..models.payment import Payment
from ..models.user import User
from sqlalchemy import select
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PayService:
    def __init__(self):
        self.token = settings.YOOMONEY_TOKEN
        self.receiver = settings.YOOMONEY_WALLET
        self.client = None
        self.lock = threading.Lock()
        if self.token:
            try:
                self.client = Client(self.token)
            except Exception as e:
                logger.error(f"YooMoney client init error: {e}")

    def is_configured(self) -> bool:
        """Проверяет, настроена ли оплата."""
        return bool(self.token and self.receiver)

    async def generate_payment_link(
        self, label: str, amount: float, description: str = "Покупка AI-кредитов"
    ) -> str:
        """Генерирует ссылку на оплату через YooMoney Quickpay мгновенно.
        Мы собираем URL вручную, чтобы избежать лишнего сетевого запроса библиотеки,
        который вызывал задержки до 15 секунд.
        """
        if not self.is_configured():
            return ""

        params = {
            "receiver": self.receiver,
            "quickpay-form": "shop",
            "targets": description,
            "paymentType": "AC",  # AC - Банковская карта
            "sum": amount,
            "label": label,
        }

        base_url = "https://yoomoney.ru/quickpay/confirm"
        query_string = urllib.parse.urlencode(params)
        return f"{base_url}?{query_string}"

    async def check_payment(self, label: str) -> bool:
        """Проверяет историю операций по label. Возвращает True если оплачено.
        Использует asyncio.to_thread для предотвращения блокировки Event Loop.
        """
        if not self.client:
            return False

        try:
            # Обертка для синхронного вызова сетевого API с блокировкой для потокобезопасности
            def get_history():
                with self.lock:
                    return self.client.operation_history(label=label)

            history = await asyncio.to_thread(get_history)

            for operation in history.operations:
                # Если статус success — платеж прошел
                if operation.status == "success":
                    return True
            return False
        except Exception as e:
            logger.error(f"YooMoney check error: {e}")
            return False

    async def process_successful_payment(self, payment_id: int) -> bool:
        """Начисляет услуги пользователю при успешной оплате."""
        from datetime import timedelta

        async with async_session() as session:
            # Ищем платеж
            payment = (
                await session.execute(select(Payment).where(Payment.id == payment_id))
            ).scalar_one_or_none()
            if not payment or payment.is_paid:
                return False

            # Проверяем в YooMoney
            is_really_paid = await self.check_payment(payment.label)
            if not is_really_paid:
                return False

            # Платеж успешен -> Начисляем услугу
            payment.is_paid = True
            payment.paid_at = datetime.now(timezone.utc)

            # Обновляем пользователя
            user = (
                await session.execute(
                    select(User).where(User.telegram_id == payment.user_telegram_id)
                )
            ).scalar_one_or_none()
            if not user:
                return False

            p_type = payment.product_type or "credits"
            p_val = payment.product_val or getattr(payment, "credits_amount", 0) or 0

            if p_type == "credits":
                user.ai_credits += p_val
            elif p_type == "premium":
                now = datetime.now(timezone.utc)
                base = (
                    user.premium_until
                    if user.premium_until and user.premium_until > now
                    else now
                )
                user.is_premium = True
                user.premium_until = base + timedelta(days=p_val)
            elif p_type == "hr_pack":
                user.vacancy_credits += p_val

            await session.commit()
            return True
