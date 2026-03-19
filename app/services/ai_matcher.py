import logging
import json
from .ai_base import BaseAIService
from ..models.job import Job
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AIMatcherService(BaseAIService):
    async def analyze_match(self, user_resume: str, job: Job) -> Optional[Dict]:
        """
        Проводит глубокий анализ соответствия резюме и вакансии через Gemini.
        Возвращает структурированный JSON с оценкой и комментариями.
        """
        prompt = (
            f"Ты — профессиональный IT-рекрутер. Проанализируй соответствие кандидата вакансии.\n\n"
            f"РЕЗЮМЕ КАНДИДАТА:\n{user_resume[:4000]}\n\n"
            f"ВАКАНСИЯ: {job.title}\n"
            f"ОПИСАНИЕ:\n{job.description[:3000]}\n\n"
            f"Твоя задача — дать честный и конструктивный разбор в формате JSON.\n"
            f"Пример формата:\n"
            f"{{\n"
            f'  "score": 85,\n'
            f'  "pros": ["Наличие опыта с Python/FastAPI", "Знание Docker"],\n'
            f'  "cons": ["Не указан опыт с Kubernetes", "Нет примеров работы с Kafka"],\n'
            f'  "summary": "Кандидат отлично подходит на роль Backend-разработчика, но нужно подготовиться к вопросам по инфраструктуре.",\n'
            f'  "advice": "В сопроводительном письме сделайте упор на ваши проекты на FastAPI."\n'
            f"}}\n\n"
            f"Важные условия:\n"
            f"1. score — число от 0 до 100.\n"
            f"2. Пиши только на русском языке.\n"
            f"3. Возвращай ТОЛЬКО чистый JSON, без markdown-разметки или пояснений."
        )

        messages = [
            {
                "role": "system",
                "content": "Ты помогаешь соискателям понять их шансы на трудоустройство и подготовиться к интервью.",
            },
            {"role": "user", "content": prompt},
        ]

        raw_result = await self.get_chat_completion(messages, temperature=0.3)

        # Очистка JSON от возможных markdown-тегов
        clean_json = raw_result.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
        clean_json = clean_json.strip()

        try:
            return json.loads(clean_json)
        except Exception as e:
            logger.error(
                f"Failed to parse AI Matcher JSON: {e}\nRaw result: {raw_result}"
            )
            return None
