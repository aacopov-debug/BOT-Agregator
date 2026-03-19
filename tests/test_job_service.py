import pytest
from app.services.job_service import JobService

@pytest.mark.asyncio
async def test_add_job(db_session):
    job_service = JobService(db_session)
    
    # 1. Тест добавления новой вакансии
    job1 = await job_service.add_job(
        title="Python Developer",
        description="We need a strong python dev",
        link="http://example.com/job1",
        source="Хабр Карьера",
        category="backend"
    )
    assert job1 is not None
    assert job1.title == "Python Developer"
    assert job1.category == "backend"
    
    # 2. Тест дедупликации (защита от записи точно такой же вакансии)
    job2 = await job_service.add_job(
        title="Python Developer",
        description="We need a strong python dev",
        link="http://example.com/job1",
        source="Хабр Карьера"
    )
    assert job2 is None  # Вернет None из-за проверки по job_hash

    # Проверяем количество вакансий
    count = await job_service.count_jobs()
    assert count == 1

@pytest.mark.asyncio
async def test_search_jobs(db_session):
    job_service = JobService(db_session)
    
    await job_service.add_job("Python Dev", "Django Backend", "link1", "src", "backend")
    await job_service.add_job("React Dev", "Frontend Next.js", "link2", "src", "frontend")
    await job_service.add_job("Fullstack JS", "React and Node", "link3", "src", "fullstack")

    # Поиск "Python"
    res1 = await job_service.search_jobs("Python")
    assert len(res1) == 1
    assert res1[0].title == "Python Dev"

    # Поиск "React" - должно найти две вакансии
    res2 = await job_service.search_jobs("React")
    assert len(res2) == 2

@pytest.mark.asyncio
async def test_favorites_logic(db_session):
    job_service = JobService(db_session)
    telegram_id = 998877

    job = await job_service.add_job("Test Job", "Test Desc", "link123", "src")
    assert job is not None

    # Добавление в избранное
    success = await job_service.add_favorite(telegram_id, job.id)
    assert success is True

    # Проверка счетчика
    fav_count = await job_service.count_favorites(telegram_id)
    assert fav_count == 1

    # Повторное добавление должно быть False
    success_duplicate = await job_service.add_favorite(telegram_id, job.id)
    assert success_duplicate is False

    # Проверка получения списка
    favs = await job_service.get_favorites(telegram_id)
    assert len(favs) == 1
    assert favs[0].id == job.id

    # Удаление
    success_remove = await job_service.remove_favorite(telegram_id, job.id)
    assert success_remove is True
    assert await job_service.count_favorites(telegram_id) == 0
