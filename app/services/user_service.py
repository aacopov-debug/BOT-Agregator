from datetime import date, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..models.user import User
from typing import Optional, List


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        referrer_id: Optional[int] = None,
    ) -> User:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            from ..config import settings

            role = "admin" if telegram_id == settings.ADMIN_ID else "user"
            user = User(
                telegram_id=telegram_id,
                username=username,
                referred_by=referrer_id,
                role=role,
            )
            self.session.add(user)
            await self.session.flush()

            # Начисляем бонусы за регистрацию по реферальной ссылке
            if referrer_id:
                stmt_ref = select(User).where(User.telegram_id == referrer_id)
                ref_res = await self.session.execute(stmt_ref)
                referrer = ref_res.scalar_one_or_none()
                if referrer:
                    referrer.ai_credits += 3  # Стандартный бонус
                    user.ai_credits += 3  # Экстра бонус новому

                    # Referral 2.0: +1 день Premium за каждых 3 друзей
                    stmt_count = select(func.count(User.id)).where(
                        User.referred_by == referrer_id
                    )
                    res_count = await self.session.execute(stmt_count)
                    total_referred = res_count.scalar() or 0

                    if total_referred > 0 and total_referred % 3 == 0:
                        now = datetime.now(timezone.utc)
                        base = (
                            referrer.premium_until
                            if referrer.premium_until and referrer.premium_until > now
                            else now
                        )
                        referrer.is_premium = True
                        referrer.premium_until = base + timedelta(days=1)

            await self.session.commit()
            await self.session.refresh(user)

        return user

    async def update_keywords(self, telegram_id: int, keywords: str) -> bool:
        user = await self.get_or_create_user(telegram_id)
        user.keywords = keywords
        await self.session.commit()
        return True

    async def update_stop_words(self, telegram_id: int, stop_words: str) -> bool:
        """Обновляет черный список слов (через запятую)."""
        user = await self.get_or_create_user(telegram_id)
        user.stop_words = stop_words
        await self.session.commit()
        return True

    async def update_notify_mode(self, telegram_id: int, mode: str) -> bool:
        """Обновляет режим уведомлений: instant / hourly / daily / off."""
        user = await self.get_or_create_user(telegram_id)
        user.notify_mode = mode
        await self.session.commit()
        return True

    async def update_voice(self, telegram_id: int, voice: str) -> bool:
        """Обновляет голос для озвучки (TTS)."""
        user = await self.get_or_create_user(telegram_id)
        user.voice = voice
        await self.session.commit()
        return True

    async def get_users_to_notify(self) -> List[User]:
        """Пользователи с ключевыми словами и включёнными уведомлениями."""
        stmt = select(User).where(
            User.keywords.isnot(None), User.keywords != "", User.notify_mode != "off"
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_vacancy_credits(self, telegram_id: int, amount: int) -> bool:
        """Начисляет кредиты на публикацию вакансий."""
        user = await self.get_or_create_user(telegram_id)
        user.vacancy_credits += amount
        await self.session.commit()
        return True

    async def update_daily_streak(self, telegram_id: int) -> dict:
        """Обновляет стрик посещений. Начисляет +1 кредит за каждые 3 дня."""
        user = await self.get_or_create_user(telegram_id)
        today = date.today()

        if user.last_streak_date == today:
            return {"updated": False, "streak": user.streak_count}

        if user.last_streak_date == today - timedelta(days=1):
            user.streak_count += 1
        else:
            user.streak_count = 1

        user.last_streak_date = today
        bonus = False

        if user.streak_count >= 3:
            user.ai_credits += 1
            user.streak_count = 0  # Сброс прогресса после награды
            bonus = True

        await self.session.commit()
        return {"updated": True, "streak": user.streak_count, "bonus": bonus}
