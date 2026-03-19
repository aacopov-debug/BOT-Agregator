import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.parsers.hh import HHParser
from app.services.parsers.base import ParserRegistry
from app.services.job_service import JobService

class MockResponse:
    def __init__(self, json_data, status=200):
        self._json_data = json_data
        self.status = status
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def json(self): return self._json_data

@pytest.mark.asyncio
async def test_hh_parser_logic(db_session):
    job_service = JobService(db_session)
    # Мокаем метод add_job, чтобы изолированно проверить только логику парсера
    job_service.add_job = AsyncMock(return_value=True) 

    parser = HHParser()
    # Уменьшаем кол-во запросов и задержек для быстрого теста
    parser.queries = ["Python Tester"]
    parser.request_delay = 0 

    # Подготавливаем фейковый ответ от API hh.ru
    mock_response_data = {
        "items": [
            {
                "name": "Super Python Dev",
                "alternate_url": "https://hh.ru/vacancy/123",
                "employer": {"name": "Test Company"},
                "area": {"name": "Moscow"},
                "experience": {"name": "1-3 года"},
                "schedule": {"name": "Удаленная работа"},
                "salary": {"from": 100000, "to": 200000, "currency": "RUR"}
            }
        ]
    }

    # Подменяем HTTP-запрос с помощью кастомного класса-контекст менеджера
    mock_get = MagicMock(return_value=MockResponse(mock_response_data, status=200))

    with patch("aiohttp.ClientSession.request", mock_get):
        added_count = await parser.parse(job_service)

    # Проверяем, что парсер вернул 1 успешное добавление
    assert added_count == 1
    job_service.add_job.assert_called_once()
    
    # Проверяем, как парсер сконвертировал JSON от hh.ru в параметры для БД
    kwargs = job_service.add_job.call_args.kwargs
    assert kwargs["title"] == "Super Python Dev"
    assert kwargs["link"] == "https://hh.ru/vacancy/123"
    assert kwargs["source"] == "hh.ru"
    
    # Проверяем форматирование description
    desc = kwargs["description"]
    assert "Компания: Test Company" in desc
    assert "Город: Moscow" in desc
    assert "1-3 года" in desc
    assert "Удаленная работа" in desc
    assert "💰 100000–200000 RUR" in desc

def test_parser_registry():
    # Проверяем, что реестр парсеров корректно регистрирует их при старте
    parsers = ParserRegistry.get_all_parsers()
    # Как минимум HHParser должен быть в списке
    assert len(parsers) > 0
    names = [p.get_name() for p in parsers]
    assert "HHParser" in names
