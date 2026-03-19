import pytest
from unittest.mock import AsyncMock, patch
from app.services.ai_digest import _generate_ai_summary, send_ai_digest
from app.models.user import User
from app.models.job import Job

@pytest.mark.asyncio
async def test_generate_ai_summary():
    user = User(telegram_id=123, keywords="python, django")
    jobs = [
        Job(title="Python Developer", source="hh", link="http://example.com/1"),
        Job(title="Junior Django Backend", source="habr", link="http://example.com/2")
    ]
    
    # Мокаем вызов к реальному OpenAI API
    with patch("app.services.ai_base.BaseAIService.get_chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "✨ AI Test Summary\n1. [Python Developer](http://example.com/1)"
        
        summary = await _generate_ai_summary(user, jobs)
        
        # Проверяем, что вернулась строка из мока
        assert "AI Test Summary" in summary
        
        # Проверяем параметры вызова (был ли правильный промпт сформирован)
        mock_ai.assert_called_once()
        args, kwargs = mock_ai.call_args
        messages = args[0]
        
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        
        # Проверяем, что в промпт передались ключевые слова пользователя и текст вакансий
        prompt = messages[1]["content"]
        assert "python, django" in prompt
        assert "Python Developer (hh)" in prompt
        assert "Junior Django Backend (habr)" in prompt

@pytest.mark.asyncio
async def test_send_ai_digest_empty(db_session):
    # Тестируем ситуацию, когда нечего отправлять
    bot_mock = AsyncMock()
    
    with patch("app.services.ai_digest.async_session") as session_mock:
        # Подменяем сессию на нашу тестовую
        session_mock.return_value.__aenter__.return_value = db_session
        
        # Без вакансий и пользователей бот не должен никого "пинговать"
        await send_ai_digest(bot_mock)
        
        bot_mock.send_message.assert_not_called()
