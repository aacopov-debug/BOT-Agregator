"""AI-ранжирование вакансий по профилю пользователя.

Использует TF-IDF подход для сопоставления ключевых слов
пользователя с текстом вакансий и вычисления релевантности.
"""

import re
from typing import List, Tuple


# Стоп-слова (не влияют на релевантность)
STOP_WORDS = {
    "и",
    "в",
    "на",
    "с",
    "по",
    "для",
    "от",
    "до",
    "из",
    "к",
    "за",
    "не",
    "а",
    "но",
    "или",
    "мы",
    "вы",
    "он",
    "она",
    "они",
    "это",
    "то",
    "что",
    "как",
    "так",
    "все",
    "при",
    "без",
    "под",
    "над",
    "между",
    "через",
    "the",
    "and",
    "or",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "is",
    "are",
    "be",
    "will",
    "we",
    "you",
    "our",
    "can",
    "a",
    "an",
}

# Весовые коэффициенты
TITLE_WEIGHT = 3.0  # Совпадение в заголовке важнее
DESC_WEIGHT = 1.0  # Совпадение в описании
SALARY_BONUS = 0.5  # Бонус за указание зарплаты
REMOTE_BONUS = 0.3  # Бонус за удалённую работу

# Маркеры зарплаты и удалёнки
SALARY_MARKERS = ["₽", "$", "€", "зарплата", "оклад", "от ", "до ", "salary"]
REMOTE_MARKERS = [
    "remote",
    "удалённ",
    "удаленн",
    "удалёнка",
    "удаленка",
    "из дома",
    "гибрид",
]


def tokenize(text: str) -> List[str]:
    """Разбивает текст на токены (слова), убирая стоп-слова."""
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9#+.]+", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]


def compute_relevance(user_keywords: str, title: str, description: str) -> float:
    """
    Вычисляет оценку релевантности вакансии для пользователя.

    Возвращает значение от 0.0 до 10.0
    """
    if not user_keywords or not user_keywords.strip():
        return 5.0  # Нейтральная оценка для пользователей без ключевых слов

    # Токенизация ключевых слов пользователя
    user_tokens = set()
    for kw in user_keywords.split(","):
        kw = kw.strip().lower()
        if kw:
            user_tokens.add(kw)
            # Также добавляем отдельные слова из многословных ключей
            for word in tokenize(kw):
                user_tokens.add(word)

    if not user_tokens:
        return 5.0

    title_lower = title.lower() if title else ""
    desc_lower = description.lower() if description else ""
    full_text = f"{title_lower} {desc_lower}"

    # 1. Подсчёт совпадений в заголовке
    title_score = 0.0
    for token in user_tokens:
        if token in title_lower:
            title_score += TITLE_WEIGHT

    # 2. Подсчёт совпадений в описании
    desc_score = 0.0
    for token in user_tokens:
        if token in desc_lower:
            desc_score += DESC_WEIGHT

    # 3. Бонусы
    bonus = 0.0
    if any(m in full_text for m in SALARY_MARKERS):
        bonus += SALARY_BONUS
    if any(m in full_text for m in REMOTE_MARKERS):
        bonus += REMOTE_BONUS

    # 4. Нормализация оценки (0-10)
    raw_score = title_score + desc_score + bonus
    max_possible = (
        len(user_tokens) * (TITLE_WEIGHT + DESC_WEIGHT) + SALARY_BONUS + REMOTE_BONUS
    )

    if max_possible == 0:
        return 5.0

    normalized = (raw_score / max_possible) * 10.0
    return round(min(normalized, 10.0), 1)


def rank_jobs(user_keywords: str, jobs: list) -> List[Tuple[float, object]]:
    """Ранжирует список вакансий по релевантности для пользователя."""
    scored = []
    for job in jobs:
        score = compute_relevance(user_keywords, job.title, job.description)
        scored.append((score, job))

    # Сортировка по убыванию оценки
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def relevance_emoji(score: float) -> str:
    """Возвращает эмодзи релевантности."""
    if score >= 8.0:
        return "🔥"  # Идеальное совпадение
    elif score >= 6.0:
        return "✅"  # Хорошее
    elif score >= 4.0:
        return "🟡"  # Среднее
    else:
        return "⬜"  # Низкое
