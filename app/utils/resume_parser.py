"""Парсер резюме: извлекает навыки, опыт и предпочтения из текста."""

import re
from typing import Dict, Set

# Словарь навыков по категориям
SKILLS_DATABASE = {
    # Языки
    "python": ["python", "питон", "пайтон"],
    "javascript": ["javascript", "js", "typescript", "ts"],
    "java": ["java", "jvm"],
    "go": ["golang", " go ", "go developer"],
    "c++": ["c++", "cpp", "плюсы"],
    "c#": ["c#", "csharp", ".net", "dotnet"],
    "ruby": ["ruby", "rails"],
    "php": ["php", "laravel", "symfony"],
    "rust": ["rust"],
    "swift": ["swift"],
    "kotlin": ["kotlin"],
    # Frontend
    "react": ["react", "reactjs", "react.js"],
    "vue": ["vue", "vuejs", "vue.js", "nuxt"],
    "angular": ["angular"],
    "next.js": ["next.js", "nextjs"],
    "html/css": ["html", "css", "вёрстка", "верстка"],
    "tailwind": ["tailwind"],
    # Backend
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi"],
    "spring": ["spring", "spring boot"],
    "node.js": ["node.js", "nodejs", "express", "nestjs"],
    # DevOps
    "docker": ["docker", "докер"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon"],
    "ci/cd": ["ci/cd", "cicd", "jenkins", "gitlab ci", "github actions"],
    "terraform": ["terraform"],
    "ansible": ["ansible"],
    "linux": ["linux", "линукс", "ubuntu", "debian"],
    # Data
    "sql": ["sql", "postgresql", "mysql", "sqlite", "postgres"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"],
    "elasticsearch": ["elasticsearch", "elastic"],
    "kafka": ["kafka"],
    # ML/AI
    "machine learning": ["machine learning", "ml", "deep learning", "dl"],
    "tensorflow": ["tensorflow"],
    "pytorch": ["pytorch"],
    "pandas": ["pandas", "numpy", "scipy"],
    # Другое
    "git": ["git", "github", "gitlab"],
    "rest api": ["rest", "api", "graphql"],
    "agile": ["agile", "scrum", "kanban"],
    "figma": ["figma", "sketch"],
}

# Уровни опыта
EXPERIENCE_PATTERNS = {
    "intern": ["стажёр", "стажер", "intern", "стажировка"],
    "junior": ["junior", "джуниор", "начинающ"],
    "middle": ["middle", "миддл", "средн"],
    "senior": ["senior", "сениор", "старш", "ведущ"],
    "lead": ["lead", "лид", "руководит", "тимлид", "team lead"],
}

# Формат работы
WORK_FORMAT_PATTERNS = {
    "remote": ["remote", "удалённ", "удаленн", "удалёнка", "удаленка", "из дома"],
    "office": ["офис", "office", "очно"],
    "hybrid": ["гибрид", "hybrid", "смешанн"],
}


def extract_skills(text: str) -> Set[str]:
    """Извлекает навыки из текста резюме."""
    text_lower = text.lower()
    found = set()
    for skill, patterns in SKILLS_DATABASE.items():
        for pattern in patterns:
            if pattern in text_lower:
                found.add(skill)
                break
    return found


def extract_experience(text: str) -> str:
    """Определяет уровень опыта."""
    text_lower = text.lower()
    for level, patterns in EXPERIENCE_PATTERNS.items():
        for pattern in patterns:
            if pattern in text_lower:
                return level
    # Попробуем определить по годам
    years_match = re.search(r"(\d+)\s*(?:лет|год|года|years?)", text_lower)
    if years_match:
        years = int(years_match.group(1))
        if years < 1:
            return "intern"
        elif years < 3:
            return "junior"
        elif years < 5:
            return "middle"
        else:
            return "senior"
    return "middle"


def extract_work_format(text: str) -> str:
    """Определяет предпочтительный формат работы."""
    text_lower = text.lower()
    for fmt, patterns in WORK_FORMAT_PATTERNS.items():
        for pattern in patterns:
            if pattern in text_lower:
                return fmt
    return "any"


def extract_salary_expectation(text: str) -> int:
    """Извлекает ожидаемую зарплату."""
    patterns = [
        r"(?:от|зарплата|ожидан|salary)\s*(\d[\d\s]*\d)\s*(?:₽|руб|rub)",
        r"(\d{2,3})\s*(?:000|к|k)\s*(?:₽|руб|rub)?",
    ]
    for pat in patterns:
        match = re.search(pat, text.lower())
        if match:
            val = match.group(1).replace(" ", "")
            try:
                num = int(val)
                if num < 1000:
                    num *= 1000
                return num
            except ValueError:
                pass
    return 0


def parse_resume(text: str) -> Dict:
    """Полный парсинг резюме. Возвращает структурированный профиль."""
    skills = extract_skills(text)
    experience = extract_experience(text)
    work_format = extract_work_format(text)
    salary = extract_salary_expectation(text)

    return {
        "skills": sorted(skills),
        "experience": experience,
        "work_format": work_format,
        "salary_expectation": salary,
        "skills_text": ", ".join(sorted(skills)),
    }


def match_score(resume_profile: Dict, job_title: str, job_description: str) -> float:
    """Вычисляет совпадение резюме с вакансией (0-100%)."""
    text = f"{job_title} {job_description}".lower()
    skills = resume_profile.get("skills", [])

    if not skills:
        return 0.0

    matched = sum(
        1
        for s in skills
        if s in text or any(p in text for p in SKILLS_DATABASE.get(s, []))
    )

    skill_score = (matched / len(skills)) * 70  # 70% веса навыкам

    # Бонус за уровень опыта
    exp = resume_profile.get("experience", "")
    exp_bonus = 15 if exp in text else 0

    # Бонус за формат работы
    fmt = resume_profile.get("work_format", "")
    fmt_bonus = 15 if fmt == "any" or fmt in text else 0

    return min(round(skill_score + exp_bonus + fmt_bonus, 1), 100.0)
