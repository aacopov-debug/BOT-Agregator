"""Утилита автоматического определения категории вакансии по тексту."""

CATEGORY_RULES = {
    "python": {
        "label": "🐍 Python",
        "keywords": [
            "python",
            "django",
            "flask",
            "fastapi",
            "asyncio",
            "celery",
            "pandas",
            "numpy",
        ],
    },
    "javascript": {
        "label": "🟨 JavaScript",
        "keywords": [
            "javascript",
            "typescript",
            "js",
            "ts",
            "node.js",
            "nodejs",
            "express",
            "nest",
        ],
    },
    "frontend": {
        "label": "🎨 Frontend",
        "keywords": [
            "frontend",
            "фронтенд",
            "react",
            "vue",
            "angular",
            "next.js",
            "nuxt",
            "svelte",
            "html",
            "css",
            "tailwind",
        ],
    },
    "backend": {
        "label": "⚙️ Backend",
        "keywords": [
            "backend",
            "бэкенд",
            "бекенд",
            "серверная",
            "api",
            "rest",
            "graphql",
            "microservices",
        ],
    },
    "devops": {
        "label": "🔧 DevOps",
        "keywords": [
            "devops",
            "sre",
            "docker",
            "kubernetes",
            "k8s",
            "ci/cd",
            "terraform",
            "ansible",
            "jenkins",
            "gitlab",
        ],
    },
    "qa": {
        "label": "🧪 QA",
        "keywords": [
            "qa",
            "тестировщик",
            "тестирование",
            "автотест",
            "selenium",
            "playwright",
            "quality assurance",
        ],
    },
    "mobile": {
        "label": "📱 Mobile",
        "keywords": [
            "ios",
            "android",
            "swift",
            "kotlin",
            "flutter",
            "react native",
            "мобильн",
        ],
    },
    "data": {
        "label": "📊 Data/ML",
        "keywords": [
            "data",
            "ml",
            "machine learning",
            "data science",
            "аналитик",
            "bi",
            "etl",
            "spark",
            "hadoop",
            "нейросет",
        ],
    },
    "design": {
        "label": "🎨 Дизайн",
        "keywords": [
            "дизайн",
            "design",
            "ui",
            "ux",
            "figma",
            "sketch",
            "верстка",
            "графич",
        ],
    },
    "management": {
        "label": "📋 Менеджмент",
        "keywords": [
            "product manager",
            "project manager",
            "проджект",
            "продакт",
            "scrum",
            "agile",
            "менеджер проект",
        ],
    },
    "go": {
        "label": "🔵 Golang",
        "keywords": ["golang", " go ", "go developer", "go разработчик"],
    },
    "java": {
        "label": "☕ Java",
        "keywords": ["java", "spring", "spring boot", "jvm", "kotlin"],
    },
    "remote": {
        "label": "🏠 Удалёнка",
        "keywords": ["remote", "удалённ", "удаленн", "удалёнка", "удаленка", "из дома"],
    },
}


def detect_category(title: str, description: str) -> str:
    """Определяет категорию вакансии по тексту. Возвращает ключ категории или 'other'."""
    text = f"{title} {description}".lower()

    scores = {}
    for cat_key, cat_data in CATEGORY_RULES.items():
        score = sum(1 for kw in cat_data["keywords"] if kw in text)
        if score > 0:
            scores[cat_key] = score

    if not scores:
        return "other"

    return max(scores, key=scores.get)


def get_category_label(category: str) -> str:
    """Возвращает красивое название категории."""
    if category in CATEGORY_RULES:
        return CATEGORY_RULES[category]["label"]
    return "📁 Другое"
