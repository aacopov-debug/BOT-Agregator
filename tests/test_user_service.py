import pytest
from app.services.user_service import UserService
from app.models.user import User
from sqlalchemy import select

@pytest.mark.asyncio
async def test_get_or_create_user(db_session):
    user_service = UserService(db_session)
    telegram_id = 999123
    username = "test_user_pytest"

    # Создание нового пользователя
    user = await user_service.get_or_create_user(telegram_id, username)
    assert user is not None
    assert user.telegram_id == telegram_id
    assert user.username == username
    assert user.ai_credits == 3 # По умолчанию 3 кредита
    assert user.vacancy_credits == 0

    # Проверяем, что он сохранился в базе данных
    result = await db_session.execute(select(User).where(User.telegram_id == telegram_id))
    db_user = result.scalar_one_or_none()
    assert db_user is not None
    assert db_user.id == user.id

    # Проверка получения существующего пользователя вместо повторного создания
    user2 = await user_service.get_or_create_user(telegram_id, "different_username")
    assert user2.id == user.id
    
    # Считаем общее количество пользователей в таблице - должен быть 1
    count = await db_session.execute(select(User))
    all_users = count.scalars().all()
    assert len(all_users) == 1

@pytest.mark.asyncio
async def test_add_vacancy_credits(db_session):
    user_service = UserService(db_session)
    telegram_id = 112233
    
    user = await user_service.get_or_create_user(telegram_id)
    assert user.vacancy_credits == 0

    success = await user_service.add_vacancy_credits(telegram_id, 5)
    assert success is True
    
    user_updated = await user_service.get_or_create_user(telegram_id)
    assert user_updated.vacancy_credits == 5
