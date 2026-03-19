import logging
from .ai_base import BaseAIService
from ..models.user import User
from ..models.job import Job

logger = logging.getLogger(__name__)


async def generate_cover_letter(user: User, job: Job) -> str:
    """Генерирует профессиональное сопроводительное письмо через Gemini Pro."""
    ai = BaseAIService()

    user_skills = user.keywords if user.keywords else "не указаны (IT сфера)"
    job_desc = job.description or ""

    prompt = (
        f"Ты — эксперт по карьере в IT. Напиши профессиональное, персонализированное и короткое "
        f"сопроводительное письмо для вакансии '{job.title}'.\n\n"
        f"Данные кандидата (навыки/опыт): {user_skills}\n"
        f"Описание вакансии:\n{job_desc[:3000]}\n\n"
        f"Инструкции:\n"
        f"1. Пиши на русском языке.\n"
        f"2. Фокусируйся на том, как навыки кандидата решают задачи бизнеса из вакансии.\n"
        f"3. Тон должен быть уверенным, но не хвастливым.\n"
        f"4. Не используй шаблоны вроде 'Меня зовут...', начинай сразу с сути.\n"
        f"5. Длина — до 150 слов.\n"
    )

    messages = [
        {
            "role": "system",
            "content": "Ты помогаешь соискателям получать офферы в топовые IT-компании.",
        },
        {"role": "user", "content": prompt},
    ]

    result = await ai.get_chat_completion(messages, temperature=0.8)

    if "❌" in result:
        return result

    return f"🚀 <b>AI Cover Letter (Gemini Pro):</b>\n\n{result}"
