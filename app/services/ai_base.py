import logging
from openai import AsyncOpenAI
from ..config import settings

logger = logging.getLogger(__name__)


class BaseAIService:
    """
    Базовый сервис для работы с AI через OpenRouter (или OpenAI).
    Обеспечивает единый интерфейс для всех AI-функций бота.
    """

    def __init__(self, model: str = None):
        self.api_key = settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY
        self.base_url = (
            "https://openrouter.ai/api/v1" if settings.OPENROUTER_API_KEY else None
        )
        self.model = model or settings.AI_MODEL

        if not self.api_key:
            logger.warning("AI Service: No API key found!")
            self.client = None
        else:
            self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def get_chat_completion(
        self, messages: list, max_tokens: int = 1000, temperature: float = 0.7
    ) -> str:
        """Общий метод для получения ответа от нейросети."""
        if not self.client:
            return "❌ AI сервис не настроен (проверьте API ключи)."

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                extra_headers={
                    "HTTP-Referer": "http://localhost",
                    "X-Title": "ArBOT Agregator",
                },
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"AI API error ({self.model}): {e}")
            return f"❌ Ошибка нейросети: {str(e)}"
