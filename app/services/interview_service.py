import logging
from .ai_base import BaseAIService

logger = logging.getLogger(__name__)


class InterviewService:
    """Сервис для проведения технических интервью с помощью Gemini Pro."""

    def __init__(self):
        self.ai = BaseAIService()

    async def get_next_question(
        self, history: list, job_desc: str = "", job_title: str = "Вакансия"
    ) -> str:
        """Генерирует следующий вопрос интервью на основе истории."""
        # Исправляем TypeError: 'NoneType' object is not subscriptable
        current_job_desc = job_desc if job_desc is not None else ""
        safe_job_desc = current_job_desc[:2000]
        prompt = (
            f"Ты — опытный технический интервьюер. Проведи интервью на позицию '{job_title}'.\n\n"
            f"Описание вакансии:\n{safe_job_desc}\n"
            f"История диалога:\n"
        )

        for msg in history:
            if not msg or not isinstance(msg, dict):
                continue
            role = "Интервьюер" if msg.get("role") == "assistant" else "Кандидат"
            prompt += f"{role}: {msg.get('content', '')}\n"

        prompt += (
            "\nТвоя задача: задать ОДИН глубокий уточняющий технический вопрос на основе последнего ответа кандидата. "
            "Если ответов еще нет, задай вводный вопрос по ключевым технологиям вакансии. "
            "Будь вежлив, но проверяй реальные знания. Не пиши лишний текст, только вопрос."
        )

        messages = [
            {
                "role": "system",
                "content": "Ты — требовательный, но справедливый технический интервьюер.",
            },
            {"role": "user", "content": prompt},
        ]

        return await self.ai.get_chat_completion(messages, temperature=0.7)

    async def get_final_feedback(
        self, history: list, job_title: str = "Вакансия"
    ) -> str:
        """Генерирует итоговый фидбек по результатам интервью."""
        prompt = (
            f"Проанализируй интервью на позицию '{job_title}'. Вот история диалога:\n\n"
        )

        for msg in history:
            if not msg or not isinstance(msg, dict):
                continue
            role = "Интервьюер" if msg.get("role") == "assistant" else "Кандидат"
            prompt += f"{role}: {msg.get('content', '')}\n"

        prompt += (
            "\nНапиши подробный фидбек для кандидата:\n"
            "1. ✅ Сильные стороны (что было отвечено хорошо).\n"
            "2. ⚠️ Зоны роста (какие технические темы стоит подтянуть).\n"
            "3. 📈 Итоговая оценка готовности к позиции (в процентах).\n"
            "4. 💡 Совет: на что сделать упор при подготовке к реальному собеседованию.\n\n"
            "Пиши профессионально и конструктивно."
        )

        messages = [
            {
                "role": "system",
                "content": "Ты — Senior Developer, оценивающий кандидата после технического интервью.",
            },
            {"role": "user", "content": prompt},
        ]

        return await self.ai.get_chat_completion(messages, temperature=0.5)
