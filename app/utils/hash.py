import hashlib


def generate_job_hash(title: str, description: str) -> str:
    """Генерирует уникальный хеш для вакансии на основе названия и описания."""
    data = f"{title.strip().lower()}{description.strip().lower()}"
    return hashlib.sha256(data.encode()).hexdigest()
