import logging
from openai import AsyncOpenAI
from ..config import settings

logger = logging.getLogger(__name__)

# Инициализируем клиент OpenAI
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def generate_resume_roast(resume_text: str) -> dict:
    """
    Генерирует саркастичную 'прожарку' резюме с помощью AI.
    Возвращает словарь с текстом и оценкой (score).
    """
    if not settings.OPENAI_API_KEY:
        return {
            "text": "❌ AI-прожарка временно недоступна (нет API ключа).",
            "score": 0,
        }

    prompt = (
        "Ты — самый циничный, саркастичный и вредный HR-директор в мире IT. "
        "Тебе прислали резюме, и твоя задача — 'прожарить' его (Resume Roast). "
        "Будь жестким, но смешным. Высмеивай клише, странные навыки, отсутствие опыта или "
        "наоборот — слишком пафосные формулировки. Используй молодежный сленг, мемы и эмодзи.\n\n"
        f"ТЕКСТ РЕЗЮМЕ:\n{resume_text[:3000]}\n\n"
        "СТРУКТУРА ОТВЕТА:\n"
        "1. 🔥 ЖЕСТОКИЙ ВЕРДИКТ (одной фразой)\n"
        "2. 💀 РАЗБОР ПО ФАКТАМ (3-4 язвительных пункта)\n"
        "3. 📉 ШКАЛА ГОРЕЛОЙ ЖОПЫ (Roast Score) — число от 0 до 100, где 100 — это абсолютный позор.\n"
        "4. 💡 СОВЕТ (если ты еще не совсем умер от смеха)\n\n"
        "В конце ответа ОБЯЗАТЕЛЬНО напиши строку строго в формате: SCORE: [число]"
    )

    try:
        response = await client.chat.completions.create(
            model=settings.AI_MODEL or "gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ты — токсичный HR-эксперт. Твоя цель — высмеять резюме.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=1000,
            timeout=30.0,
        )

        content = response.choices[0].message.content.strip()

        # Парсим SCORE из текста
        score = 50
        if "SCORE:" in content:
            try:
                score_part = content.split("SCORE:")[-1].strip()
                # Извлекаем все цифры
                score_digits = "".join(filter(str.isdigit, score_part))
                if score_digits:
                    score = int(score_digits)
            except Exception as parse_err:
                logger.warning(f"Failed to parse roast score: {parse_err}")

            # Удаляем техническую строку из текста для пользователя
            content = content.split("SCORE:")[0].strip()

        return {"text": content, "score": min(max(score, 0), 100)}
    except Exception as e:
        logger.error(f"Roast AI error: {e}")
        return {
            "text": "❌ Нейросеть в шоке от твоего резюме и временно ушла в запой. Попробуй чуть позже!",
            "score": 0,
        }
